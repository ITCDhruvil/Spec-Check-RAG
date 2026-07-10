from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SpecCheckBucket = Literal[
    "project_metadata_items",
    "project_people_items",
    "project_size_location_items",
    "project_dates",
    "bond_items",
    "set_aside_items",
]


@dataclass(frozen=True)
class SpecCheckFieldDef:
    """
    Canonical definition of a spec-check field.

    This registry is the single source of truth for:
    - which bucket a field belongs to
    - how it should be displayed (label casing / spacing)
    - which extraction labels map to it
    - value_hint documents expected value shape for extraction/UI
    """

    name: str
    bucket: SpecCheckBucket
    display_label: str
    value_hint: str = ""


# Canonical field definitions (extend here as new fields are added).
FIELD_DEFS: dict[str, SpecCheckFieldDef] = {
    # ── Project metadata ──────────────────────────────────────────────────
    "project_name": SpecCheckFieldDef("project_name", "project_metadata_items", "Project name"),
    "project_description": SpecCheckFieldDef(
        "project_description", "project_metadata_items", "Project description"
    ),
    "project_owner": SpecCheckFieldDef("project_owner", "project_metadata_items", "Project owner"),
    "project_sector": SpecCheckFieldDef("project_sector", "project_metadata_items", "Project sector"),
    "project_solicitation_number": SpecCheckFieldDef(
        "project_solicitation_number",
        "project_metadata_items",
        "Project solicitation number",
    ),
    "project_document_acquisition_note": SpecCheckFieldDef(
        "project_document_acquisition_note",
        "project_metadata_items",
        "Project document acquisition note",
    ),
    "project_value": SpecCheckFieldDef("project_value", "project_metadata_items", "Project value"),
    # ── People ────────────────────────────────────────────────────────────
    "project_engineer": SpecCheckFieldDef(
        "project_engineer",
        "project_people_items",
        "Project engineer",
        "Firm and/or individual (e.g. ABC Engineering LLC — Jane Doe)",
    ),
    "project_architect": SpecCheckFieldDef(
        "project_architect",
        "project_people_items",
        "Project architect",
        "Firm and/or individual (e.g. Smith Architects — John Smith)",
    ),
    # ── Size / location ───────────────────────────────────────────────────
    "project_square_footage": SpecCheckFieldDef(
        "project_square_footage",
        "project_size_location_items",
        "Project square footage",
    ),
    "project_location": SpecCheckFieldDef(
        "project_location", "project_size_location_items", "Project location"
    ),
}


# Submission-deadline label mapping (extraction item label -> display text)
DEADLINE_LABEL_DISPLAY: dict[str, str] = {
    "bid_deadline_date_time": "Bid deadline",
    "bid_open_date_time": "Bid open date",
    "project_start_date_time": "Project start date",
    "project_end_date_time": "Project end date",
    "pre_bid_deadline_date_time": "Pre-bid deadline",
    "site_visit_date_time": "Site visit",
    "question_deadline_date_time": "Question deadline",
    "municipal_meeting_date_time": "Award date",
}

# Display label -> stable field_key for confidence / UI
DEADLINE_FIELD_KEYS: dict[str, str] = {
    "Bid deadline": "bid_deadline_date_time",
    "Bid open date": "bid_open_date_time",
    "Project start date": "project_start_date_time",
    "Project end date": "project_end_date_time",
    "Pre-bid deadline": "pre_bid_deadline_date_time",
    "Site visit": "site_visit_date_time",
    "Question deadline": "question_deadline_date_time",
    "Award date": "municipal_meeting_date_time",
}


# Bond label mapping (extraction item label -> display text)
BOND_LABEL_DISPLAY: dict[str, str] = {
    "bid_bond_information": "Bid bond information",
    "payment_and_security_bond": "Performance & payment bond",
    "maintenance_and_labor_bond": "Maintenance & labor bond",
    "certified_checks": "Certified checks",
    "other_bonds": "Other bonds",
}

BOND_FIELD_KEYS: dict[str, str] = {
    "Bid bond information": "bid_bond_information",
    "Performance & payment bond": "payment_and_security_bond",
    "Maintenance & labor bond": "maintenance_and_labor_bond",
    "Certified checks": "certified_checks",
    "Other bonds": "other_bonds",
}

# Set-aside label mapping (extraction item label -> display text)
SET_ASIDE_LABEL_DISPLAY: dict[str, str] = {
    "set_aside_mbe": "MBE",
    "set_aside_wbe": "WBE",
    "set_aside_dbe": "DBE",
    "set_aside_dvbe": "DVBE",
    "set_aside_hub": "HUB",
    "set_aside_sbe": "SBE",
}

SET_ASIDE_FIELD_KEYS: dict[str, str] = {
    "MBE": "set_aside_mbe",
    "WBE": "set_aside_wbe",
    "DBE": "set_aside_dbe",
    "DVBE": "set_aside_dvbe",
    "HUB": "set_aside_hub",
    "SBE": "set_aside_sbe",
}

# Fields where only one row should survive post-processing (best citation wins).
SINGLETON_FIELD_KEYS: frozenset[str] = frozenset(
    {
        "project_name",
        "project_owner",
        "project_sector",
        "project_value",
        "project_engineer",
        "project_architect",
        "project_square_footage",
        "project_location",
        "project_description",
        "project_document_acquisition_note",
        "project_solicitation_number",
        "bid_deadline_date_time",
        "bid_open_date_time",
        "project_start_date_time",
        "project_end_date_time",
        "pre_bid_deadline_date_time",
        "site_visit_date_time",
        "question_deadline_date_time",
        "municipal_meeting_date_time",
    }
)

# Fields that may legitimately repeat (distinct values kept; exact dupes removed).
MULTI_VALUE_FIELD_KEYS: frozenset[str] = frozenset(
    {
        "bid_bond_information",
        "payment_and_security_bond",
        "maintenance_and_labor_bond",
        "certified_checks",
        "other_bonds",
        # Set asides — each program type is a distinct row
        "set_aside_mbe",
        "set_aside_wbe",
        "set_aside_dbe",
        "set_aside_dvbe",
        "set_aside_hub",
        "set_aside_sbe",
    }
)


def field_def(label: str) -> SpecCheckFieldDef | None:
    """Resolve an extraction label to a canonical field definition."""
    key = (label or "").strip().lower()
    if not key:
        return None
    return FIELD_DEFS.get(key)

