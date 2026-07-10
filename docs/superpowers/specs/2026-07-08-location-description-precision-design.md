# Location & Description Precision Fixes — Design

**Date:** 2026-07-08
**Status:** Approved, pending implementation
**Scope:** Two precision fixes on the current spec-check extraction pipeline. No LangGraph (deferred to v2). No reindex. No new modules.

---

## Problem

Two extracted spec-check fields are wrong on real documents:

1. **`project_location`** returns a bare city/jurisdiction ("IN THE CITY OF BELL GARDENS") instead of the most specific location available in the document ("John Anson Ford Park, 8000 Park Lane, Bell Gardens, CA 90201").
2. **`project_description`** returns the correct scope-of-work text **plus extra adjacent content** — neighbor clauses, boilerplate, and unrelated sections bleed in.

Both are **precision** problems, not retrieval misses: the right chunks are retrieved, but the wrong content is selected/kept. No reindex required.

## Root Causes

### Location
- Owned by `technical_requirements` extraction type.
- Winner among multiple `project_location` candidates is chosen by `_row_quality_key` in `spec_check_postrules.py` (grounding, citation, confidence). **No signal for address completeness** — a high-confidence bare city beats or merges over a full address.
- Merge branch: `merge_spec_check_multi_fields` joins location rows with `; ` (`spec_check_postrules.py` lines 286-290), so a bare city and a full address can both survive and concatenate.
- Prompt/few-shot give only one address example; no taxonomy for the many location shapes real docs use.

### Description
- Owned by `scope_of_work` extraction type.
- Prompt (`templates.py` lines 198-211) instructs the LLM to copy VERBATIM and **concatenate ALL scope-like text in a chunk** with no boundary. Chunks carry neighbor text → included.

## Location Taxonomy (drives prompt few-shot)

| Type | Example | Capture rule |
|------|---------|--------------|
| Full street address | `John Anson Ford Park, 8000 Park Lane, Bell Gardens, CA 90201` | preferred — most complete |
| Named facility + address | `Union Hill Elementary School, 5242 South State Hwy ZZ, Republic, MO` | combine facility + address |
| Building / site name only | `Ford Park East Playground` | keep if no address stated |
| Road / segment | `Main Street from 1st Ave to 5th Ave` | capture full segment |
| Point-to-point | `SR-91 between Exit 12 and Exit 18` | capture both endpoints |
| Multiple distinct sites | `Site A: 100 Oak St; Site B: 200 Elm St` | list all as separate items |
| City / jurisdiction only | `City of Bell Gardens` | fallback ONLY if nothing more specific exists |

## Decisions

- **City vs address (same site):** capture the **most specific only**. Drop the bare city as redundant. Bell Gardens case → full address only.
- **Genuine multiple sites:** **list all distinct sites**, deduped by subset.

These are consistent: prefer specific, drop redundant, keep genuinely distinct sites.

---

## Design

### Fix A — Location

#### A1. Prompt taxonomy examples (source-level fix)

**File:** `backend/apps/intelligence/prompts/templates.py`
**Targets:** `technical_requirements` instruction (~lines 187-197) and its few-shot (~lines 303-314).

Rewrite the instruction to state capture rules explicitly:
- Capture the **most specific** location for each distinct work site.
- Prefer full address / facility+address over a bare city or jurisdiction.
- A bare city (e.g. "IN THE CITY OF BELL GARDENS") is a fallback ONLY when nothing more specific exists.
- Capture road segments and point-to-point endpoints in full.
- If multiple **distinct** sites exist, emit one `project_location` item per site.
- Do NOT emit both a bare city and the full address for the same site — the full address already contains the city.

Expand the few-shot with one worked example per taxonomy row:
- Full address (Bell Gardens).
- Facility + address.
- Building/site name only (no address in doc).
- Road segment.
- Point-to-point.
- Multiple distinct sites → multiple items.
- Negative case: bare city present alongside full address → emit address only.

Allowed labels unchanged (`project_location`, `project_square_footage`).

#### A2. Dedup tie-break backstop (deterministic safety net)

**File:** `backend/apps/intelligence/services/spec_check_postrules.py`
**Target:** the `project_location` branch of `merge_spec_check_multi_fields` (~lines 286-290).

- Add `_address_completeness_score(value: str) -> int`:
  - +2 street number present (e.g. `\b\d{2,6}\b` in an address context / comma-separated part)
  - +1 has a comma (multi-part: name / street / city)
  - +1 has state + ZIP (`\b[A-Z]{2}\s+\d{5}\b`)
  - bare single-token city or "in the city of X" → 0
- Winner value = highest completeness score; tie broken by existing `_row_quality_key`.
- **Subset drop:** if a candidate value is a (normalized) substring of a more-complete kept value, drop it (city ⊂ full address).
- **Keep distinct:** non-subset locations survive as separate `; `-joined entries (multi-site support).

Prompt (A1) does the primary work; A2 guarantees correctness even when the LLM still emits both. Change is scoped to the `project_location` branch only.

### Fix C — Description over-inclusion (prompt boundary)

**File:** `backend/apps/intelligence/prompts/templates.py`
**Target:** `scope_of_work` instruction (~lines 198-211).

Replace the "concatenate ALL scope-like text" rule with a bounded rule:
- Extract ONLY the contiguous scope/description section body.
- **STOP at the next unrelated heading** (bonds, insurance, instructions to bidders, evaluation, payment, general conditions).
- Do NOT concatenate across unrelated section boundaries.
- Exclude adjacent boilerplate (signature blocks, form headers, page furniture).
- Remain verbatim **within** the section — no summarizing or paraphrasing.

Allowed label unchanged (`project_description`).

---

## Testing

- **Golden check — Bell Gardens doc:**
  - `project_location` == full address; no separate bare-city row.
  - `project_description` == scope body only; no adjacent-section bleed.
- **Regression:** existing spec-check tests must still pass — `test_extraction_retrieval`, `test_spec_check_postrules`.
- Add a unit test for `_address_completeness_score` covering each taxonomy row + the subset-drop path.

## Regression Guards

- A2 modifies only the `project_location` merge branch; other fields' merge/dedup untouched.
- Prompt changes are additive examples + a tighter boundary; no extraction labels or field keys change.
- No embedding/index change → no reprocessing of existing documents needed for the postrule change (prompt changes take effect on next extraction run).

## Out of Scope (v2)

- LangGraph rewrite of the extraction pipeline.
- Quality-critique / Self-RAG loop for `project_value` and other fields.
- Wiring `project_value` / `project_location` into the agentic verifier's `REQUIRED_FIELD_KEYS`.
