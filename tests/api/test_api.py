import asyncio
import json

import httpx
import pytest

from app.agents.fact_checker import FactChecker
from app.agents.fakes import AlwaysVerifies, TemplateCommentator
from app.agents.workflow import build_workflow
from app.api.clock import BroadcastClock
from app.api.main import app
from app.api.streams import MatchRun, template_workflow
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
    data = response.json()
    assert data["status"] == "ok"
    assert data["running"] is False
    assert data["active_runs"] == 0
    assert data["running"] == (data["active_runs"] > 0)

    # Start a match, health reports running: True, active_runs == 1
    started = await client.post("/api/match/start", json={"seed": 7, "speed": 100, "delay_s": 5, "minutes": 10})
    assert started.status_code == 200
    health_running = (await client.get("/api/health")).json()
    assert health_running["running"] is True
    assert health_running["active_runs"] == 1

    # Stop match, health reverts to running: False, active_runs == 0
    stopped = await client.post("/api/match/stop")
    assert stopped.status_code == 200
    health_stopped = (await client.get("/api/health")).json()
    assert health_stopped["running"] is False
    assert health_stopped["active_runs"] == 0


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
    assert len(run._late) == expected, "every late moment is remembered, whether detected before or after its closing event aired"


async def test_moment_detected_after_its_closing_event_aired_counts_as_late() -> None:
    """Deterministic version of the race behind the flaky test: at tiny delays the display loop can pass a moment's
    closing seq before the ingest loop detects it; such a moment is late at once and never shown."""
    run = MatchRun(seed=7, speed=1, delay_s=600, minutes=10, precompute=False, workflow_factory=template_workflow)
    run.events = simulate(7, minutes=10)
    run.clock = BroadcastClock(started_at=0.0, speed=1, delay_s=600)
    moments = detect_all(run.events)
    first, second = moments[0], moments[1]
    run._displayed_seq = first.window[1]  # the display loop already aired the first moment's closing event
    run._on_moment_detected(first)
    run._on_moment_detected(second)
    await asyncio.gather(*run._tasks)
    assert run.metrics["moments_detected"] == 2 and run.metrics["cues_dropped_late"] == 1
    assert first.moment_id in run._late and run.processed[first.moment_id].displayed == "late"
    assert run.pending_by_seq[second.window[1]] == [second] and first.window[1] not in run.pending_by_seq
    event = run.events[second.window[1] - 1]
    run._displayed_seq = event.seq
    await run._show_or_drop(second, event)
    assert run.metrics["cues_shown"] == 1 and run.processed[second.moment_id].displayed == "shown"


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
    # A forged first entry with the same real ingress address is still blocked
    forged = (await client.post("/api/match/start", json={"seed": 7, "speed": FAST, "minutes": 4}, headers={"x-forwarded-for": "9.9.9.9, 203.0.113.5"})).json()
    assert forged["agent_mode"] == "template" and "limit reached" in forged["fallback_reason"]
    other = (await client.post("/api/match/start", json={"seed": 7, "speed": FAST, "minutes": 4}, headers={"x-forwarded-for": "203.0.113.9"})).json()
    assert other["agent_mode"] == "foundry"
    assert RunLimiter(per_day=0).allow("anyone") and RunLimiter(per_day=0).remaining("anyone") is None


def test_visitor_id_uses_last_forwarded_entry_and_prevents_forgery() -> None:
    from starlette.requests import Request
    from app.api.main import visitor_id

    def make_req(forwarded: str | None = None, client_host: str = "127.0.0.1") -> Request:
        headers = []
        if forwarded is not None:
            headers.append((b"x-forwarded-for", forwarded.encode("latin-1")))
        scope = {
            "type": "http",
            "headers": headers,
            "client": (client_host, 12345),
        }
        return Request(scope)

    # Forged first entry does not change visitor
    req1 = make_req(forwarded="1.1.1.1, 203.0.113.5")
    req2 = make_req(forwarded="2.2.2.2, 203.0.113.5")
    assert visitor_id(req1) == "203.0.113.5"
    assert visitor_id(req2) == "203.0.113.5"
    assert visitor_id(req1) == visitor_id(req2)

    # Two different real addresses are two visitors
    req3 = make_req(forwarded="1.1.1.1, 203.0.113.6")
    assert visitor_id(req3) == "203.0.113.6"
    assert visitor_id(req1) != visitor_id(req3)

    # Single entry
    req4 = make_req(forwarded="203.0.113.7")
    assert visitor_id(req4) == "203.0.113.7"

    # Fallback to connecting address if header absent
    req5 = make_req(forwarded=None, client_host="10.0.0.1")
    assert visitor_id(req5) == "10.0.0.1"


async def test_qa_endpoint_answers_text_first(client: httpx.AsyncClient) -> None:
    await client.post("/api/match/start", json={"seed": 30, "speed": FAST, "delay_s": 10, "minutes": 12})
    await read_sse(client, "/api/stream/cues")
    body = (await client.post("/api/qa", json={"transcript": "what is the score?", "profile_key": "iva|iva-06|casual|en"})).json()
    assert body["question"]["profile_key"] == "iva|iva-06|casual|en" and body["answer"]["text"].startswith("It is Kestrel Bay")
    assert body["answer"]["verdict"]["status"] == "verified" and "score" in body["answer"]["tool_calls"]
    assert body["answer"]["timing"]["answered_at"] >= body["answer"]["timing"]["pressed_at"]
    nothing = (await client.post("/api/qa", json={"transcript": "who will win the league?"})).json()
    assert nothing["answer"]["text"] == "I don't have data on that."
    state = (await client.get("/api/match/state")).json()["metrics"]
    assert state["questions_answered"] == 2 and state["questions_without_data"] == 1
    assert state["qa_answer_p50_ms"] >= 0 and "qa_speech_p50_ms" not in state, "text-only questions are never spoken"
    assert (await client.post("/api/qa", json={"transcript": "x", "profile_key": "bad"})).status_code == 422
    assert (await client.get("/api/match/audits")).json() == {"audits": [], "exact": 0}


async def test_timelines_returns_only_moments_on_air_at_playback_time() -> None:
    events = simulate(seed=7)
    moments = detect_all(events)
    assert len(moments) >= 5
    run = MatchRun(seed=7, speed=100.0, delay_s=10.0, minutes=90, precompute=True)
    await run.start()

    early_timelines = run.timelines(playback_t=100.0)
    early_ids = {t["moment_id"] for t in early_timelines}

    for m in moments:
        m_closing_t = events[m.window[1] - 1].t
        if m_closing_t > 100.0:
            assert m.moment_id not in early_ids
        else:
            assert m.moment_id in early_ids

    full_timelines = run.timelines(playback_t=6000.0)
    assert len(full_timelines) == len(run.processed)

    run.finished.set()
    finished_timelines = run.timelines()
    assert len(finished_timelines) == len(run.processed)
    await run.stop()


async def test_start_match_with_plant_forbidden_without_env_flag(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.delenv("DEMO_PLANT", raising=False)
    health = (await client.get("/api/health")).json()
    assert health["demo_plant"] is False
    res = await client.post("/api/match/start", json={"seed": 30, "speed": FAST, "plant": 1})
    assert res.status_code == 403
    assert "Planted-claim demo disabled" in res.json()["detail"]


async def test_planted_demo_moment_rejected_and_never_aired(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_PLANT", "1")
    health = (await client.get("/api/health")).json()
    assert health["demo_plant"] is True

    res = await client.post("/api/match/start", json={"seed": 30, "speed": FAST, "delay_s": 5, "minutes": 20, "plant": 1})
    assert res.status_code == 200

    cues = await read_sse(client, "/api/stream/cues")
    aired_moment_ids = {data["cue"]["moment_id"] for event, data in cues if event == "cue" and "cue" in data}
    assert "kby-iva-30-31-pass_streak" not in aired_moment_ids

    moments_resp = await client.get("/api/match/moments")
    moments_data = moments_resp.json()
    planted_timeline = next((m for m in moments_data["moments"] if m["moment_id"] == "kby-iva-30-31-pass_streak"), None)
    assert planted_timeline is not None
    assert planted_timeline["verdict"]["status"] == "rejected"
    assert planted_timeline["cue"] is None
    assert planted_timeline["displayed"] == "rejected"
    assert any("6 shots does not match the cited shots value (away_shots_last_10min = 0)" in r for r in planted_timeline["verdict"]["reasons"])
    assert any("Ironvale have had 6 shots." in a["claim"] for a in planted_timeline["attempts"])


async def test_recap_delivered_via_sse_and_get_endpoint(client: httpx.AsyncClient) -> None:
    res = await client.post("/api/match/start", json={"seed": 7, "speed": FAST, "delay_s": 5, "minutes": 4})
    assert res.status_code == 200

    profile_en = "-|-|casual|en"
    fan_events = await read_sse(client, f"/api/stream/fan?profile={profile_en}")
    recaps = [data for event, data in fan_events if event == "recap"]
    assert len(recaps) == 1, "recap SSE event must arrive exactly once at full time"
    recap_data = recaps[0]
    assert recap_data["ok"] is True
    assert recap_data["profile_key"] == profile_en
    assert "Full time" in recap_data["text"]

    recap_resp = await client.get(f"/api/match/recap?profile={profile_en}")
    assert recap_resp.status_code == 200
    recap_json = recap_resp.json()
    assert recap_json["text"] == recap_data["text"]

    profile_tr = "kby|-|analyst|tr"
    recap_tr_resp = await client.get(f"/api/match/recap?profile={profile_tr}")
    assert recap_tr_resp.status_code == 200
    recap_tr = recap_tr_resp.json()
    assert recap_tr["ok"] is True
    assert "Maç sonu" in recap_tr["text"]


async def test_start_match_global_daily_cap_fallback(client: httpx.AsyncClient, monkeypatch) -> None:
    from app.api.limits import RunLimiter
    monkeypatch.setenv("AGENT_MODE", "foundry")
    app.state.limiter = RunLimiter(per_day=10, total_per_day=1)

    res1 = await client.post("/api/match/start", json={"seed": 7, "speed": FAST, "delay_s": 5, "minutes": 4})
    assert res1.status_code == 200
    assert res1.json()["agent_mode"] == "foundry"
    assert res1.json()["fallback_reason"] is None
    await client.post("/api/match/stop")

    res2 = await client.post(
        "/api/match/start",
        json={"seed": 7, "speed": FAST, "delay_s": 5, "minutes": 4},
        headers={"x-forwarded-for": "10.0.0.99"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["agent_mode"] == "template"
    assert data2["fallback_reason"] == "Live runs for today are used up, playing with offline agents"
    assert data2["live_runs_remaining"] == 0
    await client.post("/api/match/stop")



