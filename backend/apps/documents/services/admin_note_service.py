"""
Admin note: a short, accurate one-paragraph summary of a document's
extraction outcome — key facts, user corrections (old → new, why), and
fields still flagged for review. Deterministic (no LLM), so the draft is
reproducible and instant. The user can edit the draft before saving.
"""

from __future__ import annotations

from apps.documents.models import Document
from apps.intelligence.models import FieldFeedback, GeneratedSummary
from apps.intelligence.services.spec_check_fields_registry import (
    DEADLINE_LABEL_DISPLAY,
    FIELD_DEFS,
)

REVIEW_CONFIDENCE_THRESHOLD = 70

_LABELS: dict[str, str] = {
    **{k: d.display_label for k, d in FIELD_DEFS.items()},
    **DEADLINE_LABEL_DISPLAY,
    "set_aside": "Set-aside",
}


def _label(field_key: str) -> str:
    return _LABELS.get(field_key, field_key.replace("_", " "))


def _iter_spec_rows(summary_json: dict):
    spec = (summary_json or {}).get("spec_check_fields") or {}
    for bucket in spec.values():
        if not isinstance(bucket, list):
            continue
        for row in bucket:
            if isinstance(row, dict):
                yield row


def generate_admin_note(document: Document) -> str:
    """One-paragraph draft note for this document."""
    summary = (
        GeneratedSummary.objects.filter(
            document=document, is_current=True, status="completed"
        ).first()
    )

    sentences: list[str] = []

    # ── Key facts ────────────────────────────────────────────────────────
    key_facts: list[str] = []
    fields_total = 0
    low_conf: list[str] = []
    if summary:
        wanted = {"project_name": None, "bid_deadline_date_time": None}
        for row in _iter_spec_rows(summary.summary_json):
            fk = str(row.get("field_key") or "")
            if row.get("_not_found"):
                continue
            fields_total += 1
            if fk in wanted and wanted[fk] is None:
                # Date rows keep the label in "text" and the value in "date".
                if fk.endswith("_date_time"):
                    value = str(row.get("date") or "").strip()
                else:
                    value = str(row.get("text") or "").strip()
                    if ": " in value:
                        value = value.split(": ", 1)[1]
                wanted[fk] = value or None
            conf = row.get("confidence")
            if isinstance(conf, int) and conf < REVIEW_CONFIDENCE_THRESHOLD:
                low_conf.append(_label(fk))
        if wanted["project_name"]:
            key_facts.append(f'"{wanted["project_name"]}"')
        if wanted["bid_deadline_date_time"]:
            deadline = wanted["bid_deadline_date_time"]
            # ISO datetime → readable 12-hour form.
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(deadline)
                deadline = dt.strftime("%B %d, %Y, %I:%M %p").replace(" 0", " ")
            except ValueError:
                pass
            key_facts.append(f"bid deadline {deadline}")

    if key_facts:
        sentences.append(
            f"Processed {' — '.join(key_facts)} with {fields_total} field(s) extracted."
        )
    elif summary:
        sentences.append(f"Processed with {fields_total} field(s) extracted.")
    else:
        sentences.append("Document has no completed briefing yet.")

    # ── Corrections (user thumbs-down feedback) ──────────────────────────
    corrections = list(
        FieldFeedback.objects.filter(document=document, rating="down")
        .order_by("created_at")
        .values("field_key", "extracted_value", "correct_value", "issue_type", "comment")
    )
    if corrections:
        parts: list[str] = []
        for fb in corrections[:6]:
            label = _label(fb["field_key"])
            old = (fb["extracted_value"] or "").strip()
            new = (fb["correct_value"] or "").strip()
            why = (fb["comment"] or fb["issue_type"] or "").strip()
            if new and old:
                piece = f'{label} corrected from "{old[:60]}" to "{new[:60]}"'
            elif new:
                piece = f'{label} corrected to "{new[:60]}"'
            else:
                piece = f"{label} flagged as wrong"
            if why:
                piece += f" ({why[:80]})"
            parts.append(piece)
        more = len(corrections) - 6
        tail = f" and {more} more correction(s)" if more > 0 else ""
        sentences.append("Corrections: " + "; ".join(parts) + tail + ".")

    confirmed = FieldFeedback.objects.filter(document=document, rating="up").count()
    if confirmed:
        sentences.append(f"{confirmed} field(s) confirmed correct by the reviewer.")

    # ── Outstanding review flags ─────────────────────────────────────────
    corrected_keys = {c["field_key"] for c in corrections}
    outstanding = [f for f in dict.fromkeys(low_conf) if f not in {_label(k) for k in corrected_keys}]
    if outstanding:
        sentences.append(
            "Pending review (low confidence): " + ", ".join(outstanding[:6]) + "."
        )

    if len(sentences) == 1 and summary and not corrections:
        sentences.append("No corrections were needed.")

    return " ".join(sentences)
