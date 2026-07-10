"""Minimal Django settings for offline CI eval (no Postgres required)."""

from .development import *  # noqa: F403

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Avoid external service calls in CI eval paths.
CELERY_TASK_ALWAYS_EAGER = True
