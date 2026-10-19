"""Unit tests for shared credential and Foundry client caching (app.agents.auth)."""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock
from azure.core.credentials import AccessToken

from app.agents.auth import (
    AsyncCachedTokenCredential,
    SyncCachedTokenCredential,
    get_shared_async_credential,
    get_shared_credential,
    get_foundry_chat_client,
    is_running_in_azure,
    reset_auth_cache_for_tests,
)


@pytest.fixture(autouse=True)
def clean_auth_cache():
    reset_auth_cache_for_tests()
    yield
    reset_auth_cache_for_tests()


def test_is_running_in_azure(monkeypatch):
    monkeypatch.delenv("CONTAINER_APP_NAME", raising=False)
    monkeypatch.delenv("IDENTITY_ENDPOINT", raising=False)
    monkeypatch.delenv("MSI_ENDPOINT", raising=False)
    monkeypatch.delenv("WEBSITE_INSTANCE_ID", raising=False)
    assert not is_running_in_azure()

    monkeypatch.setenv("CONTAINER_APP_NAME", "ca-matchday")
    assert is_running_in_azure()


async def test_async_cached_credential_reuses_unexpired_token():
    mock_cred = AsyncMock()
    # Token expiring in 1 hour
    mock_cred.get_token.return_value = AccessToken("token-123", int(time.time()) + 3600)

    cached = AsyncCachedTokenCredential(mock_cred)

    t1 = await cached.get_token("scope1")
    t2 = await cached.get_token("scope1")

    assert t1.token == "token-123"
    assert t2.token == "token-123"
    assert mock_cred.get_token.call_count == 1  # Called only once!


def test_sync_cached_credential_reuses_unexpired_token():
    mock_cred = MagicMock()
    mock_cred.get_token.return_value = AccessToken("token-456", int(time.time()) + 3600)

    cached = SyncCachedTokenCredential(mock_cred)

    t1 = cached.get_token("scope2")
    t2 = cached.get_token("scope2")

    assert t1.token == "token-456"
    assert t2.token == "token-456"
    assert mock_cred.get_token.call_count == 1


def test_get_shared_credentials_singleton(monkeypatch):
    monkeypatch.delenv("CONTAINER_APP_NAME", raising=False)
    c1 = get_shared_async_credential()
    c2 = get_shared_async_credential()
    assert c1 is c2

    s1 = get_shared_credential()
    s2 = get_shared_credential()
    assert s1 is s2


def test_get_foundry_chat_client_caches_per_model_and_endpoint(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://test.foundry.azure.com/api/projects/test")
    monkeypatch.setenv("SMALL_MODEL_DEPLOYMENT", "gpt-5.4-mini")
    monkeypatch.setenv("FRONTIER_MODEL_DEPLOYMENT", "gpt-5.5")

    client1 = get_foundry_chat_client("https://test.foundry.azure.com/api/projects/test", "gpt-5.4-mini")
    client2 = get_foundry_chat_client("https://test.foundry.azure.com/api/projects/test", "gpt-5.4-mini")
    client_diff = get_foundry_chat_client("https://test.foundry.azure.com/api/projects/test", "gpt-5.5")

    assert client1 is client2
    assert client1 is not client_diff


async def test_warm_up_calls_each_model_once_and_never_raises(monkeypatch) -> None:
    from app.agents import auth

    calls = []

    class _Agent:
        def __init__(self, model):
            self.model = model

        async def run(self, prompt, options=None):
            calls.append(self.model)
            if self.model == "big":
                raise RuntimeError("cold model unavailable")

    class _Client:
        def __init__(self, model):
            self.model = model

        def as_agent(self, **_):
            return _Agent(self.model)

    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.invalid/api/projects/p")
    monkeypatch.setenv("SMALL_MODEL_DEPLOYMENT", "small")
    monkeypatch.setenv("FRONTIER_MODEL_DEPLOYMENT", "big")
    monkeypatch.setattr(auth, "get_foundry_chat_client", lambda endpoint, model: _Client(model))
    await auth.warm_up_foundry()
    assert calls == ["small", "big"]
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT")
    await auth.warm_up_foundry()  # no endpoint: nothing to warm
    assert calls == ["small", "big"]
