"""
Severity tiers for penalties_and_risks extractions.

critical — direct financial loss, payment risk, bonds, LDs, liability $
medium  — award/compliance/commercial exposure without stated $
low     — process/discretion without clear financial impact
"""

from __future__ import annotations

import re
from typing import Any

VALID_SEVERITIES = frozenset({"critical", "medium", "low"})

# LLM may return high/medium/low — map high → critical for penalties
_ALIASES = {
    "high": "critical",
    "critical": "critical",
    "severe": "critical",
    "medium": "medium",
    "moderate": "medium",
    "low": "low",
    "minor": "low",
}

_CRITICAL_PATTERNS = [
    r"liquidated damages?",
    r"\bld[s]?\b",
    r"penalt(y|ies)",
    r"damages?",
    r"indemnif",
    r"overpayment",
    r"forfeit",
    r"retention",
    r"performance guarantee",
    r"payment bond",
    r"advance payment bond",
    r"bank guarantee",
    r"bond\b",
    r"%\s*(per|of)",
    r"\$\s*\d",
    r"liable for",
    r"liability",
    r"no liability.*appropriat",
    r"appropriated funds",
    r"federal or state funds",
    r"reimbursement",
    r"fixed[- ]price",
    r"lowest bidder",
    r"bafo",
    r"non[- ]responsive",
    r"termination",
    r"withhold",
    r"deduct",
]

_MEDIUM_PATTERNS = [
    r"reject",
    r"cancel",
    r"withdraw",
    r"amend",
    r"clarification",
    r"correction",
    r"non[- ]conform",
    r"disqualif",
    r"subcontractor",
    r"accountab",
    r"under[- ]performance",
    r"non[- ]performance",
    r"sole discretion",
    r"compliance",
]


def normalize_severity(raw: str | None) -> str:
    key = (raw or "medium").lower().strip()
    return _ALIASES.get(key, "medium")


def classify_penalty_severity(text: str) -> str:
    """Rule-based fallback / boost when LLM severity is missing or weak."""
    lower = (text or "").lower()
    if not lower:
        return "medium"

    if any(re.search(p, lower) for p in _CRITICAL_PATTERNS):
        return "critical"
    if any(re.search(p, lower) for p in _MEDIUM_PATTERNS):
        return "medium"
    return "low"


def apply_penalty_severity(item: dict[str, Any]) -> dict[str, Any]:
    """Set severity on one extraction item; rules can upgrade, not downgrade critical."""
    req = str(item.get("requirement") or "").strip()
    src = str(item.get("source_text") or "").strip()
    combined = f"{req} {src}"

    llm = normalize_severity(item.get("severity"))
    rules = classify_penalty_severity(combined)

    # Rules upgrade only: critical wins; else take max of llm and rules
    order = {"low": 0, "medium": 1, "critical": 2}
    final = llm
    if order.get(rules, 1) > order.get(llm, 1):
        final = rules
    item["severity"] = final
    return item


def apply_penalties_severity(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [apply_penalty_severity(i) for i in items if isinstance(i, dict)]
