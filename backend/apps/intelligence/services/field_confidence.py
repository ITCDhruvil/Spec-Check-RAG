"""
Per-field confidence scoring for spec_check_fields (Phase 5).

Produces a 0–100% confidence score on each summary block based on extraction
grounding signals — not a second LLM call.
"""

from __future__ import annotations

from typing import Any

from apps.intelligence.services.spec_check_fields_registry import (
    BOND_FIELD_KEYS,
    DEADLINE_FIELD_KEYS,
    FIELD_DEFS,
    SET_ASIDE_FIELD_KEYS,
)


def score_spec_field_confidence(
    *,
    extraction_confidence: float | None = None,
    citation_verified: bool | None = None,
    has_source_text: bool = False,
    is_calculated: bool = False,
    awaiting_project_value: bool = False,
    is_alias: bool = False,
) -> int:
    """
    Compute 0–100 confidence for one spec-check field row.

    extraction_confidence is 0.0–1.0 from the extraction item (LLM + grounding).
    """
    # Grounded confidence: document grounding is the PRIMARY signal, not the LLM's
    # self-reported number (LLMs are systematically overconfident). The verbatim
    # citation check (citation_verified) is ground truth — when a field's source_text
    # is found verbatim in the parsed PDF, the field is correct regardless of what the
    # LLM guessed. LLM confidence only modulates within each grounding tier.
    base = float(extraction_confidence if extraction_confidence is not None else 0.55)
    base = max(0.0, min(1.0, base))

    if citation_verified is True:
        # Verified verbatim in document → floor 90, LLM nudges within 90–100.
        score = 90.0 + base * 10.0
    elif has_source_text:
        # Has a source quote but not verified verbatim → uncertain band 30–55.
        score = 30.0 + base * 25.0
    else:
        # No source text at all → ungrounded, cap low.
        score = min(30.0, base * 30.0)

    if is_calculated:
        score = min(score, 72.0)
    if awaiting_project_value:
        score = min(score, 58.0)
    if is_alias:
        score = min(score, 95.0)

    return int(round(max(0.0, min(100.0, score))))


def _extraction_confidence(item: dict[str, Any]) -> float | None:
    """Return 0–1 extraction confidence; ignore already-scored 0–100 values."""
    raw = item.get("confidence")
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val > 1.0:
        return None
    return val


def infer_field_key_for_row(row: dict[str, Any], bucket: str) -> str | None:
    """Best-effort field_key for legacy rows missing it."""
    if row.get("field_key"):
        return str(row["field_key"])
    text = str(row.get("text") or "").strip()
    if bucket == "project_dates":
        return field_key_for_deadline_label(text)
    if bucket == "bond_items":
        return field_key_for_bond_label(text)
    if bucket == "set_aside_items":
        return field_key_for_set_aside_label(text)
    if ":" in text:
        label = text.split(":", 1)[0].strip()
        for fdef in FIELD_DEFS.values():
            if fdef.display_label == label:
                return fdef.name
    return None


def _confidence_from_source_item(item: dict[str, Any]) -> int:
    source = item if item.get("source_text") else {}
    verified = item.get("citation_verified")
    if verified is None and item.get("sources"):
        src0 = item["sources"][0]
        if isinstance(src0, dict):
            verified = src0.get("citation_verified")
    return score_spec_field_confidence(
        extraction_confidence=_extraction_confidence(item),
        citation_verified=verified,
        has_source_text=bool(
            item.get("source_text")
            or (item.get("sources") or [{}])[0].get("source_text")
        ),
        is_calculated=bool(item.get("_calculated")),
        awaiting_project_value=bool(item.get("_awaiting_project_value")),
        is_alias=bool(item.get("_alias_of")),
    )


def enrich_spec_check_field_entry(
    entry: dict[str, Any],
    *,
    field_key: str | None = None,
    source_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach field_key and confidence to a spec_check_fields row."""
    out = dict(entry)
    if field_key:
        out["field_key"] = field_key
    if source_item is not None:
        out["confidence"] = _confidence_from_source_item({**source_item, **out})
    elif "confidence" not in out:
        out["confidence"] = _confidence_from_source_item(out)
    # Inferred/calculated rows carry _parent_confidence_cap set by date rules.
    # The derived row must never exceed the parent it was calculated from.
    cap = out.get("_parent_confidence_cap")
    if isinstance(cap, int):
        out["confidence"] = min(out["confidence"], cap)
    return out


def apply_confidence_to_spec_check_fields(spec_check_fields: dict[str, Any]) -> dict[str, Any]:
    """Ensure every row in spec_check_fields has confidence (0–100)."""
    if not isinstance(spec_check_fields, dict):
        return spec_check_fields

    list_keys = (
        "project_metadata_items",
        "project_people_items",
        "project_size_location_items",
        "project_dates",
        "bond_items",
        "set_aside_items",
    )
    for bucket in list_keys:
        items = spec_check_fields.get(bucket)
        if not isinstance(items, list):
            continue
        enriched: list[dict[str, Any]] = []
        for row in items:
            if not isinstance(row, dict):
                continue
            fk = infer_field_key_for_row(row, bucket)
            enriched.append(enrich_spec_check_field_entry(row, field_key=fk))
        spec_check_fields[bucket] = enriched
    return spec_check_fields


def field_key_for_deadline_label(display_label: str) -> str | None:
    return DEADLINE_FIELD_KEYS.get(display_label)


def field_key_for_bond_label(display_label: str) -> str | None:
    return BOND_FIELD_KEYS.get(display_label)


def field_key_for_set_aside_label(display_label: str) -> str | None:
    return SET_ASIDE_FIELD_KEYS.get(display_label)


def all_registered_field_keys() -> set[str]:
    keys = set(FIELD_DEFS.keys())
    keys.update(DEADLINE_FIELD_KEYS.values())
    keys.update(BOND_FIELD_KEYS.values())
    return keys
