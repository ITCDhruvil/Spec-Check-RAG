"""Unit tests for Phase 5 per-field confidence scoring."""

from types import SimpleNamespace

from apps.intelligence.services.field_confidence import (
    apply_confidence_to_spec_check_fields,
    enrich_spec_check_field_entry,
    score_spec_field_confidence,
)
from apps.intelligence.services.summary_postprocess import (
    _apply_award_date_alias,
    build_spec_check_fields_from_insights,
    finalize_spec_check_fields,
)


def test_score_spec_field_confidence_verified_boost():
    verified = score_spec_field_confidence(
        extraction_confidence=0.8,
        citation_verified=True,
        has_source_text=True,
    )
    unverified = score_spec_field_confidence(
        extraction_confidence=0.8,
        citation_verified=False,
        has_source_text=False,
    )
    assert verified > unverified
    assert 0 <= verified <= 100


def test_score_spec_field_confidence_calculated_cap():
    raw = score_spec_field_confidence(
        extraction_confidence=0.95,
        citation_verified=True,
        has_source_text=True,
    )
    calc = score_spec_field_confidence(
        extraction_confidence=0.95,
        citation_verified=True,
        has_source_text=True,
        is_calculated=True,
    )
    assert calc <= 72
    assert calc < raw


def test_enrich_spec_check_field_entry_attaches_field_key():
    row = enrich_spec_check_field_entry(
        {"text": "Project name: Main St Bridge"},
        field_key="project_name",
        source_item={"confidence": 0.9, "citation_verified": True, "source_text": "x"},
    )
    assert row["field_key"] == "project_name"
    assert isinstance(row["confidence"], int)
    assert row["confidence"] >= 85


def test_apply_award_date_alias_from_municipal_meeting():
    spec = {
        "project_dates": [
            {
                "text": "Municipal meeting date",
                "date": "June 1, 2026",
                "field_key": "municipal_meeting_date_time",
                "confidence": 88,
                "sources": [],
            }
        ]
    }
    _apply_award_date_alias(spec)
    labels = [d["text"] for d in spec["project_dates"]]
    assert "Award date" in labels
    award = next(d for d in spec["project_dates"] if d["text"] == "Award date")
    assert award["field_key"] == "award_date"
    assert award["_alias_of"] == "municipal_meeting_date_time"
    assert award["date"] == "June 1, 2026"


def test_build_spec_check_fields_includes_confidence():
    insight = SimpleNamespace(
        extraction_type="submission_deadlines",
        payload={
            "items": [
                {
                    "label": "bid_deadline_date_time",
                    "date_time": "March 15, 2026 at 2:00 PM",
                    "confidence": 0.87,
                    "citation_verified": True,
                    "source_text": "Bids due March 15, 2026 at 2:00 PM",
                    "page": 2,
                }
            ]
        },
    )
    spec = build_spec_check_fields_from_insights([insight])
    finalize_spec_check_fields(spec)
    bid = next(d for d in spec["project_dates"] if d["text"] == "Bid deadline")
    assert bid["field_key"] == "bid_deadline_date_time"
    assert isinstance(bid["confidence"], int)
    assert bid["confidence"] > 0


def test_apply_confidence_to_all_buckets():
    spec = {
        "project_metadata_items": [{"text": "Project name: X", "sources": []}],
        "project_people_items": [],
        "project_size_location_items": [],
        "project_dates": [],
        "bond_items": [],
    }
    out = apply_confidence_to_spec_check_fields(spec)
    assert "confidence" in out["project_metadata_items"][0]
