"""
Phase 6 eval: post-rules hardening (date parse, dedupe, warnings).

Usage:
  cd backend
  python eval/run_phase6_postrules_test.py
  python eval/run_phase6_postrules_test.py --document-id <uuid>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

from apps.documents.models import Document
from apps.intelligence.models import ExtractedInsight
from apps.intelligence.services.summary_postprocess import (
    _parse_date_string,
    build_spec_check_fields_from_insights,
    finalize_spec_check_fields,
)

VALIDATION_DIR = BACKEND.parent / "sample-docs" / "validation_results"


def _analyze(spec: dict, warnings: list) -> dict:
    dates = spec.get("project_dates") or []
    pre_bid = [d for d in dates if d.get("field_key") == "pre_bid_deadline_date_time"]
    start = next((d for d in dates if d.get("field_key") == "project_start_date_time"), None)
    kinds = {d.get("field_key"): d.get("_date_kind") for d in dates if d.get("_date_kind")}
    return {
        "date_count": len(dates),
        "pre_bid_count": len(pre_bid),
        "start_calculated": bool(start and start.get("_calculated")),
        "start_date": (start or {}).get("date", "")[:60],
        "date_kinds_sample": dict(list(kinds.items())[:6]),
        "warning_count": len(warnings),
        "warnings": warnings[:8],
        "pass": len(pre_bid) <= 1 and (not start or start.get("_calculated") is not True or "estimated" in str(start.get("date", "")).lower() or "April" in str(start.get("date", ""))),
    }


def run_document(document_id: str) -> dict:
    doc = Document.objects.get(id=document_id)
    insights = list(ExtractedInsight.objects.filter(document=doc))
    spec = build_spec_check_fields_from_insights(insights)
    warnings = finalize_spec_check_fields(spec)
    return {
        "document_id": document_id,
        "filename": doc.original_filename,
        "analysis": _analyze(spec, warnings),
    }


def run_validation(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    insights_data = ((doc.get("data") or {}).get("insights")) or []
    insights = []
    for block in insights_data:
        if isinstance(block, dict):
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
    spec = build_spec_check_fields_from_insights(insights)
    warnings = finalize_spec_check_fields(spec)
    return {
        "filename": doc.get("filename") or path.name,
        "analysis": _analyze(spec, warnings),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id")
    args = parser.parse_args()

    print("=== Phase 6 date parse smoke ===")
    samples = [
        "March 4, 2026 at 1:00 PM CST",
        "February 26, 2026 at 12:00 PM EST",
        "03/04/2026 1300",
    ]
    for s in samples:
        print(f"  {s!r} -> {_parse_date_string(s)}")

    results = []
    if args.document_id:
        results.append(run_document(args.document_id))
    else:
        for path in sorted(VALIDATION_DIR.glob("doc_*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("pipeline_status") != "completed":
                continue
            results.append(run_validation(path))

    print("\n=== Phase 6 post-rules on sample docs ===")
    passed = 0
    for r in results:
        a = r["analysis"]
        status = "PASS" if a["pass"] else "FAIL"
        if a["pass"]:
            passed += 1
        name = (r.get("filename") or r.get("document_id", ""))[:55]
        print(
            f"  [{status}] dates={a['date_count']} pre_bid_dupes={a['pre_bid_count']} "
            f"start_calc={a['start_calculated']} warnings={a['warning_count']}  {name}"
        )
        if a["start_calculated"]:
            print(f"         start: {a['start_date']}")

    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
