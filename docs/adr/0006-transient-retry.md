# ADR 0006: Transient Error Retry Policy with Exponential Backoff

## Status
Accepted

## Context
External model calls to Azure AI Foundry, OpenAI APIs, and remote services can experience transient network hiccups, HTTP 429 rate limits, and temporary 5xx server errors.

Early implementations duplicated retry logic across `app/agents/workflow.py` and `app/agents/producer.py`. These legacy loops caught generic `Exception` unconditionally and slept for fixed intervals (up to 6 seconds). This created several antipatterns:
1. Non-transient bugs (such as `KeyError`, invalid schema formats, or bad authentication tokens) were repeatedly retried, wasting time and tokens before eventually failing.
2. Fixed sleeps without jitter caused synchronized retry bursts (the thundering herd problem) against upstream model endpoints.
3. Explicit server backoff signals (such as `Retry-After` response headers) were ignored.

## Decision
1. **Centralized Retry Helper (`app/agents/retry.py`):**
   - All external model invocations route through a single helper: `retry_call(fn, max_retries=3, base_delay=0.5, max_delay=6.0, sleep_fn=asyncio.sleep)`.

2. **Selective Transient Error Filtering (`is_transient_error`):**
   - The retry policy checks exception types and attributes:
     - Standard network issues: `TimeoutError`, `asyncio.TimeoutError`, `ConnectionError`, `BrokenPipeError`.
     - Upstream SDK error codes: HTTP 429 (rate limits) and 5xx (500, 502, 503, 504 server errors) from Azure AI Foundry and OpenAI SDKs (`RateLimitError`, `InternalServerError`, `APIConnectionError`, `APITimeoutError`).
   - Non-transient exceptions (such as `AuthenticationError`, `BadRequestError`, `KeyError`, and `TypeError`) propagate immediately on the first attempt without retrying.

3. **Exponential Backoff with Full Jitter:**
   - Sleep intervals scale exponentially: `delay = min(max_delay, base_delay * (2 ** (attempt - 1)))`.
   - Full jitter is applied by picking a uniform random duration in `[0, delay]`, spreading out retry traffic across concurrent match sessions.

4. **Honoring `Retry-After`:**
   - If an exception carries a `retry_after` attribute or header, that value is honored (bounded by `max_delay`).

5. **Testability via Injectable Clock:**
   - The sleep function (`sleep_fn`) is injectable as a parameter, enabling unit tests to verify backoff invariants without real wall-clock delays.

## Consequences
- **Positive:**
  - Fast failure on programming bugs and permanent configuration errors.
  - Resilience against temporary network latency and transient upstream model rate spikes.
  - Clean separation of concerns with zero duplicated retry loops.
- **Negative / Trade-offs:**
  - Transient failures that persist past the retry cap trigger fallback to deterministic template commentary per SPEC design rule 7.
