# Task 1 Report — Address-completeness tie-break + subset-drop in location merge

**Status:** DONE

## Files changed

### 1. `backend/apps/intelligence/services/spec_check_postrules.py`

- **Added** module-level regex constants after `_row_display_value`:
  - `_STREET_NUMBER_RE`, `_STATE_ZIP_RE`, `_BARE_CITY_RE`
- **Added** helper `_address_completeness_score(value: str) -> int` (after `_row_display_value`).
  Scores a location string: street number (+2), comma-separated parts (+1), state+ZIP (+1);
  a bare "City of X" / "In the City of X" with no other detail scores 0.
- **Added** helper `_merge_location_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]`
  directly above `merge_spec_check_multi_fields`. Ranks `project_location` candidates by
  completeness (tie broken by `_row_quality_key`), then keeps values dropping any that are a
  literal subset of an already-kept value OR a bare city/jurisdiction (completeness 0) once a
  more-complete location is already kept. Genuinely distinct sites (both score > 0) are kept and
  `; `-joined. Other fields' merges are untouched.
- **Modified** the `project_location` branch of `merge_spec_check_multi_fields`
  (the `size = spec_check_fields.get("project_size_location_items")` block) to call
  `_merge_location_rows(size)` instead of `_merge_rows_by_field_key(size, "project_location", joiner="; ")`.
  No other field's merge changed; `_merge_rows_by_field_key` remains in use for
  solicitation number, acquisition note, and description.

### 2. `backend/apps/intelligence/tests/test_spec_check_postrules.py`

- **Modified** the import block to also import `_address_completeness_score` and
  `merge_spec_check_multi_fields`.
- **Appended** three new tests (existing tests untouched):
  - `test_address_completeness_score_ranks_full_address_highest`
  - `test_location_merge_prefers_full_address_and_drops_bare_city`
  - `test_location_merge_keeps_distinct_sites`

## Deviation from the plan (authorized)

The plan's `_merge_location_rows` (Step 4, verbatim) used only a literal-substring subset check.
`"in the city of bell gardens"` is NOT a literal substring of
`"john anson ford park, 8000 park lane, bell gardens, ca 90201"`, so the bare-city row was never
dropped and `test_location_merge_prefers_full_address_and_drops_bare_city` failed (12 passed,
1 failed) even with the plan's code transcribed exactly. This was surfaced to the coordinator, who
authorized adding a second drop condition: a bare-city/jurisdiction candidate (completeness 0) is
dropped once a more-complete location (completeness > 0) is already kept. The literal-substring
check was retained. No test was weakened or edited to pass.

Added drop logic in `_merge_location_rows`:

```python
        # Drop a bare city/jurisdiction (completeness 0) once a more-complete
        # location is already kept — its phrasing ("in the city of X") need not
        # be a literal substring of the fuller address.
        if _address_completeness_score(val) == 0 and any(
            _address_completeness_score(k) > 0 for k in kept_values
        ):
            continue
```

## Test commands and output

### Step 2 — confirm new tests fail (before implementation)

```
cd backend && python -m pytest \
  apps/intelligence/tests/test_spec_check_postrules.py::test_address_completeness_score_ranks_full_address_highest \
  apps/intelligence/tests/test_spec_check_postrules.py::test_location_merge_prefers_full_address_and_drops_bare_city \
  apps/intelligence/tests/test_spec_check_postrules.py::test_location_merge_keeps_distinct_sites -v
```

Result: collection ERROR — `ImportError: cannot import name '_address_completeness_score'`
(expected pre-implementation failure per the plan).

### Step 5 — final run (full postrules file)

```
cd backend && python -m pytest apps/intelligence/tests/test_spec_check_postrules.py -v
```

Full output:

```
collected 13 items

apps/intelligence/tests/test_spec_check_postrules.py::test_parse_date_string_cst_est_military PASSED [  7%]
apps/intelligence/tests/test_spec_check_postrules.py::test_dedupe_singleton_pre_bid_deadline PASSED [ 15%]
apps/intelligence/tests/test_spec_check_postrules.py::test_tag_date_kinds PASSED [ 23%]
apps/intelligence/tests/test_spec_check_postrules.py::test_start_date_calculated_with_cst_bid_open PASSED [ 30%]
apps/intelligence/tests/test_spec_check_postrules.py::test_build_field_warnings_missing_bid_deadline PASSED [ 38%]
apps/intelligence/tests/test_spec_check_postrules.py::test_is_placeholder_date PASSED [ 46%]
apps/intelligence/tests/test_spec_check_postrules.py::test_acquisition_note_filter PASSED [ 53%]
apps/intelligence/tests/test_spec_check_postrules.py::test_merge_solicitation_numbers PASSED [ 61%]
apps/intelligence/tests/test_spec_check_postrules.py::test_placeholder_start_date_replaced_with_calculated PASSED [ 69%]
apps/intelligence/tests/test_spec_check_postrules.py::test_rebind_bid_deadline_citation_from_extraction PASSED [ 76%]
apps/intelligence/tests/test_spec_check_postrules.py::test_address_completeness_score_ranks_full_address_highest PASSED [ 84%]
apps/intelligence/tests/test_spec_check_postrules.py::test_location_merge_prefers_full_address_and_drops_bare_city PASSED [ 92%]
apps/intelligence/tests/test_spec_check_postrules.py::test_location_merge_keeps_distinct_sites PASSED [100%]

============================= 13 passed in 1.98s ==============================
```

**13 passed (10 pre-existing + 3 new).**

---

## Post-review fixes (coordinator round 2)

Task review found a Critical bug introduced by round-1's fix, plus a vacuous test line.

### Critical: distinct non-address sites wrongly dropped
Round-1's drop condition keyed on `_address_completeness_score(val) == 0`. But road segments
("Main Street from 1st Avenue to 5th Avenue"), point-to-point ("SR-91 between Exit 12 and Exit 18"),
and building-name-only locations also score 0 — so they were dropped whenever another site scored
> 0, violating "keep genuinely distinct sites." "Score 0" is not the same as "bare
city/jurisdiction."

Fixes in `spec_check_postrules.py`:
- **Added** helper `_is_bare_jurisdiction(value: str) -> bool` next to `_address_completeness_score`
  — keys off `_BARE_CITY_RE` + no comma + no street number.
- **Replaced** the zero-score drop in `_merge_location_rows` with a bare-jurisdiction drop:

  ```python
          # Drop a bare city/jurisdiction once ANY more-specific location is kept —
          # a road segment or building name (score 0 but NOT a bare jurisdiction) is
          # a distinct site and must be kept.
          if _is_bare_jurisdiction(val) and kept_values:
              continue
  ```

### Important: vacuous assertion fixed
In `test_location_merge_prefers_full_address_and_drops_bare_city`, the final assertion
`value.count("BELL GARDENS") == 0 or value.upper().count("CITY OF") == 0` always passed (mixed-case
`value`). Replaced with `assert value.upper().count("CITY OF") == 0`.

### New regression test
Appended `test_location_merge_keeps_distinct_road_and_point_sites` — proves a road segment and a
point-to-point site (both score 0, neither a bare jurisdiction) both survive the merge.

### Verification

```
cd backend && python -m pytest apps/intelligence/tests/test_spec_check_postrules.py -v
```

```
collected 14 items

apps/intelligence/tests/test_spec_check_postrules.py::test_parse_date_string_cst_est_military PASSED [  7%]
apps/intelligence/tests/test_spec_check_postrules.py::test_dedupe_singleton_pre_bid_deadline PASSED [ 14%]
apps/intelligence/tests/test_spec_check_postrules.py::test_tag_date_kinds PASSED [ 21%]
apps/intelligence/tests/test_spec_check_postrules.py::test_start_date_calculated_with_cst_bid_open PASSED [ 28%]
apps/intelligence/tests/test_spec_check_postrules.py::test_build_field_warnings_missing_bid_deadline PASSED [ 35%]
apps/intelligence/tests/test_spec_check_postrules.py::test_is_placeholder_date PASSED [ 42%]
apps/intelligence/tests/test_spec_check_postrules.py::test_acquisition_note_filter PASSED [ 50%]
apps/intelligence/tests/test_spec_check_postrules.py::test_merge_solicitation_numbers PASSED [ 57%]
apps/intelligence/tests/test_spec_check_postrules.py::test_placeholder_start_date_replaced_with_calculated PASSED [ 64%]
apps/intelligence/tests/test_spec_check_postrules.py::test_rebind_bid_deadline_citation_from_extraction PASSED [ 71%]
apps/intelligence/tests/test_spec_check_postrules.py::test_address_completeness_score_ranks_full_address_highest PASSED [ 78%]
apps/intelligence/tests/test_spec_check_postrules.py::test_location_merge_prefers_full_address_and_drops_bare_city PASSED [ 85%]
apps/intelligence/tests/test_spec_check_postrules.py::test_location_merge_keeps_distinct_sites PASSED [ 92%]
apps/intelligence/tests/test_spec_check_postrules.py::test_location_merge_keeps_distinct_road_and_point_sites PASSED [100%]

============================= 14 passed in 0.54s ==============================
```

**14 passed (10 pre-existing + 4 new).**
