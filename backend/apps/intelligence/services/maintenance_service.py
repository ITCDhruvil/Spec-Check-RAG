"""
Maintenance mode for the fine-tuning window.

When maintenance is active:
- Health endpoint returns  {"status": "maintenance", "reason": "..."}
- All document write endpoints return HTTP 503 with Retry-After header.
- Read endpoints (GET) remain available.

Uses AppSetting DB rows — no Redis/cache dependency.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MAINTENANCE_KEY = "maintenance_mode"
_MAINTENANCE_REASON_KEY = "maintenance_reason"
_MAINTENANCE_END_KEY = "maintenance_expected_end"


def is_maintenance() -> bool:
    from apps.intelligence.models import AppSetting
    return AppSetting.get(_MAINTENANCE_KEY, "0") == "1"


def enable_maintenance(reason: str = "Fine-tuning in progress", expected_end: str = "") -> None:
    from apps.intelligence.models import AppSetting
    AppSetting.set(_MAINTENANCE_KEY, "1", "Maintenance mode active flag")
    AppSetting.set(_MAINTENANCE_REASON_KEY, reason, "Maintenance reason")
    AppSetting.set(_MAINTENANCE_END_KEY, expected_end, "Expected end time")
    logger.info("maintenance_enabled reason=%s expected_end=%s", reason, expected_end)


def disable_maintenance() -> None:
    from apps.intelligence.models import AppSetting
    AppSetting.set(_MAINTENANCE_KEY, "0", "Maintenance mode active flag")
    logger.info("maintenance_disabled")


def maintenance_status() -> dict:
    from apps.intelligence.models import AppSetting
    active = AppSetting.get(_MAINTENANCE_KEY, "0") == "1"
    return {
        "maintenance": active,
        "reason": AppSetting.get(_MAINTENANCE_REASON_KEY, ""),
        "expected_end": AppSetting.get(_MAINTENANCE_END_KEY, ""),
    }
