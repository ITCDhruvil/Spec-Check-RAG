"""Upload and run full pipeline for every PDF in testing-docs."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8002/api/v1"
DEFAULT_DOCS_DIR = Path(r"D:\RAQ-Document-summarizer\testing-docs")

PROCESS_POLL_INTERVAL = 3
PROCESS_POLL_MAX = 120
SUMMARY_POLL_INTERVAL = 5
SUMMARY_POLL_MAX = 180
GENERATE_TIMEOUT = 600
UPLOAD_TIMEOUT = 120


def safe_print(*args, **kwargs) -> None:
    """Avoid Windows cp1252 console crashes on non-ASCII API error text."""
    text = " ".join(str(a) for a in args)
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"), **kwargs)


def slug_from_name(name: str) -> str:
    stem = Path(name).stem
    safe = "".join(c if c.isalnum() else "-" for c in stem).strip("-")
    return safe[:48] or "test-doc"


def list_existing_filenames() -> set[str]:
    names: set[str] = set()
    page = 1
    while True:
        r = requests.get(f"{BASE}/documents/", params={"page": page}, timeout=30)
        r.raise_for_status()
        data = r.json()
        for item in data.get("results", []):
            names.add(item.get("original_filename", ""))
        if not data.get("next"):
            break
        page += 1
    return names


def upload_pdf(path: Path) -> dict:
    ref = slug_from_name(path.name).upper()
    with path.open("rb") as f:
        r = requests.post(
            f"{BASE}/documents/upload/",
            files={"file": (path.name, f, "application/pdf")},
            data={
                "tender_reference": f"TEST-{ref}",
                "tender_title": path.stem,
                "version_type": "original",
            },
            timeout=UPLOAD_TIMEOUT,
        )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"upload failed {r.status_code}: {r.text}")
    return r.json()


def wait_for_processing(doc_id: str) -> tuple[str, dict]:
    last: dict = {}
    for i in range(PROCESS_POLL_MAX):
        r = requests.get(f"{BASE}/documents/{doc_id}/status/", timeout=30)
        r.raise_for_status()
        last = r.json()
        status = last.get("status")
        job = last.get("latest_job") or {}
        safe_print(f"  process poll {i}: status={status} stage={job.get('current_stage')}")
        if status in ("completed", "failed"):
            return status, last
        time.sleep(PROCESS_POLL_INTERVAL)
    return "timeout", last


def generate_summary(doc_id: str) -> None:
    r = requests.post(
        f"{BASE}/documents/{doc_id}/summary/generate/",
        timeout=GENERATE_TIMEOUT,
    )
    if r.status_code not in (200, 202):
        raise RuntimeError(f"generate failed {r.status_code}: {r.text}")
    safe_print(f"  generate: {r.status_code} {r.text[:200]}")


def wait_for_summary(doc_id: str) -> tuple[str, dict]:
    last: dict = {}
    for i in range(SUMMARY_POLL_MAX):
        r = requests.get(f"{BASE}/documents/{doc_id}/summary/status/", timeout=30)
        r.raise_for_status()
        last = r.json()
        safe_print(
            f"  summary poll {i}:",
            last.get("summary_status"),
            last.get("progress_stage"),
        )
        if last.get("summary_status") in ("completed", "failed"):
            return last.get("summary_status") or "unknown", last
        time.sleep(SUMMARY_POLL_INTERVAL)
    return "timeout", last


def print_results(doc_id: str) -> None:
    summary = requests.get(f"{BASE}/documents/{doc_id}/summary/", timeout=60).json()
    insights = requests.get(f"{BASE}/documents/{doc_id}/insights/", timeout=60).json()
    parsed = requests.get(f"{BASE}/documents/{doc_id}/parsed/", timeout=60).json()

    sj = summary.get("summary_json") or {}
    exec_text = (sj.get("executive_summary") or {}).get("text", "")
    checklist = sj.get("submission_checklist") or []
    signals = sj.get("critical_signals") or []

    safe_print("  --- results ---")
    safe_print(f"  document_id: {doc_id}")
    safe_print(f"  pages: {parsed.get('total_pages')} quality={parsed.get('parsing_quality_score')}")
    safe_print(f"  summary_tokens: {summary.get('total_tokens')}")
    safe_print(f"  executive_summary: {exec_text[:280]}...")
    safe_print(f"  critical_signals: {len(signals)} checklist_items: {len(checklist)}")
    for x in insights:
        safe_print(
            f"  insight {x['extraction_type']}: {x['item_count']} items "
            f"(conf={x.get('confidence_score')})"
        )


def run_one(path: Path) -> int:
    safe_print(f"\n=== {path.name} ===")
    upload = upload_pdf(path)
    doc_id = upload["id"]
    safe_print(f"  uploaded id={doc_id} status={upload.get('status')}")

    proc_status, proc_payload = wait_for_processing(doc_id)
    if proc_status != "completed":
        if proc_status == "timeout":
            safe_print("  Celery may be stuck; run: python manage.py shell < scripts/process_queued_sync.py")
            safe_print("  Or: celery -A config worker -l info -P solo")
        safe_print("  FAILED processing:", json.dumps(proc_payload, indent=2))
        return 1

    generate_summary(doc_id)
    sum_status, sum_payload = wait_for_summary(doc_id)
    if sum_status != "completed":
        safe_print("  FAILED summary:", json.dumps(sum_payload, indent=2))
        return 1

    print_results(doc_id)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E test all PDFs in testing-docs")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files whose original_filename already exists in the API",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        help="Basenames to run (default: all PDFs in dir)",
    )
    args = parser.parse_args()

    if not args.dir.is_dir():
        safe_print(f"Directory not found: {args.dir}")
        return 1

    pdfs = sorted(args.dir.glob("*.pdf"))
    if args.only:
        only_set = {n.lower() for n in args.only}
        pdfs = [p for p in pdfs if p.name.lower() in only_set]

    if not pdfs:
        safe_print("No PDF files to test.")
        return 1

    existing: set[str] = set()
    if args.skip_existing:
        existing = list_existing_filenames()
        safe_print("Already in system:", ", ".join(sorted(existing)) or "(none)")

    failures = 0
    for path in pdfs:
        if args.skip_existing and path.name in existing:
            safe_print(f"\n=== {path.name} === SKIP (already uploaded)")
            continue
        try:
            failures += run_one(path)
        except Exception as exc:
            safe_print(f"  ERROR: {exc}")
            failures += 1

    safe_print(f"\nDone. failures={failures} of {len(pdfs)} file(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
