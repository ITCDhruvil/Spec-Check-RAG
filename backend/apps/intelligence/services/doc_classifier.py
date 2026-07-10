"""
Lightweight, rules-based document classification for retrieval query routing (C1).

Classifies a solicitation's cover text along two independent axes:

* ``solicitation_type`` — federal_rfq | state_ifb | rfp | prequalification | unknown.
  Mirrors the procurement-document families the pipeline already handles.
* ``domain`` — it_network | construction | general. Content domain, used to inject
  domain-specific retrieval vocabulary (e.g. structured-cabling terms) only for the
  documents that warrant it instead of polluting every document's queries.

No LLM call: classification runs on the cover-page sample (`AdaptiveLexiconService.
cover_sample_text`) that the extraction pipeline already computes. Keyword scoring keeps
it cheap and deterministic; ties resolve to the most specific class, else the fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Each marker list is scored by counting distinct keyword hits in the cover text.
# Patterns are matched as word-boundaried, case-insensitive substrings.
_SOLICITATION_MARKERS: dict[str, list[str]] = {
    # Federal RFQ / quotation — Standard Forms, FAR, NAICS, combined synopsis/solicitation.
    "federal_rfq": [
        "request for quotation", "request for quote", "rfq",
        "sf-1449", "sf 1449", "sf-18", "sf-33", "standard form",
        "naics", "combined synopsis", "federal acquisition regulation", "far ",
        "dpas", "solicitation number",
    ],
    # State / municipal sealed competitive bid. Many public eProcurement
    # solicitations never print "IFB" literally — they identify as a numbered
    # "Solicitation" addressed to "Bidders" (vs RFP "Offerors" / RFQ "Quoters"),
    # so bidder-oriented language is the reliable signal. RFP/RFQ still win when
    # their explicit request-for-proposal/quotation phrases are present (higher score).
    "state_ifb": [
        "invitation for bid", "invitation for bids", "invitation to bid", "ifb", "itb",
        "sealed bid", "sealed bids", "competitive sealed",
        "lowest responsible bidder", "bidders", "bidder's",
        "bidders/offerors", "bidders certification",
    ],
    # Request for proposal (evaluated, not low-bid).
    "rfp": [
        "request for proposal", "request for proposals", "rfp",
    ],
    # Prequalification / statement of qualifications.
    "prequalification": [
        "prequalification", "pre-qualification", "prequalify",
        "statement of qualifications", "soq", "aia document",
        "qualification questionnaire", "qualifications questionnaire",
    ],
}

# Specificity tiebreak: prefer narrower families over the broad RFP bucket when scores tie.
_SOLICITATION_PRIORITY: list[str] = [
    "prequalification",
    "federal_rfq",
    "state_ifb",
    "rfp",
]

_DOMAIN_MARKERS: dict[str, list[str]] = {
    "it_network": [
        "structured cabling", "cabling", "network switch", "switches", "switch",
        "wireless", "wi-fi", "wifi", "access point", "fiber", "voip",
        "telecommunication", "telecommunications", "e-rate", "erate",
        "category 6", "cat6", "cat 6", "ethernet", "lan", "wan",
        "data network", "patch panel",
    ],
    "construction": [
        "demolition", "hvac", "square feet", "square footage", "architect",
        "renovation", "masonry", "roofing", "sitework", "general contractor",
        "concrete", "plumbing", "mechanical", "earthwork", "building construction",
    ],
}

_DOMAIN_PRIORITY: list[str] = ["it_network", "construction"]


@dataclass(frozen=True)
class DocClassification:
    solicitation_type: str = "unknown"
    domain: str = "general"

    def to_debug_dict(self) -> dict[str, str]:
        return {"solicitation_type": self.solicitation_type, "domain": self.domain}


def _score(text: str, markers: list[str]) -> int:
    hits = 0
    for marker in markers:
        # Word-boundaried, case-insensitive; escape regex metachars in markers.
        pattern = r"\b" + re.escape(marker) + r"\b"
        if re.search(pattern, text):
            hits += 1
    return hits


def _pick(text: str, markers: dict[str, list[str]], priority: list[str], default: str) -> str:
    scores = {label: _score(text, terms) for label, terms in markers.items()}
    best = max(scores.values(), default=0)
    if best == 0:
        return default
    # Among classes tied at the top score, choose the most specific by priority order.
    tied = [label for label, score in scores.items() if score == best]
    for label in priority:
        if label in tied:
            return label
    return tied[0]


def classify(cover_text: str | None) -> DocClassification:
    """Classify a document from its cover-page sample text. Never raises."""
    if not cover_text or not cover_text.strip():
        return DocClassification()
    text = cover_text.lower()
    return DocClassification(
        solicitation_type=_pick(text, _SOLICITATION_MARKERS, _SOLICITATION_PRIORITY, "unknown"),
        domain=_pick(text, _DOMAIN_MARKERS, _DOMAIN_PRIORITY, "general"),
    )
