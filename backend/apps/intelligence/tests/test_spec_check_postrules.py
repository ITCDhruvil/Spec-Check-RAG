"""Phase 6 post-rules tests."""

from django.test import override_settings

from apps.intelligence.services.spec_check_postrules import (
    _address_completeness_score,
    apply_spec_check_postrules,
    build_field_warnings,
    is_placeholder_date,
    is_valid_acquisition_note,
    merge_spec_check_multi_fields,
    tag_date_kinds,
)
from apps.intelligence.services.summary_postprocess import (
    _parse_date_string,
    finalize_spec_check_fields,
    rebind_spec_check_sources_from_extractions,
)


class _FakeInsight:
    def __init__(self, extraction_type: str, items: list):
        self.extraction_type = extraction_type
        self.payload = {"items": items}


def test_parse_date_string_cst_est_military():
    from datetime import datetime

    assert _parse_date_string("March 4, 2026 at 1:00 PM CST") == datetime(2026, 3, 4, 13, 0)
    assert _parse_date_string("February 26, 2026 at 12:00 PM EST") == datetime(2026, 2, 26, 12, 0)
    assert _parse_date_string("February 20, 2026, 1:00 PM CST") == datetime(2026, 2, 20, 13, 0)
    assert _parse_date_string("03/04/2026 1300") == datetime(2026, 3, 4, 13, 0)


def test_dedupe_singleton_pre_bid_deadline():
    spec = {
        "project_dates": [
            {
                "text": "Pre-bid deadline",
                "date": "Feb 20, 2026 1:00 PM",
                "field_key": "pre_bid_deadline_date_time",
                "sources": [{"citation_verified": False}],
            },
            {
                "text": "Pre-bid deadline",
                "date": "February 20, 2026 at 1:00 PM CST",
                "field_key": "pre_bid_deadline_date_time",
                "sources": [{"citation_verified": True, "source_text": "Site Visit Friday Feb 20"}],
            },
        ]
    }
    warnings = apply_spec_check_postrules(spec)
    assert len(spec["project_dates"]) == 1
    assert spec["project_dates"][0]["sources"][0]["citation_verified"] is True
    assert any("pre_bid_deadline" in w.get("field_key", "") for w in warnings)


def test_tag_date_kinds():
    spec = {
        "project_dates": [
            {"text": "Bid deadline", "date": "March 1, 2026"},
            {"text": "Project end date", "date": "180 calendar days"},
            {"text": "Project start date", "date": "April 1, 2026", "_calculated": True},
        ]
    }
    tag_date_kinds(spec)
    kinds = {d["text"]: d["_date_kind"] for d in spec["project_dates"]}
    assert kinds["Bid deadline"] == "absolute"
    assert kinds["Project end date"] == "duration"
    assert kinds["Project start date"] == "estimated"


def test_start_date_calculated_with_cst_bid_open():
    spec = {
        "project_dates": [
            {"text": "Bid open date", "date": "March 4, 2026 at 1:00 PM CST"},
        ],
        "project_metadata_items": [],
    }
    with override_settings(INTELLIGENCE_INFER_PROJECT_DATES=True):
        finalize_spec_check_fields(spec)
    start = next(d for d in spec["project_dates"] if d["text"] == "Project start date")
    assert start.get("_calculated") is True
    assert "April" in start["date"]
    assert start["date"] != "March 4, 2026 at 1:00 PM CST"


def test_build_field_warnings_missing_bid_deadline():
    spec = {"project_dates": [], "project_metadata_items": []}
    warnings = build_field_warnings(spec)
    assert any(w.get("field_key") == "bid_deadline_date_time" for w in warnings)


def test_is_placeholder_date():
    assert is_placeholder_date("PENDING FUNDING APPROVAL")
    assert is_placeholder_date("TBD")
    assert not is_placeholder_date("March 6, 2026 at 2:00 PM")


def test_acquisition_note_filter():
    assert not is_valid_acquisition_note("Not explicitly stated in the document")
    assert not is_valid_acquisition_note(
        "Offers must be clearly labeled in the subject line of the email"
    )
    assert is_valid_acquisition_note(
        "Download bid documents at https://portal.example.com/procurement"
    )


def test_merge_solicitation_numbers():
    spec = {
        "project_metadata_items": [
            {
                "text": "Project solicitation number: RFP-001",
                "field_key": "project_solicitation_number",
                "sources": [],
            },
            {
                "text": "Project solicitation number: Form 470 #12345",
                "field_key": "project_solicitation_number",
                "sources": [{"citation_verified": True}],
            },
        ],
        "project_dates": [],
    }
    apply_spec_check_postrules(spec)
    assert len(spec["project_metadata_items"]) == 1
    merged = spec["project_metadata_items"][0]["text"]
    assert "RFP-001" in merged
    assert "470" in merged


def test_placeholder_start_date_replaced_with_calculated():
    spec = {
        "project_dates": [
            {
                "text": "Project start date",
                "date": "PENDING FUNDING APPROVAL",
                "field_key": "project_start_date_time",
            },
            {
                "text": "Bid open date",
                "date": "March 4, 2026 at 1:00 PM CST",
                "field_key": "bid_open_date_time",
            },
        ],
        "project_metadata_items": [],
    }
    with override_settings(INTELLIGENCE_INFER_PROJECT_DATES=True):
        finalize_spec_check_fields(spec)
    start = next(d for d in spec["project_dates"] if d["text"] == "Project start date")
    assert "PENDING" not in start["date"].upper()
    assert start.get("_calculated") is True


def test_rebind_bid_deadline_citation_from_extraction():
    insights = [
        _FakeInsight(
            "submission_deadlines",
            [
                {
                    "label": "bid_deadline_date_time",
                    "source_text": "Proposals Deadline | March 6, 2026 @ 2:00 P.M.",
                    "page": 2,
                    "citation_verified": True,
                    "confidence": 0.9,
                },
                {
                    "label": "question_deadline_date_time",
                    "source_text": "Requests for Information Deadline | February 20, 2026",
                    "page": 2,
                    "confidence": 0.8,
                },
            ],
        )
    ]
    spec = {
        "project_dates": [
            {
                "text": "Bid deadline",
                "date": "March 6, 2026 at 2:00 PM",
                "field_key": "bid_deadline_date_time",
                "sources": [
                    {
                        "source_text": "Requests for Information Deadline | February 20, 2026",
                        "page": 2,
                    }
                ],
            },
        ],
    }
    rebind_spec_check_sources_from_extractions(spec, insights)
    source_text = spec["project_dates"][0]["sources"][0]["source_text"]
    assert "Proposals" in source_text
    assert "RFI" not in source_text and "Information" not in source_text


def test_address_completeness_score_ranks_full_address_highest():
    full = _address_completeness_score(
        "John Anson Ford Park, 8000 Park Lane, Bell Gardens, CA 90201"
    )
    facility_street = _address_completeness_score(
        "5242 South State Hwy ZZ, Republic, MO"
    )
    bare_city = _address_completeness_score("IN THE CITY OF BELL GARDENS")
    building_only = _address_completeness_score("Ford Park East Playground")

    assert full > facility_street > bare_city
    assert bare_city == 0
    assert building_only >= 0
    assert full > building_only


def test_location_merge_prefers_full_address_and_drops_bare_city():
    spec = {
        "project_size_location_items": [
            {
                "text": "Project location: IN THE CITY OF BELL GARDENS",
                "field_key": "project_location",
                "confidence": 95,
                "sources": [{"citation_verified": True}],
            },
            {
                "text": (
                    "Project location: John Anson Ford Park, 8000 Park Lane, "
                    "Bell Gardens, CA 90201"
                ),
                "field_key": "project_location",
                "confidence": 80,
                "sources": [{"citation_verified": True}],
            },
        ]
    }
    merge_spec_check_multi_fields(spec)
    rows = spec["project_size_location_items"]
    assert len(rows) == 1
    value = rows[0]["text"].split(": ", 1)[1]
    assert "8000 Park Lane" in value
    assert "Bell Gardens, CA 90201" in value
    # bare-city row dropped as a subset of the full address
    assert value.upper().count("CITY OF") == 0


def test_location_merge_keeps_distinct_sites():
    spec = {
        "project_size_location_items": [
            {
                "text": "Project location: 100 Oak Street, Springfield, IL 62701",
                "field_key": "project_location",
                "confidence": 90,
                "sources": [{"citation_verified": True}],
            },
            {
                "text": "Project location: 200 Elm Avenue, Springfield, IL 62702",
                "field_key": "project_location",
                "confidence": 90,
                "sources": [{"citation_verified": True}],
            },
        ]
    }
    merge_spec_check_multi_fields(spec)
    rows = spec["project_size_location_items"]
    assert len(rows) == 1  # single merged row
    value = rows[0]["text"].split(": ", 1)[1]
    assert "100 Oak Street" in value
    assert "200 Elm Avenue" in value  # both distinct sites kept


def test_rejects_null_solicitation_and_title_as_description():
    spec = {
        "project_metadata_items": [
            {
                "text": "Project name: HOMEWOOD SCHOOLS RENOVATIONS",
                "field_key": "project_name",
                "sources": [{"citation_verified": True}],
            },
            {
                "text": "Project solicitation number: null",
                "field_key": "project_solicitation_number",
                "sources": [],
            },
            {
                "text": "Project solicitation number: ABHM250064",
                "field_key": "project_solicitation_number",
                "sources": [{"citation_verified": True}],
            },
            {
                "text": "Project description: HOMEWOOD SCHOOLS RENOVATIONS",
                "field_key": "project_description",
                "sources": [],
            },
            {
                "text": "Project sector: Public",
                "field_key": "project_sector",
                "sources": [],
            },
        ],
        "project_dates": [],
    }
    apply_spec_check_postrules(spec)
    meta = spec["project_metadata_items"]
    keys = {str(r.get("field_key")) for r in meta}
    assert "project_solicitation_number" in keys
    assert "project_description" not in keys
    assert "project_sector" not in keys
    sol = next(r for r in meta if r["field_key"] == "project_solicitation_number")
    assert "ABHM250064" in sol["text"]
    assert "null" not in sol["text"].lower()


def test_accuracy_mode_drops_inferred_start_date():
    spec = {
        "project_dates": [
            {
                "text": "Bid open date",
                "date": "March 4, 2026 at 1:00 PM CST",
                "field_key": "bid_open_date_time",
            },
        ],
        "project_metadata_items": [],
    }
    with override_settings(INTELLIGENCE_INFER_PROJECT_DATES=False):
        finalize_spec_check_fields(spec)
    assert not any(
        str(d.get("field_key")) == "project_start_date_time" for d in spec["project_dates"]
    )


def test_location_merge_keeps_distinct_road_and_point_sites():
    spec = {
        "project_size_location_items": [
            {
                "text": "Project location: Main Street from 1st Avenue to 5th Avenue",
                "field_key": "project_location",
                "confidence": 90,
                "sources": [{"citation_verified": True}],
            },
            {
                "text": "Project location: SR-91 between Exit 12 and Exit 18",
                "field_key": "project_location",
                "confidence": 90,
                "sources": [{"citation_verified": True}],
            },
        ]
    }
    merge_spec_check_multi_fields(spec)
    rows = spec["project_size_location_items"]
    assert len(rows) == 1
    value = rows[0]["text"].split(": ", 1)[1]
    assert "Main Street from 1st Avenue to 5th Avenue" in value
    assert "SR-91 between Exit 12 and Exit 18" in value
