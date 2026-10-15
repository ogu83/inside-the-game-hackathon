import asyncio
import json

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.api.main import app
from app.api.streams import MatchRun
from app.ledger.mcp_server import TOOL_NAMES, LedgerTools, build_mcp_server
from app.simulator.engine import simulate

FAST = 2000.0


class StaticView:
    def __init__(self, events, moments=None):
        self._events, self._moments = events, moments or []

    def events(self):
        return self._events

    def shown_moments(self):
        return self._moments


@pytest.fixture(scope="module")
def tools() -> LedgerTools:
    events = [e for e in simulate(30) if e.t <= 30 * 60]
    moments = [{"moment_id": "m1", "minute": 1.0, "kind": "pass_streak", "team_id": "iva", "team": "Ironvale", "claim": "c1", "why_it_matters": "w1", "narrative_tr": None, "evidence": {"pass_streak_passes": 22.0}},
               {"moment_id": "m2", "minute": 4.0, "kind": "pass_streak", "team_id": "kby", "team": "Kestrel Bay", "claim": "c2", "why_it_matters": "w2", "narrative_tr": "tr2", "evidence": {"pass_streak_passes": 12.0}}]
    return LedgerTools(StaticView(events, moments))


def test_score_and_team_stats_are_bounded_by_the_view(tools: LedgerTools) -> None:
    score = tools.score()
    assert score["minute"] in (29.0, 30.0) and {"kby_goals", "iva_goals", "teams"} <= score.keys()
    full = tools.team_stats("iva")
    last10 = tools.team_stats("iva", 10)
    assert full["team"] == "Ironvale" and full["passes"] > last10["passes"] > 0 and last10["window_minutes"] == 10.0
    assert full["possession_pct"] + tools.team_stats("kby")["possession_pct"] == 100.0
    assert "error" in tools.team_stats("xyz")
    assert all(isinstance(v, float) for k, v in full.items() if k not in ("team",))


def test_player_stats_and_squads(tools: LedgerTools) -> None:
    stats = tools.player_stats("iva-06")
    assert stats["player"] == "Remy Tallis" and stats["team"] == "Ironvale" and stats["passes"] >= 1
    assert "error" in tools.player_stats("iva-99")
    squads = tools.squads()
    assert set(squads) == {"kby", "iva"} and len(squads["kby"]["players"]) == 14


def test_recent_moments_newest_first_with_limit(tools: LedgerTools) -> None:
    recent = tools.recent_moments(1)
    assert recent["count"] == 2 and [m["moment_id"] for m in recent["moments"]] == ["m2"]
    assert [m["moment_id"] for m in tools.recent_moments(5)["moments"]] == ["m2", "m1"]


def test_empty_view_reports_no_match() -> None:
    empty = LedgerTools(StaticView([]))
    assert "error" in empty.score() and "error" in empty.team_stats("kby") and "error" in empty.player_stats("kby-07")
    assert empty.recent_moments()["moments"] == []


async def test_mcp_server_exposes_the_tools_in_process(tools: LedgerTools) -> None:
    server = build_mcp_server(tools)
    assert sorted(t.name for t in await server.list_tools()) == sorted(TOOL_NAMES)
    result = await server.call_tool("team_stats", {"team_id": "iva", "last_minutes": 10})
    payload = result.structured_content or json.loads(result.content[0].text)
    assert payload["team"] == "Ironvale" and payload["window_minutes"] == 10.0
    assert "possession" in next(t for t in await server.list_tools() if t.name == "team_stats").description.casefold()


async def test_mcp_over_streamable_http_against_the_app() -> None:
    """The real transport, in process: the Q&A agent's tool calls take this path."""
    async with app.router.lifespan_context(app):
        app.state.run = None
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transport, base_url="http://test") as http:
            async with streamable_http_client("http://test/mcp/", http_client=http) as (read, write, *_):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    names = sorted(t.name for t in (await session.list_tools()).tools)
                    assert names == sorted(TOOL_NAMES)
                    result = await session.call_tool("score", {})
                    assert "error" in (result.structured_content or json.loads(result.content[0].text))


async def test_run_view_is_bounded_by_the_display_clock() -> None:
    run = MatchRun(seed=30, speed=1, delay_s=600, minutes=10, precompute=True)
    await run.start()
    try:
        assert run.displayed_events() == [] and "error" in run.tools().score()
    finally:
        await run.stop()
    run = MatchRun(seed=30, speed=FAST, delay_s=10, minutes=10, precompute=True)
    await run.start()
    await asyncio.wait_for(run.finished.wait(), timeout=10)
    assert len(run.displayed_events()) == len(run.events)
    shown = run.shown_moments()
    assert shown and shown[0]["claim"] and "pass_streak_passes" in shown[0]["evidence"]
    assert run.tools().recent_moments(1)["moments"][0]["moment_id"] == shown[-1]["moment_id"]
