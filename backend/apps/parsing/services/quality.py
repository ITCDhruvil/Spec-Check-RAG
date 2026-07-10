import re

from django.conf import settings

GARBLED_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
REPLACEMENT_CHAR_RATIO_THRESHOLD = 0.05


def score_page_text(text: str) -> float:
    """
    Heuristic quality score 0.0–1.0 for extracted page text.
    Low scores trigger OCR fallback on PDFs.
    """
    if not text or not text.strip():
        return 0.0

    stripped = text.strip()
    length = len(stripped)

    if length < settings.PARSING_MIN_PAGE_TEXT_LENGTH:
        return 0.15

    alnum_space = sum(1 for c in stripped if c.isalnum() or c.isspace())
    readable_ratio = alnum_space / length

    replacement_chars = stripped.count("\ufffd")
    replacement_penalty = min(
        0.4,
        (replacement_chars / max(length, 1)) / REPLACEMENT_CHAR_RATIO_THRESHOLD * 0.2,
    )

    if GARBLED_PATTERN.search(stripped):
        readable_ratio *= 0.5

    # Very short lines dominated by symbols
    words = stripped.split()
    if words and len(words) < 5 and readable_ratio < 0.6:
        readable_ratio *= 0.6

    score = max(0.0, min(1.0, readable_ratio - replacement_penalty))

    if length < 80:
        score *= 0.75

    return round(score, 4)


def is_poor_extraction(quality_score: float) -> bool:
    return quality_score < settings.PARSING_QUALITY_OCR_THRESHOLD


def aggregate_quality(page_scores: list[float]) -> float:
    if not page_scores:
        return 0.0
    return round(sum(page_scores) / len(page_scores), 4)
