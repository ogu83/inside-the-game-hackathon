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
    skipped = [d for e, d in received if e == "skipped"]
    metrics = received[-1][1]["metrics"]
    said = [m.moment_id for m in expected if m.moment_id in {c["cue"]["moment_id"] for c in cues}]
    assert [c["cue"]["moment_id"] for c in cues] == said and len(cues) + len(skipped) == len(expected)
    assert all(c["verdict"]["status"] == "verified" for c in cues)
    assert all(len(c["narratives"]) == 2 for c in cues)
    assert metrics["cues_shown"] == len(cues) and metrics.get("cues_dropped_late", 0) == 0
    assert metrics.get("moments_skipped", 0) == len(skipped)
    assert metrics["number_checks_failed"] == 0

    state = (await client.get("/api/match/state")).json()
    assert state["running"] is False and state["metrics"]["cues_shown"] == len(cues)


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
    run = MatchRun(seed=7, speed=1000, delay_s=60, minutes=10, precompute=False)  # 0.6 s wall, 0.06 s wall delay, instant agents
    await run.start()
    await asyncio.wait_for(run.finished.wait(), timeout=30)
    expected = len(detect_all(simulate(7, minutes=10)))
    assert expected >= 2
    assert run.metrics["cues_shown"] + run.metrics.get("moments_skipped", 0) == expected and run.metrics.get("cues_dropped_late", 0) == 0
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


async def test_profiles_endpoint_lists_the_fictional_league(client: httpx.AsyncClient) -> None:
    data = (await client.get("/api/profiles")).json()
    assert [c["id"] for c in data["clubs"]] == ["kby", "iva"] and len(data["clubs"][0]["players"]) == 14
    assert data["depths"] == ["casual", "analyst"] and data["languages"] == ["en", "tr"] and data["active"] == []


async def test_fan_profile_re_renders_the_latest_moment_immediately(client: httpx.AsyncClient) -> None:
    await client.post("/api/match/start", json={"seed": 30, "speed": FAST, "delay_s": 10, "minutes": 20})
    await read_sse(client, "/api/stream/cues")  # play the whole match
    response = await client.post("/api/fan/profile", json={"club_id": "iva", "player_id": "iva-06", "depth": "analyst", "language": "tr"})
    body = response.json()
    assert body["profile_key"] == "iva|iva-06|analyst|tr"
    assert body["latest"] is not None and body["latest"]["profile_key"] == "iva|iva-06|analyst|tr" and body["latest"]["text"]
    moments = (await client.get("/api/match/moments")).json()["moments"]
    shown = [m for m in moments if m["displayed"] == "shown"]
    assert shown and any(n["profile_key"] == "iva|iva-06|analyst|tr" for n in shown[-1]["narratives"])
    assert (await client.get("/api/profiles")).json()["active"][-1] == "iva|iva-06|analyst|tr"


async def test_fan_stream_replays_latest_then_follows_the_match(client: httpx.AsyncClient) -> None:
    await client.post("/api/match/start", json={"seed": 30, "speed": FAST, "delay_s": 60, "minutes": 20, "precompute": True})
    received = await read_sse(client, "/api/stream/fan?profile=-|-|casual|tr")
    narratives = [d for e, d in received if e == "narrative"]
    assert narratives and all(n["profile_key"] == "-|-|casual|tr" for n in narratives)
    assert all("pası" in n["text"] or "baskı" in n["text"] for n in narratives)
    assert received[-1][0] == "match_end"
    assert (await client.get("/api/stream/fan?profile=nonsense")).status_code == 422


async def test_fan_stream_sends_the_replay_first_even_after_the_match(client: httpx.AsyncClient) -> None:
    await client.post("/api/match/start", json={"seed": 30, "speed": FAST, "delay_s": 10, "minutes": 20})
    await read_sse(client, "/api/stream/cues")
    received = await read_sse(client, "/api/stream/fan?profile=kby|kby-07|analyst|en")
    assert [e for e, _ in received] == ["narrative", "match_end"]
    replay = received[0][1]
    assert replay["replay"] is True and replay["profile_key"] == "kby|kby-07|analyst|en" and replay["minute"] >= 1
    moments = (await client.get("/api/match/moments")).json()["moments"]
    assert any(n["profile_key"] == "kby|kby-07|analyst|en" for m in moments for n in m["narratives"])


async def test_moments_endpoint_carries_the_agent_timeline(client: httpx.AsyncClient) -> None:
    await client.post("/api/match/start", json={"seed": 7, "speed": FAST, "delay_s": 10, "minutes": 20})
    await read_sse(client, "/api/stream/cues")
    data = (await client.get("/api/match/moments")).json()
    timeline = data["moments"][0]
    assert {"decision", "attempts", "verdict", "checks", "cue", "narratives", "displayed", "evidence", "kind"} <= timeline.keys()
    assert timeline["decision"]["say"] in (True, False) and timeline["displayed"] in ("shown", "skipped", "rejected", "late")
    assert all(c["gate"] in ("insight", "producer") for c in timeline["checks"])
    assert data["metrics"]["agent_mode"] == "template"


async def test_verdict_stream_streams_timelines_and_skips(client: httpx.AsyncClient) -> None:
    await client.post("/api/match/start", json={"seed": 7, "speed": FAST, "delay_s": 60, "minutes": 20, "precompute": False})
    received = await read_sse(client, "/api/stream/verdicts")
    kinds = {e for e, _ in received}
    assert "verdict" in kinds and received[-1][0] == "match_end"
    verdicts = [d for e, d in received if e in ("verdict", "skipped")]
    assert all("decision" in d and "attempts" in d for d in verdicts)


class ExplodingWriter:
    async def write(self, moment, labels, feedback):
        raise RuntimeError("Foundry is down")


def exploding_workflow():
    return build_workflow(ExplodingWriter(), FactChecker(AlwaysVerifies()))


async def test_agent_errors_fall_back_to_offline_agents_mid_match() -> None:
    run = MatchRun(seed=7, speed=FAST, delay_s=10, minutes=20, precompute=True, workflow_factory=exploding_workflow, agent_mode="foundry")
    await run.start()
    await asyncio.wait_for(run.finished.wait(), timeout=10)
    report = run.report()
    assert report["agent_mode"] == "template" and report["fallback_reason"] == "agent error: RuntimeError"
    assert report["cues_shown"] >= 1 and all(p.fallback for p in run.processed.values() if p.result.decision.say) is not None


async def test_live_run_limit_falls_back_to_offline_mode(client: httpx.AsyncClient, monkeypatch) -> None:
    from app.api.limits import RunLimiter

    monkeypatch.setenv("AGENT_MODE", "foundry")
    app.state.limiter = RunLimiter(per_day=1)
    first = (await client.post("/api/match/start", json={"seed": 7, "speed": FAST, "minutes": 4}, headers={"x-forwarded-for": "203.0.113.5"})).json()
    assert first["agent_mode"] == "foundry" and first["live_runs_remaining"] == 0 and first["fallback_reason"] is None
    second = (await client.post("/api/match/start", json={"seed": 7, "speed": FAST, "minutes": 4}, headers={"x-forwarded-for": "203.0.113.5"})).json()
    assert second["agent_mode"] == "template" and "limit reached" in second["fallback_reason"]
    other = (await client.post("/api/match/start", json={"seed": 7, "speed": FAST, "minutes": 4}, headers={"x-forwarded-for": "203.0.113.9"})).json()
    assert other["agent_mode"] == "foundry"
    assert RunLimiter(per_day=0).allow("anyone") and RunLimiter(per_day=0).remaining("anyone") is None


async def test_qa_endpoint_answers_text_first(client: httpx.AsyncClient) -> None:
    await client.post("/api/match/start", json={"seed": 30, "speed": FAST, "delay_s": 10, "minutes": 12})
    await read_sse(client, "/api/stream/cues")
    body = (await client.post("/api/qa", json={"transcript": "what is the score?", "profile_key": "iva|iva-06|casual|en"})).json()
    assert body["question"]["profile_key"] == "iva|iva-06|casual|en" and body["answer"]["text"].startswith("It is Kestrel Bay")
    assert body["answer"]["verdict"]["status"] == "verified" and "score" in body["answer"]["tool_calls"]
    nothing = (await client.post("/api/qa", json={"transcript": "who will win the league?"})).json()
    assert nothing["answer"]["text"] == "I don't have data on that."
    state = (await client.get("/api/match/state")).json()["metrics"]
    assert state["questions_answered"] == 2 and state["questions_without_data"] == 1
    assert (await client.post("/api/qa", json={"transcript": "x", "profile_key": "bad"})).status_code == 422
    assert (await client.get("/api/match/audits")).json() == {"audits": [], "exact": 0}
