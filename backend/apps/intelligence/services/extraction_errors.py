"""Exceptions for intelligence extraction pipeline."""

from apps.core.exceptions import ServiceError


class GroupExtractionIncompleteError(ServiceError):
    """Raised when critical field groups fail to extract after all retries."""

    def __init__(self, missing_group_ids: list[str]):
        self.missing_group_ids = missing_group_ids
        super().__init__(
            f"Critical extraction groups incomplete: {', '.join(missing_group_ids)}",
            code="group_extraction_incomplete",
            status_code=502,
        )
