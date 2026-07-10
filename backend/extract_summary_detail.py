"""Extract detailed summary JSON content for validation."""
import json
from pathlib import Path

RESULTS_DIR = Path(r"D:\Spec_check_RAG_Approach\sample-docs\validation_results")

files = [
    ("F1_HCD_Vacant", "doc_20260217_102024_3f1f11ad_7417982_specs_20260216123049_be.json"),
    ("F2_Vanguard", "doc_20260216_175551_875c18ea_7413766_specs_20260216042650_43.json"),
    ("F3_Homewood", "doc_20260217_093852_9efac7ea_7420226_specs_20260216061659_b5.json"),
    ("F4_Brevard", "doc_20260216_181824_3cd182f4_7410235_specs_20260216061605_06.json"),
    ("F5_MCAS", "doc_20260217_090751_2e9d2172_7419759_specs_20260216121638_45.json"),
]

for label, fname in files:
    path = RESULTS_DIR / fname
    d = json.loads(path.read_text(encoding="utf-8"))
    data = d.get("data") or {}
    summary = data.get("summary") or {}
    sj = summary.get("summary_json") or {}

    print(f"\n{'='*70}")
    print(f"[{label}] {d.get('filename','?')[:60]}")

    # Print each non-meta section
    for key, val in sj.items():
        if key.startswith("_"):
            continue
        print(f"\n  *** {key} ***")
        if isinstance(val, dict):
            text = val.get("text") or val.get("item") or ""
            srcs = val.get("sources") or []
            if text:
                print(f"    text: {str(text)[:300]}")
            if srcs:
                print(f"    sources: {len(srcs)}")
        elif isinstance(val, list):
            print(f"    ({len(val)} items):")
            for item in val[:5]:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("item") or item.get("signal") or item.get("insight") or ""
                    date = item.get("date") or ""
                    srcs = item.get("sources") or []
                    entry = f"    - {str(text)[:120]}"
                    if date:
                        entry += f"  | date: {date}"
                    entry += f"  [srcs={len(srcs)}]"
                    print(entry)
        else:
            print(f"    {str(val)[:200]}")
