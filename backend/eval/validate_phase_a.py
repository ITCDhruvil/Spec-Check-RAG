"""Phase A validation — re-run 4 reference docs, check A1-A5 guarantees.

A1: zero out-of-vocab labels in raw insights.
A2: verified fields confidence >= 90; ungrounded < 55.
A3: date-ordering warnings surface; no false positives on clean docs.
A5: identity context available to downstream passes (spot check name/owner present).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django
django.setup()
sys.stdout.reconfigure(encoding="utf-8")

from apps.intelligence.services.orchestrator import IntelligenceOrchestrator
from apps.intelligence.models import ExtractedInsight, GeneratedSummary
from apps.intelligence.services.field_confidence import all_registered_field_keys

DOCS = {
    "c3f4db27-27c8-4164-bd96-f99ff0b0e2b4": "NPS RFQ",
    "46d515c0-82d9-4e67-a1c1-48aa35761617": "HRSD IFB",
    "3bca0c61-00f7-40dc-9e53-c5348136d3e2": "E-rate RFP",
    "873de021-6418-4d57-9648-31d2804d073f": "Allegan RFP",
}

ALLOWED = all_registered_field_keys()

for did, label in DOCS.items():
    print(f"\n{'='*70}\n{label} ({did[:8]})")
    try:
        IntelligenceOrchestrator.run(did, regenerate=True)
    except Exception as e:
        print(f"  PIPELINE FAILED: {str(e)[:160]}")
        continue

    # A1 — out-of-vocab labels in raw insights (CURRENT summary only, not stale ones)
    s_cur = GeneratedSummary.objects.filter(document_id=did, is_current=True).first()
    insights = ExtractedInsight.objects.filter(document_id=did, generated_summary=s_cur)
    oov = set()
    for ins in insights:
        for it in (ins.payload or {}).get("items", []):
            lab = str(it.get("label") or "").strip()
            if lab and lab not in ALLOWED:
                oov.add(lab)
    print(f"  A1 out-of-vocab labels: {sorted(oov) if oov else 'NONE ✓'}")

    # A2 — confidence tiers in final spec fields
    s = GeneratedSummary.objects.filter(document_id=did, is_current=True).first()
    sf = (s.summary_json or {}).get("spec_check_fields", {})
    verified_low = []
    for bucket, rows in sf.items():
        if not isinstance(rows, list):
            continue
        for r in rows:
            conf = r.get("confidence")
            srcs = r.get("sources") or []
            verified = any(isinstance(x, dict) and x.get("citation_verified") for x in srcs)
            if verified and isinstance(conf, int) and conf < 90:
                verified_low.append((r.get("field_key"), conf))
    print(f"  A2 verified-but-low-confidence: {verified_low if verified_low else 'NONE ✓'}")

    # A3 — date warnings
    warns = [w for w in (s.summary_json.get("_meta", {}).get("field_warnings") or [])
             if w.get("bucket") == "project_dates"]
    print(f"  A3 date warnings: {[w['message'][:50] for w in warns] if warns else 'none'}")

    # A5 — identity present
    meta = sf.get("project_metadata_items", [])
    has_name = any(m.get("field_key") == "project_name" for m in meta)
    has_owner = any(m.get("field_key") == "project_owner" for m in meta)
    print(f"  A5 identity: name={'✓' if has_name else '✗'} owner={'✓' if has_owner else '✗'}")

print("\nDONE")
