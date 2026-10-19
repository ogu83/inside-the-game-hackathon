"""Tests for per-visitor match sessions, concurrency cap, idle cleanup, and MCP isolation (ADR 0001)."""

import asyncio
import json
import time

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.api.main import app
from app.api.sessions import SESSION_COOKIE, MatchRegistry
from app.api.streams import MatchRun, template_workflow
from app.ledger.mcp_server import TOOL_NAMES

FAST = 2000.0


def _payload(result):
    return result.structuredContent or json.loads(result.content[0].text)


@pytest.fixture
async def clients():
    """Create two independent httpx async clients representing two separate visitors."""
    app.state.workflow_factory = template_workflow
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c1:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as c2:
                yield c1, c2


async def test_two_clients_get_isolated_runs(clients) -> None:
    c1, c2 = clients

    # Visitor 1 starts a match with Kestrel Bay vs Ironvale
    r1 = await c1.post("/api/match/start", json={"seed": 7, "speed": FAST, "delay_s": 10, "minutes": 10, "home": "kby", "away": "iva"})
    assert r1.status_code == 200
    info1 = r1.json()

    # Visitor 2 starts a match with Ironvale vs Kestrel Bay
    r2 = await c2.post("/api/match/start", json={"seed": 30, "speed": FAST, "delay_s": 10, "minutes": 10, "home": "iva", "away": "kby"})
    assert r2.status_code == 200
    info2 = r2.json()

    assert info1["match_id"] != info2["match_id"]
    assert info1["match_id"].startswith("kby-iva-")
    assert info2["match_id"].startswith("iva-kby-")

    # State check is isolated per visitor
    s1 = (await c1.get("/api/match/state")).json()
    s2 = (await c2.get("/api/match/state")).json()
    assert s1["match_id"] == info1["match_id"]
    assert s2["match_id"] == info2["match_id"]

    # Visitor 1 asks a question
    q_res = await c1.post("/api/qa", json={"transcript": "score", "profile_key": "-|-|casual|en"})
    assert q_res.status_code == 200

    # Visitor 1 sees 1 question answered, Visitor 2 sees 0
    m1 = (await c1.get("/api/match/state")).json()
    m2 = (await c2.get("/api/match/state")).json()
    assert m1["metrics"]["questions_answered"] == 1
    assert m2["metrics"].get("questions_answered", 0) == 0


async def test_max_concurrent_runs_cap_returns_503() -> None:
    async with app.router.lifespan_context(app):
        # Configure registry with a cap of 2 concurrent runs
        app.state.registry.max_concurrent = 2
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c1:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as c2:
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as c3:
                    r1 = await c1.post("/api/match/start", json={"seed": 7, "speed": FAST, "delay_s": 10, "minutes": 10})
                    assert r1.status_code == 200

                    r2 = await c2.post("/api/match/start", json={"seed": 30, "speed": FAST, "delay_s": 10, "minutes": 10})
                    assert r2.status_code == 200

                    # 3rd visitor exceeds capacity
                    r3 = await c3.post("/api/match/start", json={"seed": 42, "speed": FAST, "delay_s": 10, "minutes": 10})
                    assert r3.status_code == 503
                    assert "The demo is busy, try again in a minute." in r3.json()["detail"]


async def test_idle_cleanup_stops_and_removes_expired_runs() -> None:
    async with app.router.lifespan_context(app):
        # Configure short idle TTL
        app.state.registry.idle_ttl_s = 0.1
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/match/start", json={"seed": 7, "speed": 1.0, "delay_s": 10, "minutes": 10})
            assert r.status_code == 200

            # Wait beyond idle TTL
            await asyncio.sleep(0.25)

            # Cleanup removes the idle run
            assert app.state.registry.active_count() == 0
            state = (await c.get("/api/match/state")).json()
            assert state["running"] is False


async def test_mcp_isolation_between_visitors() -> None:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c1:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as c2:
                r1 = await c1.post("/api/match/start", json={"seed": 7, "speed": FAST, "delay_s": 5, "minutes": 8, "home": "kby", "away": "iva"})
                r2 = await c2.post("/api/match/start", json={"seed": 30, "speed": FAST, "delay_s": 5, "minutes": 8, "home": "iva", "away": "kby"})
                info1 = r1.json()
                info2 = r2.json()

                # Client 1 queries MCP using its run id in the path
                def asgi_c1(headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
                    return httpx.AsyncClient(transport=transport, base_url="http://test", headers=headers, timeout=timeout, auth=auth)

                async with streamablehttp_client(f"http://test/mcp/{info1['match_id']}/", httpx_client_factory=asgi_c1) as (r, w, _):
                    async with ClientSession(r, w) as session:
                        await session.initialize()
                        res1 = await session.call_tool("score", {})
                        p1 = _payload(res1)
                        assert "teams" in p1

                # Client 2 queries MCP using its run id in the path
                async with streamablehttp_client(f"http://test/mcp/{info2['match_id']}/", httpx_client_factory=asgi_c1) as (r, w, _):
                    async with ClientSession(r, w) as session:
                        await session.initialize()
                        res2 = await session.call_tool("score", {})
                        p2 = _payload(res2)
                        assert "teams" in p2


async def test_single_visitor_can_restart_match(clients) -> None:
    c1, _ = clients
    r1 = await c1.post("/api/match/start", json={"seed": 7, "speed": FAST, "delay_s": 10, "minutes": 10})
    assert r1.status_code == 200
    id1 = r1.json()["match_id"]

    r2 = await c1.post("/api/match/start", json={"seed": 30, "speed": FAST, "delay_s": 10, "minutes": 10})
    assert r2.status_code == 200
    id2 = r2.json()["match_id"]

    assert id1 != id2
    state = (await c1.get("/api/match/state")).json()
    assert state["match_id"] == id2
