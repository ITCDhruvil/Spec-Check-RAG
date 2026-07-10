"""Quick E2E: login -> upload -> parse -> group extraction -> summary fields."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8004/api/v1"
ADMIN_EMAIL = "admin@itcube.net"
ADMIN_PASSWORD = "TestAdmin1234!"
DOC_PATH = Path(r"D:\RAQ-Document-summarizer\testing-docs\2-RFP 2025-06.pdf")


def login() -> str:
    r = requests.post(
        f"{BASE}/auth/login/",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        raise SystemExit(f"Login failed {r.status_code}: {r.text}")
    return r.json()["access"]


def main() -> int:
    if not DOC_PATH.exists():
        print(f"Test PDF not found: {DOC_PATH}")
        return 1

    token = login()
    headers = {"Authorization": f"Bearer {token}"}
    started = time.time()

    with DOC_PATH.open("rb") as f:
        r = requests.post(
            f"{BASE}/documents/upload/",
            headers=headers,
            files={"file": (DOC_PATH.name, f, "application/pdf")},
            data={
                "tender_reference": f"E2E-GROUP-{int(time.time())}",
                "tender_title": "Group extraction E2E test",
                "version_type": "original",
            },
            timeout=180,
        )
    print("UPLOAD", r.status_code, f"({time.time() - started:.1f}s)")
    if r.status_code not in (200, 201):
        print(r.text)
        return 1

    doc_id = r.json()["id"]
    print("Document ID:", doc_id)

    doc_status = None
    for i in range(120):
        s = requests.get(
            f"{BASE}/documents/{doc_id}/status/", headers=headers, timeout=30
        ).json()
        doc_status = s.get("status")
        job = s.get("latest_job") or {}
        print(f"  parse poll {i}: {doc_status} / {job.get('current_stage')}")
        if doc_status in ("completed", "failed"):
            break
        time.sleep(2)

    if doc_status != "completed":
        print("PARSE FAILED", json.dumps(s, indent=2))
        return 1
    print(f"Parse done in {time.time() - started:.1f}s")

    g = requests.post(
        f"{BASE}/documents/{doc_id}/summary/generate/", headers=headers, timeout=60
    )
    print("GENERATE", g.status_code, g.text[:200])

    summary_status = None
    for i in range(180):
        ss = requests.get(
            f"{BASE}/documents/{doc_id}/summary/status/", headers=headers, timeout=30
        ).json()
        summary_status = ss.get("summary_status")
        print(
            f"  summary poll {i}: {summary_status} / {ss.get('progress_stage')}"
        )
        if summary_status in ("completed", "failed"):
            break
        time.sleep(3)

    elapsed = time.time() - started
    if summary_status != "completed":
        print("SUMMARY FAILED", json.dumps(ss, indent=2))
        return 1

    summary = requests.get(
        f"{BASE}/documents/{doc_id}/summary/", headers=headers, timeout=60
    ).json()
    insights = requests.get(
        f"{BASE}/documents/{doc_id}/insights/", headers=headers, timeout=60
    ).json()

    fields = summary.get("summary_json", {}).get("spec_check_fields", {})
    insight_list = insights if isinstance(insights, list) else insights.get("results", insights)

    print("\n=== RESULTS ===")
    print(f"Total time: {elapsed:.1f}s")
    print("Insights:", len(insight_list) if isinstance(insight_list, list) else "n/a")
    for bucket, items in fields.items():
        if items:
            print(f"  {bucket}: {len(items)} items")
            for item in items[:2]:
                print(f"    - {item.get('text', '')[:100]}")

    modes = []
    if isinstance(insight_list, list):
        for ins in insight_list:
            usage = (ins.get("token_usage") or {}) if isinstance(ins, dict) else {}
            if usage.get("mode") == "group_extraction":
                modes.append("group_extraction")
    print("Extraction mode:", "group_extraction" if modes else "legacy/unknown")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
