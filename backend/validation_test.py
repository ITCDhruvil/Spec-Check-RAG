"""
Validation test: upload 5 sample docs, run pipeline, save results.

Usage:
  python validation_test.py

Env overrides:
  - SPEC_CHECK_API_BASE (default: http://127.0.0.1:8004/api/v1)
  - SPEC_CHECK_SAMPLE_DIR (default: <repo>/sample-docs)
  - SPEC_CHECK_VALIDATION_OUT_DIR (default: <sample_dir>/validation_results)
"""
import json
import os
import time
from pathlib import Path
import requests

DEFAULT_BASE = "http://127.0.0.1:8004/api/v1"
BASE = os.environ.get("SPEC_CHECK_API_BASE", DEFAULT_BASE).rstrip("/")

# Resolve paths relative to repo root (works across machines).
REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = Path(os.environ.get("SPEC_CHECK_SAMPLE_DIR", str(REPO_ROOT / "sample-docs")))
OUT_DIR = Path(
    os.environ.get("SPEC_CHECK_VALIDATION_OUT_DIR", str(SAMPLE_DIR / "validation_results"))
)

# 5 smallest files chosen for validation
DEFAULT_TARGET_FILES = [
    "doc_20260217_102024_3f1f11ad_7417982_specs_20260216123049_be8c9b14-cb85-4cc7-8_VQMl5ya.pdf",
    "doc_20260216_175551_875c18ea_7413766_specs_20260216042650_43d35bcd-66a7-4d7b-b_zRlKmXk.pdf",
    "doc_20260217_093852_9efac7ea_7420226_specs_20260216061659_b54e9c03-82ea-4793-9_mFCGliV.pdf",
    "doc_20260216_181824_3cd182f4_7410235_specs_20260216061605_06080d59-f41b-4198-a_5Fp6dVF.pdf",
    "doc_20260217_090751_2e9d2172_7419759_specs_20260216121638_4511ef3a-8075-4038-a_mIXBHHx.pdf",
]

# Optional override: comma-separated filenames (relative to SAMPLE_DIR)
_override = (os.environ.get("SPEC_CHECK_TARGET_FILES") or "").strip()
if _override:
    TARGET_FILES = [p.strip() for p in _override.split(",") if p.strip()]
else:
    TARGET_FILES = DEFAULT_TARGET_FILES

POLL_INTERVAL = int(os.environ.get("SPEC_CHECK_POLL_INTERVAL", "4"))
PROCESS_POLL_MAX = int(os.environ.get("SPEC_CHECK_PROCESS_POLL_MAX", "200"))  # ~13 min default
SUMMARY_POLL_MAX = int(os.environ.get("SPEC_CHECK_SUMMARY_POLL_MAX", "240"))  # ~16 min default
UPLOAD_TIMEOUT = int(os.environ.get("SPEC_CHECK_UPLOAD_TIMEOUT", "180"))
GENERATE_TIMEOUT = int(os.environ.get("SPEC_CHECK_GENERATE_TIMEOUT", "600"))


def log(msg):
    print(msg, flush=True)


def upload_file(path: Path) -> dict:
    ref = path.stem[:48].upper().replace(" ", "-")
    with path.open("rb") as f:
        r = requests.post(
            f"{BASE}/documents/upload/",
            files={"file": (path.name, f, "application/pdf")},
            data={
                "tender_reference": f"VAL-{ref[:40]}",
                "tender_title": path.stem[:80],
                "version_type": "original",
            },
            timeout=UPLOAD_TIMEOUT,
        )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Upload failed {r.status_code}: {r.text[:300]}")
    return r.json()


def wait_processing(doc_id: str) -> tuple[str, dict]:
    for i in range(PROCESS_POLL_MAX):
        r = requests.get(f"{BASE}/documents/{doc_id}/status/", timeout=30)
        r.raise_for_status()
        d = r.json()
        status = d.get("status")
        stage = (d.get("latest_job") or {}).get("current_stage", "")
        log(f"    proc [{i:02d}] status={status} stage={stage}")
        if status in ("completed", "failed"):
            return status, d
        time.sleep(POLL_INTERVAL)
    return "timeout", {}


def generate_summary(doc_id: str):
    r = requests.post(f"{BASE}/documents/{doc_id}/summary/generate/", timeout=GENERATE_TIMEOUT)
    if r.status_code not in (200, 202):
        raise RuntimeError(f"Generate failed {r.status_code}: {r.text[:300]}")
    log(f"    generate: {r.status_code}")


def wait_summary(doc_id: str) -> tuple[str, dict]:
    for i in range(SUMMARY_POLL_MAX):
        r = requests.get(f"{BASE}/documents/{doc_id}/summary/status/", timeout=30)
        r.raise_for_status()
        d = r.json()
        ss = d.get("summary_status")
        stage = d.get("progress_stage", "")
        log(f"    sum  [{i:02d}] status={ss} stage={stage}")
        if ss in ("completed", "failed"):
            return ss, d
        time.sleep(POLL_INTERVAL)
    return "timeout", {}


def fetch_results(doc_id: str) -> dict:
    summary = requests.get(f"{BASE}/documents/{doc_id}/summary/", timeout=60).json()
    insights = requests.get(f"{BASE}/documents/{doc_id}/insights/", timeout=60).json()
    parsed = requests.get(f"{BASE}/documents/{doc_id}/parsed/", timeout=60).json()
    return {"summary": summary, "insights": insights, "parsed": parsed}


def run_one(path: Path) -> dict:
    log(f"\n{'='*60}")
    log(f"FILE: {path.name}")
    log(f"SIZE: {path.stat().st_size / 1024:.1f} KB")
    t0 = time.time()

    result = {
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "doc_id": None,
        "pipeline_status": None,
        "summary_status": None,
        "elapsed_seconds": None,
        "data": None,
        "error": None,
    }

    try:
        upload = upload_file(path)
        doc_id = upload["id"]
        result["doc_id"] = doc_id
        log(f"  uploaded  id={doc_id}")

        proc_status, _ = wait_processing(doc_id)
        result["pipeline_status"] = proc_status
        if proc_status != "completed":
            raise RuntimeError(f"Processing {proc_status}")

        generate_summary(doc_id)
        sum_status, _ = wait_summary(doc_id)
        result["summary_status"] = sum_status
        if sum_status != "completed":
            raise RuntimeError(f"Summary {sum_status}")

        result["data"] = fetch_results(doc_id)
        log(f"  DONE in {time.time()-t0:.1f}s")

    except Exception as exc:
        result["error"] = str(exc)
        log(f"  ERROR: {exc}")

    result["elapsed_seconds"] = round(time.time() - t0, 1)
    return result


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_results = []

    log(f"API base: {BASE}")
    log(f"Sample dir: {SAMPLE_DIR}")
    log(f"Output dir: {OUT_DIR}")

    for fname in TARGET_FILES:
        path = SAMPLE_DIR / fname
        if not path.exists():
            log(f"SKIP (not found): {fname}")
            continue
        result = run_one(path)
        all_results.append(result)
        # Save per-file result immediately
        safe_name = "".join(c if c.isalnum() else "_" for c in path.stem)[:60]
        out_file = OUT_DIR / f"{safe_name}.json"
        out_file.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        log(f"  saved -> {out_file.name}")

    # Save combined
    combined = OUT_DIR / "all_results.json"
    combined.write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")
    log(f"\n{'='*60}")
    log(f"All done. Results saved to {OUT_DIR}")
    log(f"Files processed: {len(all_results)}")
    successes = sum(1 for r in all_results if r.get("data"))
    log(f"Successful: {successes} / {len(all_results)}")


if __name__ == "__main__":
    main()
