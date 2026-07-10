# Location & Description Precision Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `project_location` capture the most specific location (full address, not bare city) and `project_description` stop bleeding adjacent content, via prompt taxonomy examples plus a deterministic dedup tie-break.

**Architecture:** Three changes on the existing spec-check pipeline: (1) rewrite the `technical_requirements` location prompt + few-shot with a location taxonomy; (2) tighten the `scope_of_work` prompt with a section boundary; (3) add an address-completeness tie-break + subset-drop to the `project_location` merge branch in post-rules. No new modules, no LangGraph, no reindex.

**Tech Stack:** Python 3.11, Django, pytest. LLM prompts are plain Python string constants.

## Global Constraints

- Repo is **not** a git repo — do **not** run `git add` / `git commit`. Each task's final step is running the test suite green instead of committing.
- Run all tests from the `backend/` directory. Runner: `python -m pytest` (Django wired via `apps/intelligence/tests/conftest.py`, `DJANGO_SETTINGS_MODULE=config.settings.development`).
- Post-rule functions in `spec_check_postrules.py` are pure (no DB); tests import them directly, no `django_db` fixture.
- Do not change existing extraction labels or field keys: `project_location`, `project_square_footage`, `project_description` stay exactly as-is.
- A2 changes must be scoped to the `project_location` merge branch only — do not alter merge/dedup behavior of any other field.
- Preserve existing behavior of all passing tests: `test_spec_check_postrules.py`, `test_extraction_retrieval.py`.

---

### Task 1: Address-completeness tie-break + subset-drop in location merge

**Files:**
- Modify: `backend/apps/intelligence/services/spec_check_postrules.py` (add `_address_completeness_score`; rewrite the `project_location` branch of `merge_spec_check_multi_fields`, ~lines 286-290)
- Test: `backend/apps/intelligence/tests/test_spec_check_postrules.py`

**Interfaces:**
- Consumes: existing `_row_display_value(row) -> str`, `_row_quality_key(row) -> tuple`, `merge_spec_check_multi_fields(spec_check_fields: dict) -> None` (mutates in place), `apply_spec_check_postrules(spec) -> list[warnings]`.
- Produces: `_address_completeness_score(value: str) -> int` (module-level helper); `merge_spec_check_multi_fields` keeps the most-complete `project_location` value, drops any candidate whose normalized value is a substring of a more-complete kept value, and keeps genuinely distinct locations `; `-joined.

- [ ] **Step 1: Write the failing tests**

Add to `backend/apps/intelligence/tests/test_spec_check_postrules.py`:

```python
from apps.intelligence.services.spec_check_postrules import (
    _address_completeness_score,
    merge_spec_check_multi_fields,
)


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
    assert value.count("BELL GARDENS") == 0 or value.upper().count("CITY OF") == 0


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest apps/intelligence/tests/test_spec_check_postrules.py::test_address_completeness_score_ranks_full_address_highest apps/intelligence/tests/test_spec_check_postrules.py::test_location_merge_prefers_full_address_and_drops_bare_city apps/intelligence/tests/test_spec_check_postrules.py::test_location_merge_keeps_distinct_sites -v`
Expected: FAIL — `ImportError: cannot import name '_address_completeness_score'` (and the merge tests fail once import is added, because current merge blindly `; `-joins).

- [ ] **Step 3: Add the `_address_completeness_score` helper**

In `backend/apps/intelligence/services/spec_check_postrules.py`, after `_row_display_value` (~line 165), add:

```python
_STREET_NUMBER_RE = re.compile(r"\b\d{2,6}\b")
_STATE_ZIP_RE = re.compile(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b")
_BARE_CITY_RE = re.compile(r"^\s*(in\s+the\s+city\s+of|city\s+of)\b", re.IGNORECASE)


def _address_completeness_score(value: str) -> int:
    """Higher = more complete/specific location string.

    Signals: street number (+2), comma-separated parts (+1), state+ZIP (+1).
    A bare 'City of X' / 'In the City of X' with no other detail scores 0.
    """
    v = (value or "").strip()
    if not v:
        return 0
    if _BARE_CITY_RE.match(v) and "," not in v and not _STREET_NUMBER_RE.search(v):
        return 0
    score = 0
    if _STREET_NUMBER_RE.search(v):
        score += 2
    if "," in v:
        score += 1
    if _STATE_ZIP_RE.search(v):
        score += 1
    return score
```

- [ ] **Step 4: Rewrite the `project_location` merge branch**

In `merge_spec_check_multi_fields` (~lines 286-290), replace the location block:

```python
    size = spec_check_fields.get("project_size_location_items") or []
    if isinstance(size, list):
        spec_check_fields["project_size_location_items"] = _merge_rows_by_field_key(
            size, "project_location", joiner="; "
        )
```

with a completeness-aware merge:

```python
    size = spec_check_fields.get("project_size_location_items") or []
    if isinstance(size, list):
        spec_check_fields["project_size_location_items"] = _merge_location_rows(size)
```

Then add the helper directly above `merge_spec_check_multi_fields`:

```python
def _merge_location_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge project_location rows: prefer the most complete value, drop any
    candidate that is a subset of a more-complete kept value, keep distinct sites.
    """
    matching = [r for r in rows if str(r.get("field_key") or "") == "project_location"]
    if len(matching) <= 1:
        return rows
    others = [r for r in rows if str(r.get("field_key") or "") != "project_location"]

    # Rank candidates: most complete first; tie broken by existing quality key.
    ranked = sorted(
        matching,
        key=lambda r: (
            _address_completeness_score(_row_display_value(r)),
            _row_quality_key(r),
        ),
        reverse=True,
    )

    kept_values: list[str] = []
    for row in ranked:
        val = _row_display_value(row).strip()
        if not val:
            continue
        norm = re.sub(r"\s+", " ", val.lower())
        # Drop if this value is a subset of an already-kept, more-complete value.
        if any(norm in re.sub(r"\s+", " ", k.lower()) for k in kept_values):
            continue
        kept_values.append(val)

    if not kept_values:
        return others

    winner = ranked[0]
    fdef = FIELD_DEFS.get("project_location")
    label = fdef.display_label if fdef else "Project location"
    merged = dict(winner)
    merged["text"] = f"{label}: {'; '.join(kept_values)}"
    merged["field_key"] = "project_location"
    return others + [merged]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && python -m pytest apps/intelligence/tests/test_spec_check_postrules.py -v`
Expected: PASS — the three new tests plus all pre-existing postrule tests.

---

### Task 2: Location prompt taxonomy (instruction + few-shot)

**Files:**
- Modify: `backend/apps/intelligence/prompts/templates.py` — `EXTRACTION_TYPE_INSTRUCTIONS["technical_requirements"]` (~lines 187-197) and `EXTRACTION_FEW_SHOT["technical_requirements"]` (~lines 303-314)
- Test: `backend/apps/intelligence/tests/test_operational_scope_guidance.py` (string-content assertions on the prompt constants; no LLM call)

**Interfaces:**
- Consumes: `EXTRACTION_TYPE_INSTRUCTIONS: dict[str, str]`, `EXTRACTION_FEW_SHOT: dict[str, str]` (module-level dicts in `templates.py`).
- Produces: updated string constants only. No signature changes.

- [ ] **Step 1: Write the failing test**

Add a new test file `backend/apps/intelligence/tests/test_location_prompt.py`:

```python
from apps.intelligence.prompts.templates import (
    EXTRACTION_FEW_SHOT,
    EXTRACTION_TYPE_INSTRUCTIONS,
)


def test_location_instruction_states_specificity_rules():
    instr = EXTRACTION_TYPE_INSTRUCTIONS["technical_requirements"].lower()
    # Must tell the model to prefer the most specific location.
    assert "most specific" in instr
    # Bare city is a fallback only.
    assert "fallback" in instr
    # Distinct sites emitted separately.
    assert "distinct" in instr


def test_location_few_shot_covers_taxonomy():
    shot = EXTRACTION_FEW_SHOT["technical_requirements"]
    lower = shot.lower()
    # Full address example present.
    assert "8000 park lane" in lower
    # Road segment example present.
    assert "from" in lower and "to" in lower
    # Point-to-point example present.
    assert "between" in lower
    # Negative case: bare city alongside full address -> address only.
    assert "city of" in lower
    # Allowed labels unchanged.
    assert "project_location" in shot
    assert "project_square_footage" in shot
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest apps/intelligence/tests/test_location_prompt.py -v`
Expected: FAIL — current instruction lacks "most specific"/"fallback"/"distinct"; few-shot lacks road-segment/point-to-point/negative-city examples.

- [ ] **Step 3: Rewrite the instruction**

Replace `EXTRACTION_TYPE_INSTRUCTIONS["technical_requirements"]` (~lines 187-197) with:

```python
    "technical_requirements": (
        "Extract ONLY project_square_footage and project_location. "
        "For project_location, capture the MOST SPECIFIC location of the work for each "
        "distinct work site. Prefer, in order: a full street address, then facility/building "
        "name plus address, then a road segment or point-to-point description, then a building "
        "or site name alone. A bare city or jurisdiction (e.g. 'In the City of Bell Gardens') "
        "is a FALLBACK — use it ONLY when no more specific location appears anywhere in the text. "
        "Do NOT emit both a bare city and a full address for the same site; the full address "
        "already contains the city. If the document describes MULTIPLE DISTINCT work sites, "
        "emit one project_location item per distinct site. "
        "If facility name, street, and city/state appear together for one site, combine them "
        "into a single comma-separated project_location value. "
        "Do NOT capture detailed scope-of-work cable runs or equipment lists as a location. "
        "CRITICAL: every item MUST set label = 'project_location' or label = 'project_square_footage' exactly. "
        "Set requirement = '<label>: <value>' and value = extracted text. "
        "Field names: project_square_footage, project_location."
    ),
```

- [ ] **Step 4: Rewrite the few-shot with taxonomy examples**

Replace `EXTRACTION_FEW_SHOT["technical_requirements"]` (~lines 303-314) with:

```python
    "technical_requirements": (
        "Example A — full address (preferred over bare city):\n"
        'Input: "IN THE CITY OF BELL GARDENS. Ford Park East Playground is located at '
        'John Anson Ford Park, 8000 Park Lane, Bell Gardens, CA 90201. Area approx 12,000 sq ft."\n'
        'Output: {"items": ['
        '{"requirement": "project_location: John Anson Ford Park, 8000 Park Lane, Bell Gardens, CA 90201", '
        '"label": "project_location", '
        '"value": "John Anson Ford Park, 8000 Park Lane, Bell Gardens, CA 90201", '
        '"source_text": "Ford Park East Playground is located at John Anson Ford Park, 8000 Park Lane, Bell Gardens, CA 90201", '
        '"confidence": 0.95}, '
        '{"requirement": "project_square_footage: approx 12,000 sq ft", '
        '"label": "project_square_footage", "value": "approx 12,000 sq ft", '
        '"source_text": "Area approx 12,000 sq ft", "confidence": 0.9}]}\n'
        'NOTE: "IN THE CITY OF BELL GARDENS" is a bare jurisdiction and is correctly OMITTED '
        "because the full address above already contains the city.\n"
        "Example B — facility name + address (combine into one value):\n"
        'Input: "Union Hill Elementary School, 5242 South State Hwy ZZ, Republic, MO."\n'
        'Output: {"items": [{"requirement": "project_location: Union Hill Elementary School, 5242 South State Hwy ZZ, Republic, MO", '
        '"label": "project_location", "value": "Union Hill Elementary School, 5242 South State Hwy ZZ, Republic, MO", '
        '"source_text": "Union Hill Elementary School, 5242 South State Hwy ZZ, Republic, MO", "confidence": 0.93}]}\n'
        "Example C — road segment:\n"
        'Input: "Resurfacing of Main Street from 1st Avenue to 5th Avenue."\n'
        'Output: {"items": [{"requirement": "project_location: Main Street from 1st Avenue to 5th Avenue", '
        '"label": "project_location", "value": "Main Street from 1st Avenue to 5th Avenue", '
        '"source_text": "Main Street from 1st Avenue to 5th Avenue", "confidence": 0.9}]}\n'
        "Example D — point-to-point:\n"
        'Input: "Guardrail installation on SR-91 between Exit 12 and Exit 18."\n'
        'Output: {"items": [{"requirement": "project_location: SR-91 between Exit 12 and Exit 18", '
        '"label": "project_location", "value": "SR-91 between Exit 12 and Exit 18", '
        '"source_text": "SR-91 between Exit 12 and Exit 18", "confidence": 0.9}]}\n'
        "Example E — multiple distinct sites (one item each):\n"
        'Input: "Work at Site A: 100 Oak Street, Springfield, IL and Site B: 200 Elm Avenue, Springfield, IL."\n'
        'Output: {"items": ['
        '{"requirement": "project_location: 100 Oak Street, Springfield, IL", '
        '"label": "project_location", "value": "100 Oak Street, Springfield, IL", '
        '"source_text": "Site A: 100 Oak Street, Springfield, IL", "confidence": 0.92}, '
        '{"requirement": "project_location: 200 Elm Avenue, Springfield, IL", '
        '"label": "project_location", "value": "200 Elm Avenue, Springfield, IL", '
        '"source_text": "Site B: 200 Elm Avenue, Springfield, IL", "confidence": 0.92}]}\n'
        "Example F — building/site name only (no address stated in doc):\n"
        'Input: "Renovation of the Ford Park East Playground. No street address provided."\n'
        'Output: {"items": [{"requirement": "project_location: Ford Park East Playground", '
        '"label": "project_location", "value": "Ford Park East Playground", '
        '"source_text": "Renovation of the Ford Park East Playground", "confidence": 0.8}]}\n'
        "Allowed label values ONLY: project_location, project_square_footage."
    ),
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && python -m pytest apps/intelligence/tests/test_location_prompt.py -v`
Expected: PASS.

---

### Task 3: Description section boundary (scope_of_work prompt)

**Files:**
- Modify: `backend/apps/intelligence/prompts/templates.py` — `EXTRACTION_TYPE_INSTRUCTIONS["scope_of_work"]` (~lines 198-211)
- Test: `backend/apps/intelligence/tests/test_scope_prompt.py` (new; string-content assertions)

**Interfaces:**
- Consumes: `EXTRACTION_TYPE_INSTRUCTIONS: dict[str, str]`.
- Produces: updated `scope_of_work` instruction string. Label `project_description` unchanged.

- [ ] **Step 1: Write the failing test**

Create `backend/apps/intelligence/tests/test_scope_prompt.py`:

```python
from apps.intelligence.prompts.templates import EXTRACTION_TYPE_INSTRUCTIONS


def test_scope_instruction_has_section_boundary():
    instr = EXTRACTION_TYPE_INSTRUCTIONS["scope_of_work"].lower()
    # Must instruct to stop at the next unrelated heading.
    assert "stop" in instr
    assert "heading" in instr
    # Must NOT tell the model to concatenate across unrelated sections.
    assert "across unrelated" in instr or "do not concatenate" in instr
    # Must still be verbatim within the section.
    assert "verbatim" in instr
    # Must still exclude boilerplate.
    assert "boilerplate" in instr
    # Label unchanged.
    assert "project_description" in EXTRACTION_TYPE_INSTRUCTIONS["scope_of_work"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest apps/intelligence/tests/test_scope_prompt.py -v`
Expected: FAIL — current instruction says "concatenate ALL scope sections" and lacks stop/heading/boilerplate boundary language.

- [ ] **Step 3: Rewrite the scope_of_work instruction**

Replace `EXTRACTION_TYPE_INSTRUCTIONS["scope_of_work"]` (~lines 198-211) with:

```python
    "scope_of_work": (
        "Extract the work description from the scope/description section only. "
        "Recognised headings: Scope of Work, Project Description, Project Details, "
        "Description of Work, Work Summary, Scope of Services, Project Scope, Specification, "
        "Work to be Performed, Description of Services, or a similar heading. "
        "Copy the section body VERBATIM — do not summarize, paraphrase, or shorten. "
        "STOP at the next unrelated heading (for example: bonds, bid security, insurance, "
        "instructions to bidders, evaluation criteria, payment terms, general conditions, "
        "special provisions). Do NOT concatenate text across unrelated section boundaries. "
        "Exclude adjacent boilerplate: signature blocks, form headers, page numbers, "
        "footers, and cover-page furniture. "
        "If the SAME chunk contains two clearly-related scope/description sections for the "
        "same project, you may include both in document order separated by a blank line; "
        "otherwise extract only the single relevant section. "
        "Do NOT add commentary. Do NOT extract any other fields from scope_of_work. "
        "Set requirement to 'project_description: <verbatim scope text>' and value to the same verbatim text. "
        "Field names to use: project_description."
    ),
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest apps/intelligence/tests/test_scope_prompt.py -v`
Expected: PASS.

---

### Task 4: Full regression + integration sweep

**Files:**
- Test only: run the intelligence test suite.

**Interfaces:**
- Consumes: all changes from Tasks 1-3.
- Produces: green suite, confirming no regressions in extraction retrieval or post-rules.

- [ ] **Step 1: Run the postrules + prompt tests together**

Run: `cd backend && python -m pytest apps/intelligence/tests/test_spec_check_postrules.py apps/intelligence/tests/test_location_prompt.py apps/intelligence/tests/test_scope_prompt.py -v`
Expected: PASS — all Task 1-3 tests.

- [ ] **Step 2: Run the broader intelligence suite for regressions**

Run: `cd backend && python -m pytest apps/intelligence/tests/test_extraction_retrieval.py apps/intelligence/tests/test_operational_scope_guidance.py apps/intelligence/tests/test_field_confidence.py -v`
Expected: PASS — no regressions introduced by the prompt or merge changes.

- [ ] **Step 3: Run the whole intelligence test package**

Run: `cd backend && python -m pytest apps/intelligence/tests/ -v`
Expected: PASS (or only pre-existing, unrelated failures — if any fail, confirm they failed before Task 1 by checking they touch neither location, scope, nor the location merge branch).

- [ ] **Step 4: Manual end-to-end check on the Bell Gardens document (if available)**

If the Bell Gardens tender is loaded in a dev environment, re-run extraction for that document and confirm in the resulting `spec_check_fields`:
- `project_size_location_items` shows one `project_location` row = the full address `John Anson Ford Park, 8000 Park Lane, Bell Gardens, CA 90201` (no separate "IN THE CITY OF BELL GARDENS" row).
- `project_metadata_items` `project_description` = scope body only, no bond/insurance/instructions bleed.

Record the observed values in the task notes. If no dev environment is available, note that the unit tests stand in for this check and flag it for manual QA.

---

## Notes for the implementer

- The `project_value` / Engineer's Estimate fix and the LangGraph rewrite are explicitly **out of scope** (v2) — do not touch `agentic_field_verifier.py`, `REQUIRED_FIELD_KEYS`, `payment_terms` prompt, or add any framework dependency.
- Prompt changes take effect on the next extraction run; existing stored summaries are unaffected until regenerated. No reindex.
- `_merge_rows_by_field_key` is still used for solicitation number, acquisition note, and description — do not remove it. Only the `project_location` call is replaced by `_merge_location_rows`.
