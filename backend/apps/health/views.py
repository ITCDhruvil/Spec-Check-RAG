import logging

from django.conf import settings
from django.db import connection
from redis import Redis
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        checks = {
            "database": self._check_database(),
            "redis": self._check_redis(),
            "media_storage": self._check_media(),
            "worker": self._check_worker(),
        }
        # Worker degraded is non-fatal when running in sync mode
        critical = {k: v for k, v in checks.items() if k != "worker"}
        healthy = all(c["status"] == "ok" for c in critical.values())

        # Maintenance mode (fine-tuning in progress).
        maintenance_info: dict = {}
        try:
            from apps.intelligence.services.maintenance_service import maintenance_status
            maintenance_info = maintenance_status()
        except Exception:
            pass

        payload = {
            "status": "maintenance" if maintenance_info.get("maintenance") else ("healthy" if healthy else "degraded"),
            "service": "spec-check-platform",
            "version": "1.0.0-phase1",
            "checks": checks,
            **maintenance_info,
        }
        code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(payload, status=code)

    def _check_worker(self) -> dict:
        """
        Returns ok in sync mode (no worker needed).
        In async mode pings Celery workers with a 2 s timeout.
        Reports how many workers are alive and the Redis queue depth.
        """
        sync_mode = (
            getattr(settings, "PROCESSING_SYNC", False)
            and getattr(settings, "INTELLIGENCE_SYNC_GENERATION", False)
        )
        if sync_mode:
            return {"status": "ok", "mode": "sync"}

        try:
            from celery import current_app as celery_app
            inspector = celery_app.control.inspect(timeout=2.0)
            ping = inspector.ping() or {}
            worker_count = len(ping)

            # Also report pending task count from Redis
            queue_depth: int | None = None
            try:
                client = Redis.from_url(settings.CELERY_BROKER_URL)
                queue_depth = client.llen("celery")
            except Exception:
                pass

            if worker_count == 0:
                return {
                    "status": "error",
                    "message": "No Celery workers responding — documents will queue forever.",
                    "workers": 0,
                    "queue_depth": queue_depth,
                }

            return {
                "status": "ok",
                "workers": worker_count,
                "queue_depth": queue_depth,
            }
        except Exception as exc:
            logger.warning("health_worker_check_failed error=%s", exc)
            return {"status": "error", "message": str(exc)}

    def _check_database(self) -> dict:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return {"status": "ok"}
        except Exception as exc:
            logger.exception("health_db_failed")
            return {"status": "error", "message": str(exc)}

    def _check_redis(self) -> dict:
        try:
            client = Redis.from_url(settings.CELERY_BROKER_URL)
            client.ping()
            return {"status": "ok"}
        except Exception as exc:
            logger.exception("health_redis_failed")
            return {"status": "error", "message": str(exc)}

    def _check_media(self) -> dict:
        try:
            settings.DOCUMENT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            test_path = settings.DOCUMENT_UPLOAD_DIR / ".healthcheck"
            test_path.write_text("ok")
            test_path.unlink()
            return {"status": "ok"}
        except Exception as exc:
            logger.exception("health_media_failed")
            return {"status": "error", "message": str(exc)}
