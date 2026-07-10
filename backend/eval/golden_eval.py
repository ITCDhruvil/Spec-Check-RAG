"""
Phase 7 golden-set evaluation (offline, no LLM/API).

Rebuilds spec_check_fields from committed validation_results JSON insights
and scores field-level precision/recall/F1 against manifest labels.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BUCKETS = (
    "project_metadata_items",
    "project_people_items",
    "project_size_location_items",
    "project_dates",
    "bond_items",
)

DEFAULT_MANIFEST = Path(__file__).resolve().parent / "golden_set" / "manifest.json"


@dataclass
class FieldScore:
    field_key: str
    document_id: str
    expected: bool
    matched: bool
    extracted: bool
    actual_values: list[str] = field(default_factory=list)

    @property
    def tp(self) -> int:
        return 1 if self.expected and self.matched else 0

    @property
    def fp(self) -> int:
        return 1 if self.extracted and self.expected and not self.matched else 0

    @property
    def fn(self) -> int:
        return 1 if self.expected and not self.matched else 0


@dataclass
class DocEvalResult:
    document_id: str
    validation_json: str
    passed: bool
    issues: list[str]
    row_count: int
    avg_confidence: float | None
    field_keys: list[str]
    field_scores: list[FieldScore]
    warnings_count: int = 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or DEFAULT_MANIFEST
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _insights_from_validation(doc: dict[str, Any]) -> list[Any]:
    insights_data = ((doc.get("data") or {}).get("insights")) or []
    rows: list[Any] = []
    for block in insights_data:
        if not isinstance(block, dict):
            continue
        rows.append(
            type(
                "Insight",
                (),
                {
                    "extraction_type": block.get("extraction_type", ""),
                    "payload": block.get("payload") or {},
                },
            )()
        )
    return rows


def rebuild_spec_from_validation_doc(doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Import postprocess lazily so callers can configure Django first."""
    from apps.intelligence.services.summary_postprocess import (
        build_spec_check_fields_from_insights,
        finalize_spec_check_fields,
    )

    insights = _insights_from_validation(doc)
    spec = build_spec_check_fields_from_insights(insights)
    warnings = finalize_spec_check_fields(spec)
    return spec, warnings


def extract_field_values(spec: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for bucket in BUCKETS:
        for row in spec.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            fk = str(row.get("field_key") or "").strip()
            if not fk:
                continue
            val = str(row.get("date") or row.get("text") or "").strip()
            if val:
                out.setdefault(fk, []).append(val)
    return out


def _normalize_match_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _field_matches(label_spec: dict[str, Any], values: list[str]) -> bool:
    if not values:
        return False
    match_mode = str(label_spec.get("match") or "contains_any").lower()
    needles = label_spec.get("values") or label_spec.get("value_contains") or []
    if isinstance(needles, str):
        needles = [needles]
    needles_norm = [_normalize_match_text(str(n)) for n in needles if str(n).strip()]
    if not needles_norm:
        return bool(values)

    haystack = _normalize_match_text(" | ".join(values))
    if match_mode == "contains_all":
        return all(n in haystack for n in needles_norm)
    if match_mode == "regex":
        pattern = str(label_spec.get("pattern") or "")
        return bool(pattern and re.search(pattern, haystack, re.IGNORECASE))
    # default: contains_any
    return any(n in haystack for n in needles_norm)


def _avg_confidence(spec: dict[str, Any]) -> float | None:
    confs: list[int] = []
    for bucket in BUCKETS:
        for row in spec.get(bucket) or []:
            if isinstance(row, dict) and isinstance(row.get("confidence"), int):
                confs.append(row["confidence"])
    if not confs:
        return None
    return round(sum(confs) / len(confs), 1)


def _row_count(spec: dict[str, Any]) -> int:
    return sum(len(spec.get(b) or []) for b in BUCKETS)


def _singleton_duplicate_count(spec: dict[str, Any]) -> int:
    from apps.intelligence.services.spec_check_fields_registry import SINGLETON_FIELD_KEYS

    dupes = 0
    for bucket in BUCKETS:
        counts: dict[str, int] = {}
        for row in spec.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            fk = str(row.get("field_key") or "")
            if fk in SINGLETON_FIELD_KEYS:
                counts[fk] = counts.get(fk, 0) + 1
        dupes += sum(max(0, c - 1) for c in counts.values())
    return dupes


def evaluate_document(
    *,
    document_id: str,
    validation_path: Path,
    expect: dict[str, Any],
    skip_pipeline_check: bool = False,
) -> DocEvalResult:
    doc = json.loads(validation_path.read_text(encoding="utf-8"))
    issues: list[str] = []

    if not skip_pipeline_check:
        if doc.get("pipeline_status") != "completed":
            issues.append(f"pipeline_status={doc.get('pipeline_status')}")
        if doc.get("summary_status") != "completed":
            issues.append(f"summary_status={doc.get('summary_status')}")

    if issues:
        return DocEvalResult(
            document_id=document_id,
            validation_json=str(validation_path),
            passed=False,
            issues=issues,
            row_count=0,
            avg_confidence=None,
            field_keys=[],
            field_scores=[],
        )

    spec, warnings = rebuild_spec_from_validation_doc(doc)
    field_values = extract_field_values(spec)
    field_keys = sorted(field_values.keys())
    avg_conf = _avg_confidence(spec)
    rows = _row_count(spec)

    if rows < int(expect.get("min_row_count") or 1):
        issues.append(f"row_count {rows} < min {expect.get('min_row_count')}")

    min_conf = expect.get("min_avg_confidence")
    if min_conf is not None and avg_conf is not None and avg_conf < float(min_conf):
        issues.append(f"avg_confidence {avg_conf} < min {min_conf}")

    max_dupes = expect.get("max_singleton_duplicates")
    if max_dupes is not None:
        dupes = _singleton_duplicate_count(spec)
        if dupes > int(max_dupes):
            issues.append(f"singleton_duplicates {dupes} > max {max_dupes}")

    for fk in expect.get("required_field_keys") or []:
        if fk not in field_values:
            issues.append(f"missing required field_key '{fk}'")

    field_scores: list[FieldScore] = []
    labeled = expect.get("labeled_fields") or {}
    for fk, label_spec in labeled.items():
        values = field_values.get(fk, [])
        matched = _field_matches(label_spec, values)
        field_scores.append(
            FieldScore(
                field_key=fk,
                document_id=document_id,
                expected=True,
                matched=matched,
                extracted=bool(values),
                actual_values=values[:3],
            )
        )
        if not matched:
            issues.append(
                f"label mismatch '{fk}' expected {label_spec.get('values') or label_spec.get('value_contains')} "
                f"got {values[:1]}"
            )

    # Structural: every row needs confidence + field_key
    for bucket in BUCKETS:
        for i, row in enumerate(spec.get(bucket) or []):
            if not isinstance(row, dict):
                continue
            if row.get("confidence") is None:
                issues.append(f"{bucket}[{i}] missing confidence")
            if not row.get("field_key"):
                issues.append(f"{bucket}[{i}] missing field_key")

    return DocEvalResult(
        document_id=document_id,
        validation_json=str(validation_path),
        passed=len(issues) == 0,
        issues=issues,
        row_count=rows,
        avg_confidence=avg_conf,
        field_keys=field_keys,
        field_scores=field_scores,
        warnings_count=len(warnings),
    )


def aggregate_field_metrics(results: list[DocEvalResult]) -> dict[str, Any]:
    by_field: dict[str, dict[str, int]] = {}
    for result in results:
        for fs in result.field_scores:
            stats = by_field.setdefault(fs.field_key, {"tp": 0, "fp": 0, "fn": 0})
            stats["tp"] += fs.tp
            stats["fp"] += fs.fp
            stats["fn"] += fs.fn

    per_field: dict[str, Any] = {}
    precisions: list[float] = []
    recalls: list[float] = []
    f1s: list[float] = []

    for fk, stats in sorted(by_field.items()):
        tp, fp, fn = stats["tp"], stats["fp"], stats["fn"]
        precision = tp / (tp + fp) if (tp + fp) else (1.0 if tp else 0.0)
        recall = tp / (tp + fn) if (tp + fn) else (1.0 if tp else 0.0)
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        per_field[fk] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)

    macro = {
        "precision": round(sum(precisions) / len(precisions), 4) if precisions else 0.0,
        "recall": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
        "f1": round(sum(f1s) / len(f1s), 4) if f1s else 0.0,
    }
    return {"per_field": per_field, "macro": macro}


def run_golden_eval(manifest_path: Path | None = None) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    repo = _repo_root()
    thresholds = manifest.get("thresholds") or {}
    doc_results: list[DocEvalResult] = []

    for entry in manifest.get("documents") or []:
        if not entry.get("enabled", True):
            continue
        rel = entry.get("validation_json")
        if not rel:
            continue
        path = (repo / rel).resolve()
        doc_results.append(
            evaluate_document(
                document_id=str(entry.get("id") or path.stem),
                validation_path=path,
                expect=entry.get("expect") or {},
                skip_pipeline_check=bool(entry.get("skip_pipeline_check")),
            )
        )

    metrics = aggregate_field_metrics(doc_results)
    docs_passed = sum(1 for d in doc_results if d.passed)
    docs_total = len(doc_results)

    gate_issues: list[str] = []
    min_docs = int(thresholds.get("min_docs_passing") or 1)
    if docs_passed < min_docs:
        gate_issues.append(f"docs_passing {docs_passed}/{docs_total} < min {min_docs}")

    min_recall = thresholds.get("min_labeled_field_recall")
    if min_recall is not None and metrics["macro"]["recall"] < float(min_recall):
        gate_issues.append(
            f"macro recall {metrics['macro']['recall']} < min {min_recall}"
        )

    min_f1 = thresholds.get("min_macro_f1")
    if min_f1 is not None and metrics["macro"]["f1"] < float(min_f1):
        gate_issues.append(f"macro F1 {metrics['macro']['f1']} < min {min_f1}")

    per_field_min = thresholds.get("min_field_recall") or {}
    for fk, min_r in per_field_min.items():
        actual = (metrics["per_field"].get(fk) or {}).get("recall")
        if actual is not None and actual < float(min_r):
            gate_issues.append(f"field '{fk}' recall {actual} < min {min_r}")

    passed = len(gate_issues) == 0 and docs_passed == docs_total

    return {
        "manifest_version": manifest.get("version"),
        "passed": passed,
        "gate_issues": gate_issues,
        "documents": [
            {
                "document_id": d.document_id,
                "passed": d.passed,
                "issues": d.issues,
                "row_count": d.row_count,
                "avg_confidence": d.avg_confidence,
                "field_keys": d.field_keys,
                "warnings_count": d.warnings_count,
            }
            for d in doc_results
        ],
        "metrics": metrics,
        "summary": {
            "documents_passed": docs_passed,
            "documents_total": docs_total,
            "macro_f1": metrics["macro"]["f1"],
            "macro_recall": metrics["macro"]["recall"],
            "macro_precision": metrics["macro"]["precision"],
        },
    }


def _significant_tokens(value: str, limit: int = 4) -> list[str]:
    """Pick stable substring needles for bootstrap labels."""
    cleaned = re.sub(r"^(project name|project owner|bid deadline|project solicitation number):\s*", "", value, flags=re.I)
    cleaned = cleaned.strip()
    if len(cleaned) <= 48:
        return [cleaned] if cleaned else []
    parts = re.split(r"[\s/,\-–—]+", cleaned)
    parts = [p for p in parts if len(p) >= 4][:limit]
    return parts or [cleaned[:40]]


def bootstrap_manifest(
    validation_dir: Path,
    *,
    version: str = "1.0.0",
) -> dict[str, Any]:
    """Build manifest expectations from current pipeline outputs."""
    documents: list[dict[str, Any]] = []
    repo = _repo_root()

    for path in sorted(validation_dir.glob("doc_*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        rel = str(path.relative_to(repo)).replace("\\", "/")
        doc_id = path.stem[:48]

        if doc.get("pipeline_status") != "completed":
            documents.append(
                {
                    "id": doc_id,
                    "validation_json": rel,
                    "enabled": False,
                    "skip_pipeline_check": True,
                    "note": f"pipeline_status={doc.get('pipeline_status')}",
                    "expect": {},
                }
            )
            continue

        spec, _ = rebuild_spec_from_validation_doc(doc)
        field_values = extract_field_values(spec)
        avg_conf = _avg_confidence(spec) or 0
        rows = _row_count(spec)

        labeled: dict[str, Any] = {}
        label_keys = (
            "bid_deadline_date_time",
            "project_name",
            "project_owner",
            "project_solicitation_number",
            "question_deadline_date_time",
            "bid_open_date_time",
        )
        for fk in label_keys:
            vals = field_values.get(fk)
            if not vals:
                continue
            labeled[fk] = {
                "match": "contains_any",
                "values": _significant_tokens(vals[0]),
            }

        required = [k for k in label_keys if k in field_values]
        documents.append(
            {
                "id": doc_id,
                "validation_json": rel,
                "enabled": True,
                "expect": {
                    "required_field_keys": required,
                    "min_row_count": max(8, rows - 4),
                    "min_avg_confidence": max(55, int(avg_conf - 15)),
                    "max_singleton_duplicates": 0,
                    "labeled_fields": labeled,
                },
            }
        )

    return {
        "version": version,
        "description": "Golden set for offline spec-check eval (Phase 7). Regenerate with bootstrap_golden_manifest.py when outputs change intentionally.",
        "thresholds": {
            "min_docs_passing": sum(1 for d in documents if d.get("enabled")),
            "min_labeled_field_recall": 0.85,
            "min_macro_f1": 0.80,
            "min_field_recall": {
                "bid_deadline_date_time": 0.95,
                "project_name": 0.85,
                "project_owner": 0.85,
            },
        },
        "documents": documents,
    }
