import asyncio
import httpx
import openai
import pytest

from app.agents.retry import is_transient_error, retry_call


class NonTransientError(Exception):
    pass


async def test_transient_error_retried_then_succeeds() -> None:
    calls = 0
    slept = []

    async def fake_sleep(duration: float) -> None:
        slept.append(duration)

    async def flaky_call() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TimeoutError("Connection timed out")
        return "success"

    result = await retry_call(flaky_call, max_attempts=3, sleep_func=fake_sleep)
    assert result == "success"
    assert calls == 3
    assert len(slept) == 2


async def test_non_transient_error_raised_immediately() -> None:
    calls = 0
    slept = []

    async def fake_sleep(duration: float) -> None:
        slept.append(duration)

    async def bad_call() -> str:
        nonlocal calls
        calls += 1
        raise NonTransientError("Invalid argument")

    with pytest.raises(NonTransientError):
        await retry_call(bad_call, max_attempts=3, sleep_func=fake_sleep)

    assert calls == 1
    assert len(slept) == 0


async def test_transient_error_exhausts_retries() -> None:
    calls = 0
    slept = []

    async def fake_sleep(duration: float) -> None:
        slept.append(duration)

    async def always_failing() -> str:
        nonlocal calls
        calls += 1
        raise ConnectionError("Server unreachable")

    with pytest.raises(ConnectionError):
        await retry_call(always_failing, max_attempts=3, sleep_func=fake_sleep)

    assert calls == 3
    assert len(slept) == 2


async def test_retry_after_respected_from_headers() -> None:
    calls = 0
    slept = []

    async def fake_sleep(duration: float) -> None:
        slept.append(duration)

    response = httpx.Response(
        status_code=429,
        headers={"retry-after": "2.5"},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat"),
    )
    exc = openai.RateLimitError(
        message="Rate limit exceeded",
        response=response,
        body=None,
    )

    async def rate_limited_call() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise exc
        return "ok after 429"

    result = await retry_call(rate_limited_call, max_attempts=3, sleep_func=fake_sleep)
    assert result == "ok after 429"
    assert calls == 2
    assert len(slept) == 1
    assert slept[0] == 2.5


async def test_retry_after_capped_at_max_delay() -> None:
    calls = 0
    slept = []

    async def fake_sleep(duration: float) -> None:
        slept.append(duration)

    response = httpx.Response(
        status_code=503,
        headers={"retry-after": "60.0"},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat"),
    )
    exc = httpx.HTTPStatusError("Service unavailable", request=response.request, response=response)

    async def service_down() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise exc
        return "recovered"

    result = await retry_call(service_down, max_attempts=3, max_delay=6.0, sleep_func=fake_sleep)
    assert result == "recovered"
    assert calls == 2
    assert len(slept) == 1
    assert slept[0] == 6.0


def test_is_transient_error_detection() -> None:
    assert is_transient_error(TimeoutError())[0] is True
    assert is_transient_error(ConnectionError())[0] is True
    assert is_transient_error(ValueError())[0] is False
    assert is_transient_error(KeyError())[0] is False
