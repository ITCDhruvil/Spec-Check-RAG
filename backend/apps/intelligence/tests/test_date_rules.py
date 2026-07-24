"""
Exhaustive tests for the spec-check date derivation rules.

These rules are the core automation promise: project start/end dates must be
correct every time — explicit thresholds, weekend shifts, duration math.
"""

from datetime import datetime

import pytest

from apps.intelligence.services.summary_postprocess import (
    _add_calendar_months,
    _apply_end_date_rule,
    _apply_award_date_anchor_rule,
    _apply_start_date_rule,
    _duration_to_datetime,
    _next_business_day,
    _parse_date_string,
    _parse_dollar_amount,
)


# ── _parse_date_string ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("March 11, 2026 at 10:00 AM", datetime(2026, 3, 11, 10, 0)),
        ("March 11, 2026, 10:00 AM", datetime(2026, 3, 11, 10, 0)),
        ("February 27, 2026 at 12:00 P.M.", datetime(2026, 2, 27, 12, 0)),
        ("2026-03-11T10:00:00", datetime(2026, 3, 11, 10, 0)),
        ("2026-03-11T10:00:00-05:00", datetime(2026, 3, 11, 10, 0)),
        ("2026-03-11", datetime(2026, 3, 11)),
        ("3/06/2026 @ 3:00 P.M. PST", datetime(2026, 3, 6, 15, 0)),
        ("03/04/2026 1300", datetime(2026, 3, 4, 13, 0)),
        ("03/04/2026 13:00", datetime(2026, 3, 4, 13, 0)),
        ("3:00 PM on February 25, 2026", datetime(2026, 2, 25)),
        ("12-Mar-2026", datetime(2026, 3, 12)),
        ("Mar 12, 2026", datetime(2026, 3, 12)),
        ("04/10/2026", datetime(2026, 4, 10)),
        # Our own calculated annotation must round-trip
        (
            "April 10, 2026 (estimated — 30 calendar days from Bid open date)",
            datetime(2026, 4, 10),
        ),
        # Real-world variants that previously failed silently
        ("March 11th, 2026", datetime(2026, 3, 11)),
        ("11 March 2026", datetime(2026, 3, 11)),
        ("11 Mar 2026", datetime(2026, 3, 11)),
        ("03-11-2026", datetime(2026, 3, 11)),
        ("3/11/26", datetime(2026, 3, 11)),
        ("Wednesday, March 11, 2026", datetime(2026, 3, 11)),
        ("Wed, March 11, 2026", datetime(2026, 3, 11)),
        ("March 11, 2026 at 10:00 a.m. local time", datetime(2026, 3, 11, 10, 0)),
        ("10:00 AM EST, March 11, 2026", datetime(2026, 3, 11)),
        ("MARCH 11, 2026", datetime(2026, 3, 11)),
        ("2026/03/11", datetime(2026, 3, 11)),
        ("March 11 2026", datetime(2026, 3, 11)),
        ("May 1, 2026, prevailing time", datetime(2026, 5, 1)),
    ],
)
def test_parse_date_string_formats(raw, expected):
    assert _parse_date_string(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "Fall 2026", "TBD", "upon award", "180 calendar days", "N/A"],
)
def test_parse_date_string_rejects_non_dates(raw):
    assert _parse_date_string(raw) is None


# ── _next_business_day (weekend rule) ────────────────────────────────────────

@pytest.mark.parametrize(
    ("dt", "expected"),
    [
        (datetime(2026, 4, 10), datetime(2026, 4, 10)),  # Friday stays
        (datetime(2026, 4, 11), datetime(2026, 4, 13)),  # Saturday → Monday
        (datetime(2026, 4, 12), datetime(2026, 4, 13)),  # Sunday → Monday
        (datetime(2026, 4, 13), datetime(2026, 4, 13)),  # Monday stays
    ],
)
def test_next_business_day(dt, expected):
    assert _next_business_day(dt) == expected


# ── _parse_dollar_amount (drives the 30 vs 60 day threshold) ─────────────────

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$500,000", 500_000.0),
        ("$1,000,000", 1_000_000.0),
        ("$1,000,001", 1_000_001.0),
        ("$2M", 2_000_000.0),
        ("$1.5 million", 1_500_000.0),
        ("$750K", 750_000.0),
        ("$2 billion", 2_000_000_000.0),
        ("$500K–$1.2M", 1_200_000.0),  # range → highest
        ("Project value: $999,999.99", 999_999.99),
        ("no dollars here", None),
        # Real-world variants that previously failed silently
        ("One Million Dollars", 1_000_000.0),
        ("Two Million Dollars", 2_000_000.0),
        ("1,500,000.00 USD", 1_500_000.0),
        ("estimated at 2.5 million dollars", 2_500_000.0),
        ("$1M-$3M", 3_000_000.0),
        ("$1.2M to $2M", 2_000_000.0),
    ],
)
def test_parse_dollar_amount(text, expected):
    assert _parse_dollar_amount(text) == expected


# ── _duration_to_datetime (end-date duration math) ───────────────────────────

START = datetime(2026, 4, 10)


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        ("180 days", datetime(2026, 10, 7)),
        ("180 calendar days", datetime(2026, 10, 7)),
        ("90 working days", datetime(2026, 7, 9)),
        ("8 weeks", datetime(2026, 6, 5)),
        ("12 months", datetime(2027, 4, 10)),
        ("6 months", datetime(2026, 10, 10)),
        ("1 year", datetime(2027, 4, 10)),
        ("2 years", datetime(2028, 4, 10)),
        ("9 months from contract execution", datetime(2027, 1, 10)),
        # Real-world variants that previously failed silently
        ("One hundred eighty (180) calendar days", datetime(2026, 10, 7)),
        ("180 consecutive calendar days", datetime(2026, 10, 7)),
        ("18 mos.", datetime(2027, 10, 10)),
        ("one year", datetime(2027, 4, 10)),
        ("two years", datetime(2028, 4, 10)),
        ("six months", datetime(2026, 10, 10)),
    ],
)
def test_duration_to_datetime(duration, expected):
    assert _duration_to_datetime(duration, START) == expected


def test_duration_rejects_calendar_date():
    # Already a real date — must NOT be treated as duration.
    assert _duration_to_datetime("March 11, 2026", START) is None


def test_add_calendar_months_clamps_month_end():
    # Jan 31 + 1 month must clamp to Feb 28/29, never overflow to Mar 2/3.
    assert _add_calendar_months(datetime(2026, 1, 31), 1) == datetime(2026, 2, 28)
    assert _add_calendar_months(datetime(2024, 1, 31), 1) == datetime(2024, 2, 29)  # leap
    assert _add_calendar_months(datetime(2026, 10, 31), 4) == datetime(2027, 2, 28)


# ── Rule 2: start-date calculation (the 30/60-day threshold) ─────────────────

def _fields(dates, value_text=None):
    meta = [{"text": f"Project value: {value_text}", "field_key": "project_value"}] if value_text else []
    return {"project_dates": dates, "project_metadata_items": meta}


def _bid_open(date_str, conf=100):
    return {"text": "Bid open date", "date": date_str, "field_key": "bid_open_date_time", "confidence": conf}


def _get_start(dates):
    return next(
        (d for d in dates if str(d.get("text", "")).lower() == "project start date"),
        None,
    )


def test_start_rule_no_value_defaults_30_days():
    dates = [_bid_open("March 11, 2026 at 10:00 AM")]
    _apply_start_date_rule(_fields(dates), dates)
    start = _get_start(dates)
    assert start is not None
    assert "April 10, 2026" in start["date"]
    assert start["_days_offset"] == 30
    assert start["_awaiting_project_value"] is True
    assert start["_calculated"] is True


def test_start_rule_value_at_threshold_uses_30():
    # Exactly $1,000,000 is NOT "> $1M" → 30 days.
    dates = [_bid_open("March 11, 2026")]
    _apply_start_date_rule(_fields(dates, "$1,000,000"), dates)
    start = _get_start(dates)
    assert start["_days_offset"] == 30
    assert start["_awaiting_project_value"] is False


def test_start_rule_value_above_threshold_uses_60():
    dates = [_bid_open("March 11, 2026")]
    _apply_start_date_rule(_fields(dates, "$1,000,001"), dates)
    start = _get_start(dates)
    assert start["_days_offset"] == 60
    assert "May 11, 2026" in start["date"]  # Mar 11 + 60 = May 10 (Sun) → May 11 Mon


def test_start_rule_small_value_uses_30():
    dates = [_bid_open("March 11, 2026")]
    _apply_start_date_rule(_fields(dates, "$500K"), dates)
    assert _get_start(dates)["_days_offset"] == 30


def test_start_rule_big_value_millions_suffix_uses_60():
    dates = [_bid_open("March 11, 2026")]
    _apply_start_date_rule(_fields(dates, "$2M"), dates)
    assert _get_start(dates)["_days_offset"] == 60


def test_start_rule_range_value_uses_highest():
    # "$500K–$1.2M" → 1.2M > 1M → 60 days.
    dates = [_bid_open("March 11, 2026")]
    _apply_start_date_rule(_fields(dates, "$500K–$1.2M"), dates)
    assert _get_start(dates)["_days_offset"] == 60


def test_start_rule_weekend_shift():
    # Bid open Thu Mar 12, 2026 + 30 = Sat Apr 11 → Mon Apr 13.
    dates = [_bid_open("March 12, 2026")]
    _apply_start_date_rule(_fields(dates), dates)
    assert "April 13, 2026" in _get_start(dates)["date"]


def test_start_rule_explicit_start_untouched():
    dates = [
        _bid_open("March 11, 2026"),
        {"text": "Project start date", "date": "July 1, 2026", "field_key": "project_start_date_time"},
    ]
    _apply_start_date_rule(_fields(dates), dates)
    starts = [d for d in dates if str(d.get("text", "")).lower() == "project start date"]
    assert len(starts) == 1
    assert starts[0]["date"] == "July 1, 2026"
    assert "_calculated" not in starts[0]


def test_start_rule_no_bid_open_no_start():
    dates = [{"text": "Question deadline", "date": "Feb 27, 2026", "field_key": "question_deadline_date_time"}]
    _apply_start_date_rule(_fields(dates), dates)
    assert _get_start(dates) is None


def test_start_rule_unparseable_bid_open_carries_text():
    dates = [_bid_open("Fall 2026")]
    _apply_start_date_rule(_fields(dates), dates)
    start = _get_start(dates)
    assert start is not None
    assert start["date"] == "Fall 2026"
    assert start["_calculated"] is True


def test_start_rule_confidence_capped_by_parent():
    dates = [_bid_open("March 11, 2026", conf=80)]
    _apply_start_date_rule(_fields(dates), dates)
    assert _get_start(dates)["_parent_confidence_cap"] == 80


# ── Rule 3: end-date duration conversion ─────────────────────────────────────

def _start(date_str, conf=90):
    return {"text": "Project start date", "date": date_str, "field_key": "project_start_date_time", "confidence": conf}


def _end(date_str):
    return {"text": "Project end date", "date": date_str, "field_key": "project_end_date_time"}


def test_end_rule_converts_days_duration():
    dates = [_start("April 10, 2026"), _end("180 calendar days")]
    _apply_end_date_rule({"project_dates": dates}, dates)
    end = dates[1]
    assert "October 07, 2026" in end["date"]
    assert 'estimated from "180 calendar days"' in end["date"]
    assert end["_calculated"] is True


def test_end_rule_converts_months_duration():
    dates = [_start("April 10, 2026"), _end("9 months from contract execution")]
    _apply_end_date_rule({"project_dates": dates}, dates)
    assert "January 10, 2027" in dates[1]["date"]


def test_end_rule_uses_calculated_start():
    # Start itself calculated (with annotation) must still anchor duration math.
    dates = [
        _start("April 10, 2026 (estimated — 30 calendar days from Bid open date)"),
        _end("12 months"),
    ]
    _apply_end_date_rule({"project_dates": dates}, dates)
    assert "April 10, 2027" in dates[1]["date"]


def test_end_rule_leaves_calendar_date_untouched():
    dates = [_start("April 10, 2026"), _end("December 31, 2026")]
    _apply_end_date_rule({"project_dates": dates}, dates)
    assert dates[1]["date"] == "December 31, 2026"
    assert "_calculated" not in dates[1]


def test_end_rule_absent_end_not_fabricated():
    dates = [_start("April 10, 2026")]
    _apply_end_date_rule({"project_dates": dates}, dates)
    assert all(str(d.get("text", "")).lower() != "project end date" for d in dates)


def test_end_rule_unparseable_start_keeps_duration_text():
    dates = [_start("Fall 2026"), _end("180 days")]
    _apply_end_date_rule({"project_dates": dates}, dates)
    assert dates[1]["date"] == "180 days"


def test_end_rule_confidence_capped_by_start():
    dates = [_start("April 10, 2026", conf=75), _end("6 months")]
    _apply_end_date_rule({"project_dates": dates}, dates)
    assert dates[1]["_parent_confidence_cap"] == 75


# ── Rule 4: award-date anchor ("N days after award") ─────────────────────────

def test_award_anchor_converts_after_award_phrase():
    dates = [
        {"text": "Award date", "date": "May 1, 2026", "field_key": "municipal_meeting_date_time", "confidence": 90},
        {"text": "Project start date", "date": "10 Days After Award", "field_key": "project_start_date_time"},
        {"text": "Project end date", "date": "180 days after award", "field_key": "project_end_date_time"},
    ]
    _apply_award_date_anchor_rule({"project_dates": dates}, dates)
    assert "May 11, 2026" in dates[1]["date"]
    assert "October 28, 2026" in dates[2]["date"]
    assert dates[1]["_calculated"] is True
    assert dates[1]["_parent_confidence_cap"] == 90


def test_award_anchor_leaves_calendar_dates():
    dates = [
        {"text": "Award date", "date": "May 1, 2026", "field_key": "municipal_meeting_date_time"},
        {"text": "Project start date", "date": "June 1, 2026", "field_key": "project_start_date_time"},
    ]
    _apply_award_date_anchor_rule({"project_dates": dates}, dates)
    assert dates[1]["date"] == "June 1, 2026"


def test_award_anchor_no_award_no_change():
    dates = [
        {"text": "Project start date", "date": "10 days after award", "field_key": "project_start_date_time"},
    ]
    _apply_award_date_anchor_rule({"project_dates": dates}, dates)
    assert dates[0]["date"] == "10 days after award"
