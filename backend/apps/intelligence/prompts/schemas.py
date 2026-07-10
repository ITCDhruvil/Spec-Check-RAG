"""Pydantic schemas for structured LLM extraction output (Component 8: A4).

Used by OpenAIService.chat_structured() to enforce a strict JSON shape via the
OpenAI/Azure `responses.parse` / `chat.completions.parse` API — eliminates the
invalid-JSON failure path and free-form hallucinations.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractionItem(BaseModel):
    """One extracted fact. Mirrors the dict shape consumed by grounding.validate_and_score_items."""

    requirement: str = Field(description="Spec-ready statement, formatted '<label>: <value>'.")
    label: str | None = Field(default=None, description="Exact allowed field label for this type.")
    value: str | None = Field(default=None, description="Extracted value text, or null.")
    date_time: str | None = Field(default=None, description="Full date+time for deadlines, or null.")
    page: int | None = Field(default=None, description="PDF page where source_text appears, or null.")
    section: str | None = Field(default=None, description="Document section heading, or null.")
    source_text: str = Field(description="Verbatim excerpt copied from the document text.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    """Top-level structured-output container."""

    items: list[ExtractionItem] = Field(default_factory=list)
