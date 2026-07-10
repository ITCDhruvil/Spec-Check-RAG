"""Diagnose retrieval misses — show top-16 returned chunks vs GT for failing groups."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

sys.stdout.reconfigure(encoding="utf-8")

from apps.chat.services.retrieval_service import RetrievalService
from apps.intelligence.services.extraction_retrieval_service import (
    EXTRACTION_RETRIEVAL_QUERIES,
)

_QUERIES_BY_TYPE: dict[str, list[str]] = {
    str(k): v for k, v in EXTRACTION_RETRIEVAL_QUERIES.items()
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _query_for_type(etype: str) -> str:
    return " ".join(_QUERIES_BY_TYPE.get(etype, []))


# Groups to diagnose: (document_id, extraction_type, [gt_source_texts])
DIAGNOSE = [
    # Full misses
    (
        "46d515c0-82d9-4e67-a1c1-48aa35761617",
        "scope_of_work",
        [
            "The successful Contractor shall furnish all labor, equipment, materials, and supervision required fuel tank demolitions for various HRSD locations in",
            "Contractor shall furnish all material, labor, equipment, and supplies required for the demolition of fuel tanks at HRSD's Army Base Treatment Plant, N",
        ],
    ),
    # Late hits (rank 11) — want to push up
    (
        "46d515c0-82d9-4e67-a1c1-48aa35761617",
        "technical_requirements",
        [
            "The successful Contractor shall furnish all labor, equipment, materials, and supervision required fuel tank demolitions for various HRSD locations in",
            "Contractor shall furnish all material, labor, equipment, and supplies required for the demolition of fuel tanks at HRSD's Army Base Treatment Plant, N",
        ],
    ),
    # Rank 5 — want rank 1-3
    (
        "c3f4db27-27c8-4164-bd96-f99ff0b0e2b4",
        "technical_requirements",
        [
            "NPS, MWR, Wilsons Creek NB",
            "5242 South State Hwy ZZ",
            "Site Visit Date/Time/Address: Friday, February 20, 2026, 1:00 PM CST Wilson's Creek National Battlefield Campground Springs Address 6349 State Highway",
            "Wilson's Creek National Battlefield",
            "WILSON'S CREEK NATIONAL BATTLEFIELD",
        ],
    ),
    # Rank 7
    (
        "873de021-6418-4d57-9648-31d2804d073f",
        "technical_requirements",
        [
            "Allegan County 3283 122nd Ave Allegan, MI 49010",
            "Allegan County RFP #1008-26A - Boat Launch Dock Refurbishment Services",
        ],
    ),
    # Rank 4
    (
        "3bca0c61-00f7-40dc-9e53-c5348136d3e2",
        "technical_requirements",
        [
            "RE-CABLE A PORTION OF THE SCHOOL OFFICE, H BUILDING, J BUILDING AND A BUILDING.",
            "8 new cable runs approx 150ft",
            "Roughly 25,000ft of CAT6a cable as specified below.",
        ],
    ),
]


def run() -> None:
    for doc_id, etype, gt_texts in DIAGNOSE:
        query = _query_for_type(etype)
        print(f"\n{'='*80}")
        print(f"DOC:   {doc_id[:8]}")
        print(f"TYPE:  {etype}")
        print(f"QUERY: {query[:120]}...")
        print(f"\nGT passages ({len(gt_texts)}):")
        for t in gt_texts:
            print(f"  GT> {t[:100]}")

        chunks = RetrievalService.retrieve(doc_id, query)
        print(f"\nTop-{len(chunks)} returned chunks:")
        norm_gt = [_normalize(t) for t in gt_texts]

        for i, c in enumerate(chunks, 1):
            norm_chunk = _normalize(c.text)
            hit = any(gt in norm_chunk for gt in norm_gt)
            marker = "*** HIT ***" if hit else ""
            print(f"  [{i:2d}] score={c.score:.4f} page={c.page_start}-{c.page_end} "
                  f"type={c.chunk_type} {marker}")
            print(f"       {c.text[:120].replace(chr(10), ' ')}")

        gt_found = set()
        for i, c in enumerate(chunks, 1):
            norm_chunk = _normalize(c.text)
            for j, gt_n in enumerate(norm_gt):
                if gt_n in norm_chunk:
                    gt_found.add(j)
        missing = [gt_texts[j] for j in range(len(gt_texts)) if j not in gt_found]
        if missing:
            print(f"\nNOT FOUND in top-{len(chunks)}:")
            for t in missing:
                print(f"  MISS> {t[:100]}")
        else:
            print(f"\nAll GT passages found in top-{len(chunks)}")


if __name__ == "__main__":
    run()
