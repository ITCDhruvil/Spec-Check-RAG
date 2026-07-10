"""
Fine-tuning pipeline: feedback → JSONL dataset → Azure OpenAI fine-tune job →
model routing update → maintenance mode clear.

Only gpt-4o-mini is used for fine-tuning (cost ~$3/1M training tokens vs ~$25
for gpt-4o). A fine-tuned mini on narrow extraction tasks consistently beats
the base strong model.

Flow:
    check_and_trigger()  ← called after each FieldFeedback save
        if enough negative feedback → estimate cost → if OK → trigger()
    trigger(extraction_type)
        build dataset → upload file → create job → enable maintenance → return job
    poll_job(job_id)         ← called by Celery task every 5 min
        retrieve status → if done → update routing → disable maintenance
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# --- settings defaults ---
FINETUNE_BASE_MODEL = "gpt-4o-mini-2024-07-18"
FINETUNE_THRESHOLD = 50           # negative feedbacks per type before trigger
FINETUNE_MAX_COST_USD = 5.0       # abort if estimated cost exceeds this
FINETUNE_TOKEN_COST_PER_M = 3.0   # USD per 1M training tokens (gpt-4o-mini)
FINETUNE_EPOCHS = 3


def _base_model() -> str:
    return getattr(settings, "FINETUNE_BASE_MODEL", FINETUNE_BASE_MODEL)


def _threshold() -> int:
    return getattr(settings, "FINETUNE_FEEDBACK_THRESHOLD", FINETUNE_THRESHOLD)


def _max_cost_usd() -> float:
    return getattr(settings, "FINETUNE_MAX_COST_USD", FINETUNE_MAX_COST_USD)


def _enabled() -> bool:
    return getattr(settings, "FINETUNE_ENABLED", True)


def _openai_client():
    """Return a raw OpenAI / AzureOpenAI client for fine-tuning API calls."""
    from openai import AzureOpenAI, OpenAI

    if getattr(settings, "AI_PROVIDER", "openai").lower() == "azure":
        return AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=getattr(settings, "AZURE_OPENAI_FINETUNE_API_VERSION",
                                settings.AZURE_OPENAI_API_VERSION),
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        )
    return OpenAI(api_key=settings.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = (
    "You are a procurement document extraction specialist. "
    "Given the following document excerpt, extract the '{field_key}' field accurately. "
    "Return a JSON object with a single key 'value' containing the extracted text. "
    "If not found, return {{\"value\": null}}."
)


def _build_training_example(feedback) -> dict[str, Any]:
    """
    Convert one FieldFeedback row into an OpenAI fine-tune message format.

    user   = source_text_context (the verbatim document excerpt)
    assistant = {"value": "<correct_value>"}
    """
    system = SYSTEM_PROMPT_TEMPLATE.format(field_key=feedback.field_key)
    user_content = (
        f"Document excerpt:\n\n{feedback.source_text_context or feedback.extracted_value}"
    )
    correct = feedback.correct_value.strip() if feedback.correct_value else ""
    assistant_content = json.dumps({"value": correct or None})
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ]
    }


def _estimate_tokens(examples: list[dict[str, Any]]) -> int:
    """Rough token estimate: 4 chars ≈ 1 token."""
    total_chars = sum(
        len(json.dumps(ex)) for ex in examples
    )
    return total_chars // 4


def build_dataset(feedbacks) -> tuple[str, int, float]:
    """
    Returns (jsonl_path, token_count, estimated_cost_usd).
    Caller must delete the temp file when done.
    """
    examples = [_build_training_example(fb) for fb in feedbacks]
    tokens = _estimate_tokens(examples) * FINETUNE_EPOCHS
    cost = (tokens / 1_000_000) * FINETUNE_TOKEN_COST_PER_M

    fd, path = tempfile.mkstemp(suffix=".jsonl", prefix="finetune_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    logger.info(
        "finetune_dataset_built examples=%d tokens_est=%d cost_est_usd=%.4f path=%s",
        len(examples), tokens, cost, path,
    )
    return path, tokens, cost


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------

def check_and_trigger(extraction_type: str) -> None:
    """
    Called after each negative FieldFeedback save.
    Triggers fine-tuning when enough corrections accumulated.
    """
    if not _enabled():
        return

    from apps.intelligence.models import FieldFeedback, FineTuneJob, FineTuneJobStatus

    # Don't start a new job if one is already running for this type.
    active = FineTuneJob.objects.filter(
        extraction_type=extraction_type,
        status__in=[FineTuneJobStatus.PENDING, FineTuneJobStatus.UPLOADING, FineTuneJobStatus.RUNNING],
    ).exists()
    if active:
        logger.debug("finetune_skip already_running extraction_type=%s", extraction_type)
        return

    count = FieldFeedback.objects.filter(
        extraction_type=extraction_type,
        rating="down",
        correct_value__gt="",
        used_in_finetune=False,
    ).count()

    if count < _threshold():
        logger.debug(
            "finetune_skip insufficient_feedback extraction_type=%s count=%d threshold=%d",
            extraction_type, count, _threshold(),
        )
        return

    logger.info(
        "finetune_threshold_reached extraction_type=%s count=%d — triggering",
        extraction_type, count,
    )
    trigger(extraction_type)


def trigger(extraction_type: str) -> "FineTuneJob":
    """
    Build dataset, upload, submit fine-tune job, enable maintenance mode.
    """
    from apps.intelligence.models import (
        FieldFeedback, FineTuneJob, FineTuneJobStatus,
    )
    from apps.intelligence.services.maintenance_service import enable_maintenance

    feedbacks = list(
        FieldFeedback.objects.filter(
            extraction_type=extraction_type,
            rating="down",
            correct_value__gt="",
            used_in_finetune=False,
        ).order_by("created_at")
    )

    if not feedbacks:
        raise ValueError(f"No usable feedback for {extraction_type}")

    job = FineTuneJob.objects.create(
        extraction_type=extraction_type,
        status=FineTuneJobStatus.UPLOADING,
        base_model=_base_model(),
        feedback_count=len(feedbacks),
    )

    dataset_path = None
    try:
        dataset_path, tokens, cost = build_dataset(feedbacks)
        job.estimated_cost_usd = cost

        if cost > _max_cost_usd():
            job.status = FineTuneJobStatus.FAILED
            job.error_message = (
                f"Estimated cost ${cost:.2f} exceeds limit ${_max_cost_usd():.2f}. "
                "Raise FINETUNE_MAX_COST_USD to proceed."
            )
            job.save()
            logger.warning(
                "finetune_aborted_cost_guard extraction_type=%s cost_usd=%.4f limit=%.4f",
                extraction_type, cost, _max_cost_usd(),
            )
            return job

        client = _openai_client()

        # Upload dataset file.
        with open(dataset_path, "rb") as f:
            file_resp = client.files.create(file=f, purpose="fine-tune")
        job.azure_file_id = file_resp.id
        job.save()

        # Create fine-tune job.
        ft_job = client.fine_tuning.jobs.create(
            training_file=file_resp.id,
            model=_base_model(),
            hyperparameters={"n_epochs": FINETUNE_EPOCHS},
        )
        job.azure_job_id = ft_job.id
        job.status = FineTuneJobStatus.RUNNING
        job.save()

        # Mark feedbacks as consumed.
        FieldFeedback.objects.filter(id__in=[fb.id for fb in feedbacks]).update(used_in_finetune=True)

        # Enable maintenance mode.
        enable_maintenance(
            reason=f"Fine-tuning {extraction_type} model ({len(feedbacks)} corrections)",
        )

        logger.info(
            "finetune_job_started extraction_type=%s azure_job_id=%s file_id=%s feedback_count=%d",
            extraction_type, ft_job.id, file_resp.id, len(feedbacks),
        )

    except Exception as exc:
        job.status = FineTuneJobStatus.FAILED
        job.error_message = str(exc)[:1000]
        job.save()
        logger.exception(
            "finetune_trigger_failed extraction_type=%s job_id=%s", extraction_type, job.id
        )
        raise

    finally:
        if dataset_path and os.path.exists(dataset_path):
            os.unlink(dataset_path)

    return job


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------

def poll_job(job_id: str) -> str:
    """
    Check status of a running fine-tune job.
    Returns new status string. Called by Celery task.
    """
    from apps.intelligence.models import AppSetting, FineTuneJob, FineTuneJobStatus
    from apps.intelligence.services.maintenance_service import disable_maintenance

    try:
        job = FineTuneJob.objects.get(id=job_id)
    except FineTuneJob.DoesNotExist:
        logger.error("finetune_poll job_not_found id=%s", job_id)
        return "not_found"

    if job.status not in (FineTuneJobStatus.RUNNING, FineTuneJobStatus.UPLOADING):
        return job.status

    try:
        client = _openai_client()
        ft = client.fine_tuning.jobs.retrieve(job.azure_job_id)
        azure_status = ft.status  # "validating_files"|"queued"|"running"|"succeeded"|"failed"|"cancelled"

        if azure_status in ("validating_files", "queued", "running"):
            job.status = FineTuneJobStatus.RUNNING
            job.save()
            return job.status

        if azure_status == "succeeded":
            model_id = ft.fine_tuned_model
            job.status = FineTuneJobStatus.SUCCEEDED
            job.fine_tuned_model_id = model_id or ""
            job.save()

            # Store fine-tuned model ID so extraction_model() can pick it up.
            if model_id:
                AppSetting.set(
                    f"finetune_model_{job.extraction_type}",
                    model_id,
                    f"Fine-tuned model for {job.extraction_type}",
                )
                logger.info(
                    "finetune_succeeded extraction_type=%s model_id=%s",
                    job.extraction_type, model_id,
                )

            disable_maintenance()
            return FineTuneJobStatus.SUCCEEDED

        if azure_status in ("failed", "cancelled"):
            job.status = (
                FineTuneJobStatus.FAILED
                if azure_status == "failed"
                else FineTuneJobStatus.CANCELLED
            )
            job.error_message = getattr(ft, "error", {}) or azure_status
            job.save()
            disable_maintenance()
            logger.warning(
                "finetune_terminal extraction_type=%s status=%s", job.extraction_type, azure_status
            )
            return job.status

    except Exception:
        logger.exception("finetune_poll_error job_id=%s", job_id)

    return job.status
