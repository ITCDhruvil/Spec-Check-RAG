from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FieldIssue:
    level: str  # "error" | "warn" | "info"
    message: str


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_spec_fields(doc: dict[str, Any]) -> dict[str, Any] | None:
    data = doc.get("data") or {}
    summary = data.get("summary") or {}
    sj = summary.get("summary_json") or {}
    scf = sj.get("spec_check_fields")
    return scf if isinstance(scf, dict) else None


def _list_items(scf: dict[str, Any], key: str) -> list[dict[str, Any]]:
    v = scf.get(key)
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    return []


def _texts(items: list[dict[str, Any]]) -> list[str]:
    return [str(i.get("text") or "").strip() for i in items if str(i.get("text") or "").strip()]


def _count_sources(items: list[dict[str, Any]]) -> tuple[int, int]:
    total = 0
    verified = 0
    for i in items:
        srcs = i.get("sources") or []
        if not isinstance(srcs, list):
            continue
        for s in srcs:
            if not isinstance(s, dict):
                continue
            total += 1
            if s.get("citation_verified") is True:
                verified += 1
    return verified, total


def _has_date(items: list[dict[str, Any]], label: str) -> bool:
    label_norm = label.strip().lower()
    for i in items:
        if str(i.get("text") or "").strip().lower() == label_norm and str(i.get("date") or "").strip():
            return True
    return False


def analyze_validation_result(doc: dict[str, Any]) -> tuple[list[FieldIssue], dict[str, Any]]:
    """
    Produces:
    - issues: lightweight correctness flags
    - stats: counts per bucket + citation coverage
    """
    issues: list[FieldIssue] = []

    filename = str(doc.get("filename") or "")
    pipeline_status = str(doc.get("pipeline_status") or "")
    summary_status = str(doc.get("summary_status") or "")

    if pipeline_status != "completed" or summary_status != "completed":
        issues.append(FieldIssue("error", f"pipeline_status={pipeline_status} summary_status={summary_status}"))
        return issues, {"filename": filename, "status": "failed"}

    scf = _get_spec_fields(doc)
    if scf is None:
        issues.append(FieldIssue("error", "missing spec_check_fields"))
        return issues, {"filename": filename, "status": "missing_spec_fields"}

    meta = _list_items(scf, "project_metadata_items")
    people = _list_items(scf, "project_people_items")
    size_loc = _list_items(scf, "project_size_location_items")
    dates = _list_items(scf, "project_dates")
    bonds = _list_items(scf, "bond_items")

    # Basic presence checks (warn-level; some docs legitimately miss fields)
    if not meta:
        issues.append(FieldIssue("warn", "no project_metadata_items"))
    if not dates:
        issues.append(FieldIssue("warn", "no project_dates"))
    if not size_loc:
        issues.append(FieldIssue("warn", "no project_size_location_items"))

    # Specific field sanity
    meta_texts = _texts(meta)
    project_names = [t for t in meta_texts if t.lower().startswith("project name:")]
    solicitation_nos = [t for t in meta_texts if t.lower().startswith("project solicitation number:")]
    if len(project_names) > 1:
        issues.append(FieldIssue("warn", f"multiple project_name entries ({len(project_names)})"))
    if len(solicitation_nos) > 1:
        issues.append(FieldIssue("info", f"multiple solicitation numbers ({len(solicitation_nos)})"))

    # Dates that we generally expect for tenders
    if not _has_date(dates, "Bid deadline"):
        issues.append(FieldIssue("warn", "missing Bid deadline"))
    if not _has_date(dates, "Question deadline"):
        issues.append(FieldIssue("info", "missing Question deadline"))

    # Bonds: many tenders have at least bid security wording; track as warn
    if not bonds:
        issues.append(FieldIssue("warn", "no bond_items"))

    verified, total = _count_sources(meta + people + size_loc + dates + bonds)
    if total > 0 and verified / total < 0.9:
        issues.append(FieldIssue("warn", f"low citation_verified rate ({verified}/{total})"))

    stats = {
        "filename": filename,
        "counts": {
            "project_metadata_items": len(meta),
            "project_people_items": len(people),
            "project_size_location_items": len(size_loc),
            "project_dates": len(dates),
            "bond_items": len(bonds),
        },
        "citations": {"verified": verified, "total": total},
        "issues": [{"level": i.level, "message": i.message} for i in issues],
    }
    return issues, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Check spec_check_fields across validation_results JSONs")
    parser.add_argument("--input", required=True, help="validation_results directory")
    parser.add_argument("--out", required=True, help="output markdown path")
    args = parser.parse_args()

    in_dir = Path(args.input).resolve()
    out_path = Path(args.out).resolve()
    files = sorted([p for p in in_dir.glob("*.json") if p.name != "all_results.json"])

    rows: list[dict[str, Any]] = []
    for f in files:
        doc = _read_json(f)
        _issues, stats = analyze_validation_result(doc)
        rows.append(stats)

    # Render markdown (no tables to keep it readable)
    lines: list[str] = []
    lines.append("# Spec-check fields report")
    lines.append("")
    lines.append(f"- Input: `{in_dir}`")
    lines.append(f"- Files: **{len(rows)}**")
    lines.append("")

    for r in rows:
        fn = r.get("filename") or "?"
        lines.append(f"## {fn}")
        counts = r.get("counts") or {}
        cit = r.get("citations") or {}
        lines.append(
            "- Counts: "
            f"meta={counts.get('project_metadata_items', 0)}, "
            f"people={counts.get('project_people_items', 0)}, "
            f"size_loc={counts.get('project_size_location_items', 0)}, "
            f"dates={counts.get('project_dates', 0)}, "
            f"bonds={counts.get('bond_items', 0)}"
        )
        lines.append(f"- Citations verified: **{cit.get('verified', 0)}/{cit.get('total', 0)}**")
        issues = r.get("issues") or []
        if issues:
            lines.append("- Issues:")
            for i in issues:
                lines.append(f"  - **{i.get('level','info')}**: {i.get('message')}")
        else:
            lines.append("- Issues: none")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

