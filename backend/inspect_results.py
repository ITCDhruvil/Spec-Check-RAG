"""Inspect validation results and print extracted fields."""
import json
from pathlib import Path

RESULTS_DIR = Path(r"D:\Spec_check_RAG_Approach\sample-docs\validation_results")

files = [
    "doc_20260217_102024_3f1f11ad_7417982_specs_20260216123049_be.json",
    "doc_20260216_175551_875c18ea_7413766_specs_20260216042650_43.json",
    "doc_20260217_093852_9efac7ea_7420226_specs_20260216061659_b5.json",
    "doc_20260216_181824_3cd182f4_7410235_specs_20260216061605_06.json",
    "doc_20260217_090751_2e9d2172_7419759_specs_20260216121638_45.json",
]

for fname in files:
    path = RESULTS_DIR / fname
    d = json.loads(path.read_text(encoding="utf-8"))
    print(f"\n{'='*60}")
    print(f"FILE: {d.get('filename','?')}")
    print(f"pipeline_status={d.get('pipeline_status')} summary_status={d.get('summary_status')}")

    data = d.get("data") or {}
    summary = data.get("summary") or {}
    sj = summary.get("summary_json") or {}
    scf = sj.get("spec_check_fields") or {}

    print(f"summary_json top-level keys: {list(sj.keys())}")
    print(f"spec_check_fields keys: {list(scf.keys())}")

    for key, val in scf.items():
        if isinstance(val, list):
            print(f"\n  [{key}] ({len(val)} items):")
            for item in val[:10]:
                text = item.get("text", "")
                date = item.get("date", "")
                srcs = item.get("sources", [])
                if date:
                    print(f"    - {text}: {date}  [srcs={len(srcs)}]")
                else:
                    print(f"    - {text}  [srcs={len(srcs)}]")

    insights = data.get("insights") or []
    print(f"\n  INSIGHTS ({len(insights)} types):")
    for ins in insights:
        et = ins.get("extraction_type", "?")
        ic = ins.get("item_count", 0)
        cs = ins.get("confidence_score", 0)
        payload = ins.get("payload") or {}
        items = payload.get("items") or []
        print(f"    [{et}] items={ic} conf={cs:.2f}")
        for item in items[:3]:
            req = item.get("requirement") or item.get("insight") or ""
            conf = item.get("confidence", "?")
            print(f"      conf={conf} -> {str(req)[:120]}")
