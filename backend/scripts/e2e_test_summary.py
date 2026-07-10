"""End-to-end test: upload -> parse -> generate summary."""
import json
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8002/api/v1"
DOC_PATH = Path(r"D:\RAQ-Document-summarizer\testing-docs\TENDER_41467_0_1724_1_1.pdf")


def main() -> int:
    if not DOC_PATH.exists():
        print(f"File not found: {DOC_PATH}")
        return 1

    with DOC_PATH.open("rb") as f:
        r = requests.post(
            f"{BASE}/documents/upload/",
            files={"file": (DOC_PATH.name, f, "application/pdf")},
            data={
                "tender_reference": "RFP-TEST-41467",
                "tender_title": "Test Tender 41467",
                "version_type": "original",
            },
            timeout=120,
        )
    print("UPLOAD", r.status_code)
    if r.status_code not in (200, 201):
        print(r.text)
        return 1

    upload = r.json()
    print(json.dumps(upload, indent=2))
    doc_id = upload["id"]

    status = None
    for i in range(90):
        s = requests.get(f"{BASE}/documents/{doc_id}/status/", timeout=30).json()
        status = s.get("status")
        job = s.get("latest_job") or {}
        print(f"poll {i}: doc={status} job={job.get('current_stage')}")
        if status in ("completed", "failed"):
            break
        time.sleep(3)

    if status == "failed":
        print("PROCESSING FAILED", json.dumps(s, indent=2))
        return 1

    g = requests.post(f"{BASE}/documents/{doc_id}/summary/generate/", timeout=30)
    print("GENERATE", g.status_code, g.text)
    if g.status_code not in (200, 202):
        return 1

    ss = {}
    for i in range(120):
        ss = requests.get(f"{BASE}/documents/{doc_id}/summary/status/", timeout=30).json()
        print(
            f"summary poll {i}:",
            ss.get("summary_status"),
            ss.get("progress_stage"),
        )
        if ss.get("summary_status") in ("completed", "failed"):
            break
        time.sleep(5)

    if ss.get("summary_status") != "completed":
        print("SUMMARY FAILED", json.dumps(ss, indent=2))
        return 1

    summary = requests.get(f"{BASE}/documents/{doc_id}/summary/", timeout=30).json()
    insights = requests.get(f"{BASE}/documents/{doc_id}/insights/", timeout=30).json()
    parsed = requests.get(f"{BASE}/documents/{doc_id}/parsed/", timeout=30).json()

    print("\n=== RESULTS ===")
    print("Document ID:", doc_id)
    print("Parsed pages:", parsed.get("total_pages"))
    print("Parse quality:", parsed.get("parsing_quality_score"))
    print("Summary tokens:", summary.get("total_tokens"))
    exec_text = (summary.get("summary_json") or {}).get("executive_summary", {}).get("text", "")
    print("Executive summary (preview):", exec_text[:600])
    print("Insights:")
    for x in insights:
        print(f"  - {x['extraction_type']}: {x['item_count']} items (conf={x['confidence_score']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
