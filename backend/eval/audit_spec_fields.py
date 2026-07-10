"""
Audit spec_check_fields from validation JSON or live API results.

Checks field presence, confidence, citation verification, and whether
source_text plausibly supports the extracted value.

Usage:
  python eval/audit_spec_fields.py --input ../sample-docs/validation_results/doc_....json
  python eval/audit_spec_fields.py --input ../sample-docs/validation_results --limit 10
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

from eval.golden_eval import BUCKETS, rebuild_spec_from_validation_doc

TOKEN_RE = re.compile(r"[a-z0-9]{3,}", re.I)


def _tokens(text: str, limit: int = 8) -> set[str]:
    return set(list(TOKEN_RE.findall(text.lower()))[:limit])


def _source_support_score(value: str, sources: list[dict]) -> tuple[float, bool]:
    """Return (overlap_ratio, any_verified)."""
    if not value or not sources:
        return 0.0, False
    val_tokens = _tokens(value)
    if not val_tokens:
        return 0.0, any(s.get("citation_verified") for s in sources if isinstance(s, dict))

    best = 0.0
    any_verified = False
    for src in sources:
        if not isinstance(src, dict):
            continue
        if src.get("citation_verified") is True:
            any_verified = True
        st = str(src.get("source_text") or "")
        if not st:
            continue
        src_tokens = _tokens(st, limit=20)
        if not src_tokens:
            continue
        overlap = len(val_tokens & src_tokens) / max(1, len(val_tokens))
        best = max(best, overlap)
    return best, any_verified


def _rows_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket in BUCKETS:
        for row in spec.get(bucket) or []:
            if isinstance(row, dict):
                rows.append({**row, "_bucket": bucket})
    return rows


def audit_validation_doc(doc: dict[str, Any], *, label: str = "") -> dict[str, Any]:
    name = label or doc.get("filename") or "unknown"
    pipeline = doc.get("pipeline_status")
    summary = doc.get("summary_status")
    if pipeline != "completed" or summary != "completed" or not doc.get("data"):
        return {
            "filename": name,
            "status": "failed",
            "pipeline_status": pipeline,
            "summary_status": summary,
            "error": doc.get("error"),
        }

    data = doc.get("data") or {}
    summary_obj = data.get("summary") or {}
    summary_json = summary_obj.get("summary_json") or {}
    spec = summary_json.get("spec_check_fields")
    warnings = (summary_json.get("_meta") or {}).get("field_warnings") or []

    if isinstance(spec, dict) and spec:
        import copy

        spec = copy.deepcopy(spec)
        from apps.intelligence.services.summary_postprocess import finalize_spec_check_fields

        finalize_spec_check_fields(spec)
    else:
        spec, warnings = rebuild_spec_from_validation_doc(doc)
    rows = _rows_from_spec(spec)

    field_audits: list[dict[str, Any]] = []
    confidences: list[int] = []
    verified_count = 0
    source_total = 0
    suspicious: list[str] = []

    for row in rows:
        fk = row.get("field_key") or "?"
        text = str(row.get("text") or "")
        date = str(row.get("date") or "")
        value = date if date and row.get("_bucket") == "project_dates" else text
        if row.get("_bucket") == "bond_items" and date:
            value = f"{text} | {date}"

        sources = row.get("sources") or []
        conf = row.get("confidence")
        if isinstance(conf, int):
            confidences.append(conf)

        for s in sources:
            if isinstance(s, dict):
                source_total += 1
                if s.get("citation_verified") is True:
                    verified_count += 1

        support, verified = _source_support_score(value, sources)
        flags: list[str] = []
        if conf is not None and conf >= 70 and not verified:
            flags.append("high_conf_unverified")
        if conf is not None and conf < 50:
            flags.append("low_confidence")
        if row.get("_calculated"):
            flags.append("calculated")
        if support < 0.15 and not row.get("_calculated"):
            flags.append("weak_source_support")
        if verified and support >= 0.3:
            flags.append("grounded")

        entry = {
            "field_key": fk,
            "bucket": row.get("_bucket"),
            "value": value[:100],
            "confidence": conf,
            "citation_verified": verified,
            "source_support": round(support, 2),
            "flags": flags,
            "_date_kind": row.get("_date_kind"),
        }
        field_audits.append(entry)

        if "high_conf_unverified" in flags or "weak_source_support" in flags:
            suspicious.append(f"{fk}: conf={conf}% support={support:.0%} — {value[:60]}")

    date_keys = {
        r.get("field_key")
        for r in rows
        if r.get("_bucket") == "project_dates" and r.get("field_key")
    }
    missing_core: list[str] = []
    for req in ("bid_deadline_date_time", "project_name", "project_owner"):
        if req not in {r.get("field_key") for r in rows}:
            missing_core.append(req)

    avg_conf = round(sum(confidences) / len(confidences), 1) if confidences else None

    return {
        "filename": name,
        "status": "ok",
        "row_count": len(rows),
        "avg_confidence": avg_conf,
        "min_confidence": min(confidences) if confidences else None,
        "max_confidence": max(confidences) if confidences else None,
        "citation_verified_rate": round(verified_count / source_total, 2) if source_total else 0,
        "date_field_keys": sorted(date_keys),
        "missing_core_fields": missing_core,
        "warnings_count": len(warnings),
        "field_warnings": warnings[:6],
        "suspicious_count": len(suspicious),
        "suspicious": suspicious[:10],
        "fields": field_audits,
    }


def _render_markdown(reports: list[dict[str, Any]]) -> str:
    lines = ["# Spec-check field audit", ""]
    ok = [r for r in reports if r.get("status") == "ok"]
    failed = [r for r in reports if r.get("status") != "ok"]
    lines.append(f"- Documents audited: **{len(reports)}** ({len(ok)} ok, {len(failed)} failed)")
    if ok:
        avg = round(sum(r.get("avg_confidence") or 0 for r in ok) / len(ok), 1)
        lines.append(f"- Average confidence (ok docs): **{avg}%**")
    lines.append("")

    for r in reports:
        lines.append(f"## {r.get('filename', '?')[:70]}")
        if r.get("status") != "ok":
            lines.append(f"- **FAILED** pipeline={r.get('pipeline_status')} summary={r.get('summary_status')}")
            if r.get("error"):
                lines.append(f"- Error: {r.get('error')}")
            lines.append("")
            continue

        lines.append(
            f"- rows={r.get('row_count')} avg_conf={r.get('avg_confidence')}% "
            f"citation_verified={int((r.get('citation_verified_rate') or 0)*100)}% "
            f"suspicious={r.get('suspicious_count')}"
        )
        if r.get("missing_core_fields"):
            lines.append(f"- **Missing core:** {', '.join(r['missing_core_fields'])}")
        if r.get("date_field_keys"):
            lines.append(f"- Dates: `{', '.join(r['date_field_keys'])}`")

        lines.append("")
        lines.append("| Field | Conf | Verified | Support | Flags |")
        lines.append("|-------|------|----------|---------|-------|")
        for f in r.get("fields") or []:
            flags = ", ".join(f.get("flags") or []) or "—"
            lines.append(
                f"| {f.get('field_key')} | {f.get('confidence')}% | "
                f"{'yes' if f.get('citation_verified') else 'no'} | "
                f"{int((f.get('source_support') or 0)*100)}% | {flags} |"
            )

        if r.get("suspicious"):
            lines.append("")
            lines.append("**Suspicious rows:**")
            for s in r["suspicious"]:
                lines.append(f"- {s}")
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit spec_check_fields")
    parser.add_argument("--input", required=True, help="Validation JSON file or directory")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", type=Path, help="Write markdown report")
    args = parser.parse_args()

    inp = Path(args.input).resolve()
    files: list[Path] = []
    if inp.is_dir():
        files = sorted(p for p in inp.glob("*.json") if p.name != "all_results.json")
        if args.limit:
            files = files[: args.limit]
    else:
        files = [inp]

    reports = []
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        reports.append(audit_validation_doc(doc, label=f.name))

    md = _render_markdown(reports)
    out = args.out or (BACKEND / "eval" / "out" / "field_audit_report.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")

    json_out = out.with_suffix(".json")
    json_out.write_text(json.dumps(reports, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(md)
    print(f"Wrote {out} and {json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
