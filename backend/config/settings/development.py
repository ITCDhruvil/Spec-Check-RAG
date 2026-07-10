from config.settings.base import *  # noqa: F403

DEBUG = env.bool("DEBUG", default=True)  # noqa: F405

# Dev CORS: explicit list so browser on :3002 works (env is read once at process start)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
    "http://localhost:3003",
    "http://127.0.0.1:3003",
    "http://localhost:3010",
    "http://127.0.0.1:3010",
]
# start.bat sets EXTRA_CORS_ORIGINS when the frontend binds an alternate port
_extra_cors = env.list("EXTRA_CORS_ORIGINS", default=[])  # noqa: F405
if _extra_cors:
    CORS_ALLOWED_ORIGINS = list(dict.fromkeys([*CORS_ALLOWED_ORIGINS, *_extra_cors]))
CORS_URLS_REGEX = r"^.*$"

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# Dev: avoid throttling during local E2E testing
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # noqa: F405

# Run summary/regenerate in-process (no Celery required). Set False if using a worker.
INTELLIGENCE_SYNC_GENERATION = env.bool("INTELLIGENCE_SYNC_GENERATION", default=True)  # noqa: F405
# Parse uploads without Celery (recommended on Windows). Set False if worker uses -P solo.
PROCESSING_SYNC = env.bool("PROCESSING_SYNC", default=True)  # noqa: F405
