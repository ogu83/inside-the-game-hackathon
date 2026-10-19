"""Shared helper for transient error retries (OpenAI, Azure, network timeouts).

Retries only transient errors (timeouts, connection drops, HTTP 429 and 5xx) with exponential
backoff, full jitter, cap, and honouring Retry-After headers when present.
Non-transient errors (e.g. 400 Bad Request, 401 Unauthorized, ValueError) fail fast on first attempt.
"""

import asyncio
from collections.abc import Awaitable, Callable
import logging
import random
from typing import Any, TypeVar

import httpx
import openai
from azure.core.exceptions import (
    HttpResponseError,
    ServiceRequestError,
    ServiceResponseTimeoutError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def is_transient_error(exc: BaseException) -> tuple[bool, float | None]:
    """Check if an exception is transient, returning (is_transient, retry_after_s)."""
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, ConnectionError)):
        return True, None

    if isinstance(exc, (ServiceResponseTimeoutError, ServiceRequestError)):
        return True, None

    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError, openai.RateLimitError)):
        retry_after = _extract_retry_after(exc)
        return True, retry_after

    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True, None

    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        if response is not None:
            status_code = getattr(response, "status_code", None)

    if isinstance(status_code, int) and status_code in TRANSIENT_STATUS_CODES:
        return True, _extract_retry_after(exc)

    if isinstance(exc, (HttpResponseError, openai.APIStatusError, httpx.HTTPStatusError)):
        if status_code in TRANSIENT_STATUS_CODES:
            return True, _extract_retry_after(exc)

    return False, None


def _extract_retry_after(exc: Any) -> float | None:
    """Extract Retry-After duration in seconds from response headers or exception attributes."""
    if hasattr(exc, "retry_after") and isinstance(exc.retry_after, (int, float)):
        return float(exc.retry_after)

    response = getattr(exc, "response", None)
    if response is None:
        return None

    headers = getattr(response, "headers", None)
    if not headers:
        return None

    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw:
        try:
            return float(raw)
        except (ValueError, TypeError):
            pass

    raw_ms = headers.get("retry-after-ms") or headers.get("Retry-After-Ms")
    if raw_ms:
        try:
            return float(raw_ms) / 1000.0
        except (ValueError, TypeError):
            pass

    return None


async def retry_call(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 6.0,
    sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
    jitter_func: Callable[[float, float], float] = random.uniform,
) -> T:
    """Execute an async callable, retrying transient errors with exponential backoff and jitter."""
    for attempt in range(max_attempts):
        try:
            return await fn()
        except Exception as exc:
            is_transient, retry_after = is_transient_error(exc)
            if not is_transient or attempt >= max_attempts - 1:
                raise

            if retry_after is not None and retry_after > 0:
                delay = min(max_delay, retry_after)
            else:
                delay = jitter_func(0.0, min(max_delay, base_delay * (2 ** attempt)))

            logger.warning(
                "Transient error on attempt %d/%d (%s: %s). Retrying in %.2fs.",
                attempt + 1,
                max_attempts,
                type(exc).__name__,
                exc,
                delay,
            )
            await sleep_func(delay)

    raise RuntimeError("Unreachable: loop exited without return or raise")
