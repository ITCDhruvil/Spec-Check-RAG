"""
Base settings for Spec Check — tender document intelligence platform.
"""
import sys
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:3000"]),
    MAX_UPLOAD_SIZE_MB=(int, 50),
    CELERY_TASK_MAX_RETRIES=(int, 3),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="change-me-in-production-use-strong-key")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.core",
    "apps.authentication",
    "apps.documents",
    "apps.processing",
    "apps.parsing",
    "apps.intelligence",
    "apps.chat",
    "apps.health",
]

# OpenAI (Phase 3)
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_MODEL = env("OPENAI_MODEL", default="gpt-4o")
OPENAI_MODEL_FAST = env("OPENAI_MODEL_FAST", default="gpt-4o-mini")
OPENAI_TIMEOUT_SECONDS = env.int("OPENAI_TIMEOUT_SECONDS", default=120)
OPENAI_MAX_RETRIES = env.int("OPENAI_MAX_RETRIES", default=3)
OPENAI_TEMPERATURE = env.float("OPENAI_TEMPERATURE", default=0.1)
INTELLIGENCE_MAX_CHUNK_CHARS = env.int("INTELLIGENCE_MAX_CHUNK_CHARS", default=6000)
# Leaf chunk embedded + retrieved (~400 tokens ≈ 1600 chars); parent section sent to LLM
INTELLIGENCE_LEAF_CHUNK_CHARS = env.int("INTELLIGENCE_LEAF_CHUNK_CHARS", default=1600)
INTELLIGENCE_CHUNK_OVERLAP_RATIO = env.float("INTELLIGENCE_CHUNK_OVERLAP_RATIO", default=0.10)
# Agentic field verifier: retry low-confidence / missing required fields after extraction
INTELLIGENCE_AGENTIC_VERIFIER_ENABLED = env.bool("INTELLIGENCE_AGENTIC_VERIFIER_ENABLED", default=True)
INTELLIGENCE_AGENTIC_LOW_CONF_THRESHOLD = env.int("INTELLIGENCE_AGENTIC_LOW_CONF_THRESHOLD", default=50)
INTELLIGENCE_COVER_PAGE_MAX = env.int("INTELLIGENCE_COVER_PAGE_MAX", default=2)
INTELLIGENCE_MIN_SECTION_CHARS = env.int("INTELLIGENCE_MIN_SECTION_CHARS", default=40)
# text-embedding-3-* allows 8192 tokens (~32 000 chars). Cap at 1.5× the max chunk
# size — no need to send more; truncation just wastes the API call budget.
OPENAI_EMBEDDING_MAX_CHARS = env.int("OPENAI_EMBEDDING_MAX_CHARS", default=9000)
INTELLIGENCE_PROMPT_VERSION = env("INTELLIGENCE_PROMPT_VERSION", default="4.4.1")
INTELLIGENCE_DEFAULT_EXTRACTION_CHUNKS = env.int(
    "INTELLIGENCE_DEFAULT_EXTRACTION_CHUNKS", default=10
)
INTELLIGENCE_BROAD_EXTRACTION_CHUNKS = env.int(
    "INTELLIGENCE_BROAD_EXTRACTION_CHUNKS", default=14
)
# Number of parallel threads for extraction (one per type). Default = 8 = len(FOCUSED_EXTRACTION_TYPES).
# Lower this on resource-constrained machines or when hitting OpenAI rate limits.
INTELLIGENCE_EXTRACTION_WORKERS = env.int("INTELLIGENCE_EXTRACTION_WORKERS", default=8)
# Opt #5 — max chars per chunk after paragraph-level pre-filtering (3 500 ≈ 875 tokens).
INTELLIGENCE_CHUNK_TRIM_CHARS = env.int("INTELLIGENCE_CHUNK_TRIM_CHARS", default=3500)
# Opt #6 — chunks grouped into one LLM call. 3 → 14 chunks = 5 calls instead of 14.
# Set to 1 to send one chunk per call (original behaviour).
INTELLIGENCE_EXTRACTION_BATCH_SIZE = env.int("INTELLIGENCE_EXTRACTION_BATCH_SIZE", default=3)
# Advanced RAG A4 — structured output via Pydantic-schema parse API (default off until validated).
INTELLIGENCE_STRUCTURED_OUTPUT_ENABLED = env.bool("INTELLIGENCE_STRUCTURED_OUTPUT_ENABLED", default=False)
# Phase 4 — hybrid retrieval for extraction (keyword + vector/BM25 fusion)
INTELLIGENCE_HYBRID_RETRIEVAL_ENABLED = env.bool("INTELLIGENCE_HYBRID_RETRIEVAL_ENABLED", default=True)
INTELLIGENCE_EXTRACTION_RETRIEVAL_TOP_K = env.int("INTELLIGENCE_EXTRACTION_RETRIEVAL_TOP_K", default=12)
INTELLIGENCE_EXTRACTION_MIN_RETRIEVAL_SCORE = env.float(
    "INTELLIGENCE_EXTRACTION_MIN_RETRIEVAL_SCORE", default=0.18
)
INTELLIGENCE_KEYWORD_RRF_WEIGHT = env.float("INTELLIGENCE_KEYWORD_RRF_WEIGHT", default=1.0)
INTELLIGENCE_HYBRID_RRF_WEIGHT = env.float("INTELLIGENCE_HYBRID_RRF_WEIGHT", default=1.0)
# Advanced RAG C1 — doc-type classification + query routing. ON = inject only the
# overrides matching a document's class; OFF = inject all overrides (pre-C1 behavior).
INTELLIGENCE_DOC_TYPE_ROUTING_ENABLED = env.bool(
    "INTELLIGENCE_DOC_TYPE_ROUTING_ENABLED", default=True
)
# Phase 4b — adaptive per-document vocabulary (heuristic + LLM + hybrid feedback)
INTELLIGENCE_ADAPTIVE_LEXICON_ENABLED = env.bool("INTELLIGENCE_ADAPTIVE_LEXICON_ENABLED", default=True)
INTELLIGENCE_ADAPTIVE_LEXICON_LLM = env.bool("INTELLIGENCE_ADAPTIVE_LEXICON_LLM", default=True)
INTELLIGENCE_ADAPTIVE_RETRY_ON_EMPTY = env.bool("INTELLIGENCE_ADAPTIVE_RETRY_ON_EMPTY", default=True)
INTELLIGENCE_ADAPTIVE_TERM_WEIGHT = env.float("INTELLIGENCE_ADAPTIVE_TERM_WEIGHT", default=1.0)
INTELLIGENCE_ADAPTIVE_FEEDBACK_MIN_SCORE = env.float(
    "INTELLIGENCE_ADAPTIVE_FEEDBACK_MIN_SCORE", default=0.22
)
# Learned lexicon DB cache — Layer 1 grows from Layer 2/3 discoveries; skips LLM when mature
INTELLIGENCE_LEARNED_LEXICON_ENABLED = env.bool("INTELLIGENCE_LEARNED_LEXICON_ENABLED", default=True)
INTELLIGENCE_LEARNED_LEXICON_MIN_TERMS_PER_TYPE = env.int(
    "INTELLIGENCE_LEARNED_LEXICON_MIN_TERMS_PER_TYPE", default=8
)
INTELLIGENCE_LEARNED_LEXICON_MAX_PER_TYPE = env.int(
    "INTELLIGENCE_LEARNED_LEXICON_MAX_PER_TYPE", default=60
)
INTELLIGENCE_ADAPTIVE_LLM_SKIP_IF_CACHE_FULL = env.bool(
    "INTELLIGENCE_ADAPTIVE_LLM_SKIP_IF_CACHE_FULL", default=True
)
# False = enqueue Celery; True = run pipeline in HTTP request (slow, dev-friendly)
INTELLIGENCE_SYNC_GENERATION = env.bool("INTELLIGENCE_SYNC_GENERATION", default=False)
# False = Celery worker parses uploads; True = parse in background thread (dev/Windows)
PROCESSING_SYNC = env.bool("PROCESSING_SYNC", default=False)

# Phase 4 — Document-scoped RAG chat (Chroma)
CHROMA_PERSIST_DIR = Path(
    env("CHROMA_PERSIST_DIR", default=str(BASE_DIR / "chroma_data"))
)
CHROMA_COLLECTION_NAME = env("CHROMA_COLLECTION_NAME", default="spec_check_document_chunks")
OPENAI_EMBEDDING_MODEL = env("OPENAI_EMBEDDING_MODEL", default="text-embedding-3-small")
CHAT_RETRIEVAL_TOP_K = env.int("CHAT_RETRIEVAL_TOP_K", default=8)
CHAT_MAX_HISTORY_TURNS = env.int("CHAT_MAX_HISTORY_TURNS", default=6)
CHAT_PROMPT_VERSION = env("CHAT_PROMPT_VERSION", default="4.1.0")
CHAT_MIN_RETRIEVAL_SCORE = env.float("CHAT_MIN_RETRIEVAL_SCORE", default=0.25)
# Advanced RAG C2 — HyDE: append hypothetical-answer passage to retrieval queries.
# Default off; enable together with semantic ranker to recover vocab-mismatch recall.
CHAT_HYDE_ENABLED = env.bool("CHAT_HYDE_ENABLED", default=False)
CHAT_OPENAI_MODEL = env("CHAT_OPENAI_MODEL", default="")

# C5 — User feedback + automatic fine-tuning pipeline.
# FINETUNE_ENABLED=True allows auto fine-tuning when feedback threshold reached.
# Set False to collect feedback without triggering fine-tune (safe default).
FINETUNE_ENABLED = env.bool("FINETUNE_ENABLED", default=False)
FINETUNE_FEEDBACK_THRESHOLD = env.int("FINETUNE_FEEDBACK_THRESHOLD", default=50)
FINETUNE_BASE_MODEL = env("FINETUNE_BASE_MODEL", default="gpt-4o-mini-2024-07-18")
FINETUNE_MAX_COST_USD = env.float("FINETUNE_MAX_COST_USD", default=5.0)
# Azure OpenAI API version for fine-tuning (may differ from chat version).
AZURE_OPENAI_FINETUNE_API_VERSION = env(
    "AZURE_OPENAI_FINETUNE_API_VERSION", default="2024-10-01-preview"
)

# Document parsing (Phase 2)
PARSING_OCR_ENABLED = env.bool("PARSING_OCR_ENABLED", default=True)
PARSING_QUALITY_OCR_THRESHOLD = env.float("PARSING_QUALITY_OCR_THRESHOLD", default=0.35)
PARSING_MIN_PAGE_TEXT_LENGTH = env.int("PARSING_MIN_PAGE_TEXT_LENGTH", default=25)
# PDF parser: docling (default) | auto | azure | pymupdf
# docling = Docling open-source parser, falls back to PyMuPDF if unavailable
# auto   = Azure DI when configured, else PyMuPDF (legacy)
PARSING_PDF_PARSER = env("PARSING_PDF_PARSER", default="docling")

# Azure Document Intelligence (layout parsing)
AZURE_DI_ENDPOINT = env("AZURE_DI_ENDPOINT", default="")
AZURE_DI_KEY = env("AZURE_DI_KEY", default="") or env("AZURE_DI_API_KEY", default="")
AZURE_DI_API_KEY = AZURE_DI_KEY  # backwards-compatible alias
AZURE_DI_MODEL = (
    env("AZURE_DI_MODEL", default="")
    or env("PARSING_AZURE_DI_MODEL", default="prebuilt-layout")
)
PARSING_AZURE_DI_MODEL = AZURE_DI_MODEL  # backwards-compatible alias

# AI provider: openai | azure
AI_PROVIDER = env("AI_PROVIDER", default="openai").lower()

# Azure OpenAI (LLM + embeddings when AI_PROVIDER=azure)
AZURE_OPENAI_ENDPOINT = env("AZURE_OPENAI_ENDPOINT", default="")
AZURE_OPENAI_API_KEY = env("AZURE_OPENAI_API_KEY", default="")
AZURE_OPENAI_API_VERSION = env("AZURE_OPENAI_API_VERSION", default="2024-12-01-preview")
# Optional: Azure deployment names (override OPENAI_MODEL / OPENAI_EMBEDDING_MODEL when set)
AZURE_OPENAI_CHAT_DEPLOYMENT = env("AZURE_OPENAI_CHAT_DEPLOYMENT", default="")
AZURE_OPENAI_CHAT_DEPLOYMENT_FAST = env("AZURE_OPENAI_CHAT_DEPLOYMENT_FAST", default="")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", default="")

# Azure AI Search (Phase 3+ vector store; Chroma used when disabled)
AZURE_SEARCH_ENDPOINT = env("AZURE_SEARCH_ENDPOINT", default="")
AZURE_SEARCH_KEY = env("AZURE_SEARCH_KEY", default="")
AZURE_SEARCH_INDEX_NAME = env("AZURE_SEARCH_INDEX_NAME", default="speccheck-chunks")
AZURE_SEARCH_RAG_ENABLED = env.bool("AZURE_SEARCH_RAG_ENABLED", default=False)
AZURE_SEARCH_VECTOR_DIMENSIONS = env.int("AZURE_SEARCH_VECTOR_DIMENSIONS", default=0)
# Azure RRF scores are query-relative (~0.01–0.05); CHAT_MIN_RETRIEVAL_SCORE=0.25
# is calibrated for Chroma cosine similarity and must not be applied to Azure.
AZURE_SEARCH_MIN_RETRIEVAL_SCORE = env.float("AZURE_SEARCH_MIN_RETRIEVAL_SCORE", default=0.0)
# Azure returns more candidates than Chroma; a higher top_k improves Citation Recall
# without hurting latency significantly (hybrid RRF is server-side).
AZURE_SEARCH_TOP_K = env.int("AZURE_SEARCH_TOP_K", default=16)
# Advanced RAG B1 — native semantic ranker (L2 cross-encoder). Validated best config:
# vs RRF baseline R@1 +22pp, R@3 +5.5pp, R@8 1.0 (held), MRR +14pp, latency -41%.
# Service tier Basic+ (confirmed basic); index has SemanticConfiguration. Runtime
# fallback to RRF if quota exceeded. Default ON.
AZURE_SEARCH_SEMANTIC_ENABLED = env.bool("AZURE_SEARCH_SEMANTIC_ENABLED", default=True)
AZURE_SEARCH_SEMANTIC_CONFIG = env.str("AZURE_SEARCH_SEMANTIC_CONFIG", default="speccheck-semantic")
# Advanced RAG CR — Contextual Retrieval (Anthropic 2024). Prepends LLM-generated
# context snippets to each chunk before embedding and BM25 indexing. Requires a
# full index rebuild after enabling. Default OFF — set True, rebuild, then benchmark.
CONTEXTUAL_RETRIEVAL_ENABLED = env.bool("CONTEXTUAL_RETRIEVAL_ENABLED", default=False)
# Max document chars sent to the contextualizer prompt (≈15k tokens at 4 chars/tok).
CONTEXTUAL_RETRIEVAL_MAX_DOC_CHARS = env.int("CONTEXTUAL_RETRIEVAL_MAX_DOC_CHARS", default=60_000)
# Parallel workers for prefix generation (rate-limit safe default).
CONTEXTUAL_RETRIEVAL_MAX_WORKERS = env.int("CONTEXTUAL_RETRIEVAL_MAX_WORKERS", default=2)

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.request_logging.RequestLoggingMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://postgres:postgres@localhost:5432/spec_check_rag",
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

ADMIN_EMAIL = env("ADMIN_EMAIL", default="admin@itcube.net")

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Media / uploads
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))
DOCUMENT_UPLOAD_DIR = MEDIA_ROOT / "documents"

# DOCX → PDF preview (LibreOffice headless or docx2pdf on Windows + Word)
DOCX_PREVIEW_ENABLED = env.bool("DOCX_PREVIEW_ENABLED", default=True)
LIBREOFFICE_PATH = env("LIBREOFFICE_PATH", default="")
DOCX_PREVIEW_USE_WORD = env.bool(
    "DOCX_PREVIEW_USE_WORD", default=sys.platform == "win32"
)
DOCX_PREVIEW_TIMEOUT_SEC = env.int("DOCX_PREVIEW_TIMEOUT_SEC", default=120)

MAX_UPLOAD_SIZE_BYTES = env.int("MAX_UPLOAD_SIZE_MB", default=50) * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_UPLOAD_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("API_THROTTLE_RATE", default="100/hour"),
        "upload": env("UPLOAD_THROTTLE_RATE", default="30/hour"),
    },
}

# CORS
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Celery
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True

# ── P5: Worker hardening ──────────────────────────────────────────────────────
# Recycle each worker process after N tasks to prevent memory leaks.
CELERY_WORKER_MAX_TASKS_PER_CHILD = env.int("CELERY_WORKER_MAX_TASKS_PER_CHILD", default=50)
# Soft/hard memory limit per worker process (MB). Soft triggers a graceful restart;
# hard kills the process. Requires billiard ≥ 4.x or use --max-memory-per-child flag.
CELERY_WORKER_MAX_MEMORY_PER_CHILD = env.int(
    "CELERY_WORKER_MAX_MEMORY_PER_CHILD", default=512000  # 512 MB in KB
)
# Store results for 24 h then expire from Redis.
CELERY_RESULT_EXPIRES = env.int("CELERY_RESULT_EXPIRES", default=86400)
# Prefetch 1 task at a time — avoids one worker hoarding long-running doc jobs.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
# Reject tasks that have been waiting in queue longer than 1 hour (stale uploads).
CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=600)   # 10 min
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=900)              # 15 min
# Send task-failure events so the Django app can poll/react.
CELERY_SEND_TASK_ERROR_EMAILS = False  # use structured logging instead
CELERY_TASK_SEND_SENT_EVENT = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_MAX_RETRIES = env.int("CELERY_TASK_MAX_RETRIES", default=3)
CELERY_TASK_DEFAULT_RETRY_DELAY = env.int("CELERY_TASK_RETRY_DELAY", default=60)

# Structured logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": (
                '{"timestamp":"%(asctime)s","level":"%(levelname)s",'
                '"logger":"%(name)s","message":"%(message)s"}'
            ),
            "datefmt": "%Y-%m-%dT%H:%M:%SZ",
        },
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO"), "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_BYTES
