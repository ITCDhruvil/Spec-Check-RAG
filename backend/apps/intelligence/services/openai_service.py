import json
import logging
import time
from typing import Any

from django.conf import settings
from openai import APIConnectionError, APITimeoutError, AzureOpenAI, OpenAI, RateLimitError

from apps.core.exceptions import ServiceError

logger = logging.getLogger(__name__)


def _resolve_azure_deployment(explicit: str, fallback: str) -> str:
    """Use explicit Azure deployment when set; otherwise fall back to OPENAI_* model name."""
    value = (explicit or "").strip()
    if value and value not in {"your-gpt-deployment-name", "your-embedding-deployment-name"}:
        return value
    return fallback


def _use_azure_openai() -> bool:
    return getattr(settings, "AI_PROVIDER", "openai").lower() == "azure"


def _azure_openai_configured() -> bool:
    return bool(
        getattr(settings, "AZURE_OPENAI_ENDPOINT", "")
        and getattr(settings, "AZURE_OPENAI_API_KEY", "")
    )


class OpenAIService:
    """Reusable OpenAI / Azure OpenAI client with retries, timeouts, and JSON responses."""

    def __init__(self) -> None:
        if _use_azure_openai():
            if not _azure_openai_configured():
                raise ServiceError(
                    "AI_PROVIDER=azure but AZURE_OPENAI_ENDPOINT/AZURE_OPENAI_API_KEY are not set.",
                    code="azure_openai_not_configured",
                    status_code=503,
                )
            self._client = AzureOpenAI(
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                timeout=settings.OPENAI_TIMEOUT_SECONDS,
                max_retries=0,
            )
        if _use_azure_openai():
            self.model = _resolve_azure_deployment(
                getattr(settings, "AZURE_OPENAI_CHAT_DEPLOYMENT", ""),
                settings.OPENAI_MODEL,
            )
            self._embedding_model = _resolve_azure_deployment(
                getattr(settings, "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", ""),
                settings.OPENAI_EMBEDDING_MODEL,
            )
            logger.debug(
                "openai_client provider=azure chat=%s embed=%s",
                self.model,
                self._embedding_model,
            )
        else:
            if not settings.OPENAI_API_KEY:
                raise ServiceError(
                    "OPENAI_API_KEY is not configured.",
                    code="openai_not_configured",
                    status_code=503,
                )
            self._client = OpenAI(
                api_key=settings.OPENAI_API_KEY,
                timeout=settings.OPENAI_TIMEOUT_SECONDS,
                max_retries=0,
            )
            self.model = settings.OPENAI_MODEL
            self._embedding_model = settings.OPENAI_EMBEDDING_MODEL

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float | None = None,
        model: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        temperature = temperature if temperature is not None else settings.OPENAI_TEMPERATURE
        deployment = model or self.model
        last_error: Exception | None = None

        for attempt in range(settings.OPENAI_MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=deployment,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                    temperature=temperature,
                )
                content = response.choices[0].message.content or "{}"
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                    "model": deployment,
                    "provider": "azure" if _use_azure_openai() else "openai",
                }
                return json.loads(content), usage

            except (APITimeoutError, APIConnectionError, RateLimitError) as exc:
                last_error = exc
                wait = min(2 ** attempt * (3 if isinstance(exc, RateLimitError) else 1), 45)
                logger.warning(
                    "openai_retry attempt=%s error=%s wait=%s",
                    attempt + 1,
                    type(exc).__name__,
                    wait,
                )
                time.sleep(wait)
            except json.JSONDecodeError as exc:
                raise ServiceError(
                    "OpenAI returned invalid JSON.",
                    code="openai_invalid_json",
                    status_code=502,
                ) from exc

        raise ServiceError(
            f"OpenAI request failed after retries: {last_error}",
            code="openai_request_failed",
            status_code=502,
        ) from last_error

    def chat_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type,
        temperature: float | None = None,
        model: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Structured-output chat using the Pydantic-schema parse API.

        Falls back to chat_json() when the provider/SDK lacks parse support (older
        Azure api-version). Returns (parsed_dict, usage) — same contract as chat_json.
        """
        temperature = temperature if temperature is not None else settings.OPENAI_TEMPERATURE
        deployment = model or self.model
        parse_fn = getattr(getattr(self._client.beta.chat, "completions", None), "parse", None)
        if parse_fn is None:
            return self.chat_json(system=system, user=user, temperature=temperature, model=model)

        last_error: Exception | None = None
        for attempt in range(settings.OPENAI_MAX_RETRIES + 1):
            try:
                response = parse_fn(
                    model=deployment,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format=schema,
                    temperature=temperature,
                )
                parsed = response.choices[0].message.parsed
                data = parsed.model_dump() if parsed is not None else {"items": []}
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                    "model": deployment,
                    "provider": "azure" if _use_azure_openai() else "openai",
                }
                return data, usage
            except (APITimeoutError, APIConnectionError, RateLimitError) as exc:
                last_error = exc
                time.sleep(min(2**attempt, 30))
            except Exception as exc:
                # Parse API unsupported for this model/version → fall back once.
                logger.warning("openai_structured_fallback error=%s", type(exc).__name__)
                return self.chat_json(system=system, user=user, temperature=temperature, model=model)

        raise ServiceError(
            f"OpenAI structured request failed after retries: {last_error}",
            code="openai_request_failed",
            status_code=502,
        ) from last_error

    def chat_text(
        self,
        *,
        system: str,
        user: str,
        temperature: float | None = None,
        model: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Plain-text chat completion (no JSON response_format). Returns (text, usage)."""
        temperature = temperature if temperature is not None else settings.OPENAI_TEMPERATURE
        deployment = model or self.model
        last_error: Exception | None = None

        for attempt in range(settings.OPENAI_MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=deployment,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                )
                content = response.choices[0].message.content or ""
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                    "model": deployment,
                    "provider": "azure" if _use_azure_openai() else "openai",
                }
                return content, usage

            except (APITimeoutError, APIConnectionError, RateLimitError) as exc:
                last_error = exc
                wait = min(2 ** attempt * (3 if isinstance(exc, RateLimitError) else 1), 45)
                logger.warning(
                    "openai_retry attempt=%s error=%s wait=%s",
                    attempt + 1,
                    type(exc).__name__,
                    wait,
                )
                time.sleep(wait)

        raise ServiceError(
            f"OpenAI request failed after retries: {last_error}",
            code="openai_request_failed",
            status_code=502,
        ) from last_error

    def embed_texts(self, texts: list[str]) -> tuple[list[list[float]], dict[str, Any]]:
        """Batch embed texts for Chroma indexing / retrieval."""
        if not texts:
            embed_model = (
                self._embedding_model if _use_azure_openai() else settings.OPENAI_EMBEDDING_MODEL
            )
            return [], {"total_tokens": 0, "model": embed_model}

        model = self._embedding_model if _use_azure_openai() else settings.OPENAI_EMBEDDING_MODEL
        batch_size = 100
        all_embeddings: list[list[float]] = []
        total_tokens = 0
        last_error: Exception | None = None

        max_chars = settings.OPENAI_EMBEDDING_MAX_CHARS

        def _truncate_for_embedding(text: str) -> str:
            if len(text) <= max_chars:
                return text
            return text[:max_chars]

        for start in range(0, len(texts), batch_size):
            batch = [_truncate_for_embedding(t) for t in texts[start : start + batch_size]]
            for attempt in range(settings.OPENAI_MAX_RETRIES + 1):
                try:
                    response = self._client.embeddings.create(
                        model=model,
                        input=batch,
                    )
                    ordered = sorted(response.data, key=lambda x: x.index)
                    all_embeddings.extend([row.embedding for row in ordered])
                    if response.usage:
                        total_tokens += response.usage.total_tokens or 0
                    break
                except (APITimeoutError, APIConnectionError, RateLimitError) as exc:
                    last_error = exc
                    time.sleep(min(2**attempt, 30))
            else:
                raise ServiceError(
                    f"OpenAI embedding failed: {last_error}",
                    code="openai_embedding_failed",
                    status_code=502,
                ) from last_error

        usage = {
            "total_tokens": total_tokens,
            "model": model,
            "embedding_count": len(texts),
            "provider": "azure" if _use_azure_openai() else "openai",
        }
        return all_embeddings, usage
