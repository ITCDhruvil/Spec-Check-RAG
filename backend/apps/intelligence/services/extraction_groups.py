"""
Prompt-based extraction groups — one LLM call per UI field group.

Each group maps to a legacy extraction_type so summary_postprocess.py
continues to build spec_check_fields without changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.intelligence.choices import ExtractionType


@dataclass(frozen=True)
class ExtractionGroup:
    group_id: str
    title: str
    extraction_type: str
    field_labels: tuple[str, ...]
    instructions: str


GROUP_EXTRACTION_GROUPS: tuple[ExtractionGroup, ...] = (
    ExtractionGroup(
        group_id="project_identity",
        title="Project identity & parties",
        extraction_type=ExtractionType.ELIGIBILITY_CRITERIA,
        field_labels=(
            "project_name",
            "project_owner",
            "project_engineer",
            "project_architect",
            "project_sector",
            "project_solicitation_number",
            "project_document_acquisition_note",
        ),
        instructions=(
            "Extract project identity and key parties from the FULL document. "
            "project_name = tender/project title from cover, notice, or bid schedule header. "
            "project_owner = issuing agency/owner entity. "
            "project_engineer / project_architect = firm or person as written. "
            "project_sector = Public or Private only when explicit. "
            "project_solicitation_number = each Bid No., RFP No., Project No., etc. (one item per ID). "
            "Never use the project title or the word 'null' as a solicitation number. "
            "project_document_acquisition_note = where to OBTAIN/COLLECT the bid documents themselves: "
            "a procurement portal or e-bidding platform (e.g. BidNet, DemandStar, Bonfire, PlanetBids), "
            "a download URL for the solicitation, or a physical office/plan room where documents are picked up. "
            "Priority: (1) named portal/platform, (2) document download URL, (3) pickup office address. "
            "Do NOT use: the addenda-posting URL, the agency's general homepage, the bid SUBMISSION address, "
            "or the questions/contact email — none of these are where documents are acquired. "
            "If the document only names a portal (e.g. 'uploaded to BidNet'), that portal IS the acquisition source. "
            "Omit any field not explicitly stated. Never invent values."
        ),
    ),
    ExtractionGroup(
        group_id="project_description",
        title="Project description",
        extraction_type=ExtractionType.SCOPE_OF_WORK,
        field_labels=("project_description",),
        instructions=(
            "Extract the FULL scope of work / project description verbatim from sections titled "
            "Scope of Work, Project Description, Description of Work, Work Summary, or similar. "
            "Copy text exactly — do not summarize. One project_description item with the complete text. "
            "Do NOT use only the project title — extract the full scope paragraph(s)."
        ),
    ),
    ExtractionGroup(
        group_id="project_value",
        title="Project value",
        extraction_type=ExtractionType.PAYMENT_TERMS,
        field_labels=("project_value",),
        instructions=(
            "Extract project_value when an estimated cost, budget, or contract value is stated. "
            "Keep exact wording including ranges (e.g. '$2M–$3M'). Omit if not stated."
        ),
    ),
    ExtractionGroup(
        group_id="location_and_size",
        title="Location & size",
        extraction_type=ExtractionType.TECHNICAL_REQUIREMENTS,
        field_labels=("project_location", "project_square_footage"),
        instructions=(
            "Extract project_location (most specific work site address or description) and "
            "project_square_footage when stated. Prefer full street addresses over bare city names. "
            "One project_location item per distinct work site. "
            "project_location must be a PHYSICAL PLACE where work is performed or delivered "
            "(address, building, city/county) — NEVER a technology platform, system, or "
            "environment name (e.g. 'Azure environment' is NOT a location). "
            "If only the issuing agency's city/county is stated (no explicit work site), you may "
            "return it but set confidence to 0.5 or lower so it is flagged for human review."
        ),
    ),
    ExtractionGroup(
        group_id="dates",
        title="Dates & deadlines",
        extraction_type=ExtractionType.SUBMISSION_DEADLINES,
        field_labels=(
            "bid_deadline_date_time",
            "bid_open_date_time",
            "pre_bid_deadline_date_time",
            "site_visit_date_time",
            "question_deadline_date_time",
            "municipal_meeting_date_time",
            "project_start_date_time",
            "project_end_date_time",
        ),
        instructions=(
            "Extract ALL submission and project milestone dates/times from the cover page, "
            "timeline table, schedule, or administrative section. "
            "Look for: Proposal Due Date, Bids Due, Proposer's Conference, Pre-bid meeting, "
            "Technical Questions Due, Site Visit, Bid Opening. "
            "Use EXACTLY these label values: bid_deadline_date_time, bid_open_date_time, "
            "pre_bid_deadline_date_time, site_visit_date_time, question_deadline_date_time, "
            "municipal_meeting_date_time, project_start_date_time, project_end_date_time. "
            "Set date_time to the full date+time from the document. "
            "Omit project_start_date_time and project_end_date_time unless an explicit calendar date "
            "or computable 'N days after award' phrase appears in the document. "
            "NEVER map issue/advertisement dates to bid_deadline_date_time — omit issue dates entirely. "
            "Bid due = when proposals must be submitted (later than issue date)."
        ),
    ),
    ExtractionGroup(
        group_id="bonds",
        title="Bonds & security",
        extraction_type=ExtractionType.PENALTIES_AND_RISKS,
        field_labels=(
            "bid_bond_information",
            "payment_and_security_bond",
            "maintenance_and_labor_bond",
            "certified_checks",
            "other_bonds",
        ),
        instructions=(
            "Extract ONLY bid/performance/payment bond and security deposit requirements. "
            "Labels: bid_bond_information, payment_and_security_bond, maintenance_and_labor_bond, "
            "certified_checks, other_bonds. Do NOT extract insurance, wage forms, or general penalties."
        ),
    ),
    ExtractionGroup(
        group_id="set_asides",
        title="Set-aside programs",
        extraction_type=ExtractionType.SET_ASIDES,
        field_labels=("set_aside",),
        instructions=(
            "Extract set-aside / diversity program requirements into the single label set_aside. "
            "One item per distinct program mentioned (MBE, WBE, DBE, DVBE, HUB, SBE, veteran-owned, etc.), "
            "value = program name plus its stated goal/percentage exactly as written "
            "(e.g. 'MBE: 10% participation goal'). "
            "Omit generic equal-opportunity statements without a specific program goal."
        ),
    ),
)


def group_by_extraction_type() -> dict[str, ExtractionGroup]:
    return {g.extraction_type: g for g in GROUP_EXTRACTION_GROUPS}
