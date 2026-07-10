"""Phase 7 golden-set regression tests (offline, uses validation_results)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.golden_eval import DEFAULT_MANIFEST, load_manifest, run_golden_eval

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def golden_report() -> dict:
    if not DEFAULT_MANIFEST.exists():
        pytest.skip("golden manifest missing — run eval/bootstrap_golden_manifest.py")
    return run_golden_eval(DEFAULT_MANIFEST)


def test_golden_manifest_exists():
    assert DEFAULT_MANIFEST.exists(), "Run python eval/bootstrap_golden_manifest.py"


def test_golden_manifest_has_enabled_documents():
    manifest = load_manifest()
    enabled = [d for d in manifest.get("documents", []) if d.get("enabled", True)]
    assert len(enabled) >= 5


def test_golden_eval_passes(golden_report: dict):
    assert golden_report.get("passed") is True, json.dumps(
        {
            "gate_issues": golden_report.get("gate_issues"),
            "failed_docs": [
                d for d in golden_report.get("documents", []) if not d.get("passed")
            ],
        },
        indent=2,
    )


def test_golden_macro_f1_threshold(golden_report: dict):
    manifest = load_manifest()
    min_f1 = float((manifest.get("thresholds") or {}).get("min_macro_f1") or 0.8)
    actual = (golden_report.get("summary") or {}).get("macro_f1") or 0
    assert actual >= min_f1, f"macro F1 {actual} < {min_f1}"


def test_golden_bid_deadline_recall(golden_report: dict):
    manifest = load_manifest()
    min_r = float(
        ((manifest.get("thresholds") or {}).get("min_field_recall") or {}).get(
            "bid_deadline_date_time", 0.95
        )
    )
    per_field = (golden_report.get("metrics") or {}).get("per_field") or {}
    actual = (per_field.get("bid_deadline_date_time") or {}).get("recall")
    if actual is None:
        pytest.skip("bid_deadline_date_time not labeled in golden set")
    assert actual >= min_r
