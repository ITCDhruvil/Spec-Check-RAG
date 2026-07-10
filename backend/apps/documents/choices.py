from django.db import models


class TenderStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    CLOSED = "closed", "Closed"
    ARCHIVED = "archived", "Archived"


class DocumentVersionType(models.TextChoices):
    """Lineage type within a tender package."""

    ORIGINAL = "original", "Original RFP/RFQ"
    REVISION = "revision", "Revised Version"
    CORRIGENDUM = "corrigendum", "Corrigendum"
    ADDENDUM = "addendum", "Addendum"
    CLARIFICATION = "clarification", "Clarification Response"
    ANNEXURE = "annexure", "Annexure / Technical Spec"
    OTHER = "other", "Other"


class SourceReferenceKind(models.TextChoices):
    """How a source reference was produced (Phase 2+)."""

    EXTRACTION = "extraction", "Structured Extraction"
    SUMMARY = "summary", "Summary Citation"
    CITATION = "citation", "RAG Citation"
    COMPARISON = "comparison", "Version Comparison"
