"""
Standalone tests for spec-check date rules.
Run from the backend directory (no Django setup required):
    python test_date_rules.py

Covers:
  Rule 1 - Bid open date fallback
  Rule 2 - Project start date calculation (value threshold, weekends, ranges, unparseable)
  Rule 3 - Project end date duration conversion (days, weeks, months, years, month-end clamping)
"""
import sys
import importlib
import importlib.util
import pathlib
import types
import copy
from datetime import datetime

BACKEND = pathlib.Path(__file__).parent
sys.path.insert(0, str(BACKEND))

# ---------------------------------------------------------------------------
# Shim: citation_service only (avoids Django); other modules load normally.
# ---------------------------------------------------------------------------
def _make_stub(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod

for _pkg in ("apps", "apps.intelligence", "apps.intelligence.services"):
    if _pkg not in sys.modules:
        _make_stub(_pkg)

_services = sys.modules["apps.intelligence.services"]
_services.__path__ = [str(BACKEND / "apps" / "intelligence" / "services")]

_cs = _make_stub("apps.intelligence.services.citation_service")
_cs.build_extraction_citation_lookup  = lambda *a, **kw: {}
_cs.canonicalize_summary_sources      = lambda *a, **kw: None
_cs.enforce_verbatim_summary_sources  = lambda *a, **kw: None

# Load the module under test
_spec = importlib.util.spec_from_file_location(
    "summary_postprocess",
    pathlib.Path(__file__).parent / "apps/intelligence/services/summary_postprocess.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_parse_dollar_amount         = _mod._parse_dollar_amount
_parse_date_string           = _mod._parse_date_string
_next_business_day           = _mod._next_business_day
_add_calendar_months         = _mod._add_calendar_months
_duration_to_datetime        = _mod._duration_to_datetime
_apply_spec_check_date_rules = _mod._apply_spec_check_date_rules

results = {"pass": 0, "fail": 0}

def check(label, condition, extra=""):
    marker = "PASS" if condition else "FAIL"
    suffix = f"  ->  {extra}" if (not condition and extra) else ""
    print(f"  [{marker}]  {label}{suffix}")
    results["pass" if condition else "fail"] += 1

def run_rules(spec):
    s = copy.deepcopy(spec)
    _apply_spec_check_date_rules(s)
    return s

def date_text(dates, label):
    for d in dates:
        if (d.get("text") or "").strip().lower() == label.lower():
            return d.get("date")
    return None

def date_entry(dates, label):
    for d in dates:
        if (d.get("text") or "").strip().lower() == label.lower():
            return d
    return None

# ---------------------------------------------------------------------------
# Section 0 - Low-level helpers
# ---------------------------------------------------------------------------
print("\n=== Section 0: Low-level helpers ===")

check("$2,200,000 -> 2_200_000",
      _parse_dollar_amount("$2,200,000") == 2_200_000)
check("$2.2M -> 2_200_000",
      _parse_dollar_amount("$2.2M") == 2_200_000)
check("$500K -> 500_000",
      _parse_dollar_amount("$500K") == 500_000)
check("Range $500K-$1.5M: max = 1_500_000",
      _parse_dollar_amount("$500K-$1.5M") == 1_500_000)
check("Range $20,000-$50,000: max = 50_000",
      _parse_dollar_amount("$20,000-$50,000") == 50_000)
check("Range $1M-$2M: max = 2_000_000",
      _parse_dollar_amount("$1M-$2M") == 2_000_000)
check("Words 'Two million' -> None",
      _parse_dollar_amount("Two million dollars") is None)
check("Empty string -> None",
      _parse_dollar_amount("") is None)

check("'March 11, 2026 at 11:00 AM' parses correctly",
      _parse_date_string("March 11, 2026 at 11:00 AM") == datetime(2026, 3, 11, 11, 0))
check("'March 11, 2026' parses correctly",
      _parse_date_string("March 11, 2026") == datetime(2026, 3, 11))
check("'Fall 2026' -> None",
      _parse_date_string("Fall 2026") is None)
check("'March 2026' (no day) -> None",
      _parse_date_string("March 2026") is None)
check("'May 11, 2026 (estimated -- 60 calendar days from Bid open date)' -> May 11",
      _parse_date_string("May 11, 2026 (estimated -- 60 calendar days from Bid open date)")
      == datetime(2026, 5, 11))

check("'March 4, 2026 at 1:00 PM CST' parses (timezone stripped)",
      _parse_date_string("March 4, 2026 at 1:00 PM CST") == datetime(2026, 3, 4, 13, 0))
check("'February 20, 2026, 1:00 PM CST' parses (comma before time)",
      _parse_date_string("February 20, 2026, 1:00 PM CST") == datetime(2026, 2, 20, 13, 0))
check("'03/04/2026 1300' military format parses",
      _parse_date_string("03/04/2026 1300") == datetime(2026, 3, 4, 13, 0))

sat = datetime(2026, 3, 14)
check("Saturday -> Monday",
      _next_business_day(sat).weekday() == 0)
sun = datetime(2026, 3, 15)
check("Sunday -> Monday",
      _next_business_day(sun).weekday() == 0)
wed = datetime(2026, 3, 11)
check("Wednesday stays Wednesday",
      _next_business_day(wed).weekday() == 2)

check("Jan 31 + 1 month -> Feb 28 (2026, non-leap)",
      _add_calendar_months(datetime(2026, 1, 31), 1) == datetime(2026, 2, 28))
check("Jan 31 + 1 month -> Feb 29 (2028, leap)",
      _add_calendar_months(datetime(2028, 1, 31), 1) == datetime(2028, 2, 29))

# ---------------------------------------------------------------------------
# Section 1 - Rule 1: Bid open date fallback
# ---------------------------------------------------------------------------
print("\n=== Section 1: Rule 1 - Bid open date fallback ===")

# 1a. Both present -> no change
s = run_rules({
    "project_dates": [
        {"text": "Bid deadline",  "date": "March 11, 2026 at 11:00 AM"},
        {"text": "Bid open date", "date": "March 11, 2026 at 2:00 PM"},
    ],
    "project_metadata_items": [{"text": "project_value: $500,000"}],
})
check("1a - Both present: bid open date unchanged",
      date_text(s["project_dates"], "Bid open date") == "March 11, 2026 at 2:00 PM")

# 1b. Bid open date absent -> copied from deadline
s = run_rules({
    "project_dates": [
        {"text": "Bid deadline", "date": "March 11, 2026 at 11:00 AM"},
    ],
    "project_metadata_items": [{"text": "project_value: $500,000"}],
})
check("1b - Open date absent: copied from deadline",
      date_text(s["project_dates"], "Bid open date") == "March 11, 2026 at 11:00 AM")

# 1c. Both absent -> nothing added
s = run_rules({"project_dates": [], "project_metadata_items": []})
check("1c - Both absent: no bid open date added",
      "Bid open date" not in [d.get("text") for d in s["project_dates"]])

# ---------------------------------------------------------------------------
# Section 2 - Rule 2: Project start date
# ---------------------------------------------------------------------------
print("\n=== Section 2: Rule 2 - Project start date ===")

BID_OPEN = {"text": "Bid open date", "date": "March 11, 2026 at 11:00 AM"}

# 2a. Start date already in document -> untouched
s = run_rules({
    "project_dates": [
        BID_OPEN,
        {"text": "Project start date", "date": "April 1, 2026"},
    ],
    "project_metadata_items": [{"text": "project_value: $2,200,000"}],
})
check("2a - Start date in document: not overwritten",
      date_text(s["project_dates"], "Project start date") == "April 1, 2026")

# 2b. Value > $1M -> +60 days from March 11 = May 10 (Sun) -> May 11 (Mon)
s = run_rules({
    "project_dates": [BID_OPEN],
    "project_metadata_items": [{"text": "project_value: $2,200,000"}],
})
entry = date_entry(s["project_dates"], "Project start date")
check("2b - Value $2.2M > $1M: 60-day offset",
      entry and entry.get("_days_offset") == 60, str(entry))
check("2b - Result is May 11, 2026 (Monday after May 10 Sunday)",
      entry and "May 11, 2026" in (entry.get("date") or ""), str(entry))

# 2c. Value <= $1M -> +30 days from March 11 = April 10 (Friday, no shift)
s = run_rules({
    "project_dates": [BID_OPEN],
    "project_metadata_items": [{"text": "project_value: $500,000"}],
})
entry = date_entry(s["project_dates"], "Project start date")
check("2c - Value $500K <= $1M: 30-day offset",
      entry and entry.get("_days_offset") == 30, str(entry))
check("2c - Result is April 10, 2026 (Friday - no shift needed)",
      entry and "April 10, 2026" in (entry.get("date") or ""), str(entry))

# 2d. Range $500K-$1.5M: max $1.5M > $1M -> 60 days
s = run_rules({
    "project_dates": [BID_OPEN],
    "project_metadata_items": [{"text": "project_value: $500K-$1.5M"}],
})
entry = date_entry(s["project_dates"], "Project start date")
check("2d - Range $500K-$1.5M: max $1.5M > $1M -> 60 days",
      entry and entry.get("_days_offset") == 60, str(entry))

# 2e. Range $200K-$800K: max $800K <= $1M -> 30 days
s = run_rules({
    "project_dates": [BID_OPEN],
    "project_metadata_items": [{"text": "project_value: $200K-$800K"}],
})
entry = date_entry(s["project_dates"], "Project start date")
check("2e - Range $200K-$800K: max $800K <= $1M -> 30 days",
      entry and entry.get("_days_offset") == 30, str(entry))

# 2f. Value absent -> 30 days default + _awaiting_project_value
s = run_rules({
    "project_dates": [BID_OPEN],
    "project_metadata_items": [],
})
entry = date_entry(s["project_dates"], "Project start date")
check("2f - Value absent: default 30 days",
      entry and entry.get("_days_offset") == 30, str(entry))
check("2f - Value absent: _awaiting_project_value=True",
      entry and entry.get("_awaiting_project_value") is True, str(entry))

# 2g. Bid open date is 'Fall 2026' -> carried as start date
s = run_rules({
    "project_dates": [
        {"text": "Bid deadline",  "date": "Fall 2026"},
        {"text": "Bid open date", "date": "Fall 2026"},
    ],
    "project_metadata_items": [{"text": "project_value: $2,200,000"}],
})
entry = date_entry(s["project_dates"], "Project start date")
check("2g - 'Fall 2026' bid open: start date = 'Fall 2026' (as-is)",
      entry and entry.get("date") == "Fall 2026", str(entry))
check("2g - _calculated flag set",
      entry and entry.get("_calculated") is True, str(entry))

# 2h. No bid dates at all -> no start date added
s = run_rules({"project_dates": [], "project_metadata_items": []})
check("2h - No bid dates: start date not added",
      date_entry(s["project_dates"], "Project start date") is None)

# 2i. Weekend: bid open Thursday March 12 + 30 days = Saturday April 11 -> Monday April 13
s = run_rules({
    "project_dates": [{"text": "Bid open date", "date": "March 12, 2026"}],
    "project_metadata_items": [{"text": "project_value: $999,999"}],
})
entry = date_entry(s["project_dates"], "Project start date")
print(f"     (debug 2i) start date = {entry and entry.get('date')}")
check("2i - +30 days from Thu March 12 = Sat April 11 -> Mon April 13",
      entry and "April 13, 2026" in (entry.get("date") or ""), str(entry))

# 2j. Exactly $1,000,000 -> not > $1M -> 30 days
s = run_rules({
    "project_dates": [BID_OPEN],
    "project_metadata_items": [{"text": "project_value: $1,000,000"}],
})
entry = date_entry(s["project_dates"], "Project start date")
check("2j - Exactly $1M (not > $1M): 30 days",
      entry and entry.get("_days_offset") == 30, str(entry))

# 2k. $1,000,001 -> > $1M -> 60 days
s = run_rules({
    "project_dates": [BID_OPEN],
    "project_metadata_items": [{"text": "project_value: $1,000,001"}],
})
entry = date_entry(s["project_dates"], "Project start date")
check("2k - $1,000,001 > $1M: 60 days",
      entry and entry.get("_days_offset") == 60, str(entry))

# ---------------------------------------------------------------------------
# Section 3 - Rule 3: Project end date duration
# ---------------------------------------------------------------------------
print("\n=== Section 3: Rule 3 - End date duration conversion ===")

START = {"text": "Project start date", "date": "March 11, 2026"}

# 3a. Already a calendar date -> untouched
s = run_rules({
    "project_dates": [
        {"text": "Bid open date",    "date": "March 11, 2026"},
        START,
        {"text": "Project end date", "date": "December 31, 2026"},
    ],
    "project_metadata_items": [{"text": "project_value: $500,000"}],
})
check("3a - Full calendar date: untouched",
      date_text(s["project_dates"], "Project end date") == "December 31, 2026")

# 3b. '180 calendar days' -> March 11 + 180 = Sep 7, 2026
s = run_rules({
    "project_dates": [
        {"text": "Bid open date",    "date": "March 11, 2026"},
        START,
        {"text": "Project end date", "date": "180 calendar days"},
    ],
    "project_metadata_items": [{"text": "project_value: $500,000"}],
})
entry = date_entry(s["project_dates"], "Project end date")
check("3b - '180 calendar days' -> September 07, 2026",
      entry and "September 07, 2026" in (entry.get("date") or ""), str(entry))
check("3b - _calculated flag set",
      entry and entry.get("_calculated") is True)

# 3c. '12 months' -> March 11 + 12 months = March 11, 2027
s = run_rules({
    "project_dates": [
        {"text": "Bid open date",    "date": "March 11, 2026"},
        START,
        {"text": "Project end date", "date": "12 months"},
    ],
    "project_metadata_items": [],
})
entry = date_entry(s["project_dates"], "Project end date")
check("3c - '12 months' -> March 11, 2027",
      entry and "March 11, 2027" in (entry.get("date") or ""), str(entry))

# 3d. '1 year'
s = run_rules({
    "project_dates": [
        {"text": "Bid open date",    "date": "March 11, 2026"},
        START,
        {"text": "Project end date", "date": "1 year"},
    ],
    "project_metadata_items": [],
})
entry = date_entry(s["project_dates"], "Project end date")
check("3d - '1 year' -> March 11, 2027",
      entry and "March 11, 2027" in (entry.get("date") or ""), str(entry))

# 3e. '8 weeks' -> March 11 + 56 days = May 6, 2026
s = run_rules({
    "project_dates": [
        {"text": "Bid open date",    "date": "March 11, 2026"},
        START,
        {"text": "Project end date", "date": "8 weeks"},
    ],
    "project_metadata_items": [],
})
entry = date_entry(s["project_dates"], "Project end date")
check("3e - '8 weeks' (56 days) -> May 06, 2026",
      entry and "May 06, 2026" in (entry.get("date") or ""), str(entry))

# 3f. '2 years' -> March 11 + 24 months = March 11, 2028
s = run_rules({
    "project_dates": [
        {"text": "Bid open date",    "date": "March 11, 2026"},
        START,
        {"text": "Project end date", "date": "2 years"},
    ],
    "project_metadata_items": [],
})
entry = date_entry(s["project_dates"], "Project end date")
check("3f - '2 years' -> March 11, 2028",
      entry and "March 11, 2028" in (entry.get("date") or ""), str(entry))

# 3g. '90 working days' -> March 11 + 90 = June 9, 2026
s = run_rules({
    "project_dates": [
        {"text": "Bid open date",    "date": "March 11, 2026"},
        START,
        {"text": "Project end date", "date": "90 working days"},
    ],
    "project_metadata_items": [],
})
entry = date_entry(s["project_dates"], "Project end date")
check("3g - '90 working days' -> June 09, 2026",
      entry and "June 09, 2026" in (entry.get("date") or ""), str(entry))

# 3h. Non-specific start 'Fall 2026' -> duration kept as-is
s = run_rules({
    "project_dates": [
        {"text": "Bid open date",      "date": "Fall 2026"},
        {"text": "Project start date", "date": "Fall 2026", "_calculated": True},
        {"text": "Project end date",   "date": "12 months"},
    ],
    "project_metadata_items": [],
})
check("3h - Non-specific start 'Fall 2026': duration kept as '12 months'",
      date_text(s["project_dates"], "Project end date") == "12 months")

# 3i. End date absent -> not fabricated
s = run_rules({
    "project_dates": [
        {"text": "Bid open date",    "date": "March 11, 2026"},
        START,
    ],
    "project_metadata_items": [],
})
check("3i - End date absent: not fabricated",
      date_entry(s["project_dates"], "Project end date") is None)

# 3j. Month-end clamping: Jan 31 + 1 month -> Feb 28, 2026
s = run_rules({
    "project_dates": [
        {"text": "Bid open date",      "date": "January 31, 2026"},
        {"text": "Project start date", "date": "January 31, 2026"},
        {"text": "Project end date",   "date": "1 month"},
    ],
    "project_metadata_items": [{"text": "project_value: $500,000"}],
})
entry = date_entry(s["project_dates"], "Project end date")
check("3j - Jan 31 + 1 month -> Feb 28, 2026 (month-end clamping)",
      entry and "February 28, 2026" in (entry.get("date") or ""), str(entry))

# 3k. Duration with suffix text '6 months from Notice to Proceed'
s = run_rules({
    "project_dates": [
        {"text": "Bid open date",    "date": "March 11, 2026"},
        START,
        {"text": "Project end date", "date": "6 months from Notice to Proceed"},
    ],
    "project_metadata_items": [],
})
entry = date_entry(s["project_dates"], "Project end date")
check("3k - '6 months from Notice to Proceed' -> September 11, 2026",
      entry and "September 11, 2026" in (entry.get("date") or ""), str(entry))

# 3l. '30 days' (very short project)
s = run_rules({
    "project_dates": [
        {"text": "Bid open date",    "date": "March 11, 2026"},
        START,
        {"text": "Project end date", "date": "30 days"},
    ],
    "project_metadata_items": [],
})
entry = date_entry(s["project_dates"], "Project end date")
check("3l - '30 days' -> April 10, 2026",
      entry and "April 10, 2026" in (entry.get("date") or ""), str(entry))

# 3m. '18 months' crossing year boundary
s = run_rules({
    "project_dates": [
        {"text": "Bid open date",    "date": "March 11, 2026"},
        START,
        {"text": "Project end date", "date": "18 months"},
    ],
    "project_metadata_items": [],
})
entry = date_entry(s["project_dates"], "Project end date")
check("3m - '18 months' -> September 11, 2027",
      entry and "September 11, 2027" in (entry.get("date") or ""), str(entry))

# ---------------------------------------------------------------------------
# Section 4 - Integration: rules chain together
# ---------------------------------------------------------------------------
print("\n=== Section 4: Integration (rules chained) ===")

# Full scenario: bid deadline only, value > $1M, end date is a duration
# Rule 1: bid open date copied from deadline (March 11)
# Rule 2: start date = March 11 + 60 days = May 10 (Sun) -> May 11 (Mon)
# Rule 3: end date = May 11 + 180 days = November 7, 2026
s = run_rules({
    "project_dates": [
        {"text": "Bid deadline",     "date": "March 11, 2026 at 11:00 AM"},
        {"text": "Project end date", "date": "180 calendar days"},
    ],
    "project_metadata_items": [{"text": "project_value: $2,200,000"}],
})
dates = s["project_dates"]
bid_open = date_text(dates, "Bid open date")
start    = date_entry(dates, "Project start date")
end      = date_entry(dates, "Project end date")
print(f"     (debug 4) bid_open={bid_open}  start={start and start.get('date')}  end={end and end.get('date')}")
check("4a - Bid open copied from deadline",
      bid_open == "March 11, 2026 at 11:00 AM")
check("4b - Start date: 60-day offset (value > $1M)",
      start and start.get("_days_offset") == 60, str(start))
check("4c - End date calculated from chained start date",
      end and end.get("_calculated") is True, str(end))
check("4d - End date contains 'November 07, 2026' (May 11 + 180 days)",
      end and "November 07, 2026" in (end.get("date") or ""), str(end))

# No value in document -> awaiting flag; end date still chained from default start
s = run_rules({
    "project_dates": [
        {"text": "Bid deadline",     "date": "March 11, 2026 at 11:00 AM"},
        {"text": "Project end date", "date": "12 months"},
    ],
    "project_metadata_items": [],
})
start = date_entry(s["project_dates"], "Project start date")
end   = date_entry(s["project_dates"], "Project end date")
print(f"     (debug 4e) start={start and start.get('date')}  end={end and end.get('date')}")
check("4e - No value: start date awaiting project value",
      start and start.get("_awaiting_project_value") is True)
check("4f - End date (12 months) still calculated from default start",
      end and end.get("_calculated") is True, str(end))

# Non-specific bid date propagates through all three rules
s = run_rules({
    "project_dates": [
        {"text": "Bid deadline",     "date": "Spring 2027"},
        {"text": "Project end date", "date": "6 months"},
    ],
    "project_metadata_items": [{"text": "project_value: $2,200,000"}],
})
start = date_entry(s["project_dates"], "Project start date")
end   = date_entry(s["project_dates"], "Project end date")
check("4g - Non-specific 'Spring 2027': start carries text as-is",
      start and start.get("date") == "Spring 2027")
check("4h - Non-specific start: end date duration kept as '6 months'",
      end and end.get("date") == "6 months")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
total = results["pass"] + results["fail"]
print(f"\n{'='*55}")
print(f"Results: {results['pass']}/{total} passed, {results['fail']} failed")
if results["fail"] == 0:
    print("All tests passed!")
else:
    print(f"{results['fail']} test(s) FAILED -- see output above.")
    sys.exit(1)
