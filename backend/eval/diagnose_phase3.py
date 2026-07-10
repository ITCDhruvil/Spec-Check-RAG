"""Diagnose late-rank hits for 2aef38d9 payment_terms (rank 12) and technical_requirements (rank 10)."""
from __future__ import annotations

import os, re, sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django
django.setup()
sys.stdout.reconfigure(encoding="utf-8")

from apps.chat.services.retrieval_service import RetrievalService
from apps.intelligence.services.extraction_retrieval_service import EXTRACTION_RETRIEVAL_QUERIES

_QUERIES = {str(k): v for k, v in EXTRACTION_RETRIEVAL_QUERIES.items()}

def _norm(t): return re.sub(r"\s+", " ", (t or "").strip().lower())
def _q(etype): return " ".join(_QUERIES.get(etype, []))

CASES = [
    (
        "2aef38d9-b6a1-42a6-8f7c-73ad03173840",
        "payment_terms",
        [
            "For projects exceeding $50,000, this notice must be run once a week for three successive weeks in a newspaper of general circulation",
            "If the project involves an estimated amount exceeding $500,000, this notice must also be run at least once in three newspapers",
        ],
    ),
    (
        "2aef38d9-b6a1-42a6-8f7c-73ad03173840",
        "technical_requirements",
        [
            "SEALED PROPOSALS will be received only from previously PRE-QUALIFIED General Contractors by Homewood City Schools, located at 450 Dale Avenue, Homewood, Alabama",
        ],
    ),
]

for doc_id, etype, gt_texts in CASES:
    query = _q(etype)
    norm_gt = [_norm(t) for t in gt_texts]
    print("\n" + "="*80)
    print(f"DOC:   {doc_id[:8]}  TYPE: {etype}")
    print(f"QUERY: {query[:120]}")
    print(f"\nGT ({len(gt_texts)}):")
    for t in gt_texts:
        print(f"  > {t[:110]}")

    chunks = RetrievalService.retrieve(doc_id, query)
    print(f"\nTop-{len(chunks)} returned:")
    for i, c in enumerate(chunks, 1):
        hit = any(gt in _norm(c.text) for gt in norm_gt)
        marker = "  *** HIT" if hit else ""
        print(f"  [{i:2d}] score={c.score:.4f} p{c.page_start}-{c.page_end} {c.chunk_type}{marker}")
        print(f"       {c.text[:110].replace(chr(10),' ')}")
