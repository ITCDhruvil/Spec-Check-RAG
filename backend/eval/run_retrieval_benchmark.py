"""
Retrieval benchmark (offline ground truth + live retrieval).

Measures retrieval quality independently of the LLM. Ground truth = verified
citation source_text from sample-docs/validation_results. For each
(document, extraction_type) we run RetrievalService.retrieve() and check whether
the returned chunks contain the verified source_text passages.

Metrics: Recall@1/3/8, MRR@8, Citation Recall@8, Hit Rate, latency p50/p95.

Usage:
  cd backend
  python eval/run_retrieval_benchmark.py
  python eval/run_retrieval_benchmark.py --md-out ../retrieval_benchmark.md --out ../retrieval_benchmark.json
  python eval/run_retrieval_benchmark.py --document-id <uuid>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.ci" if os.environ.get("CI") else "config.settings.development",
)

import django

django.setup()

from django.conf import settings

from apps.chat.services.index_service import VectorIndexService
from apps.chat.services.retrieval_service import RetrievalService
from apps.intelligence.services.extraction_retrieval_service import (
    EXTRACTION_RETRIEVAL_QUERIES,
)

# extraction types excluded from V1 (captures metadata, not real clauses)
EXCLUDED_EXTRACTION_TYPES = {"eligibility_criteria"}

# below this length substring matching is unreliable -> token-overlap fallback
SHORT_TEXT_THRESHOLD = 40
TOKEN_OVERLAP_RATIO = 0.80

# str-keyed copy of the queries (keys are ExtractionType str-enum members)
_QUERIES_BY_TYPE: dict[str, list[str]] = {
    str(k): v for k, v in EXTRACTION_RETRIEVAL_QUERIES.items()
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _normalize(text: str) -> str:
    """Match citation_validation._normalize."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


# --------------------------------------------------------------------------- #
# Layer 1 — Ground Truth Builder
# --------------------------------------------------------------------------- #
@dataclass
class GTPassage:
    source_text: str
    normalized: str
    page: Any
    section: str


@dataclass
class GTGroup:
    document_id: str
    extraction_type: str
    query: str
    passages: list[GTPassage] = field(default_factory=list)


def _query_for_type(extraction_type: str) -> str | None:
    queries = _QUERIES_BY_TYPE.get(extraction_type)
    if not queries:
        return None
    # join the type's natural-language queries into one retrieval query
    return " ".join(queries)


def build_ground_truth(
    validation_dir: Path,
    *,
    document_id: str | None = None,
) -> list[GTGroup]:
    groups: dict[tuple[str, str], GTGroup] = {}

    for path in sorted(validation_dir.glob("doc_*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc_id = str(doc.get("doc_id") or "")
        if not doc_id:
            continue
        if document_id and doc_id != document_id:
            continue

        data = doc.get("data") or {}
        for block in data.get("insights") or []:
            if not isinstance(block, dict):
                continue
            etype = str(block.get("extraction_type") or "")
            if not etype or etype in EXCLUDED_EXTRACTION_TYPES:
                continue
            query = _query_for_type(etype)
            if not query:
                continue

            items = (block.get("payload") or {}).get("items") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("citation_verified") is not True:
                    continue
                source_text = str(item.get("source_text") or "").strip()
                if not source_text:
                    continue

                key = (doc_id, etype)
                group = groups.get(key)
                if group is None:
                    group = GTGroup(
                        document_id=doc_id,
                        extraction_type=etype,
                        query=query,
                    )
                    groups[key] = group

                normalized = _normalize(source_text)
                # dedup by normalized source_text within the group
                if any(p.normalized == normalized for p in group.passages):
                    continue
                group.passages.append(
                    GTPassage(
                        source_text=source_text,
                        normalized=normalized,
                        page=item.get("page"),
                        section=str(item.get("section") or ""),
                    )
                )

    return [g for g in groups.values() if g.passages]


# --------------------------------------------------------------------------- #
# Layer 2 — Retrieval Runner
# --------------------------------------------------------------------------- #
@dataclass
class RetrievedHit:
    chunk_id: str
    text: str
    normalized_text: str
    backend_score: float
    normalized_score: float
    chunk_type: str


@dataclass
class RetrievalResult:
    indexed: bool
    retrieval_time_ms: float
    hits: list[RetrievedHit] = field(default_factory=list)


def run_retrieval(group: GTGroup) -> RetrievalResult:
    if not VectorIndexService.is_indexed(group.document_id):
        return RetrievalResult(indexed=False, retrieval_time_ms=0.0)

    start = time.perf_counter()
    chunks = RetrievalService.retrieve(group.document_id, group.query)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    hits = [
        RetrievedHit(
            chunk_id=str(c.chunk_id),
            text=c.text,
            normalized_text=_normalize(c.text),
            # V1: retrieve() returns a single score; raw backend distance is not
            # exposed through the public API, so both fields hold the same value.
            backend_score=float(c.score),
            normalized_score=float(c.score),
            chunk_type=str(c.chunk_type or ""),
        )
        for c in chunks
    ]
    return RetrievalResult(indexed=True, retrieval_time_ms=round(elapsed_ms, 2), hits=hits)


# --------------------------------------------------------------------------- #
# Layer 3 — Evaluator
# --------------------------------------------------------------------------- #
def _passage_in_chunk(passage: GTPassage, hit: RetrievedHit) -> bool:
    if len(passage.source_text) >= SHORT_TEXT_THRESHOLD:
        return passage.normalized in hit.normalized_text
    # short-text fallback: token overlap
    gt_tokens = set(passage.normalized.split())
    if not gt_tokens:
        return False
    chunk_tokens = set(hit.normalized_text.split())
    overlap = len(gt_tokens & chunk_tokens) / len(gt_tokens)
    return overlap >= TOKEN_OVERLAP_RATIO


@dataclass
class GroupMetrics:
    document_id: str
    extraction_type: str
    indexed: bool
    gt_passage_count: int
    matched_passage_count: int
    first_hit_rank: int | None  # 1-based rank of first chunk hitting any passage
    retrieval_time_ms: float
    returned_chunk_count: int

    def recall_at(self, k: int) -> bool:
        return self.first_hit_rank is not None and self.first_hit_rank <= k

    @property
    def reciprocal_rank_8(self) -> float:
        if self.first_hit_rank is not None and self.first_hit_rank <= 8:
            return 1.0 / self.first_hit_rank
        return 0.0

    @property
    def hit(self) -> bool:
        return self.first_hit_rank is not None


def evaluate(group: GTGroup, result: RetrievalResult) -> GroupMetrics:
    first_hit_rank: int | None = None
    matched: set[str] = set()

    for rank, hit in enumerate(result.hits, start=1):
        for passage in group.passages:
            if _passage_in_chunk(passage, hit):
                matched.add(passage.normalized)
                if first_hit_rank is None:
                    first_hit_rank = rank

    return GroupMetrics(
        document_id=group.document_id,
        extraction_type=group.extraction_type,
        indexed=result.indexed,
        gt_passage_count=len(group.passages),
        matched_passage_count=len(matched),
        first_hit_rank=first_hit_rank,
        retrieval_time_ms=result.retrieval_time_ms,
        returned_chunk_count=len(result.hits),
    )


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return round(ordered[idx], 2)


def aggregate(metrics: list[GroupMetrics]) -> dict[str, Any]:
    evaluated = [m for m in metrics if m.indexed]
    skipped = [m for m in metrics if not m.indexed]
    n = len(evaluated)

    total_gt = sum(m.gt_passage_count for m in evaluated)
    total_matched = sum(m.matched_passage_count for m in evaluated)
    latencies = [m.retrieval_time_ms for m in evaluated]

    def recall(k: int) -> float:
        if not n:
            return 0.0
        return round(sum(1 for m in evaluated if m.recall_at(k)) / n, 4)

    overall = {
        "groups_evaluated": n,
        "groups_skipped_unindexed": len(skipped),
        "recall_at_1": recall(1),
        "recall_at_3": recall(3),
        "recall_at_8": recall(8),
        "mrr_at_8": round(sum(m.reciprocal_rank_8 for m in evaluated) / n, 4) if n else 0.0,
        "citation_recall_at_8": round(total_matched / total_gt, 4) if total_gt else 0.0,
        "hit_rate": round(sum(1 for m in evaluated if m.hit) / n, 4) if n else 0.0,
        "total_gt_passages": total_gt,
        "total_matched_passages": total_matched,
        "latency_ms_p50": _percentile(latencies, 50),
        "latency_ms_p95": _percentile(latencies, 95),
    }

    # per extraction type
    by_type: dict[str, list[GroupMetrics]] = {}
    for m in evaluated:
        by_type.setdefault(m.extraction_type, []).append(m)
    per_type: dict[str, Any] = {}
    for etype, group_metrics in sorted(by_type.items()):
        gn = len(group_metrics)
        gt = sum(m.gt_passage_count for m in group_metrics)
        matched = sum(m.matched_passage_count for m in group_metrics)
        per_type[etype] = {
            "groups": gn,
            "recall_at_1": round(sum(1 for m in group_metrics if m.recall_at(1)) / gn, 4),
            "recall_at_3": round(sum(1 for m in group_metrics if m.recall_at(3)) / gn, 4),
            "recall_at_8": round(sum(1 for m in group_metrics if m.recall_at(8)) / gn, 4),
            "mrr_at_8": round(sum(m.reciprocal_rank_8 for m in group_metrics) / gn, 4),
            "citation_recall_at_8": round(matched / gt, 4) if gt else 0.0,
        }

    backend = VectorIndexService.backend_name()
    if backend == "azure_search":
        effective_top_k = getattr(settings, "AZURE_SEARCH_TOP_K", settings.CHAT_RETRIEVAL_TOP_K)
        effective_min_score = getattr(settings, "AZURE_SEARCH_MIN_RETRIEVAL_SCORE", 0.0)
    else:
        effective_top_k = settings.CHAT_RETRIEVAL_TOP_K
        effective_min_score = settings.CHAT_MIN_RETRIEVAL_SCORE

    return {
        "backend": backend,
        "top_k": effective_top_k,
        "min_score": effective_min_score,
        "overall": overall,
        "per_extraction_type": per_type,
        "groups": [
            {
                "document_id": m.document_id,
                "extraction_type": m.extraction_type,
                "indexed": m.indexed,
                "gt_passages": m.gt_passage_count,
                "matched_passages": m.matched_passage_count,
                "first_hit_rank": m.first_hit_rank,
                "returned_chunks": m.returned_chunk_count,
                "retrieval_time_ms": m.retrieval_time_ms,
            }
            for m in metrics
        ],
        "notes": [
            "V1: backend_score == normalized_score (raw distance not exposed by retrieve()).",
            "V1: retrieval_time_ms is total retrieve() wall time (embed/vector split deferred).",
            "eligibility_criteria excluded from V1.",
        ],
    }


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def render_markdown(report: dict[str, Any]) -> str:
    o = report["overall"]
    lines = [
        "# Retrieval benchmark report",
        "",
        f"- Backend: `{report['backend']}`  top_k=`{report['top_k']}`  min_score=`{report['min_score']}`",
        f"- Groups evaluated: **{o['groups_evaluated']}** (skipped unindexed: {o['groups_skipped_unindexed']})",
        "",
        "## Overall",
        "",
        f"- Recall@1: **{o['recall_at_1']}**",
        f"- Recall@3: **{o['recall_at_3']}**",
        f"- Recall@8: **{o['recall_at_8']}**",
        f"- MRR@8: **{o['mrr_at_8']}**",
        f"- Citation Recall@8: **{o['citation_recall_at_8']}** ({o['total_matched_passages']}/{o['total_gt_passages']})",
        f"- Hit Rate: **{o['hit_rate']}**",
        f"- Latency p50/p95 (ms): **{o['latency_ms_p50']} / {o['latency_ms_p95']}**",
        "",
        "## Per extraction type",
        "",
        "| type | groups | R@1 | R@3 | R@8 | MRR@8 | CitRecall@8 |",
        "|------|--------|-----|-----|-----|-------|-------------|",
    ]
    for etype, s in report["per_extraction_type"].items():
        lines.append(
            f"| {etype} | {s['groups']} | {s['recall_at_1']} | {s['recall_at_3']} | "
            f"{s['recall_at_8']} | {s['mrr_at_8']} | {s['citation_recall_at_8']} |"
        )

    lines.extend(["", "## Groups", "",
                  "| document | type | indexed | gt | matched | first_hit | chunks | ms |",
                  "|----------|------|---------|----|---------|-----------|--------|----|"])
    for g in report["groups"]:
        lines.append(
            f"| {g['document_id'][:8]} | {g['extraction_type']} | {g['indexed']} | "
            f"{g['gt_passages']} | {g['matched_passages']} | {g['first_hit_rank']} | "
            f"{g['returned_chunks']} | {g['retrieval_time_ms']} |"
        )

    lines.extend(["", "## Notes", ""])
    for note in report["notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieval benchmark")
    parser.add_argument(
        "--validation-dir",
        type=Path,
        default=_repo_root() / "sample-docs" / "validation_results",
    )
    parser.add_argument("--document-id", type=str, default=None)
    parser.add_argument("--out", type=Path, help="Write JSON report")
    parser.add_argument("--md-out", type=Path, help="Write markdown report")
    parser.add_argument("--top-k", type=int, default=None, help="Override CHAT_RETRIEVAL_TOP_K")
    args = parser.parse_args()

    if args.top_k:
        settings.CHAT_RETRIEVAL_TOP_K = args.top_k

    validation_dir = args.validation_dir.resolve()
    if not validation_dir.exists():
        print(f"ERROR: validation dir not found: {validation_dir}", file=sys.stderr)
        return 1

    groups = build_ground_truth(validation_dir, document_id=args.document_id)
    print(f"Built {len(groups)} ground-truth groups from {validation_dir}")

    metrics: list[GroupMetrics] = []
    for group in groups:
        result = run_retrieval(group)
        if not result.indexed:
            print(f"  SKIP (unindexed): {group.document_id[:8]} / {group.extraction_type}")
        metrics.append(evaluate(group, result))

    report = aggregate(metrics)
    print(json.dumps(report["overall"], indent=2))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.out}")

    md = render_markdown(report)
    md_path = args.md_out or (BACKEND / "eval" / "out" / "retrieval_benchmark.md")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md, encoding="utf-8")
    print(f"Wrote {md_path}")

    if report["overall"]["groups_evaluated"] == 0:
        print("No indexed documents evaluated.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
