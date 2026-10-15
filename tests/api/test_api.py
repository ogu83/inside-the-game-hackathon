import asyncio
import json

import httpx
import pytest

from app.agents.fact_checker import FactChecker
from app.agents.fakes import AlwaysVerifies, TemplateCommentator
from app.agents.workflow import build_workflow
from app.api.clock import BroadcastClock
from app.api.main import app
from app.api.streams import MatchRun
from app.ledger.state import detect_all
from app.simulator.engine import simulate

FAST = 2000.0  # 20 match minutes in 0.6 s of wall time


def test_clock_runs_playback_behind_ingest() -> None:
    clock = BroadcastClock(started_at=100.0, speed=2.0, delay_s=10.0)
    assert clock.ingest_wall(60) == 130.0
    assert clock.display_wall(60) == 135.0
    assert clock.event_t(130.0) == 60.0
    assert clock.playback_t(130.0) == 50.0
    assert clock.as_dict(130.0) == {"speed": 2.0, "delay_s": 10.0, "event_t": 60.0, "playback_t": 50.0}


class SlowCommentator(TemplateCommentator):
    def __init__(self, wall_s: float) -> None:
        self.wall_s = wall_s

    async def write(self, moment, labels, feedback):
        await asyncio.sleep(self.wall_s)
        return await super().write(moment, labels, feedback)


def slow_workflow(wall_s: float):
    return lambda: build_workflow(SlowCommentator(wall_s), FactChecker(AlwaysVerifies()))


async def read_sse(client: httpx.AsyncClient, path: str) -> list[tuple[str, dict]]:
    received: list[tuple[str, dict]] = []
    async with client.stream("GET", path) as response:
        assert response.status_code == 200
        event = None
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and event:
                received.append((event, json.loads(line.split(":", 1)[1])))
                if event == "match_end":
                    break
    return received


@pytest.fixture
async def client():
    app.state.workflow_factory = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        async with app.router.lifespan_context(app):
            yield c
            if app.state.run is not None:
                await app.state.run.stop()


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_streams_need_a_running_match(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/stream/cues")).status_code == 404
    assert (await client.post("/api/match/stop")).status_code == 404
    assert (await client.get("/api/match/state")).json() == {"running": False}


async def test_precomputed_match_streams_every_cue_on_the_delayed_clock(client: httpx.AsyncClient) -> None:
    started = await client.post("/api/match/start", json={"seed": 7, "speed": FAST, "delay_s": 10, "minutes": 20})
    assert started.status_code == 200
    info = started.json()
    assert info["mode"] == "precompute" and info["clock"]["delay_s"] == 10
    expected = [m for m in detect_all(simulate(7, minutes=20))]
    assert info["precomputed_moments"] == len(expected) >= 3

    received = await read_sse(client, "/api/stream/cues")
    cues = [d for e, d in received if e == "cue"]
    metrics = received[-1][1]["metrics"]
    assert [c["cue"]["moment_id"] for c in cues] == [m.moment_id for m in expected]
    assert all(c["verdict"]["status"] == "verified" for c in cues)
    assert all(len(c["narratives"]) == 2 for c in cues)
    assert metrics["cues_shown"] == len(expected) and metrics.get("cues_dropped_late", 0) == 0
    assert metrics["number_checks_failed"] == 0

    state = (await client.get("/api/match/state")).json()
    assert state["running"] is False and state["metrics"]["cues_shown"] == len(expected)


async def test_event_ticker_is_ordered_and_ends(client: httpx.AsyncClient) -> None:
    await client.post("/api/match/start", json={"seed": 7, "speed": FAST, "delay_s": 5, "minutes": 4})
    received = await read_sse(client, "/api/stream/events")
    seqs = [d["seq"] for e, d in received if e == "event"]
    assert seqs == list(range(1, len(seqs) + 1)) and len(seqs) > 50
    assert received[0][1]["text"].endswith("kick-off")
    assert received[-1][0] == "match_end"


async def test_live_mode_drops_cues_that_are_not_ready_in_time() -> None:
    run = MatchRun(seed=7, speed=FAST, delay_s=10, minutes=20, precompute=False, workflow_factory=slow_workflow(0.5))
    await run.start()
    assert run.mode == "live"
    await asyncio.wait_for(run.finished.wait(), timeout=10)
    await run.stop()
    expected = len(detect_all(simulate(7, minutes=20)))
    assert run.metrics["moments_detected"] == expected
    assert run.metrics["cues_dropped_late"] == expected and run.metrics.get("cues_shown", 0) == 0


async def test_live_mode_shows_cues_that_are_ready_before_display() -> None:
    run = MatchRun(seed=7, speed=500, delay_s=60, minutes=20, precompute=False)  # 2.4 s wall, 0.12 s wall delay, instant agents
    await run.start()
    await asyncio.wait_for(run.finished.wait(), timeout=30)
    expected = len(detect_all(simulate(7, minutes=20)))
    assert run.metrics["cues_shown"] == expected and run.metrics.get("cues_dropped_late", 0) == 0
    for done in run.processed.values():
        assert done.ready_wall <= run.clock.display_wall(run.events[done.moment.window[1] - 1].t)


async def test_starting_again_replaces_the_running_match(client: httpx.AsyncClient) -> None:
    first = (await client.post("/api/match/start", json={"seed": 1, "speed": 1, "minutes": 90})).json()
    second = (await client.post("/api/match/start", json={"seed": 2, "speed": 1, "minutes": 90})).json()
    assert first["match_id"] != second["match_id"] and second["mode"] == "live"
    stopped = (await client.post("/api/match/stop")).json()
    assert stopped["match_id"] == second["match_id"]


async def test_index_serves_the_page(client: httpx.AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200 and "Matchday Companion" in response.text
