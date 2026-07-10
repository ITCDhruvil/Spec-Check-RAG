"""
Phase 5 eval: per-field confidence on spec_check_fields.

Usage:
  cd backend
  python eval/run_phase5_field_confidence_test.py --document-id <uuid>
  python eval/run_phase5_field_confidence_test.py --validation-json path/to/doc.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
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


def _rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for bucket in BUCKETS:
        for row in spec.get(bucket) or []:
            if isinstance(row, dict):
                out.append({**row, "_bucket": bucket})
    return out


def analyze_spec_fields(spec: dict[str, Any]) -> dict[str, Any]:
    rows = _rows(spec)
    missing_confidence = [r for r in rows if r.get("confidence") is None]
    missing_field_key = [r for r in rows if not r.get("field_key")]
    low_confidence = [r for r in rows if isinstance(r.get("confidence"), int) and r["confidence"] < 50]
    award_rows = [r for r in rows if r.get("field_key") == "award_date" or r.get("text") == "Award date"]

    confidences = [r["confidence"] for r in rows if isinstance(r.get("confidence"), int)]
    avg_conf = round(sum(confidences) / len(confidences), 1) if confidences else None

    return {
        "row_count": len(rows),
        "avg_confidence": avg_conf,
        "missing_confidence": len(missing_confidence),
        "missing_field_key": len(missing_field_key),
        "low_confidence_count": len(low_confidence),
        "award_date_rows": len(award_rows),
        "pass": len(missing_confidence) == 0 and len(rows) > 0,
        "sample": [
            {
                "bucket": r.get("_bucket"),
                "field_key": r.get("field_key"),
                "text": (r.get("text") or "")[:60],
                "confidence": r.get("confidence"),
                "_calculated": r.get("_calculated"),
                "_alias_of": r.get("_alias_of"),
            }
            for r in rows[:12]
        ],
    }


def load_from_document(document_id: str) -> dict[str, Any]:
    doc = Document.objects.get(id=document_id)
    summary = (
        GeneratedSummary.objects.filter(document=doc, is_current=True)
        .order_by("-version")
        .first()
    )
    insights = list(
        ExtractedInsight.objects.filter(document=doc).order_by("extraction_type")
    )
    if summary and summary.summary_json.get("spec_check_fields"):
        spec = dict(summary.summary_json["spec_check_fields"])
        finalize_spec_check_fields(spec)
        source = "stored_summary+finalize"
    else:
        spec = build_spec_check_fields_from_insights(insights)
        finalize_spec_check_fields(spec)
        source = "rebuilt_from_insights"

    return {
        "document_id": str(doc.id),
        "filename": doc.original_filename,
        "insight_count": len(insights),
        "source": source,
        "analysis": analyze_spec_fields(spec),
        "spec_check_fields": spec,
    }


def load_from_validation_json(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    scf = ((doc.get("data") or {}).get("summary") or {}).get("summary_json") or {}
    spec = scf.get("spec_check_fields") or {}
    finalize_spec_check_fields(spec)
    return {
        "filename": doc.get("filename"),
        "source": "validation_json",
        "analysis": analyze_spec_fields(spec),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 field confidence eval")
    parser.add_argument("--document-id", help="Document UUID")
    parser.add_argument("--validation-json", type=Path, help="Validation result JSON path")
    args = parser.parse_args()

    if not args.document_id and not args.validation_json:
        parser.error("Provide --document-id or --validation-json")

    if args.document_id:
        result = load_from_document(args.document_id)
    else:
        result = load_from_validation_json(args.validation_json)

    analysis = result["analysis"]
    print(json.dumps(result, indent=2, default=str))

    status = "PASS" if analysis["pass"] else "FAIL"
    print(f"\n[{status}] rows={analysis['row_count']} avg_conf={analysis['avg_confidence']}% "
          f"missing_confidence={analysis['missing_confidence']} award_date={analysis['award_date_rows']}")
    sys.exit(0 if analysis["pass"] else 1)


if __name__ == "__main__":
    main()
