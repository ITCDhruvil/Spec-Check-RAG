import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class ServiceError(Exception):
    """Raised when business logic fails."""

    def __init__(self, message: str, code: str = "service_error", status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class ValidationServiceError(ServiceError):
    def __init__(self, message: str, code: str = "validation_error"):
        super().__init__(message, code=code, status_code=status.HTTP_400_BAD_REQUEST)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if isinstance(exc, ServiceError):
        logger.warning(
            "service_error path=%s code=%s message=%s",
            context["request"].path if context.get("request") else "unknown",
            exc.code,
            exc.message,
        )
        return Response(
            {"error": {"code": exc.code, "message": exc.message}},
            status=exc.status_code,
        )

    if response is not None:
        request = context.get("request")
        logger.warning(
            "api_error path=%s status=%s",
            request.path if request else "unknown",
            response.status_code,
        )
        if isinstance(response.data, dict) and "detail" in response.data:
            response.data = {
                "error": {
                    "code": "api_error",
                    "message": str(response.data["detail"]),
                    "details": response.data,
                }
            }
    else:
        logger.exception("unhandled_exception path=%s", context.get("request"))

    return response
