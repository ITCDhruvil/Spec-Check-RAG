from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_spec_fields(doc: dict[str, Any]) -> dict[str, Any] | None:
    data = doc.get("data") or {}
    summary = data.get("summary") or {}
    sj = summary.get("summary_json") or {}
    scf = sj.get("spec_check_fields")
    return scf if isinstance(scf, dict) else None


def _bid_deadlines_from_spec_fields(scf: dict[str, Any]) -> list[dict[str, Any]]:
    dates = scf.get("project_dates") or []
    if not isinstance(dates, list):
        return []
    out: list[dict[str, Any]] = []
    for item in dates:
        if not isinstance(item, dict):
            continue
        if str(item.get("text") or "").strip().lower() != "bid deadline":
            continue
        out.append(item)
    return out


def _first_source_snippet(item: dict[str, Any]) -> str:
    srcs = item.get("sources") or []
    if not isinstance(srcs, list) or not srcs:
        return ""
    s0 = srcs[0]
    if not isinstance(s0, dict):
        return ""
    page = s0.get("page")
    st = str(s0.get("source_text") or "").strip().replace("\n", " ")
    st = " ".join(st.split())
    if page is not None:
        return f"p{page}: {st[:160]}"
    return st[:160]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Bid deadline across validation_results")
    parser.add_argument("--input", required=True, help="validation_results directory")
    parser.add_argument("--out", required=True, help="output markdown path")
    args = parser.parse_args()

    in_dir = Path(args.input).resolve()
    out_path = Path(args.out).resolve()
    files = sorted([p for p in in_dir.glob("*.json") if p.name != "all_results.json"])

    lines: list[str] = []
    lines.append("# Bid deadline check")
    lines.append("")
    lines.append(f"- Input: `{in_dir}`")
    lines.append(f"- Files: **{len(files)}**")
    lines.append("")

    missing = 0
    multiple = 0

    for f in files:
        doc = _read_json(f)
        filename = str(doc.get("filename") or f.name)
        pipeline_status = str(doc.get("pipeline_status") or "")
        summary_status = str(doc.get("summary_status") or "")

        lines.append(f"## {filename}")

        if pipeline_status != "completed" or summary_status != "completed":
            lines.append(f"- Status: **not completed** (pipeline={pipeline_status}, summary={summary_status})")
            lines.append("")
            continue

        scf = _get_spec_fields(doc)
        if scf is None:
            lines.append("- Status: **missing spec_check_fields**")
            lines.append("")
            continue

        bids = _bid_deadlines_from_spec_fields(scf)
        if not bids:
            missing += 1
            lines.append("- Bid deadline: **MISSING**")
            lines.append("")
            continue

        if len(bids) > 1:
            multiple += 1
            lines.append(f"- Bid deadline: **MULTIPLE ({len(bids)})**")
        else:
            lines.append("- Bid deadline: **present**")

        for i, item in enumerate(bids[:3], start=1):
            date = str(item.get("date") or "").strip()
            snippet = _first_source_snippet(item)
            lines.append(f"  - [{i}] value: `{date}`")
            if snippet:
                lines.append(f"    - source: `{snippet}`")
            else:
                lines.append("    - source: (missing)")

        lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Missing bid deadline: **{missing}**")
    lines.append(f"- Multiple bid deadlines: **{multiple}**")
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

