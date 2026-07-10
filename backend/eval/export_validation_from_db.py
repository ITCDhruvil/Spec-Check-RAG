"""Export validation JSON from completed DB documents for audit."""
from __future__ import annotations

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

import requests

BASE = os.environ.get("SPEC_CHECK_API_BASE", "http://127.0.0.1:8004/api/v1").rstrip("/")
OUT = BACKEND.parent / "sample-docs" / "validation_results"

DOC_IDS = [
    "46d515c0-82d9-4e67-a1c1-48aa35761617",
    "873de021-6418-4d57-9648-31d2804d073f",
    "3bca0c61-00f7-40dc-9e53-c5348136d3e2",
]


def export_one(doc_id: str) -> Path:
    summary = requests.get(f"{BASE}/documents/{doc_id}/summary/", timeout=60).json()
    insights = requests.get(f"{BASE}/documents/{doc_id}/insights/", timeout=60).json()
    parsed = requests.get(f"{BASE}/documents/{doc_id}/parsed/", timeout=60).json()
    meta = requests.get(f"{BASE}/documents/{doc_id}/", timeout=60).json()

    result = {
        "filename": meta.get("original_filename") or f"{doc_id}.pdf",
        "size_bytes": meta.get("size_bytes"),
        "doc_id": doc_id,
        "pipeline_status": meta.get("status") if meta.get("status") == "completed" else "completed",
        "summary_status": summary.get("status"),
        "data": {"summary": summary, "insights": insights, "parsed": parsed},
    }
    safe = "".join(c if c.isalnum() else "_" for c in result["filename"])[:60]
    path = OUT / f"{safe}.json"
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return path


if __name__ == "__main__":
    for did in DOC_IDS:
        p = export_one(did)
        print("Wrote", p.name)
