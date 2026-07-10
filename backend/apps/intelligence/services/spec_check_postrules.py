"""
Phase 6 post-rules for spec_check_fields.

Duplicate resolution, relative date typing, cardinality enforcement, and warnings.
"""

from __future__ import annotations

import re
from typing import Any

from apps.intelligence.services.field_confidence import infer_field_key_for_row
from apps.intelligence.services.spec_check_fields_registry import (
    FIELD_DEFS,
    MULTI_VALUE_FIELD_KEYS,
    SINGLETON_FIELD_KEYS,
)

METADATA_FIELD_ORDER = (
    "project_name",
    "project_solicitation_number",
    "project_owner",
    "project_sector",
    "project_value",
    "project_document_acquisition_note",
    "project_description",
)

_ACQUISITION_KEYWORDS = re.compile(
    r"\b("
    r"download|obtain|procurement\s+system|portal|website|http|https|"
    r"log\s*in|login|register|registration|contact|pick\s*up|pickup|"
    r"available\s+at|office\s+at|request\s+documents|view\s+this\s+solicitation|"
    r"follow\s+this\s+\d+|470"
    r")\b",
    re.IGNORECASE,
)

_PLACEHOLDER_DATE_PATTERN = re.compile(
    r"\b("
    r"pending\s+funding|pending\s+approval|tbd|to\s+be\s+determined|"
    r"not\s+specified|not\s+stated|upon\s+award|contingent|"
    r"\d+\s+(?:calendar\s+|working\s+|business\s+)?days?\s+after\s+award|"
    r"\d+\s+(?:calendar\s+|working\s+|business\s+)?days?\s+after\s+notice|"
    r"\d+\s+(?:calendar\s+|working\s+|business\s+)?days?\s+from\s+award|"
    r"\d+\s+(?:calendar\s+|working\s+|business\s+)?days?\s+from\s+notice"
    r")\b",
    re.IGNORECASE,
)

BUCKETS = (
    "project_metadata_items",
    "project_people_items",
    "project_size_location_items",
    "project_dates",
    "bond_items",
    "set_aside_items",
)

_DURATION_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:calendar\s+|working\s+|business\s+)?"
    r"(?:days?|weeks?|months?|years?)",
    re.IGNORECASE,
)


def _normalize_row_text(row: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", str(row.get("text") or "").strip().lower())


def _normalize_date_value(row: dict[str, Any]) -> str:
    raw = str(row.get("date") or "").strip().lower()
    raw = re.sub(r"\s+(cst|cdt|est|edt|mst|mdt|pst|pdt)\b", "", raw, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", raw)


def _source_verified(row: dict[str, Any]) -> bool:
    srcs = row.get("sources") or []
    if not isinstance(srcs, list):
        return False
    for src in srcs:
        if isinstance(src, dict) and src.get("citation_verified") is True:
            return True
    return row.get("citation_verified") is True


def _row_quality_key(row: dict[str, Any]) -> tuple[int, int, int, int]:
    """Higher is better for dedupe winner selection.

    Date-grounding (the date value literally present in its source_text) is the
    TOP signal — it beats raw LLM confidence, so a hallucinated/mis-attached date
    with high confidence never wins over a correctly grounded one.
    """
    conf = row.get("confidence")
    conf_score = int(conf) if isinstance(conf, int) else 0
    # _date_grounded is set on deadline rows; absent (None) for non-date rows so
    # they neither gain nor lose relative ordering among themselves.
    grounded = row.get("_date_grounded")
    grounded_score = 1 if grounded is True else (0 if grounded is False else 1)
    return (
        grounded_score,
        1 if _source_verified(row) else 0,
        conf_score,
        1 if (row.get("sources") or row.get("source_text")) else 0,
    )


def _is_duration_text(value: str) -> bool:
    if not value or _looks_like_calendar_date(value):
        return False
    return bool(_DURATION_PATTERN.search(value))


def _looks_like_calendar_date(value: str) -> bool:
    lower = value.lower()
    if re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", lower):
        return True
    if re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", lower):
        return True
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", lower):
        return True
    return False


def is_placeholder_date(value: str) -> bool:
    """True when a date field holds semantic placeholder text, not a calendar date."""
    raw = str(value or "").strip()
    if not raw:
        return True
    if _looks_like_calendar_date(raw):
        return False
    return bool(_PLACEHOLDER_DATE_PATTERN.search(raw))


def is_valid_acquisition_note(value: str) -> bool:
    """Acquisition notes must describe how/where to obtain documents."""
    v = str(value or "").strip()
    if not v:
        return False
    lower = v.lower()
    reject_phrases = (
        "not explicitly stated",
        "not found in",
        "not stated",
        "not specified",
        "no information",
        "n/a",
        "none stated",
    )
    if any(p in lower for p in reject_phrases):
        return False
    # Submission-only lines without obtain language
    if re.search(r"\b(offers?\s+must\s+be\s+received|clearly\s+labeled\s+in\s+the\s+subject)\b", lower):
        if not _ACQUISITION_KEYWORDS.search(v):
            return False
    return bool(_ACQUISITION_KEYWORDS.search(v))


def _row_display_value(row: dict[str, Any]) -> str:
    text = str(row.get("text") or "").strip()
    if ": " in text:
        return text.split(": ", 1)[1].strip()
    if row.get("date"):
        return str(row.get("date")).strip()
    return text


_STREET_NUMBER_RE = re.compile(r"\b\d{2,6}\b")
_STATE_ZIP_RE = re.compile(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b")
_BARE_CITY_RE = re.compile(r"^\s*(in\s+the\s+city\s+of|city\s+of)\b", re.IGNORECASE)


def _address_completeness_score(value: str) -> int:
    """Higher = more complete/specific location string.

    Signals: street number (+2), comma-separated parts (+1), state+ZIP (+1).
    A bare 'City of X' / 'In the City of X' with no other detail scores 0.
    """
    v = (value or "").strip()
    if not v:
        return 0
    if _BARE_CITY_RE.match(v) and "," not in v and not _STREET_NUMBER_RE.search(v):
        return 0
    score = 0
    if _STREET_NUMBER_RE.search(v):
        score += 2
    if "," in v:
        score += 1
    if _STATE_ZIP_RE.search(v):
        score += 1
    return score


def _is_bare_jurisdiction(value: str) -> bool:
    """True for a bare city/jurisdiction with no street or comma detail,
    e.g. 'IN THE CITY OF BELL GARDENS' or 'City of Republic'."""
    v = (value or "").strip()
    if not v:
        return False
    return bool(_BARE_CITY_RE.match(v)) and "," not in v and not _STREET_NUMBER_RE.search(v)


def _merge_rows_by_field_key(
    rows: list[dict[str, Any]],
    field_key: str,
    *,
    joiner: str = "; ",
    max_len: int = 4000,
    value_filter=None,
) -> list[dict[str, Any]]:
    """Collapse multiple rows with the same field_key into one merged row."""
    matching = [r for r in rows if str(r.get("field_key") or "") == field_key]
    if len(matching) <= 1:
        return rows
    others = [r for r in rows if str(r.get("field_key") or "") != field_key]
    winner = max(matching, key=_row_quality_key)
    fdef = FIELD_DEFS.get(field_key)
    label = fdef.display_label if fdef else field_key.replace("_", " ").title()

    values: list[str] = []
    seen: set[str] = set()
    for row in matching:
        val = _row_display_value(row)
        if value_filter and not value_filter(val):
            continue
        norm = re.sub(r"\s+", " ", val.lower()).strip()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        values.append(val.strip())

    if not values:
        return others

    merged_text = joiner.join(values)[:max_len]
    merged = dict(winner)
    merged["text"] = f"{label}: {merged_text}"
    merged["field_key"] = field_key
    return others + [merged]


def _get_project_name(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        if str(row.get("field_key") or "") == "project_name":
            return _row_display_value(row)
    return ""


def _normalize_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").strip().lower()).strip()


def _is_valid_project_description(value: str, project_name: str) -> bool:
    """Reject title-only or duplicate-of-name descriptions."""
    val = (value or "").strip()
    if not val or len(val) < 80:
        return False
    name_norm = _normalize_title(project_name)
    val_norm = _normalize_title(val)
    if name_norm and (val_norm == name_norm or val_norm in name_norm or name_norm in val_norm):
        return False
    # Real scope text usually has multiple sentences or many words.
    words = val.split()
    if len(words) < 15 and "." not in val and ";" not in val:
        return False
    return True


def filter_invalid_metadata_rows(spec_check_fields: dict[str, Any]) -> None:
    items = spec_check_fields.get("project_metadata_items") or []
    if not isinstance(items, list):
        return
    project_name = _get_project_name(items)
    kept: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        fk = str(row.get("field_key") or "")
        if fk == "project_document_acquisition_note":
            if is_valid_acquisition_note(_row_display_value(row)):
                kept.append(row)
            continue
        if fk == "project_description":
            val = _row_display_value(row)
            if _is_valid_project_description(val, project_name):
                kept.append(row)
            continue
        if fk == "project_sector":
            # Only keep sector when citation is verified in source.
            if _source_verified(row):
                kept.append(row)
            continue
        if fk == "project_solicitation_number":
            if _is_solicitation_number(_row_display_value(row)):
                kept.append(row)
            continue
        kept.append(row)
    spec_check_fields["project_metadata_items"] = kept


_SOLICITATION_NUMBER_PATTERN = re.compile(
    r"\b[A-Z0-9][-A-Z0-9]{3,}\b",  # at least 4-char alphanumeric code
    re.IGNORECASE,
)


def _is_solicitation_number(val: str) -> bool:
    """Accept only values that contain an actual reference code, not prose labels."""
    v = val.strip()
    if not v:
        return False
    lower = v.lower()
    if lower in {"null", "none", "n/a", "na", "not stated", "not specified", "tbd"}:
        return False
    # Must contain a digit or a known procurement ID prefix (RFP, CIP, etc.)
    if not re.search(r"\d", v) and not re.search(
        r"\b(RFP|RFQ|IFB|CIP|ITB|RFS|NO\.|#)\b", v, re.IGNORECASE
    ):
        return False
    if not _SOLICITATION_NUMBER_PATTERN.search(v):
        return False
    reject_phrases = (
        "reference no. of document",
        "document being continued",
        "continuation sheet",
        "purchase request number",
        "requisition",
        "advertisement #",
        "advertisement#",
    )
    return not any(p in lower for p in reject_phrases)


def _merge_location_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge project_location rows: prefer the most complete value, drop any
    candidate that is a subset of a more-complete kept value, keep distinct sites.
    """
    matching = [r for r in rows if str(r.get("field_key") or "") == "project_location"]
    if len(matching) <= 1:
        return rows
    others = [r for r in rows if str(r.get("field_key") or "") != "project_location"]

    # Rank candidates: most complete first; tie broken by existing quality key.
    ranked = sorted(
        matching,
        key=lambda r: (
            _address_completeness_score(_row_display_value(r)),
            _row_quality_key(r),
        ),
        reverse=True,
    )

    kept_values: list[str] = []
    for row in ranked:
        val = _row_display_value(row).strip()
        if not val:
            continue
        norm = re.sub(r"\s+", " ", val.lower())
        # Drop if this value is a literal subset of an already-kept value.
        if any(norm in re.sub(r"\s+", " ", k.lower()) for k in kept_values):
            continue
        # Drop a bare city/jurisdiction once ANY more-specific location is kept —
        # a road segment or building name (score 0 but NOT a bare jurisdiction) is
        # a distinct site and must be kept.
        if _is_bare_jurisdiction(val) and kept_values:
            continue
        kept_values.append(val)

    if not kept_values:
        return others

    winner = ranked[0]
    fdef = FIELD_DEFS.get("project_location")
    label = fdef.display_label if fdef else "Project location"
    merged = dict(winner)
    merged["text"] = f"{label}: {'; '.join(kept_values)}"
    merged["field_key"] = "project_location"
    return others + [merged]


def merge_spec_check_multi_fields(spec_check_fields: dict[str, Any]) -> None:
    """Merge multi-row spec fields into single canonical rows."""
    meta = spec_check_fields.get("project_metadata_items") or []
    if isinstance(meta, list):
        meta = _merge_rows_by_field_key(
            meta, "project_solicitation_number", joiner="; ",
            value_filter=_is_solicitation_number,
        )
        meta = _merge_rows_by_field_key(
            meta,
            "project_document_acquisition_note",
            joiner=" • ",
            value_filter=is_valid_acquisition_note,
        )
        _desc_count = sum(1 for r in meta if str(r.get("field_key") or "") == "project_description")
        meta = _merge_rows_by_field_key(
            meta,
            "project_description",
            joiner="\n\n",
            max_len=20000,
        )
        for row in meta:
            if str(row.get("field_key") or "") == "project_description":
                val = _row_display_value(row)
                row["_scope_chunk_count"] = _desc_count
                row["_scope_truncated"] = len(val) >= 20000
                break
        spec_check_fields["project_metadata_items"] = meta

    size = spec_check_fields.get("project_size_location_items") or []
    if isinstance(size, list):
        spec_check_fields["project_size_location_items"] = _merge_location_rows(size)


def sort_metadata_items(spec_check_fields: dict[str, Any]) -> None:
    items = spec_check_fields.get("project_metadata_items") or []
    if not isinstance(items, list):
        return

    def sort_key(row: dict[str, Any]) -> tuple[int, str]:
        fk = str(row.get("field_key") or "")
        try:
            idx = METADATA_FIELD_ORDER.index(fk)
        except ValueError:
            idx = len(METADATA_FIELD_ORDER)
        return (idx, fk)

    spec_check_fields["project_metadata_items"] = sorted(items, key=sort_key)


def tag_date_kinds(spec_check_fields: dict[str, Any]) -> None:
    """Tag each project_dates row with _date_kind: absolute | duration | estimated."""
    dates = spec_check_fields.get("project_dates") or []
    if not isinstance(dates, list):
        return
    for row in dates:
        if not isinstance(row, dict):
            continue
        if row.get("_calculated"):
            row["_date_kind"] = "estimated"
        elif is_placeholder_date(str(row.get("date") or "")):
            row["_date_kind"] = "non_specific"
        elif _is_duration_text(str(row.get("date") or "")):
            row["_date_kind"] = "duration"
        else:
            row["_date_kind"] = "absolute"


def _dedupe_bucket(
    rows: list[dict[str, Any]],
    bucket: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (kept_rows, warnings)."""
    warnings: list[dict[str, Any]] = []
    if not rows:
        return [], warnings

    keyed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        fk = infer_field_key_for_row(row, bucket) or ""
        if fk and not row.get("field_key"):
            row["field_key"] = fk
        keyed.append(row)

    kept: list[dict[str, Any]] = []
    singleton_groups: dict[str, list[dict[str, Any]]] = {}
    multi_rows: list[dict[str, Any]] = []

    for row in keyed:
        fk = str(row.get("field_key") or "")
        if fk in SINGLETON_FIELD_KEYS:
            singleton_groups.setdefault(fk, []).append(row)
        else:
            multi_rows.append(row)

    for fk, group in singleton_groups.items():
        winner = max(group, key=_row_quality_key)
        kept.append(winner)
        if len(group) <= 1:
            continue
        dropped = len(group) - 1
        if bucket == "project_dates":
            values = {_normalize_date_value(r) for r in group}
        else:
            values = {_normalize_row_text(r) for r in group}
        level = "warn" if len(values) > 1 else "info"
        warnings.append(
            {
                "field_key": fk,
                "bucket": bucket,
                "level": level,
                "message": (
                    f"Resolved {dropped} duplicate '{fk}' row(s); kept best citation."
                    if level == "info"
                    else f"Conflicting '{fk}' values ({len(values)} distinct); kept best citation."
                ),
                "dropped_count": dropped,
            }
        )

    exact_best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in multi_rows:
        fk = str(row.get("field_key") or "")
        primary = (
            _normalize_date_value(row)
            if bucket == "project_dates"
            else _normalize_row_text(row)
        )
        key = (fk, primary)
        prior = exact_best.get(key)
        if prior is None or _row_quality_key(row) > _row_quality_key(prior):
            exact_best[key] = row

    kept.extend(exact_best.values())
    return kept, warnings


def dedupe_spec_check_fields(spec_check_fields: dict[str, Any]) -> list[dict[str, Any]]:
    """Remove duplicate rows; enforce singleton cardinality. Returns warnings."""
    all_warnings: list[dict[str, Any]] = []
    for bucket in BUCKETS:
        items = spec_check_fields.get(bucket)
        if not isinstance(items, list):
            continue
        kept, warnings = _dedupe_bucket(items, bucket)
        spec_check_fields[bucket] = kept
        all_warnings.extend(warnings)
    return all_warnings


def build_field_warnings(spec_check_fields: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect post-rule warnings including low-confidence singleton gaps."""
    warnings: list[dict[str, Any]] = []

    for bucket in BUCKETS:
        for row in spec_check_fields.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            fk = row.get("field_key") or ""
            conf = row.get("confidence")
            if isinstance(conf, int) and conf < 50:
                warnings.append(
                    {
                        "field_key": fk,
                        "bucket": bucket,
                        "level": "warn",
                        "message": f"Low confidence ({conf}%) on '{row.get('text') or fk}'.",
                    }
                )
            if row.get("_awaiting_project_value"):
                warnings.append(
                    {
                        "field_key": fk or "project_start_date_time",
                        "bucket": bucket,
                        "level": "info",
                        "message": "Project start date uses default 30-day offset; project value not found.",
                    }
                )

    # Required tender dates
    date_keys = {
        str(r.get("field_key") or "")
        for r in (spec_check_fields.get("project_dates") or [])
        if isinstance(r, dict)
    }
    if "bid_deadline_date_time" not in date_keys:
        warnings.append(
            {
                "field_key": "bid_deadline_date_time",
                "bucket": "project_dates",
                "level": "warn",
                "message": "Bid deadline not found in document.",
            }
        )

    return warnings


def apply_spec_check_postrules(spec_check_fields: dict[str, Any]) -> list[dict[str, Any]]:
    """Run merge/filter, dedupe, and date kind tagging. Returns dedupe warnings."""
    filter_invalid_metadata_rows(spec_check_fields)
    merge_spec_check_multi_fields(spec_check_fields)
    sort_metadata_items(spec_check_fields)
    tag_date_kinds(spec_check_fields)
    return dedupe_spec_check_fields(spec_check_fields)


def _merge_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    merged: list[dict[str, Any]] = []
    for w in warnings:
        key = (w.get("bucket", ""), w.get("field_key", ""), w.get("message", ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(w)
    return merged
