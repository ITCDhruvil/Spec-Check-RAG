import logging
import time
import uuid

logger = logging.getLogger("apps.request")


class RequestLoggingMiddleware:
    """Structured request/response logging for observability."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.request_id = request_id  # type: ignore[attr-defined]
        start = time.perf_counter()

        logger.info(
            "request_started method=%s path=%s request_id=%s",
            request.method,
            request.path,
            request_id,
        )

        response = self.get_response(request)
        duration_ms = (time.perf_counter() - start) * 1000

        response["X-Request-ID"] = request_id
        logger.info(
            "request_completed method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response
