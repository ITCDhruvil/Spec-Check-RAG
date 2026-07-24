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
            "project_solicitation_number = ONE item per identifier found. Capture ALL of these when present: "
            "Project No./Project Number, Contract ID/Contract No., Control No./Control No. Seq. No., "
            "Call Order, Bid No., RFP/RFQ/IFB No., Solicitation No., File No., Job No. "
            "Prefer value format '<Label>: <code>' (e.g. 'Project No.: AFE-H051', 'Contract ID: 81162', "
            "'Control No. Seq. No.: 81162 000', 'Call Order: 800') so distinct IDs stay distinguishable. "
            "Never use the project title or the word 'null' as a solicitation number. "
            "project_document_acquisition_note = ONE short statement naming ONLY where to obtain the bid "
            "documents — nothing else. Examples: 'Download from BidNet.', 'Available on PlanetBids and at "
            "City Purchasing plan room.', 'Pickup at 123 Main St Purchasing Office.'. "
            "Name every source stated (portal AND plan room when both appear). "
            "Do NOT include URLs, fees, deposits, registration, hours, contacts, what is included, "
            "availability dates, or any other logistics — those belong only in "
            "project_document_acquisition_events. "
            "Do NOT use: addenda-posting URL, agency homepage, bid SUBMISSION address, or questions email. "
            "Omit if not explicitly stated. Never invent values."
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
            "Extract EVERY distinct project_location that describes where the actual work/site is, "
            "plus project_square_footage when stated. "
            "Capture ALL of these location types when present (one project_location item each): "
            "full street address; short address; city/town/village; county or multi-county list; "
            "district/region; road/highway/route/lane names (e.g. US-20, Highway 11, Main St); "
            "bridges / overpasses / interchanges; intersections and cross roads; "
            "point-to-point or corridor descriptions (e.g. 'from X to Y', mileposts, segments); "
            "facility/building/park/campus names; corridor or area of work (e.g. 'state highways "
            "throughout District 8'). "
            "Prefer the document's own wording. Do NOT invent locations. "
            "Do NOT use only the project title when a Location / In Counties / site line exists. "
            "Do NOT treat bid-opening offices, mail addresses, or procurement portals as work sites. "
            "NEVER extract technology platforms/systems (e.g. 'Azure environment') as a location. "
            "If many counties or road segments are listed, keep them as separate items or one "
            "item that preserves the full list exactly as written."
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
            "project_start_date_time: extract Tentative Start Date / Notice to Proceed / start date when stated. "
            "project_end_date_time: extract an explicit completion calendar date OR a contract duration such as "
            "'CONTRACT TIME: 102 Calendar Days', '180 calendar days', '12 months' — keep the duration text "
            "exactly (e.g. '102 Calendar Days'); post-process will compute the calendar end from start + duration. "
            "Omit project_end_date_time only when neither a completion date nor a contract duration appears. "
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
