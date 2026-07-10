"""
Structured processing error schema for retries, observability, and legal traceability.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from apps.processing.choices import PipelineStage, ProcessingErrorType


@dataclass
class StructuredProcessingError:
    error_type: str
    stage: str
    recoverable: bool
    retry_count: int
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        *,
        stage: str,
        error_type: str = ProcessingErrorType.UNKNOWN_FAILURE,
        recoverable: bool = False,
        retry_count: int = 0,
        details: dict[str, Any] | None = None,
    ) -> StructuredProcessingError:
        return cls(
            error_type=error_type,
            stage=stage,
            recoverable=recoverable,
            retry_count=retry_count,
            message=str(exc)[:2000],
            details=details or {"exception_class": type(exc).__name__},
        )

    @classmethod
    def intake_failure(cls, exc: Exception, retry_count: int, recoverable: bool) -> StructuredProcessingError:
        return cls.from_exception(
            exc,
            stage=PipelineStage.INTAKE_PROCESSING,
            error_type=ProcessingErrorType.INTAKE_FAILURE,
            recoverable=recoverable,
            retry_count=retry_count,
        )

    @classmethod
    def extraction_failure(cls, exc: Exception, retry_count: int, recoverable: bool) -> StructuredProcessingError:
        return cls.from_exception(
            exc,
            stage=PipelineStage.EXTRACTION_PROCESSING,
            error_type=ProcessingErrorType.EXTRACTION_FAILURE,
            recoverable=recoverable,
            retry_count=retry_count,
        )

    @classmethod
    def summary_failure(cls, exc: Exception, retry_count: int, recoverable: bool) -> StructuredProcessingError:
        return cls.from_exception(
            exc,
            stage=PipelineStage.SUMMARY_PROCESSING,
            error_type=ProcessingErrorType.SUMMARY_FAILURE,
            recoverable=recoverable,
            retry_count=retry_count,
        )

    @classmethod
    def parsing_failure(cls, exc: Exception, retry_count: int, recoverable: bool) -> StructuredProcessingError:
        return cls.from_exception(
            exc,
            stage=PipelineStage.PARSING_PROCESSING,
            error_type=ProcessingErrorType.PARSING_FAILURE,
            recoverable=recoverable,
            retry_count=retry_count,
        )
