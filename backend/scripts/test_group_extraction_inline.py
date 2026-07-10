"""Run parse + group extraction in-process (bypasses stuck sync threads after dev reload)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import django

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.conf import settings  # noqa: E402

import requests  # noqa: E402

from apps.documents.models import Document  # noqa: E402
from apps.intelligence.services.orchestrator import IntelligenceOrchestrator  # noqa: E402
from apps.processing.models import ProcessingJob  # noqa: E402
from apps.processing.services.job_service import ProcessingJobService  # noqa: E402
from apps.processing.tasks import process_document_task  # noqa: E402

BASE = "http://127.0.0.1:8004/api/v1"
DOC_PATH = Path(r"D:\RAQ-Document-summarizer\testing-docs\2-RFP 2025-06.pdf")


def login() -> str:
    r = requests.post(
        f"{BASE}/auth/login/",
        json={"email": "admin@itcube.net", "password": "TestAdmin1234!"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access"]


def main() -> int:
    print("FAST_MODE:", settings.INTELLIGENCE_FAST_MODE)
    print("GROUP_EXTRACTION:", settings.INTELLIGENCE_GROUP_EXTRACTION)

    token = login()
    headers = {"Authorization": f"Bearer {token}"}
    t0 = time.time()

    with DOC_PATH.open("rb") as f:
        r = requests.post(
            f"{BASE}/documents/upload/",
            headers=headers,
            files={"file": (DOC_PATH.name, f, "application/pdf")},
            data={
                "tender_reference": f"E2E-INLINE-{int(time.time())}",
                "tender_title": "Inline group extraction test",
            },
            timeout=180,
        )
    print("UPLOAD", r.status_code)
    doc_id = r.json()["id"]
    print("Document:", doc_id)

    job = ProcessingJobService.get_latest_job_for_document(doc_id)
    if not job:
        print("No job found")
        return 1

    print("Processing parse pipeline in-process...")
    parse_t0 = time.time()
    process_document_task.apply(args=[str(job.id)])
    print(f"Parse pipeline done in {time.time() - parse_t0:.1f}s")

    doc = Document.objects.get(pk=doc_id)
    print("Document status:", doc.status)
    if doc.status == "failed":
        job.refresh_from_db()
        print("FAILED:", job.error_message)
        return 1

    print("Running group extraction + summary in-process...")
    ext_t0 = time.time()
    IntelligenceOrchestrator.begin_processing(str(doc_id), regenerate=False)
    IntelligenceOrchestrator.run(str(doc_id), regenerate=False)
    print(f"Briefing done in {time.time() - ext_t0:.1f}s")

    summary = requests.get(
        f"{BASE}/documents/{doc_id}/summary/", headers=headers, timeout=60
    ).json()
    insights = requests.get(
        f"{BASE}/documents/{doc_id}/insights/", headers=headers, timeout=60
    ).json()

    fields = summary.get("summary_json", {}).get("spec_check_fields", {})
    print("\n=== RESULTS ===")
    print(f"Total: {time.time() - t0:.1f}s")
    for bucket, items in fields.items():
        if items:
            print(f"  {bucket}: {len(items)}")
            for item in items[:2]:
                print(f"    - {(item.get('text') or '')[:90]}")

    if isinstance(insights, list):
        modes = [
            (i.get("token_usage") or {}).get("mode")
            for i in insights
            if isinstance(i, dict)
        ]
        print("Insight count:", len(insights))
        print("Modes:", set(m for m in modes if m))

    print("\nSpec fields JSON sample:")
    print(json.dumps({k: len(v) for k, v in fields.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
