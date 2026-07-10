"""Detailed Phase 5 field report for one document."""

from __future__ import annotations

import argparse
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--document-id",
        default="c3f4db27-27c8-4164-bd96-f99ff0b0e2b4",
    )
    args = parser.parse_args()

    doc = Document.objects.get(id=args.document_id)
    insights = list(ExtractedInsight.objects.filter(document=doc))
    spec = build_spec_check_fields_from_insights(insights)
    finalize_spec_check_fields(spec)

    print(f"=== Phase 5 detail: {doc.original_filename} ===")
    print(f"Insights: {len(insights)}")

    total = 0
    for bucket in BUCKETS:
        rows = spec.get(bucket) or []
        if not rows:
            continue
        print(f"\n--- {bucket} ({len(rows)}) ---")
        for r in rows:
            total += 1
            flags = []
            if r.get("_calculated"):
                flags.append("calculated")
            if r.get("_awaiting_project_value"):
                flags.append("awaiting_value")
            if r.get("_alias_of"):
                flags.append(f"alias={r['_alias_of']}")
            src = (r.get("sources") or [{}])[0]
            text = (r.get("text") or "")[:55]
            print(f"  [{r.get('confidence')}%] {r.get('field_key')}: {text}")
            if r.get("date"):
                print(f"       date: {str(r['date'])[:60]}")
            if flags:
                print(f"       flags: {', '.join(flags)}")
            if src.get("citation_verified") is not None:
                print(f"       citation_verified: {src['citation_verified']}")

    confs = []
    for bucket in BUCKETS:
        for r in spec.get(bucket) or []:
            if isinstance(r.get("confidence"), int):
                confs.append(r["confidence"])
    print(f"\nTotal rows: {total}")
    if confs:
        print(f"Avg confidence: {sum(confs)/len(confs):.1f}%")
        print(f"Min/max: {min(confs)}% / {max(confs)}%")


if __name__ == "__main__":
    main()
