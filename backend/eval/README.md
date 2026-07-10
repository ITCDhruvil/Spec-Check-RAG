# Evaluation harness (Phase 0–7)

This folder contains evaluation runners for the spec-check pipeline.

## Phase 0 — Baseline metrics

Lightweight baseline from existing `sample-docs/validation_results/*.json` outputs.

```powershell
python -m eval.run_phase0 --input ..\sample-docs\validation_results --out .\eval\out
```

## Phase 7 — Golden-set eval CI

Offline regression against a committed golden manifest. Rebuilds `spec_check_fields`
from stored extraction insights (no LLM/API calls) and checks:

- Required `field_key` presence
- Labeled field value matching (substring labels)
- Per-field precision / recall / F1
- Structural checks (confidence, singleton dedupe, min row counts)

### Bootstrap / refresh manifest

When pipeline outputs change intentionally:

```powershell
python eval/bootstrap_golden_manifest.py
# Review diff to eval/golden_set/manifest.json before committing
```

### Run locally

```powershell
python eval/run_golden_eval.py
python eval/run_golden_eval.py --out eval/out/golden_report.json
```

### CI

GitHub Actions workflow `.github/workflows/spec-check-eval.yml` runs on push/PR:

- Unit tests (`test_field_confidence`, `test_spec_check_postrules`, `test_golden_set`)
- Golden eval gate (`run_golden_eval.py`)

Uses `config.settings.ci` (SQLite in-memory, no Postgres).

---

## Phase 0 details

It is intentionally “golden-set free” for Phase 0: the goal is to measure **coverage, spend, and grounding**
before we change parsing/chunking/retrieval.

## What it measures

- **Token spend**: summary tokens and per-extraction tokens
- **Empty extraction waste**: extraction calls that returned `items: []` + their tokens
- **Missing extraction types** as reported by the summary `_meta`
- **Citation verification rate**: fraction of sources with `citation_verified: true`
- **Parsing quality**: `parsing_quality_score`, OCR page count, tables count

## Run

From `backend/` (venv activated):

```powershell
python -m eval.run_phase0 --input ..\sample-docs\validation_results --out .\eval\out
```

Outputs:

- `eval/out/phase0_report.json`
- `eval/out/phase0_report.md`

