"""
Batch Phase 5 verification across validation JSONs and optional DB documents.

Usage:
  cd backend
  python eval/run_phase5_batch_verify.py
  python eval/run_phase5_batch_verify.py --document-ids uuid1,uuid2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

from apps.documents.models import Document
from apps.intelligence.models import ExtractedInsight, GeneratedSummary
from apps.intelligence.services.summary_postprocess import (
    build_spec_check_fields_from_insights,
    finalize_spec_check_fields,
)

BUCKETS = (
    "project_metadata_items",
    "project_people_items",
    "project_size_location_items",
    "project_dates",
    "bond_items",
)
VALIDATION_DIR = REPO / "sample-docs" / "validation_results"


def _rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for bucket in BUCKETS:
        for row in spec.get(bucket) or []:
            if isinstance(row, dict):
                out.append({**row, "_bucket": bucket})
    return out


def _issues_rebuilt(spec: dict[str, Any], label: str) -> list[str]:
    """Strict checks for freshly built spec_check_fields."""
    issues: list[str] = []
    rows = _rows(spec)
    if not rows:
        issues.append(f"{label}: no spec_check rows")
        return issues

    for i, row in enumerate(rows):
        conf = row.get("confidence")
        if conf is None:
            issues.append(f"{label}: row {i} missing confidence ({row.get('text', '')[:40]})")
        elif not isinstance(conf, int) or conf < 0 or conf > 100:
            issues.append(f"{label}: row {i} invalid confidence={conf}")

        if not row.get("field_key"):
            issues.append(
                f"{label}: row {i} missing field_key bucket={row.get('_bucket')} "
                f"text={(row.get('text') or '')[:40]}"
            )

        if row.get("_calculated") and isinstance(conf, int) and conf > 72:
            issues.append(f"{label}: calculated row confidence {conf} exceeds cap 72")

        if row.get("_awaiting_project_value") and isinstance(conf, int) and conf > 58:
            issues.append(f"{label}: awaiting-value row confidence {conf} exceeds cap 58")

    municipal = [r for r in rows if (r.get("text") or "") == "Municipal meeting date"]
    award = [r for r in rows if (r.get("text") or "") == "Award date" or r.get("field_key") == "award_date"]
    if municipal and not award:
        issues.append(f"{label}: municipal meeting present but no award_date alias")

    for a in award:
        if a.get("_alias_of") != "municipal_meeting_date_time":
            issues.append(f"{label}: award_date missing _alias_of")

    return issues


def verify_validation_json(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    filename = doc.get("filename") or path.name

    # Path A: finalize stored spec_check_fields (legacy — confidence only)
    stored_spec = (
        ((doc.get("data") or {}).get("summary") or {}).get("summary_json") or {}
    ).get("spec_check_fields") or {}
    stored_copy = json.loads(json.dumps(stored_spec))
    finalize_spec_check_fields(stored_copy)
    stored_rows = _rows(stored_copy)
    stored_missing_conf = sum(1 for r in stored_rows if r.get("confidence") is None)
    pipeline_failed = (
        doc.get("pipeline_status") not in (None, "completed")
        or doc.get("summary_status") not in (None, "completed")
    )

    # Path B: rebuild from insights in validation JSON if present
    insights_data = ((doc.get("data") or {}).get("insights")) or []
    rebuilt_issues: list[str] = []
    rebuilt_row_count = 0
    if insights_data:
        insights = []
        for block in insights_data:
            if not isinstance(block, dict):
                continue
            insights.append(
                type(
                    "Insight",
                    (),
                    {
                        "extraction_type": block.get("extraction_type", ""),
                        "payload": block.get("payload") or {},
                    },
                )()
            )
        if insights:
            rebuilt = build_spec_check_fields_from_insights(insights)
            finalize_spec_check_fields(rebuilt)
            rebuilt_issues = _issues_rebuilt(rebuilt, filename)
            rebuilt_row_count = len(_rows(rebuilt))

    return {
        "file": path.name,
        "filename": filename,
        "stored_rows": len(stored_rows),
        "stored_missing_confidence": stored_missing_conf,
        "stored_pass": (stored_missing_conf == 0 and len(stored_rows) > 0)
        or (pipeline_failed and len(stored_rows) == 0),
        "pipeline_failed": pipeline_failed,
        "rebuilt_rows": rebuilt_row_count,
        "rebuilt_strict_pass": len(rebuilt_issues) == 0
        and (rebuilt_row_count > 0 or pipeline_failed),
        "rebuilt_issues": rebuilt_issues[:8],
    }


def verify_document(document_id: str) -> dict[str, Any]:
    doc = Document.objects.get(id=document_id)
    insights = list(ExtractedInsight.objects.filter(document=doc))
    rebuilt = build_spec_check_fields_from_insights(insights)
    finalize_spec_check_fields(rebuilt)
    issues = _issues_rebuilt(rebuilt, str(doc.original_filename))

    summary = GeneratedSummary.objects.filter(document=doc, is_current=True).first()
    stored_issues: list[str] = []
    if summary and summary.summary_json.get("spec_check_fields"):
        stored = json.loads(json.dumps(summary.summary_json["spec_check_fields"]))
        finalize_spec_check_fields(stored)
        stored_rows = _rows(stored)
        stored_missing_conf = sum(1 for r in stored_rows if r.get("confidence") is None)
        if stored_missing_conf:
            stored_issues.append(f"missing confidence on {stored_missing_conf} stored rows")

    return {
        "document_id": document_id,
        "filename": doc.original_filename,
        "insight_count": len(insights),
        "rebuilt_rows": len(_rows(rebuilt)),
        "rebuilt_strict_pass": len(issues) == 0,
        "rebuilt_issues": issues[:8],
        "stored_issues": stored_issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--document-ids",
        default="c3f4db27-27c8-4164-bd96-f99ff0b0e2b4,58df83e0-bd88-42dc-b515-65c543bc75a0",
        help="Comma-separated document UUIDs (default: known test docs)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Phase 5 batch verification")
    print("=" * 60)

    json_files = sorted(VALIDATION_DIR.glob("doc_*.json"))
    json_results = [verify_validation_json(p) for p in json_files]

    print(f"\n--- Validation JSONs ({len(json_results)}) ---")
    stored_ok = rebuilt_ok = 0
    for r in json_results:
        s = "PASS" if r["stored_pass"] else "FAIL"
        b = "PASS" if r["rebuilt_strict_pass"] else ("SKIP" if r["rebuilt_rows"] == 0 else "FAIL")
        if r["stored_pass"]:
            stored_ok += 1
        if r["rebuilt_strict_pass"]:
            rebuilt_ok += 1
        print(
            f"  [{s}] stored conf  [{b}] rebuilt strict  "
            f"rows={r['stored_rows']}/{r['rebuilt_rows']}  {r['filename'][:50]}"
        )
        for issue in r["rebuilt_issues"]:
            print(f"       ! {issue}")

    doc_ids = [x.strip() for x in args.document_ids.split(",") if x.strip()]
    print(f"\n--- DB documents ({len(doc_ids)}) ---")
    doc_ok = 0
    for did in doc_ids:
        try:
            r = verify_document(did)
        except Document.DoesNotExist:
            print(f"  [SKIP] document not found: {did}")
            continue
        status = "PASS" if r["rebuilt_strict_pass"] else "FAIL"
        if r["rebuilt_strict_pass"]:
            doc_ok += 1
        print(
            f"  [{status}] rebuilt rows={r['rebuilt_rows']} insights={r['insight_count']} "
            f"{r['filename'][:50]}"
        )
        for issue in r["rebuilt_issues"] + r["stored_issues"]:
            print(f"       ! {issue}")

    print("\n--- Summary ---")
    print(f"  Validation stored confidence: {stored_ok}/{len(json_results)} pass")
    print(f"  Validation rebuilt strict:    {rebuilt_ok}/{len(json_results)} pass")
    print(f"  DB documents rebuilt strict:  {doc_ok}/{len(doc_ids)} pass")

    all_pass = (
        stored_ok == len(json_results)
        and rebuilt_ok == len(json_results)
        and doc_ok == len(doc_ids)
    )
    print(f"\n{'OVERALL: PASS' if all_pass else 'OVERALL: FAIL — see issues above'}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
