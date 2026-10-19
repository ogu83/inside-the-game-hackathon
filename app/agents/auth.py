"""Shared Azure credential and FoundryChatClient caching (P5 performance).

Avoids credential churn, IMDS timeouts on developer PCs, and process spawning
overhead by creating credentials and Foundry chat clients once per process.
"""

import logging
import os
import time
from typing import Any
from azure.core.credentials import AccessToken, TokenCredential
from azure.core.credentials_async import AsyncTokenCredential

log = logging.getLogger(__name__)

_ASYNC_CREDENTIAL: Any = None
_SYNC_CREDENTIAL: Any = None
_CHAT_CLIENTS: dict[tuple[str, str], Any] = {}


def is_running_in_azure() -> bool:
    """Return True if running in Azure Container Apps or Azure App Service."""
    return bool(
        os.environ.get("CONTAINER_APP_NAME")
        or os.environ.get("IDENTITY_ENDPOINT")
        or os.environ.get("MSI_ENDPOINT")
        or os.environ.get("WEBSITE_INSTANCE_ID")
    )


class AsyncCachedTokenCredential(AsyncTokenCredential):
    """In-memory token caching wrapper around an async TokenCredential.

    AzureCliCredential spawns az child processes on every get_token call without
    caching. This wrapper preserves valid tokens until 5 minutes before expiry.
    """

    def __init__(self, credential: Any) -> None:
        self._credential = credential
        self._cache: dict[str, AccessToken] = {}

    async def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
        key = " ".join(sorted(scopes))
        now = time.time()
        cached = self._cache.get(key)
        if cached is not None and cached.expires_on > now + 300:
            return cached
        token = await self._credential.get_token(*scopes, **kwargs)
        self._cache[key] = token
        return token

    async def close(self) -> None:
        if hasattr(self._credential, "close"):
            await self._credential.close()


class SyncCachedTokenCredential(TokenCredential):
    """In-memory token caching wrapper around a synchronous TokenCredential."""

    def __init__(self, credential: Any) -> None:
        self._credential = credential
        self._cache: dict[str, AccessToken] = {}

    def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
        key = " ".join(sorted(scopes))
        now = time.time()
        cached = self._cache.get(key)
        if cached is not None and cached.expires_on > now + 300:
            return cached
        token = self._credential.get_token(*scopes, **kwargs)
        self._cache[key] = token
        return token

    def close(self) -> None:
        if hasattr(self._credential, "close"):
            self._credential.close()


def get_shared_async_credential() -> Any:
    """Return a process-wide async Azure credential with in-memory token caching.

    On a local PC, skips the managed identity probe to eliminate IMDS timeouts.
    In Azure Container Apps, uses managed identity / DefaultAzureCredential.
    """
    global _ASYNC_CREDENTIAL
    if _ASYNC_CREDENTIAL is not None:
        return _ASYNC_CREDENTIAL

    from azure.identity.aio import DefaultAzureCredential

    in_azure = is_running_in_azure()
    if in_azure:
        raw_cred = DefaultAzureCredential()
        log.info("Initialized shared async DefaultAzureCredential for Azure runtime")
    else:
        raw_cred = DefaultAzureCredential(exclude_managed_identity_credential=True)
        log.info("Initialized shared async DefaultAzureCredential (excluding IMDS probe on PC)")

    _ASYNC_CREDENTIAL = AsyncCachedTokenCredential(raw_cred)
    return _ASYNC_CREDENTIAL


def get_shared_credential() -> Any:
    """Return a process-wide synchronous Azure credential with in-memory token caching."""
    global _SYNC_CREDENTIAL
    if _SYNC_CREDENTIAL is not None:
        return _SYNC_CREDENTIAL

    from azure.identity import DefaultAzureCredential

    in_azure = is_running_in_azure()
    if in_azure:
        raw_cred = DefaultAzureCredential()
        log.info("Initialized shared sync DefaultAzureCredential for Azure runtime")
    else:
        raw_cred = DefaultAzureCredential(exclude_managed_identity_credential=True)
        log.info("Initialized shared sync DefaultAzureCredential (excluding IMDS probe on PC)")

    _SYNC_CREDENTIAL = SyncCachedTokenCredential(raw_cred)
    return _SYNC_CREDENTIAL


def get_foundry_chat_client(project_endpoint: str | None = None, model: str | None = None) -> Any:
    """Return a cached FoundryChatClient for the given endpoint and model.

    Reuses HTTP connection pools and client instances across moments and questions
    within the same event loop, avoiding closed-loop errors across pytest runs.
    """
    import asyncio
    from agent_framework_foundry import FoundryChatClient
    from dotenv import load_dotenv

    load_dotenv()
    endpoint = project_endpoint or os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model_name = model or os.environ.get("SMALL_MODEL_DEPLOYMENT", "gpt-5.4-mini")
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    key = (endpoint, model_name, loop)

    # Evict clients from closed event loops
    closed_keys = [k for k in _CHAT_CLIENTS if k[2] is not None and k[2].is_closed()]
    for k in closed_keys:
        _CHAT_CLIENTS.pop(k, None)

    if key not in _CHAT_CLIENTS:
        cred = get_shared_async_credential()
        _CHAT_CLIENTS[key] = FoundryChatClient(
            project_endpoint=endpoint,
            model=model_name,
            credential=cred,
        )
        log.info("Created and cached FoundryChatClient for model=%s endpoint=%s", model_name, endpoint)

    return _CHAT_CLIENTS[key]


def reset_auth_cache_for_tests() -> None:
    """Reset cached credentials and clients for isolated unit testing."""
    global _ASYNC_CREDENTIAL, _SYNC_CREDENTIAL
    _ASYNC_CREDENTIAL = None
    _SYNC_CREDENTIAL = None
    _CHAT_CLIENTS.clear()


async def warm_up_foundry() -> None:
    """One tiny call per model deployment at startup, so the first moment of a match does not pay for the token fetch,
    new connections and a cold model (a cold first cue missed the 20 s delay on 2026-10-18). Never raises."""
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        return
    models = dict.fromkeys(m for m in (os.environ.get("SMALL_MODEL_DEPLOYMENT"), os.environ.get("FRONTIER_MODEL_DEPLOYMENT")) if m)
    for model in models:
        try:
            agent = get_foundry_chat_client(endpoint, model).as_agent(name="warm_up", instructions="Reply with OK.")
            await agent.run("OK", options={"max_tokens": 16})
            log.info("warmed up Foundry model %s", model)
        except Exception as exc:  # a failed warm-up only means the first call is slower
            log.warning("Foundry warm-up for %s failed: %s", model, exc)
