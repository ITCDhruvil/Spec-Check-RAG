"""
Inject user feedback into extraction prompts so the LLM avoids repeated mistakes.

Negative FieldFeedback rows (thumbs-down + optional correction) are aggregated
per field group and appended to group-extraction prompts on the next run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.intelligence.services.extraction_groups import ExtractionGroup


def _format_hint(
    *,
    field_key: str,
    issue_type: str,
    extracted_value: str,
    correct_value: str,
    comment: str,
) -> str:
    wrong = (extracted_value or "").strip()
    correct = (correct_value or "").strip()
    note = (comment or "").strip()

    if issue_type == "wrong_value" and wrong and correct:
        return (
            f"{field_key}: do NOT extract \"{wrong[:100]}\" — "
            f"correct value is \"{correct[:120]}\""
        )
    if issue_type == "wrong_value" and correct:
        return f"{field_key}: correct value should look like \"{correct[:120]}\""
    if issue_type == "missing":
        return (
            f"{field_key}: often missed — search cover page, timeline tables, "
            "and administrative sections carefully"
        )
    if issue_type == "wrong_source":
        return (
            f"{field_key}: citation must be verbatim from the document section "
            "where the value actually appears"
        )
    if note:
        return f"{field_key}: {note[:200]}"
    if correct:
        return f"{field_key}: expected \"{correct[:120]}\""
    if wrong:
        return f"{field_key}: avoid repeating \"{wrong[:100]}\""
    return ""


def build_group_feedback_hints(
    group: "ExtractionGroup",
    *,
    max_hints: int = 8,
    lookback: int = 100,
) -> str:
    """
    Return prompt text with lessons from recent negative feedback for this group.
    Empty string when no relevant feedback exists.
    """
    from django.conf import settings

    if not getattr(settings, "INTELLIGENCE_FEEDBACK_HINTS_ENABLED", True):
        return ""

    from apps.intelligence.models import FieldFeedback

    field_keys = set(group.field_labels)
    rows = (
        FieldFeedback.objects.filter(
            rating="down",
            field_key__in=field_keys,
        )
        .order_by("-created_at")[:lookback]
    )

    hints: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    for fb in rows:
        extracted = (fb.extracted_value or "").strip()[:80]
        correct = (fb.correct_value or "").strip()[:80]
        dedupe_key = (fb.field_key, fb.issue_type or "", extracted or correct)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        hint = _format_hint(
            field_key=fb.field_key,
            issue_type=fb.issue_type or "",
            extracted_value=fb.extracted_value or "",
            correct_value=fb.correct_value or "",
            comment=fb.comment or "",
        )
        if hint:
            hints.append(hint)
        if len(hints) >= max_hints:
            break

    if not hints:
        return ""

    bullets = "\n".join(f"- {h}" for h in hints)
    return (
        "\n\nLessons from prior user corrections (do NOT repeat these mistakes):\n"
        f"{bullets}\n"
    )
