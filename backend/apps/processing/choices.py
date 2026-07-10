from django.db import models


class PipelineStage(models.TextChoices):
    """
    Granular pipeline stages for partial recovery, retries, and observability.
    Phase 1 uses: uploaded → queued → intake_* → completed.
    Later phases activate OCR through summary stages without schema changes.
    """

    UPLOADED = "uploaded", "Uploaded"
    QUEUED = "queued", "Queued"

    INTAKE_PROCESSING = "intake_processing", "Intake Processing"
    INTAKE_COMPLETED = "intake_completed", "Intake Completed"

    PARSING_PROCESSING = "parsing_processing", "Parsing Processing"
    PARSING_COMPLETED = "parsing_completed", "Parsing Completed"

    OCR_PROCESSING = "ocr_processing", "OCR Processing"
    OCR_COMPLETED = "ocr_completed", "OCR Completed"

    SECTIONING_PROCESSING = "sectioning_processing", "Sectioning Processing"
    SECTIONING_COMPLETED = "sectioning_completed", "Sectioning Completed"

    CHUNKING_PROCESSING = "chunking_processing", "Chunking Processing"
    CHUNKING_COMPLETED = "chunking_completed", "Chunking Completed"

    EMBEDDING_PROCESSING = "embedding_processing", "Embedding Processing"
    EMBEDDING_COMPLETED = "embedding_completed", "Embedding Completed"

    EXTRACTION_PROCESSING = "extraction_processing", "Extraction Processing"
    EXTRACTION_COMPLETED = "extraction_completed", "Extraction Completed"

    SUMMARY_PROCESSING = "summary_processing", "Summary Processing"

    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


# Stages where work is actively running (for polling/UI)
ACTIVE_STAGES = frozenset(
    {
        PipelineStage.INTAKE_PROCESSING,
        PipelineStage.PARSING_PROCESSING,
        PipelineStage.OCR_PROCESSING,
        PipelineStage.SECTIONING_PROCESSING,
        PipelineStage.CHUNKING_PROCESSING,
        PipelineStage.EMBEDDING_PROCESSING,
        PipelineStage.EXTRACTION_PROCESSING,
        PipelineStage.SUMMARY_PROCESSING,
    }
)

TERMINAL_STAGES = frozenset({PipelineStage.COMPLETED, PipelineStage.FAILED})


class ProcessingErrorType(models.TextChoices):
    """Structured failure taxonomy for production AI pipelines."""

    STORAGE_FAILURE = "STORAGE_FAILURE", "Storage Failure"
    VALIDATION_FAILURE = "VALIDATION_FAILURE", "Validation Failure"
    INTAKE_FAILURE = "INTAKE_FAILURE", "Intake Failure"
    PARSING_FAILURE = "PARSING_FAILURE", "Parsing Failure"
    OCR_FAILURE = "OCR_FAILURE", "OCR Failure"
    SECTIONING_FAILURE = "SECTIONING_FAILURE", "Sectioning Failure"
    CHUNKING_FAILURE = "CHUNKING_FAILURE", "Chunking Failure"
    EMBEDDING_FAILURE = "EMBEDDING_FAILURE", "Embedding Failure"
    EXTRACTION_FAILURE = "EXTRACTION_FAILURE", "Extraction Failure"
    SUMMARY_FAILURE = "SUMMARY_FAILURE", "Summary Failure"
    TIMEOUT_FAILURE = "TIMEOUT_FAILURE", "Timeout Failure"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE", "Unknown Failure"


class StageLogState(models.TextChoices):
    STARTED = "started", "Started"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


# Backward-compatible alias during transition (same values as PipelineStage)
ProcessingStatus = PipelineStage
