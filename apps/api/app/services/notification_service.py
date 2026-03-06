from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def notify_job_failure(
    *,
    job_name: str,
    attempt: int,
    max_retries: int,
    error_message: str,
    context: dict[str, Any] | None = None,
) -> None:
    payload = {
        "event": "job_failure",
        "job_name": job_name,
        "attempt": attempt,
        "max_retries": max_retries,
        "error_message": error_message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "context": context or {},
    }

    logger.error("Background job failed", extra=payload)

    webhook_url = settings.notification_webhook_url
    if not webhook_url:
        return

    try:
        response = httpx.post(webhook_url, json=payload, timeout=10.0)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to deliver job failure notification: %s", exc, extra={"payload": payload})
