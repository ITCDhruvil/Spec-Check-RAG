import re
from typing import Any

from apps.intelligence.choices import ExtractionType
from apps.intelligence.services.citation_service import canonicalize_extraction_item


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


# Canonical mapping: LLM-invented label → allowed spec-check label.
# Catches any label variant the model might produce regardless of prompt wording.
# Source of truth: spec_check_fields_registry DEADLINE_LABEL_DISPLAY keys +
# BOND_LABEL_DISPLAY keys + FIELD_DEFS keys.
_LABEL_ALIASES: dict[str, str] = {
    # Submission-deadline variants
    "site_visit": "site_visit_date_time",
    "site_walkthrough_date_time": "site_visit_date_time",
    "mandatory_site_visit_date_time": "site_visit_date_time",
    "pre_bid_conference_date_time": "pre_bid_deadline_date_time",
    "pre_bid_meeting_date_time": "pre_bid_deadline_date_time",
    "proposer_conference_date_time": "pre_bid_deadline_date_time",
    "prebid_conference_date_time": "pre_bid_deadline_date_time",
    "rfq_due_date_time": "bid_deadline_date_time",
    "proposal_deadline_date_time": "bid_deadline_date_time",
    "submission_deadline_date_time": "bid_deadline_date_time",
    "bid_due_date_time": "bid_deadline_date_time",
    "quote_deadline_date_time": "bid_deadline_date_time",
    "rfp_closing_date_time": "bid_deadline_date_time",
    "advertisement_date_time": "bid_open_date_time",
    "issue_date_time": "bid_open_date_time",
    "rfp_issue_date_time": "bid_open_date_time",
    "rfp_release_date_time": "bid_open_date_time",
    "rfi_deadline_date_time": "question_deadline_date_time",
    "questions_due_date_time": "question_deadline_date_time",
    "inquiry_deadline_date_time": "question_deadline_date_time",
    "award_date_time": "municipal_meeting_date_time",
    "board_meeting_date_time": "municipal_meeting_date_time",
    "council_meeting_date_time": "municipal_meeting_date_time",
    "delivery_date_time": "project_end_date_time",
    "completion_date_time": "project_end_date_time",
    "substantial_completion_date_time": "project_end_date_time",
    "contract_end_date_time": "project_end_date_time",
    "contract_start_date_time": "project_start_date_time",
    "notice_to_proceed_date_time": "project_start_date_time",
    # Bond variants
    "bid_bond": "bid_bond_information",
    "bid_guarantee": "bid_bond_information",
    "bid_security": "bid_bond_information",
    "performance_bond": "payment_and_security_bond",
    "performance_and_payment_bond": "payment_and_security_bond",
    "payment_bond": "payment_and_security_bond",
    "surety_bond": "payment_and_security_bond",
    "maintenance_bond": "maintenance_and_labor_bond",
    "warranty_bond": "maintenance_and_labor_bond",
    "maintenance_and_warranty_bond": "maintenance_and_labor_bond",
    "labor_bond": "maintenance_and_labor_bond",
    "cashiers_check": "certified_checks",
    "cashier_check": "certified_checks",
    "money_order": "certified_checks",
}


def normalize_extraction_label(label: str) -> str:
    """Map any LLM-invented label to the nearest canonical allowed label.

    Returns the original label unchanged when no alias exists, letting downstream
    field assembly drop unknowns via field_def() lookup as before.
    """
    if not label:
        return label
    key = label.strip().lower().replace(" ", "_").replace("-", "_")
    return _LABEL_ALIASES.get(key, label)


def validate_and_score_items(
    items: list[dict[str, Any]],
    *,
    chunk_text: str,
    section_title: str,
    page_start: int,
    page_end: int,
    total_pages: int,
    page_texts: list[tuple[int, str]] | None = None,
) -> list[dict[str, Any]]:
    """Grounding validation with canonical page/section resolution."""
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    pages = page_texts or []

    for raw in items:
        if not isinstance(raw, dict):
            continue

        requirement = str(raw.get("requirement") or "").strip()
        if not requirement:
            # LLMs often return label/value without requirement; synthesize so
            # grounded items are not silently dropped.
            label = str(raw.get("label") or "").strip()
            value = str(
                raw.get("value") or raw.get("date_time") or ""
            ).strip()
            if label and value:
                requirement = f"{label}: {value}"
                raw = dict(raw)
                raw["requirement"] = requirement
            else:
                continue

        dedupe_key = _normalize(requirement)[:200]
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        # Normalize label before canonicalization so citation lookup uses correct field.
        if raw.get("label"):
            raw = dict(raw)
            raw["label"] = normalize_extraction_label(str(raw["label"]))

        item = canonicalize_extraction_item(
            raw,
            chunk_text=chunk_text,
            section_title=section_title,
            page_start=page_start,
            page_end=page_end,
            total_pages=total_pages,
            page_texts=pages,
        )
        if item.get("requirement"):
            validated.append(item)

    return validated


def aggregate_confidence(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    return round(sum(i["confidence"] for i in items) / len(items), 4)


def detect_missing_extractions(present_types: set[str]) -> list[str]:
    """
    Return extraction types that are expected but not present.

    Note: in spec-check mode we intentionally skip some focused extraction passes
    (e.g. evaluation_criteria), so they should not be reported as "missing".
    """
    from django.conf import settings
    from apps.intelligence.choices import FOCUSED_EXTRACTION_TYPES

    prompt_version = str(getattr(settings, "INTELLIGENCE_PROMPT_VERSION", "") or "")
    is_spec_check = prompt_version.lower().startswith("spec-check")

    expected = list(FOCUSED_EXTRACTION_TYPES)
    if is_spec_check:
        expected = [t for t in expected if t not in (ExtractionType.EVALUATION_CRITERIA,)]

    missing: list[str] = []
    for ext_type in expected:
        if ext_type not in present_types:
            missing.append(ext_type)
    return missing


def merge_insight_items(all_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate across chunks for same extraction type."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for item in all_items:
        key = _normalize(item.get("requirement", ""))[:200]
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged
