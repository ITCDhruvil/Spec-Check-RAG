"""
Seeded keyword map for the Manual (keyword-search) feature.

One entry per spec-check field. Each field carries BOTH full phrases (so a
click jumps to the real heading, e.g. "Scope of Work") AND single-word
fallbacks (broad net). Derived from the SpecCheck Process Manual plus sensible
additions where the manual only listed fragments.

Users can override this set (add/remove) via UserAccountMeta.keyword_fields.
"""

from __future__ import annotations

# field id -> (display label, [keywords: full phrases first, then single words])
KEYWORD_FIELDS: list[dict] = [
    {
        "id": "description",
        "label": "Description / Scope of work",
        "keywords": [
            "Scope of Work", "Project Description", "Description of Work",
            "Statement of Work", "work includes", "work consists",
            "project consists", "project includes",
            "description", "scope", "work", "project",
        ],
    },
    {
        "id": "solicitation",
        "label": "Solicitation number",
        "keywords": [
            "Solicitation Number", "Contract Number", "Project Number",
            "Bid Number", "RFP No", "IFB No", "Project No", "Job Number",
            "solicitation", "contract", "number", "project", "bid no",
        ],
    },
    {
        "id": "value",
        "label": "Project value",
        "keywords": [
            "Estimated Cost", "Estimated Construction Cost", "Contract Value",
            "Engineer's Estimate", "Project Budget", "not to exceed",
            "$", "estimate", "value", "amount", "budget", "cost", "magnitude",
        ],
    },
    {
        "id": "location",
        "label": "Project location",
        "keywords": [
            "Project Location", "Site Location", "Location of Work",
            "Work Site", "Project Site", "located at", "located in",
            "site", "location", "county", "city", "address", "zip",
        ],
    },
    {
        "id": "sqft",
        "label": "Square footage",
        "keywords": [
            "Square Feet", "Square Footage", "sq. ft", "sq ft",
            "sqft", "footage", "square", "sf",
        ],
    },
    {
        "id": "set_asides",
        "label": "Set-asides / diversity goals",
        "keywords": [
            "Minority Business", "Women-Owned", "Disadvantaged Business",
            "Disabled Veteran", "Small Business", "participation goal",
            "MBE", "WBE", "DBE", "DVBE", "HUB", "SBE",
            "minority", "women", "disadvantaged", "veteran", "small business",
        ],
    },
    {
        "id": "bond",
        "label": "Bond / security",
        "keywords": [
            "Bid Bond", "Performance Bond", "Payment Bond",
            "Bid Security", "Bid Guaranty", "Proposal Guaranty",
            "Certified Check", "Surety",
            "bond", "security", "guaranty", "guarantee", "payment", "%",
        ],
    },
    {
        "id": "bid_date",
        "label": "Bid deadline / due date",
        "keywords": [
            "Bid Due Date", "Proposal Due Date", "Due Date", "Bids Due",
            "Letting Date", "Sealed Bids", "Submission Deadline",
            "tender", "due", "bid", "deadline", "closing",
        ],
    },
    {
        "id": "bids_open",
        "label": "Bid opening",
        "keywords": [
            "Bid Opening", "Publicly Opened", "Opening Date", "read aloud",
            "opened", "opening", "aloud", "publicly",
        ],
    },
    {
        "id": "pre_bid",
        "label": "Pre-bid meeting",
        "keywords": [
            "Pre-Bid Meeting", "Pre-Bid Conference", "Proposer's Conference",
            "Pre-Proposal", "Bidder Conference", "Mandatory",
            "pre-bid", "conference", "meeting", "mandatory", "proposal",
        ],
    },
    {
        "id": "site_walk",
        "label": "Site walkthrough / visit",
        "keywords": [
            "Site Visit", "Site Walk", "Walkthrough", "Walk-through",
            "Mandatory Site", "site visit", "walk", "walkthrough", "site",
        ],
    },
    {
        "id": "question_deadline",
        "label": "Question deadline",
        "keywords": [
            "Last Day for Questions", "Questions Due", "Technical Questions",
            "Deadline for Questions", "Inquiry Deadline",
            "questions", "inquiry", "clarification",
        ],
    },
    {
        "id": "award_date",
        "label": "Award date",
        "keywords": [
            "Notice of Award", "Intent to Award", "Award Date",
            "Contract Award", "Board Meeting", "Council Meeting",
            "award", "awarded", "posting",
        ],
    },
    {
        "id": "start_date",
        "label": "Project start date",
        "keywords": [
            "Notice to Proceed", "Commencement Date", "Start Date",
            "commence", "start", "proceed", "anticipated", "notice",
        ],
    },
    {
        "id": "end_date",
        "label": "Project end date / duration",
        "keywords": [
            "Substantial Completion", "Final Completion", "Calendar Days",
            "Contract Time", "Performance Period", "Liquidated Damages",
            "completion", "complete", "days", "period", "end", "duration",
        ],
    },
    {
        "id": "doc_acquisition",
        "label": "Document acquisition",
        "keywords": [
            "Bid Documents", "Proposal Documents", "Obtain Documents",
            "Plan Room", "Specifications", "download", "available",
            "document", "documents", "plan", "spec", "drawing", "copies",
        ],
    },
    {
        "id": "doc_cost",
        "label": "Document cost / deposit",
        "keywords": [
            "Refundable Deposit", "Non-Refundable", "Plan Deposit",
            "deposit", "refund", "refundable",
        ],
    },
    {
        "id": "engineer",
        "label": "Engineer",
        "keywords": [
            "Project Engineer", "City Engineer", "Professional Engineer",
            "Design Engineer", "P.E.", "Designed by", "Checked by",
            "engineer", "designed",
        ],
    },
    {
        "id": "architect",
        "label": "Architect",
        "keywords": [
            "Project Architect", "Architect of Record", "AIA", "Drawn by",
            "architect",
        ],
    },
    {
        "id": "owner",
        "label": "Owner / issuing agency",
        "keywords": [
            "Owner", "Issuing Agency", "Awarding Authority", "District",
            "County of", "City of", "Department of",
        ],
    },
    {
        "id": "roles",
        "label": "Roles / contacts",
        "keywords": [
            "Project Manager", "Contract Administrator", "Purchasing",
            "Procurement Officer", "Contact Person", "Consultant",
            "Representative", "manager", "consultant", "buyer", "contact",
        ],
    },
    {
        "id": "union",
        "label": "Union / prevailing wage",
        "keywords": [
            "Prevailing Wage", "Union", "Collective Bargaining",
            "Davis-Bacon", "bargaining", "wage",
        ],
    },
    {
        "id": "leed",
        "label": "LEED / sustainability",
        "keywords": ["LEED", "Sustainability", "Green Building", "certification"],
    },
]


def default_keyword_fields() -> list[dict]:
    """A deep copy of the seeded map (safe to mutate per user)."""
    return [
        {"id": f["id"], "label": f["label"], "keywords": list(f["keywords"])}
        for f in KEYWORD_FIELDS
    ]
