"""
Post-process LLM summary JSON: deduplication, priority tuning, citation alignment.
"""

from __future__ import annotations

import calendar as _calendar
import re
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings

from apps.intelligence.services.citation_service import (
    build_extraction_citation_lookup,
    canonicalize_summary_sources,
    enforce_verbatim_summary_sources,
)
from apps.intelligence.services.spec_check_fields_registry import (
    BOND_LABEL_DISPLAY,
    DEADLINE_LABEL_DISPLAY,
    SET_ASIDE_LABEL_DISPLAY,
    field_def,
)
from apps.intelligence.services.field_confidence import (
    apply_confidence_to_spec_check_fields,
    enrich_spec_check_field_entry,
    field_key_for_bond_label,
    field_key_for_deadline_label,
    field_key_for_set_aside_label,
)
from apps.intelligence.services.spec_check_postrules import (
    _merge_warnings,
    apply_spec_check_postrules,
    build_field_warnings,
    is_placeholder_date,
    is_valid_acquisition_note,
)

SIMILARITY_THRESHOLD = 0.72


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())




def _enrich_deadline_item(item: dict[str, Any]) -> dict[str, Any]:
    """Fill date field from source_text so UI shows date+time, not label only."""
    label = str(item.get("text") or item.get("item") or "").strip()
    date = str(item.get("date") or "").strip()
    sources = item.get("sources") or []
    source_text = ""
    if sources and isinstance(sources[0], dict):
        source_text = str(sources[0].get("source_text") or "").strip()

    if source_text and label:
        pattern = re.compile(
            rf"^{re.escape(label)}\s*[:–\-]\s*(.+)$",
            re.IGNORECASE,
        )
        match = pattern.match(source_text)
        if match:
            item["date"] = match.group(1).strip()
        elif not date and len(source_text) > len(label):
            item["date"] = source_text
    elif source_text and not date:
        item["date"] = source_text
        if not label:
            item["text"] = "Deadline"

    return item



def _load_page_texts(document) -> list[tuple[int, str]]:
    try:
        parsed = document.parsed_document
    except Exception:
        return []
    return list(
        parsed.pages.order_by("page_number").values_list("page_number", "extracted_text")
    )


def reapply_summary_citations(
    data: dict[str, Any],
    insights: list,
    document,
) -> dict[str, Any]:
    """Re-run citation grounding on stored summary JSON (no LLM call)."""
    page_texts = _load_page_texts(document)
    lookup = build_extraction_citation_lookup(insights, page_texts)
    canonicalize_summary_sources(data, lookup)
    enforce_verbatim_summary_sources(
        data,
        page_texts=page_texts,
        insights=insights,
        lookup=lookup,
    )
    return data


def _parse_dollar_amount(text: str) -> float | None:
    """
    Parse a dollar-amount string and return the value as a float.
    For ranges (e.g. "$500K–$1.2M"), returns the HIGHEST value.
    Handles suffixes: K/thousand, M/million, B/billion.
    """
    amounts: list[float] = []
    # "$1.2M", "$500,000" — and "2.5 million dollars" / "1,500,000.00 USD" without a $ sign.
    pattern = re.compile(
        r"(?:\$\s*([\d,]+(?:\.\d+)?)\s*(million|M|billion|B|thousand|K)?"
        r"|([\d,]+(?:\.\d+)?)\s*(million|billion|thousand)?\s*(?:dollars|USD)\b"
        r"|([\d,]+(?:\.\d+)?)\s+(million|billion|thousand)\s+dollars?\b)",
        re.IGNORECASE,
    )
    _WORD_AMOUNTS = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    # "One Million Dollars" / "Two Million Dollars" (spelled-out small counts)
    word_m = re.search(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+(million|billion|thousand)\s+dollars?\b",
        text,
        re.IGNORECASE,
    )
    if word_m:
        base = float(_WORD_AMOUNTS[word_m.group(1).lower()])
        mult = {"thousand": 1e3, "million": 1e6, "billion": 1e9}[word_m.group(2).lower()]
        amounts.append(base * mult)

    for match in pattern.finditer(text):
        raw = match.group(1) or match.group(3) or match.group(5)
        if not raw:
            continue
        try:
            val = float(raw.replace(",", ""))
        except ValueError:
            continue
        suffix = (match.group(2) or match.group(4) or match.group(6) or "").lower()
        if suffix in ("m", "million"):
            val *= 1_000_000
        elif suffix in ("b", "billion"):
            val *= 1_000_000_000
        elif suffix in ("k", "thousand"):
            val *= 1_000
        amounts.append(val)
    return max(amounts) if amounts else None


_MONTH_RE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", re.IGNORECASE
)


def _parse_date_string(date_str: str) -> datetime | None:
    """Parse common US tender date strings to a datetime; returns None if unparseable."""
    if not date_str:
        return None
    cleaned = re.sub(r"\s+", " ", date_str.strip())
    # Strip trailing "(estimated …)" notes added by our own post-processor
    cleaned = re.sub(r"\s*\(estimated[^)]*\)", "", cleaned, flags=re.IGNORECASE).strip()
    # Strip weekday prefix: "Wednesday, March 11, 2026" → "March 11, 2026"
    cleaned = re.sub(
        r"^(Mon|Tues?|Wed(?:nes)?|Thur?s?|Fri|Satur?|Sun)(day)?,?\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    # Strip ordinal suffixes: "March 11th, 2026" → "March 11, 2026"
    cleaned = re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", cleaned, flags=re.IGNORECASE)
    # Strip trailing "local time" / "prevailing time" qualifiers
    cleaned = re.sub(
        r",?\s*(local|prevailing|eastern|central|mountain|pacific)\s+time\b\.?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    # Normalise ISO 8601 datetime: "2026-02-25T15:00:00[-08:00]" → "2026-02-25 15:00:00"
    cleaned = re.sub(r"T(\d{2}:\d{2}:\d{2})([+-]\d{2}:\d{2}|Z)?$", r" \1", cleaned).strip()
    # Replace "@" separator used in some RFPs: "3/06/2026 @ 3:00 P.M. PST" → "3/06/2026 3:00 P.M. PST"
    cleaned = re.sub(r"\s*@\s*", " ", cleaned).strip()
    # Normalise "P.M." / "A.M." to "PM" / "AM"
    cleaned = re.sub(r"\b([AaPp])\.([Mm])\.", r"\1\2", cleaned).strip()
    # Strip US timezone abbreviations (CST, EST, CS = Central Standard shorthand, etc.)
    cleaned = re.sub(
        r"\s+(CST|CDT|EST|EDT|MST|MDT|PST|PDT|UTC|GMT|CT|ET|MT|PT|CS)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    # "February 20, 2026, 1:00 PM" -> "February 20, 2026 at 1:00 PM"
    cleaned = re.sub(
        r"^(.+?\d{4}),\s*(\d{1,2}:\d{2}\s*[APap][Mm])$",
        r"\1 at \2",
        cleaned,
    )

    # Military / compact: 03/04/2026 1300 or 03/04/2026 13:00
    mil = re.match(
        r"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):?(\d{2})$",
        cleaned,
    )
    if mil:
        month, day, year, hour, minute = (int(mil.group(i)) for i in range(1, 6))
        try:
            return datetime(year, month, day, hour, minute)
        except ValueError:
            pass

    # Strip optional ", at HH:MM AM/PM" so date-only parse works regardless of time suffix
    cleaned_date_only = re.sub(r",?\s+at\s+\d{1,2}:\d{2}\s*[APap][Mm]", "", cleaned).strip()
    # Also strip trailing comma left after time removal (e.g. "February 23, 2026,")
    cleaned_date_only = cleaned_date_only.rstrip(",").strip()
    # "3:00 PM on February 25, 2026" — time-first format: extract the date portion
    time_on_date = re.match(
        r"^\d{1,2}:\d{2}\s*[APap][Mm]\s+on\s+(.+)$", cleaned, re.IGNORECASE
    )
    if time_on_date:
        cleaned = time_on_date.group(1).strip()
        cleaned_date_only = cleaned
    # "10:00 AM, March 11, 2026" — time-first with comma: extract the date portion
    time_comma_date = re.match(
        r"^\d{1,2}:\d{2}\s*[APap][Mm],?\s+(.+)$", cleaned
    )
    if time_comma_date and _MONTH_RE.match(time_comma_date.group(1)):
        cleaned = time_comma_date.group(1).strip()
        cleaned_date_only = cleaned

    for text, fmt in (
        (cleaned, "%B %d, %Y at %I:%M %p"),
        (cleaned, "%B %d, %Y at %I:%M%p"),
        (cleaned, "%B %d, %Y, %I:%M %p"),
        (cleaned, "%Y-%m-%d %H:%M:%S"),
        (cleaned, "%m/%d/%Y %H:%M:%S"),
        (cleaned, "%m/%d/%Y %I:%M %p"),
        (cleaned, "%d-%b-%Y %H:%M:%S"),
        (cleaned, "%d-%b-%Y %H:%M"),
        (cleaned_date_only, "%d-%b-%Y"),
        (cleaned_date_only, "%B %d, %Y"),
        (cleaned_date_only, "%b %d, %Y"),
        (cleaned_date_only, "%m/%d/%Y"),
        (cleaned_date_only, "%Y-%m-%d"),
        # Additional real-world tender formats
        (cleaned_date_only, "%B %d %Y"),    # "March 11 2026" (no comma)
        (cleaned_date_only, "%d %B %Y"),    # "11 March 2026" (day-first)
        (cleaned_date_only, "%d %b %Y"),    # "11 Mar 2026"
        (cleaned_date_only, "%m-%d-%Y"),    # "03-11-2026"
        (cleaned_date_only, "%Y/%m/%d"),    # "2026/03/11"
        (cleaned_date_only, "%m/%d/%y"),    # "3/11/26" (2-digit year)
    ):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        # 2-digit years: strptime maps 26 → 2026, but guard against 1900s results.
        if parsed.year < 100:
            parsed = parsed.replace(year=parsed.year + 2000)
        return parsed
    return None


def _next_business_day(dt: datetime) -> datetime:
    """Advance dt to the next Monday if it falls on Saturday or Sunday."""
    weekday = dt.weekday()  # 0=Mon … 5=Sat, 6=Sun
    if weekday == 5:
        return dt + timedelta(days=2)
    if weekday == 6:
        return dt + timedelta(days=1)
    return dt


def _add_calendar_months(dt: datetime, months: int) -> datetime:
    """Add whole calendar months to a datetime (handles month-end clamping)."""
    new_month = dt.month + months
    new_year = dt.year + (new_month - 1) // 12
    new_month = (new_month - 1) % 12 + 1
    max_day = _calendar.monthrange(new_year, new_month)[1]
    return dt.replace(year=new_year, month=new_month, day=min(dt.day, max_day))


def _duration_to_datetime(duration_text: str, start_dt: datetime) -> datetime | None:
    """
    Detect a duration string and add it to *start_dt*.
    Returns the resulting datetime, or None if *duration_text* is not a duration.

    Recognised formats (case-insensitive, optional adjectives like "calendar"):
      • "180 days" / "180 calendar days" / "90 working days"
      • "8 weeks"
      • "12 months" / "6 months"
      • "1 year" / "2 years"
    If the text is already a parseable calendar date it is NOT treated as a duration.
    """
    if _parse_date_string(duration_text) is not None:
        return None  # Already a real calendar date — skip

    lower = duration_text.lower()
    # "One hundred eighty (180) calendar days" — trust the parenthesised numeral.
    lower = re.sub(r"[a-z\- ]+\((\d+)\)", r"\1", lower)
    # Spelled-out single-word counts: "one year", "two years", "six months".
    _WORDS = {
        "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
        "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
        "eleven": "11", "twelve": "12",
    }
    lower = re.sub(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b(?=\s+(?:calendar\s+|working\s+|business\s+|consecutive\s+)?(?:days?|weeks?|months?|mos\b|years?))",
        lambda m: _WORDS[m.group(1)],
        lower,
    )

    day_m = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:calendar\s+|working\s+|business\s+|consecutive\s+)*days?", lower
    )
    week_m = re.search(r"(\d+(?:\.\d+)?)\s*weeks?", lower)
    month_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:months?|mos\b)", lower)
    year_m = re.search(r"(\d+(?:\.\d+)?)\s*years?", lower)

    if day_m:
        return start_dt + timedelta(days=int(float(day_m.group(1))))
    if week_m:
        return start_dt + timedelta(weeks=int(float(week_m.group(1))))
    if month_m:
        return _add_calendar_months(start_dt, int(float(month_m.group(1))))
    if year_m:
        return _add_calendar_months(start_dt, int(float(year_m.group(1))) * 12)
    return None


def _apply_end_date_rule(spec_check_fields: dict[str, Any], dates: list[dict]) -> None:
    """
    Rule 3 – Project end date:
    If the document expresses the project end date as a duration (e.g. "180 calendar days",
    "12 months", "1 year", "CONTRACT TIME: 102 Calendar Days") rather than a calendar date,
    calculate the actual end date by adding that duration to the project start date.

    • If the end date is already a calendar date → leave it untouched.
    • If the end date is absent → do not fabricate one.
    • If the start date is non-specific / unparseable (e.g. "Fall 2026") → keep the
      duration text as-is because we cannot compute a meaningful offset.
    """
    end_entry = next(
        (
            d
            for d in dates
            if str(d.get("text") or "").strip().lower() == "project end date"
            or d.get("field_key") == "project_end_date_time"
        ),
        None,
    )
    if end_entry is None:
        return

    raw_date = str(end_entry.get("date") or "").strip()
    if not raw_date:
        return

    # Find project start date (may itself be calculated)
    start_entry = next(
        (
            d
            for d in dates
            if str(d.get("text") or "").strip().lower() == "project start date"
            or d.get("field_key") == "project_start_date_time"
        ),
        None,
    )
    if start_entry is None:
        return

    start_dt = _parse_date_string(str(start_entry.get("date") or ""))
    if start_dt is None:
        # Non-specific start date (e.g. "Fall 2026") — keep duration text unchanged
        return

    calc_dt = _duration_to_datetime(raw_date, start_dt)
    if calc_dt is None:
        return  # raw_date was already a calendar date or completely unrecognised

    calc_str = calc_dt.strftime("%B %d, %Y")
    # Keep the source duration visible (e.g. 102 Calendar Days) alongside the date.
    end_entry["date"] = f'{calc_str} (estimated from "{raw_date}")'
    end_entry["_calculated"] = True

    # Cap end date confidence by start date confidence (can't be more certain than the anchor).
    start_conf = start_entry.get("confidence")
    if isinstance(start_conf, int):
        end_entry["_parent_confidence_cap"] = start_conf


def _apply_start_date_rule(spec_check_fields: dict[str, Any], dates: list[dict]) -> None:
    """
    Rule 2 – Project start date:
    If the document does not state a project start date, calculate one from bid open date.
      • project value > $1 M  →  bid open date + 60 calendar days
      • project value ≤ $1 M  →  bid open date + 30 calendar days
      • project value absent   →  +30 days (default), flag _awaiting_project_value so
                                   the UI can show an input box for the user to supply the value.
    Weekend rule: if the resulting date falls on Sat/Sun, shift to the next Monday.
    If bid open date is missing or unparseable, leave project start date absent.
    """
    has_start = any(
        str(d.get("text") or "").strip().lower() == "project start date"
        and not is_placeholder_date(str(d.get("date") or ""))
        for d in dates
    )
    # Drop placeholder start rows so they do not block calculation.
    dates[:] = [
        d
        for d in dates
        if not (
            str(d.get("text") or "").strip().lower() == "project start date"
            and is_placeholder_date(str(d.get("date") or ""))
        )
    ]
    if has_start:
        return

    bid_open_entry = next(
        (d for d in dates if str(d.get("text") or "").strip().lower() == "bid open date"),
        None,
    )
    if bid_open_entry is None:
        return

    bid_open_date_str = str(bid_open_entry.get("date") or "")
    bid_open_dt = _parse_date_string(bid_open_date_str)
    if bid_open_dt is None:
        # Non-specific date (e.g. "Fall 2026", "March 2026") — can't offset by days,
        # so carry the raw text forward as the best available estimate.
        parent_conf = bid_open_entry.get("confidence")
        parent_conf_cap = int(parent_conf) if isinstance(parent_conf, int) else 72
        dates.append(
            {
                "text": "Project start date",
                "date": bid_open_date_str,
                "field_key": "project_start_date_time",
                "_calculated": True,
                "_days_offset": None,
                "_awaiting_project_value": False,
                "_parent_confidence_cap": parent_conf_cap,
                "sources": [],
            }
        )
        spec_check_fields["project_dates"] = dates
        return

    # Determine project value
    meta_items = spec_check_fields.get("project_metadata_items") or []
    value_item = next(
        (
            it for it in meta_items
            if "project value" in str(it.get("text") or "").lower()
            or "project_value" in str(it.get("text") or "").lower()
        ),
        None,
    )

    awaiting_project_value = False
    if value_item:
        parsed_amount = _parse_dollar_amount(str(value_item.get("text") or ""))
        days = 60 if (parsed_amount is not None and parsed_amount > 1_000_000) else 30
    else:
        awaiting_project_value = True
        days = 30  # default until user provides a value via the UI

    calc_dt = _next_business_day(bid_open_dt + timedelta(days=days))
    calc_str = calc_dt.strftime("%B %d, %Y")

    # Confidence capped by parent bid open date confidence (never exceed parent).
    parent_conf = bid_open_entry.get("confidence")
    parent_conf_cap = int(parent_conf) if isinstance(parent_conf, int) else 72

    dates.append(
        {
            "text": "Project start date",
            "date": f"{calc_str} (estimated — {days} calendar days from Bid open date)",
            "field_key": "project_start_date_time",
            "_calculated": True,
            "_days_offset": days,
            "_awaiting_project_value": awaiting_project_value,
            "_parent_confidence_cap": parent_conf_cap,
            "sources": [],
        }
    )
    spec_check_fields["project_dates"] = dates


def _attach_date_notes(spec_check_fields: dict[str, Any]) -> None:
    """Attach contextual notes to their date rows — after the date rules so
    derived rows (e.g. bid_open copied from bid_deadline) can't clobber them.

    If a note exists but the date itself was not found, create a shell row so
    the UI can show "Not found in document" for the date and still render Events.
    """
    notes = spec_check_fields.pop("_date_notes", None)
    if not isinstance(notes, dict) or not notes:
        return
    dates = spec_check_fields.get("project_dates") or []
    if not isinstance(dates, list):
        dates = []
        spec_check_fields["project_dates"] = dates

    for target_key, note in notes.items():
        note_text = str(note.get("text") or "").strip()
        if not note_text:
            continue
        row = next((d for d in dates if d.get("field_key") == target_key), None)
        if row is None:
            display = DEADLINE_LABEL_DISPLAY.get(target_key) or target_key.replace(
                "_", " "
            ).title()
            row = {
                "text": display,
                "field_key": target_key,
                "date": "",
                "_not_found": True,
                "sources": [],
            }
            dates.append(row)
        row["_note"] = note_text
        # Mandatory badge — only meaningful for events one attends.
        if target_key in ("pre_bid_deadline_date_time", "site_visit_date_time"):
            lowered = note_text.lower()
            if lowered.startswith("mandatory"):
                row["_mandatory"] = True
            elif lowered.startswith("non-mandatory") or lowered.startswith("not mandatory"):
                row["_mandatory"] = False
        source = note.get("source")
        if source:
            # Kept separate from the date's own sources so the Events block
            # shows its own citation (and jump target).
            row["_note_sources"] = [source]


def _attach_acquisition_events(spec_check_fields: dict[str, Any]) -> None:
    """Attach Document acquisition Events under the acquisition metadata row."""
    note = spec_check_fields.pop("_acquisition_events", None)
    if not isinstance(note, dict):
        return
    note_text = str(note.get("text") or "").strip()
    if not note_text:
        return
    items = spec_check_fields.get("project_metadata_items") or []
    row = next(
        (r for r in items if r.get("field_key") == ACQUISITION_EVENTS_TARGET),
        None,
    )
    if row is None:
        return
    row["_note"] = note_text
    source = note.get("source")
    if source:
        row["_note_sources"] = [source]


def finalize_spec_check_fields(spec_check_fields: dict[str, Any]) -> list[dict[str, Any]]:
    """Date rules, post-rules, per-field confidence, and date validation."""
    if not isinstance(spec_check_fields, dict):
        return []
    _apply_spec_check_date_rules(spec_check_fields)
    _attach_date_notes(spec_check_fields)
    _attach_acquisition_events(spec_check_fields)
    warnings = apply_spec_check_postrules(spec_check_fields)
    apply_confidence_to_spec_check_fields(spec_check_fields)
    date_warnings = validate_date_ordering(spec_check_fields)
    return _merge_warnings(warnings + build_field_warnings(spec_check_fields) + date_warnings)


def validate_date_ordering(spec_check_fields: dict[str, Any]) -> list[dict[str, Any]]:
    """Guardrail: flag impossible date orderings and out-of-range years.

    Runs after confidence scoring so it can override confidence on bad rows.
    Catches the date-inversion bug class (e.g. site-visit mislabeled as a later
    milestone) at runtime instead of relying on manual review.
    """
    warnings: list[dict[str, Any]] = []
    dates = spec_check_fields.get("project_dates")
    if not isinstance(dates, list):
        return warnings

    parsed: dict[str, Any] = {}
    for row in dates:
        if not isinstance(row, dict):
            continue
        fk = str(row.get("field_key") or "")
        dt = _parse_date_string(str(row.get("date") or ""))
        # Year sanity — clearly hallucinated dates get zeroed.
        if dt is not None and (dt.year < 2020 or dt.year > 2035):
            row["confidence"] = 0
            row["_date_out_of_range"] = True
            warnings.append({
                "field_key": fk,
                "bucket": "project_dates",
                "level": "warn",
                "message": f"Date year {dt.year} out of expected range (2020–2035); likely misread.",
            })
            continue
        if dt is not None and fk:
            parsed[fk] = dt

    def _flag(a: str, b: str, msg: str) -> None:
        if a in parsed and b in parsed and parsed[a] > parsed[b]:
            warnings.append({
                "field_key": a,
                "bucket": "project_dates",
                "level": "warn",
                "message": msg,
            })

    # Logical ordering constraints (only when both dates present and parseable).
    _flag("question_deadline_date_time", "bid_deadline_date_time",
          "Question deadline is after bid deadline — dates may be mislabeled.")
    _flag("pre_bid_deadline_date_time", "bid_deadline_date_time",
          "Pre-bid/site-visit date is after bid deadline — dates may be mislabeled.")
    _flag("project_start_date_time", "project_end_date_time",
          "Project start date is after project end date — dates may be swapped.")
    return warnings


# Extraction *_note label → the date field_key its note attaches to.
DATE_NOTE_TARGETS: dict[str, str] = {
    "bid_deadline_note": "bid_deadline_date_time",
    "bid_open_note": "bid_open_date_time",
    "pre_bid_note": "pre_bid_deadline_date_time",
    "site_visit_note": "site_visit_date_time",
    "question_deadline_note": "question_deadline_date_time",
    "award_note": "municipal_meeting_date_time",
}

# Acquisition Events label (eligibility_criteria) → metadata field_key.
ACQUISITION_EVENTS_LABEL = "project_document_acquisition_events"
ACQUISITION_EVENTS_TARGET = "project_document_acquisition_note"


_AFTER_AWARD_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:calendar\s+|working\s+|business\s+)?days?\s+after\s+award",
    re.IGNORECASE,
)


def _apply_award_date_anchor_rule(
    spec_check_fields: dict[str, Any], dates: list[dict]
) -> None:
    """
    Rule 4 — Award-date anchor:
    If municipal_meeting_date_time (award date) is a real calendar date AND
    project_start_date_time / project_end_date_time contain a phrase like
    "180 Days After Award", compute the actual calendar date using the award date
    as the anchor and update the row in-place.

    Leaves rows unchanged if:
    - No award date is present or it cannot be parsed.
    - The date value is already a calendar date (not a duration phrase).
    """
    # Find award date entry
    award_entry = next(
        (d for d in dates if d.get("field_key") == "municipal_meeting_date_time"),
        None,
    )
    if award_entry is None:
        return

    award_dt = _parse_date_string(str(award_entry.get("date") or ""))
    if award_dt is None:
        return

    award_conf = award_entry.get("confidence")
    parent_conf_cap = int(award_conf) if isinstance(award_conf, int) else 72

    for entry in dates:
        fk = entry.get("field_key") or ""
        if fk not in ("project_start_date_time", "project_end_date_time"):
            continue

        raw = str(entry.get("date") or "").strip()
        if not raw:
            continue

        # Already a real calendar date — do not overwrite
        if _parse_date_string(raw) is not None:
            continue

        m = _AFTER_AWARD_RE.search(raw)
        if not m:
            continue

        offset_days = int(float(m.group(1)))
        calc_dt = award_dt + timedelta(days=offset_days)
        calc_str = calc_dt.strftime("%B %d, %Y")
        award_str = award_dt.strftime("%B %d, %Y")

        entry["date"] = (
            f"{calc_str} (estimated — {offset_days} days after award date {award_str})"
        )
        entry["_calculated"] = True
        entry["_parent_confidence_cap"] = parent_conf_cap


def _apply_spec_check_date_rules(spec_check_fields: dict[str, Any]) -> None:
    """Apply all spec-check date derivation rules in order. Modifies in-place."""
    import copy

    dates: list[dict[str, Any]] = spec_check_fields.get("project_dates") or []
    if not isinstance(dates, list):
        return

    # Drop ungrounded bid_open rows (date not present in source → likely an issue
    # date mislabeled). They will be re-derived from the grounded bid_deadline below.
    dates[:] = [
        d for d in dates
        if not (
            str(d.get("text") or "").strip().lower() == "bid open date"
            and d.get("_date_grounded") is False
        )
    ]
    spec_check_fields["project_dates"] = dates

    # Rule 1: Bid open date — if absent, copy the (grounded) Bid deadline verbatim.
    has_bid_open = any(
        str(d.get("text") or "").strip().lower() == "bid open date"
        for d in dates
    )
    if not has_bid_open:
        bid_deadlines = [
            d for d in dates if str(d.get("text") or "").strip().lower() == "bid deadline"
        ]
        # Prefer a grounded bid_deadline as the derivation source.
        bid_deadline = next(
            (d for d in bid_deadlines if d.get("_date_grounded") is True),
            bid_deadlines[0] if bid_deadlines else None,
        )
        if bid_deadline is not None:
            bid_open = copy.deepcopy(bid_deadline)
            bid_open["text"] = "Bid open date"
            bid_open["field_key"] = field_key_for_deadline_label("Bid open date")
            # The copied row must not inherit the deadline's contextual note.
            bid_open.pop("_note", None)
            bid_open.pop("_mandatory", None)
            dates.append(bid_open)
            spec_check_fields["project_dates"] = dates

    # Rule 2: Project start date — only infer when explicitly enabled.
    if getattr(settings, "INTELLIGENCE_INFER_PROJECT_DATES", False):
        _apply_start_date_rule(spec_check_fields, dates)
        # Rule 3: Project end date — if stated as a duration, convert using start date.
        _apply_end_date_rule(spec_check_fields, dates)
        # Rule 4: Award-date anchor
        _apply_award_date_anchor_rule(spec_check_fields, dates)
    else:
        # Accuracy mode: drop calculated / ungrounded inferred dates.
        dates[:] = [
            d
            for d in dates
            if not (
                d.get("_calculated")
                and d.get("_date_grounded") is not True
            )
        ]
        spec_check_fields["project_dates"] = dates


def _make_source(item: dict[str, Any]) -> dict[str, Any]:
    s: dict[str, Any] = {}
    if item.get("page") is not None:
        s["page"] = item["page"]
    if item.get("section"):
        s["section"] = item["section"]
    if item.get("source_text"):
        s["source_text"] = item["source_text"]
    if item.get("citation_verified") is not None:
        s["citation_verified"] = item["citation_verified"]
    return s


def _extract_label_value(item: dict[str, Any]) -> tuple[str, str]:
    """Return (label, value) from a raw extraction item."""
    label = str(item.get("label") or "").strip().lower()
    value = str(item.get("value") or "").strip()
    requirement = str(item.get("requirement") or "").strip()
    if not label and ":" in requirement:
        label = requirement.split(":", 1)[0].strip().lower()
    if not value and ":" in requirement:
        value = requirement.split(":", 1)[1].strip()
    return label, value


def build_spec_check_fields_from_insights(insights: list) -> dict[str, Any]:
    """
    Deterministically build spec_check_fields directly from ExtractedInsight rows.

    Used as a fallback when the LLM summary does not return a populated
    spec_check_fields object (e.g. old-format summaries or LLM non-compliance).
    The result mirrors the structure expected by SpecCheckFields on the frontend.
    """
    by_type: dict[str, list[dict[str, Any]]] = {}
    for insight in insights:
        et: str = getattr(insight, "extraction_type", None) or ""
        if not et:
            continue
        items: list[dict[str, Any]] = (
            (getattr(insight, "payload", None) or {}).get("items") or []
        )
        by_type.setdefault(et, []).extend(items)

    project_metadata_items: list[dict[str, Any]] = []
    project_people_items: list[dict[str, Any]] = []
    project_size_location_items: list[dict[str, Any]] = []
    project_dates: list[dict[str, Any]] = []
    bond_items: list[dict[str, Any]] = []
    set_aside_items: list[dict[str, Any]] = []

    seen_meta: set[str] = set()
    seen_people: set[str] = set()
    seen_size: set[str] = set()
    seen_dates: set[str] = set()
    seen_bonds: set[str] = set()
    seen_set_asides: set[str] = set()

    # Acquisition Events (logistics paragraph) — attached later to the
    # project_document_acquisition_note row, same pattern as date *_notes.
    acquisition_events_item: dict[str, Any] | None = None
    for et in ("eligibility_criteria", "mandatory_documents"):
        for item in by_type.get(et, []):
            label, value = _extract_label_value(item)
            if label != ACQUISITION_EVENTS_LABEL or not value:
                continue
            if acquisition_events_item is None or len(value) > len(
                str(acquisition_events_item.get("value") or "")
            ):
                acquisition_events_item = item

    # ── Identity / metadata from eligibility + mandatory documents ───────────
    for et in ("eligibility_criteria", "mandatory_documents"):
        for item in by_type.get(et, []):
            label, value = _extract_label_value(item)
            if not label or not value:
                continue
            if label == ACQUISITION_EVENTS_LABEL:
                continue
            fdef = field_def(label)
            if fdef is None:
                continue
            if fdef.name == "project_description":
                continue
            if fdef.name == "project_document_acquisition_note" and not is_valid_acquisition_note(
                value
            ):
                continue
            source = _make_source(item)
            entry: dict[str, Any] = enrich_spec_check_field_entry(
                {
                    "text": f"{fdef.display_label}: {value}",
                    "sources": [source] if source else [],
                },
                field_key=fdef.name,
                source_item=item,
            )
            key = f"{fdef.name}:{value[:80]}"
            if fdef.bucket == "project_people_items":
                if key not in seen_people:
                    seen_people.add(key)
                    project_people_items.append(entry)
            elif fdef.bucket == "project_metadata_items":
                if key not in seen_meta:
                    seen_meta.add(key)
                    project_metadata_items.append(entry)

    # ── Project description from scope_of_work only ─────────────────────────
    for item in by_type.get("scope_of_work", []):
        label, value = _extract_label_value(item)
        if label != "project_description" or not value:
            continue
        fdef = field_def(label)
        if fdef is None:
            continue
        key = f"project_description:{value[:400]}"
        if key in seen_meta:
            continue
        seen_meta.add(key)
        source = _make_source(item)
        project_metadata_items.append(
            enrich_spec_check_field_entry(
                {
                    "text": f"{fdef.display_label}: {value}",
                    "sources": [source] if source else [],
                },
                field_key=fdef.name,
                source_item=item,
            )
        )

    # ── (removed combined eligibility/scope/mandatory loop) ─────────────────
    # ── Project value from payment_terms ─────────────────────────────────────
    for item in by_type.get("payment_terms", []):
        label, value = _extract_label_value(item)
        if not value:
            continue
        # Payment terms may emit "project_value" with or without label/value.
        fdef = field_def(label) if label else None
        display = fdef.display_label if fdef else "Project value"
        text = f"{display}: {value}"
        key = f"project_value:{value[:80]}"
        if key not in seen_meta:
            seen_meta.add(key)
            source = _make_source(item)
            project_metadata_items.append(
                enrich_spec_check_field_entry(
                    {"text": text, "sources": [source] if source else []},
                    field_key="project_value",
                    source_item=item,
                )
            )

    # ── Size / location from technical_requirements ──────────────────────────
    for item in by_type.get("technical_requirements", []):
        label, value = _extract_label_value(item)
        if not label or not value:
            continue
        fdef = field_def(label)
        if fdef is None or fdef.bucket != "project_size_location_items":
            continue
        key = f"{fdef.name}:{value[:80]}"
        if key not in seen_size:
            seen_size.add(key)
            source = _make_source(item)
            project_size_location_items.append(
                enrich_spec_check_field_entry(
                    {
                        "text": f"{fdef.display_label}: {value}",
                        "sources": [source] if source else [],
                    },
                    field_key=fdef.name,
                    source_item=item,
                )
            )

    # ── Dates from submission_deadlines ──────────────────────────────────────
    def _date_supported_by_source(date_val: str, source_text: str) -> bool:
        """True when the date value is actually present in its own source_text.

        Catches hallucinated/mis-attached dates: e.g. an LLM labels a chunk's
        'Reminder to monitor the posting' text as bid_deadline but attaches the
        document's issue date (02/12) — the date is not in that source. Such items
        must not win dedup over a correctly grounded date.
        """
        if not date_val or not source_text:
            return False
        src = re.sub(r"\s+", " ", source_text.lower())
        dv = date_val.lower()
        # Numeric M/D[/Y] or D-Mon patterns from the date value
        for m in re.findall(r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?", dv):
            core = re.match(r"\d{1,2}[/-]\d{1,2}", m).group(0)
            if core in src:
                return True
        # Month-name + day-number (e.g. "february ... 12")
        months = ("january february march april may june july august "
                  "september october november december").split()
        for mon in months:
            if mon in dv and mon in src:
                day = re.search(r"\b(\d{1,2})\b", dv)
                if day is None or re.search(rf"\b{day.group(1)}\b", src):
                    return True
        # ISO yyyy-mm-dd
        for iso in re.findall(r"\d{4}-\d{2}-\d{2}", dv):
            if iso in src:
                return True
        return False

    # Contextual notes around each date event (location / online details,
    # contact person, mandatory-or-not, instructions) — attached to their
    # date row below rather than shown as their own date rows.
    note_items: dict[str, dict[str, Any]] = {}

    for item in by_type.get("submission_deadlines", []):
        # Some extraction items may omit the explicit `label` field but still use
        # requirement format "<label>: <date>". Fall back to parsing it so we
        # don't drop dates like Bid deadline.
        raw_label = str(item.get("label") or "").strip().lower()
        if not raw_label:
            raw_label, _value = _extract_label_value(item)
        if raw_label in DATE_NOTE_TARGETS:
            note_val = str(item.get("value") or "").strip()
            prior = note_items.get(raw_label)
            if note_val and (
                prior is None or len(note_val) > len(str(prior.get("value") or ""))
            ):
                note_items[raw_label] = item
            continue
        display = DEADLINE_LABEL_DISPLAY.get(raw_label)
        if not display:
            continue
        date_val = str(item.get("date_time") or item.get("value") or "").strip()
        if not date_val:
            continue
        # Heuristic: "Site visit" text must not become Award date (municipal_meeting).
        # Check raw_label so this works regardless of display label renaming.
        if raw_label == "municipal_meeting_date_time":
            src = str(item.get("source_text") or "").lower()
            if "site visit" in src or "site-visit" in src or "site visit date" in src:
                display = "Pre-bid deadline"
        key = f"{display}:{date_val[:80]}"
        if key not in seen_dates:
            seen_dates.add(key)
            source = _make_source(item)
            # Date-grounding guard: a date is trustworthy only if its value actually
            # appears in its own source_text. Tag row-level so dedup can prefer a
            # grounded date over an ungrounded one even when the latter has higher
            # LLM confidence (e.g. issue date 02/12 mislabeled as bid_deadline).
            date_grounded = bool(
                source and _date_supported_by_source(date_val, str(source.get("source_text") or ""))
            )
            if source and not date_grounded:
                source["citation_verified"] = False
            project_dates.append(
                enrich_spec_check_field_entry(
                    {
                        "text": display,
                        "date": date_val,
                        "_date_grounded": date_grounded,
                        "sources": [source] if source else [],
                    },
                    field_key=field_key_for_deadline_label(display),
                    source_item=item,
                )
            )

    # Stash notes for attachment in finalize_spec_check_fields — attaching here
    # is too early: the date rules (e.g. bid_open derived by copying the
    # bid_deadline row) run later and would clobber or duplicate notes.
    date_notes: dict[str, dict[str, Any]] = {
        DATE_NOTE_TARGETS[label]: {
            "text": str(item.get("value") or "").strip(),
            "source": _make_source(item),
        }
        for label, item in note_items.items()
    }

    # ── Bonds from penalties_and_risks + mandatory_documents ─────────────────
    for et in ("penalties_and_risks", "mandatory_documents"):
        for item in by_type.get(et, []):
            raw_label = str(item.get("label") or "").strip().lower()
            display = BOND_LABEL_DISPLAY.get(raw_label)
            if not display:
                continue
            bond_detail = str(item.get("value") or item.get("source_text") or "").strip()
            if not bond_detail:
                req = str(item.get("requirement") or "").strip()
                if ":" in req:
                    bond_detail = req.split(":", 1)[1].strip()
            if not bond_detail:
                continue
            key = f"{display}:{bond_detail[:80]}"
            if key not in seen_bonds:
                seen_bonds.add(key)
                source = _make_source(item)
                bond_items.append(
                    enrich_spec_check_field_entry(
                        {
                            "text": display,
                            "date": bond_detail,
                            "sources": [source] if source else [],
                        },
                        field_key=field_key_for_bond_label(display),
                        source_item=item,
                    )
                )

    # ── Set-asides from set_asides extraction ────────────────────────────────
    for item in by_type.get("set_asides", []):
        raw_label = str(item.get("label") or "").strip().lower()
        if not raw_label:
            # requirement format: "set_aside_sbe: <text>"
            req = str(item.get("requirement") or "").strip()
            if ":" in req:
                raw_label = req.split(":", 1)[0].strip().lower()
        display = SET_ASIDE_LABEL_DISPLAY.get(raw_label)
        if not display:
            continue
        detail = str(item.get("value") or item.get("source_text") or "").strip()
        if not detail:
            req = str(item.get("requirement") or "").strip()
            detail = req.split(":", 1)[1].strip() if ":" in req else req
        if not detail:
            continue
        key = f"{raw_label}:{detail[:80]}"
        if key not in seen_set_asides:
            seen_set_asides.add(key)
            source = _make_source(item)
            # Common "set_aside" field: value already names the program
            # ("MBE: 10% goal") — avoid a redundant "Set-aside:" prefix.
            text = detail if raw_label == "set_aside" else f"{display}: {detail}"
            set_aside_items.append(
                enrich_spec_check_field_entry(
                    {
                        "text": text,
                        "sources": [source] if source else [],
                    },
                    field_key="set_aside" if raw_label == "set_aside" else raw_label,
                    source_item=item,
                )
            )

    return {
        "project_metadata_items": project_metadata_items,
        "project_people_items": project_people_items,
        "project_size_location_items": project_size_location_items,
        "project_dates": project_dates,
        "bond_items": bond_items,
        "set_aside_items": set_aside_items,
        # Consumed (and removed) by finalize_spec_check_fields.
        "_date_notes": date_notes,
        "_acquisition_events": (
            {
                "text": str(acquisition_events_item.get("value") or "").strip(),
                "source": _make_source(acquisition_events_item),
            }
            if acquisition_events_item is not None
            else None
        ),
    }


def rebind_spec_check_sources_from_extractions(
    spec_check_fields: dict[str, Any],
    insights: list,
) -> None:
    """
    Restore extraction-grounded citations on spec_check_fields rows.

    Prevents enforce_verbatim_summary_sources from swapping deadline citations
    to the wrong table row when fuzzy matching similar timeline entries.
    """
    by_type: dict[str, list[dict[str, Any]]] = {}
    for insight in insights:
        et: str = getattr(insight, "extraction_type", None) or ""
        if not et:
            continue
        items: list[dict[str, Any]] = (
            (getattr(insight, "payload", None) or {}).get("items") or []
        )
        by_type.setdefault(et, []).extend(items)

    def _best_item_for_label(label: str) -> dict[str, Any] | None:
        matches = [
            it
            for it in by_type.get("submission_deadlines", [])
            if str(it.get("label") or "").strip().lower() == label
        ]
        if not matches:
            return None
        return max(
            matches,
            key=lambda it: (
                1 if it.get("citation_verified") else 0,
                float(it.get("confidence") or 0),
            ),
        )

    dates = spec_check_fields.get("project_dates") or []
    if isinstance(dates, list):
        for row in dates:
            if not isinstance(row, dict):
                continue
            fk = str(row.get("field_key") or "").strip()
            if not fk:
                continue
            lookup_label = fk
            if fk == "bid_open_date_time":
                lookup_label = "bid_deadline_date_time"
            item = _best_item_for_label(lookup_label)
            if item is None:
                continue
            source = _make_source(item)
            if source.get("source_text"):
                row["sources"] = [source]

    bonds = spec_check_fields.get("bond_items") or []
    bond_items_raw = (
        (by_type.get("penalties_and_risks") or [])
        + (by_type.get("mandatory_documents") or [])
    )
    if isinstance(bonds, list):
        for row in bonds:
            if not isinstance(row, dict):
                continue
            fk = str(row.get("field_key") or "").strip()
            if not fk:
                continue
            matches = [
                it for it in bond_items_raw
                if str(it.get("label") or "").strip().lower() == fk
            ]
            if not matches:
                continue
            item = max(
                matches,
                key=lambda it: (
                    1 if it.get("citation_verified") else 0,
                    float(it.get("confidence") or 0),
                ),
            )
            source = _make_source(item)
            if source.get("source_text"):
                row["sources"] = [source]


def postprocess_summary(
    data: dict[str, Any],
    insights: list,
    document=None,
) -> dict[str, Any]:
    if document is not None:
        reapply_summary_citations(data, insights, document)
    else:
        lookup = build_extraction_citation_lookup(insights)
        canonicalize_summary_sources(data, lookup)

    # ── Spec-check finalize (date rules, post-rules, confidence) ───────────
    spec_fields = data.get("spec_check_fields")
    if isinstance(spec_fields, dict):
        warnings = finalize_spec_check_fields(spec_fields)
        rebind_spec_check_sources_from_extractions(spec_fields, insights)
        apply_confidence_to_spec_check_fields(spec_fields)
        if warnings:
            meta = data.setdefault("_meta", {})
            existing = meta.get("field_warnings") or []
            if isinstance(existing, list):
                meta["field_warnings"] = existing + warnings
            else:
                meta["field_warnings"] = warnings

    return data





