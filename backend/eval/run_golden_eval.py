"""
Phase 7 golden-set eval runner.

Usage:
  cd backend
  python eval/run_golden_eval.py
  python eval/run_golden_eval.py --out eval/out/golden_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.ci" if os.environ.get("CI") else "config.settings.development",
)

import django

django.setup()

from eval.golden_eval import DEFAULT_MANIFEST, run_golden_eval


def _render_markdown(report: dict) -> str:
    lines = [
        "# Phase 7 golden-set eval report",
        "",
        f"- Manifest version: `{report.get('manifest_version')}`",
        f"- Result: **{'PASS' if report.get('passed') else 'FAIL'}**",
        "",
        "## Summary",
        "",
    ]
    summary = report.get("summary") or {}
    lines.append(f"- Documents: **{summary.get('documents_passed')}/{summary.get('documents_total')}** passed")
    lines.append(f"- Macro F1: **{summary.get('macro_f1')}**")
    lines.append(f"- Macro recall: **{summary.get('macro_recall')}**")
    lines.append(f"- Macro precision: **{summary.get('macro_precision')}**")

    if report.get("gate_issues"):
        lines.extend(["", "## Gate failures", ""])
        for issue in report["gate_issues"]:
            lines.append(f"- {issue}")

    lines.extend(["", "## Per-field metrics", ""])
    per_field = (report.get("metrics") or {}).get("per_field") or {}
    for fk, stats in per_field.items():
        lines.append(
            f"- `{fk}`: P={stats.get('precision')} R={stats.get('recall')} F1={stats.get('f1')} "
            f"(tp={stats.get('tp')} fp={stats.get('fp')} fn={stats.get('fn')})"
        )

    lines.extend(["", "## Documents", ""])
    for doc in report.get("documents") or []:
        status = "PASS" if doc.get("passed") else "FAIL"
        lines.append(f"### [{status}] {doc.get('document_id')}")
        lines.append(f"- rows={doc.get('row_count')} avg_conf={doc.get('avg_confidence')} warnings={doc.get('warnings_count')}")
        if doc.get("issues"):
            lines.append("- Issues:")
            for issue in doc["issues"][:8]:
                lines.append(f"  - {issue}")
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7 golden-set evaluation")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, help="Write JSON report")
    parser.add_argument("--md-out", type=Path, help="Write markdown report")
    args = parser.parse_args()

    report = run_golden_eval(args.manifest.resolve())
    print(json.dumps(report, indent=2))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {args.out}")

    md = _render_markdown(report)
    md_path = args.md_out or (BACKEND / "eval" / "out" / "golden_report.md")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md, encoding="utf-8")
    print(f"Wrote {md_path}")

    status = "PASS" if report.get("passed") else "FAIL"
    summary = report.get("summary") or {}
    print(
        f"\n[{status}] docs={summary.get('documents_passed')}/{summary.get('documents_total')} "
        f"macro_f1={summary.get('macro_f1')} macro_recall={summary.get('macro_recall')}"
    )
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
