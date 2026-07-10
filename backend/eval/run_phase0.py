from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @staticmethod
    def from_obj(obj: dict[str, Any] | None) -> "TokenUsage":
        obj = obj or {}
        return TokenUsage(
            prompt_tokens=int(obj.get("prompt_tokens") or 0),
            completion_tokens=int(obj.get("completion_tokens") or 0),
            total_tokens=int(obj.get("total_tokens") or 0),
        )

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


def _safe_read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _iter_validation_json_files(input_dir: Path) -> list[Path]:
    files = []
    for p in sorted(input_dir.glob("*.json")):
        if p.name == "all_results.json":
            continue
        files.append(p)
    return files


def _collect_sources(summary_json: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Collect all citation dicts from a summary payload.

    Supports both legacy RFQ-style summary schemas and spec-check schemas where
    citations live under `spec_check_fields.*[].sources`.
    """

    sources: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            # Direct "sources" list pattern.
            srcs = node.get("sources")
            if isinstance(srcs, list):
                for s in srcs:
                    if isinstance(s, dict) and "source_text" in s:
                        sources.append(s)

            # Recurse to nested structures (skip _meta-ish).
            for k, v in node.items():
                if isinstance(k, str) and k.startswith("_"):
                    continue
                visit(v)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(summary_json or {})
    return sources


def _count_verified_sources(sources: list[dict[str, Any]]) -> tuple[int, int]:
    if not sources:
        return 0, 0
    verified = sum(1 for s in sources if s.get("citation_verified") is True)
    return verified, len(sources)


def _insight_items_count(insight: dict[str, Any]) -> int:
    payload = insight.get("payload") or {}
    items = payload.get("items")
    if isinstance(items, list):
        return len(items)
    return 0


def _insight_token_usage(insight: dict[str, Any]) -> TokenUsage:
    usage = insight.get("token_usage")
    if isinstance(usage, dict):
        return TokenUsage.from_obj(usage)
    return TokenUsage()


def _format_pct(n: int, d: int) -> str:
    if d <= 0:
        return "n/a"
    return f"{(100.0 * n / d):.1f}%"


def build_phase0_report(input_dir: Path) -> dict[str, Any]:
    doc_reports: list[dict[str, Any]] = []

    total_summary_tokens = TokenUsage()
    total_extraction_tokens = TokenUsage()
    total_empty_extraction_tokens = TokenUsage()

    total_verified_sources = 0
    total_sources = 0

    parsing_quality_scores: list[float] = []
    total_elapsed = 0.0

    extraction_item_counts: dict[str, int] = {}
    extraction_empty_counts: dict[str, int] = {}
    extraction_tokens_by_type: dict[str, TokenUsage] = {}

    missing_type_counts: dict[str, int] = {}
    spec_check_field_counts_total: dict[str, int] = {}

    for path in _iter_validation_json_files(input_dir):
        data = _safe_read_json(path)
        filename = str(data.get("filename") or path.name)
        doc_id = str(data.get("doc_id") or "")
        elapsed = float(data.get("elapsed_seconds") or 0.0)
        total_elapsed += elapsed

        parsed = (data.get("data") or {}).get("parsed") or {}
        parsing_quality = parsed.get("parsing_quality_score")
        if isinstance(parsing_quality, (int, float)):
            parsing_quality_scores.append(float(parsing_quality))

        summary = (data.get("data") or {}).get("summary") or {}
        summary_json = summary.get("summary_json") or {}
        meta = (summary_json or {}).get("_meta") or {}
        summary_usage = TokenUsage.from_obj((meta.get("token_usage") or {}) if isinstance(meta, dict) else {})
        total_summary_tokens += summary_usage

        missing_types = meta.get("missing_extraction_types") if isinstance(meta, dict) else []
        if isinstance(missing_types, list):
            for t in missing_types:
                if isinstance(t, str) and t:
                    missing_type_counts[t] = missing_type_counts.get(t, 0) + 1

        sources = _collect_sources(summary_json if isinstance(summary_json, dict) else {})
        verified, total = _count_verified_sources(sources)
        total_verified_sources += verified
        total_sources += total

        # Insight-level stats (per extraction type)
        insights = (data.get("data") or {}).get("insights") or []
        insight_reports: list[dict[str, Any]] = []
        if isinstance(insights, list):
            for ins in insights:
                if not isinstance(ins, dict):
                    continue
                etype = str(ins.get("extraction_type") or "unknown")
                items_count = _insight_items_count(ins)
                usage = _insight_token_usage(ins)

                extraction_item_counts[etype] = extraction_item_counts.get(etype, 0) + items_count
                extraction_tokens_by_type[etype] = extraction_tokens_by_type.get(etype, TokenUsage()) + usage
                total_extraction_tokens += usage

                is_empty = items_count == 0
                if is_empty:
                    extraction_empty_counts[etype] = extraction_empty_counts.get(etype, 0) + 1
                    total_empty_extraction_tokens += usage

                insight_reports.append(
                    {
                        "extraction_type": etype,
                        "items": items_count,
                        "token_usage": {
                            "prompt_tokens": usage.prompt_tokens,
                            "completion_tokens": usage.completion_tokens,
                            "total_tokens": usage.total_tokens,
                        },
                        "empty": is_empty,
                    }
                )

        doc_reports.append(
            {
                "file": filename,
                "doc_id": doc_id,
                "elapsed_seconds": elapsed,
                "parsing": {
                    "quality_score": parsed.get("parsing_quality_score"),
                    "total_pages": parsed.get("total_pages"),
                    "ocr_pages": parsed.get("ocr_pages"),
                    "tables_count": parsed.get("tables_count"),
                },
                "summary": {
                    "model": meta.get("model"),
                    "prompt_version": meta.get("prompt_version"),
                    "token_usage": {
                        "prompt_tokens": summary_usage.prompt_tokens,
                        "completion_tokens": summary_usage.completion_tokens,
                        "total_tokens": summary_usage.total_tokens,
                    },
                    "missing_extraction_types": missing_types if isinstance(missing_types, list) else [],
                    "spec_check_fields_counts": {},
                    "sources": {
                        "verified": verified,
                        "total": total,
                        "verified_pct": _format_pct(verified, total),
                    },
                },
                "insights": insight_reports,
            }
        )

        # Spec-check summary shape coverage
        if isinstance(summary_json, dict):
            scf = summary_json.get("spec_check_fields")
            if isinstance(scf, dict):
                counts: dict[str, int] = {}
                for k, v in scf.items():
                    if isinstance(v, list):
                        counts[k] = len(v)
                        spec_check_field_counts_total[k] = spec_check_field_counts_total.get(k, 0) + len(v)
                    else:
                        # Some keys may be dicts in future; count as 1 if present.
                        if v is not None:
                            counts[k] = 1
                            spec_check_field_counts_total[k] = spec_check_field_counts_total.get(k, 0) + 1

                doc_reports[-1]["summary"]["spec_check_fields_counts"] = counts

    avg_parsing_quality = (
        sum(parsing_quality_scores) / len(parsing_quality_scores) if parsing_quality_scores else None
    )

    report = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "input_dir": str(input_dir),
        "doc_count": len(doc_reports),
        "aggregate": {
            "elapsed_seconds_total": round(total_elapsed, 2),
            "parsing_quality_avg": round(avg_parsing_quality, 4) if isinstance(avg_parsing_quality, float) else None,
            "summary_tokens_total": {
                "prompt_tokens": total_summary_tokens.prompt_tokens,
                "completion_tokens": total_summary_tokens.completion_tokens,
                "total_tokens": total_summary_tokens.total_tokens,
            },
            "extraction_tokens_total": {
                "prompt_tokens": total_extraction_tokens.prompt_tokens,
                "completion_tokens": total_extraction_tokens.completion_tokens,
                "total_tokens": total_extraction_tokens.total_tokens,
            },
            "empty_extraction_tokens_total": {
                "prompt_tokens": total_empty_extraction_tokens.prompt_tokens,
                "completion_tokens": total_empty_extraction_tokens.completion_tokens,
                "total_tokens": total_empty_extraction_tokens.total_tokens,
            },
            "summary_sources": {
                "verified": total_verified_sources,
                "total": total_sources,
                "verified_pct": _format_pct(total_verified_sources, total_sources),
            },
            "missing_extraction_type_counts": dict(sorted(missing_type_counts.items(), key=lambda x: (-x[1], x[0]))),
            "spec_check_fields_total_counts": dict(
                sorted(spec_check_field_counts_total.items(), key=lambda x: (-x[1], x[0]))
            ),
        },
        "by_extraction_type": {
            etype: {
                "items_total": extraction_item_counts.get(etype, 0),
                "empty_doc_count": extraction_empty_counts.get(etype, 0),
                "tokens_total": {
                    "prompt_tokens": extraction_tokens_by_type[etype].prompt_tokens,
                    "completion_tokens": extraction_tokens_by_type[etype].completion_tokens,
                    "total_tokens": extraction_tokens_by_type[etype].total_tokens,
                },
            }
            for etype in sorted(extraction_tokens_by_type.keys())
        },
        "documents": doc_reports,
    }
    return report


def _render_markdown(report: dict[str, Any]) -> str:
    agg = report.get("aggregate") or {}
    src = agg.get("summary_sources") or {}
    missing = agg.get("missing_extraction_type_counts") or {}
    summary_tokens = agg.get("summary_tokens_total") or {}
    extraction_tokens = agg.get("extraction_tokens_total") or {}
    empty_tokens = agg.get("empty_extraction_tokens_total") or {}

    lines: list[str] = []
    lines.append("# Phase 0 baseline report")
    lines.append("")
    lines.append(f"- Generated at: `{report.get('generated_at')}`")
    lines.append(f"- Docs: **{report.get('doc_count', 0)}**")
    lines.append("")
    lines.append("## Aggregate")
    lines.append("")
    lines.append(f"- Parsing quality avg: **{agg.get('parsing_quality_avg')}**")
    lines.append(f"- Citation verified: **{src.get('verified')} / {src.get('total')} ({src.get('verified_pct')})**")
    lines.append(
        "- Tokens (summary total): "
        f"**{summary_tokens.get('total_tokens')}** "
        f"(prompt {summary_tokens.get('prompt_tokens')}, completion {summary_tokens.get('completion_tokens')})"
    )
    lines.append(
        "- Tokens (extractions total): "
        f"**{extraction_tokens.get('total_tokens')}** "
        f"(prompt {extraction_tokens.get('prompt_tokens')}, completion {extraction_tokens.get('completion_tokens')})"
    )
    lines.append(
        "- Tokens (empty extractions): "
        f"**{empty_tokens.get('total_tokens')}** "
        f"(prompt {empty_tokens.get('prompt_tokens')}, completion {empty_tokens.get('completion_tokens')})"
    )

    lines.append("")
    lines.append("## Missing extraction types (count of docs)")
    lines.append("")
    if missing:
        for k, v in missing.items():
            lines.append(f"- `{k}`: **{v}**")
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Per document (high level)")
    lines.append("")
    for d in report.get("documents") or []:
        if not isinstance(d, dict):
            continue
        f = d.get("file")
        elapsed = d.get("elapsed_seconds")
        pq = ((d.get("parsing") or {}).get("quality_score"))
        verified = (((d.get("summary") or {}).get("sources") or {}).get("verified_pct"))
        sum_tokens = (((d.get("summary") or {}).get("token_usage") or {}).get("total_tokens"))
        miss = ((d.get("summary") or {}).get("missing_extraction_types") or [])
        lines.append(f"- **{f}**")
        lines.append(f"  - elapsed: `{elapsed}s`, parsing_quality: `{pq}`, citations_verified: `{verified}`, summary_tokens: `{sum_tokens}`")
        if miss:
            lines.append(f"  - missing_extraction_types: `{', '.join(miss)}`")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 baseline evaluator (validation_results)")
    parser.add_argument(
        "--input",
        required=True,
        help="Directory containing validation_results JSON files",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output directory for report.json/report.md",
    )
    args = parser.parse_args()

    input_dir = Path(args.input).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_phase0_report(input_dir)

    json_path = out_dir / "phase0_report.json"
    md_path = out_dir / "phase0_report.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + os.linesep, encoding="utf-8")
    md_path.write_text(_render_markdown(report) + os.linesep, encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

