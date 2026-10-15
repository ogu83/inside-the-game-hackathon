"""Opt-in tests that call Foundry models: `python -m pytest tests/agents -q -m live`."""

import pytest

from app.agents.run_match import live_workflow, run_moment
from app.ledger.state import detect_all
from app.simulator.engine import simulate

pytestmark = pytest.mark.live


async def test_live_commentator_and_fact_checker_on_three_moments() -> None:
    workflow = live_workflow()
    moments = detect_all(simulate(7))[:3]
    for moment in moments:
        result = await run_moment(workflow, moment)
        assert result.verdict.status in ("verified", "rewritten", "rejected")
        assert result.verdict.attempt in (1, 2)
        assert result.checks and result.checks[0].gate == "insight"
        if result.verdict.status != "rejected":
            assert result.verdict.insight is not None
            assert set(result.verdict.insight.evidence_refs) <= set(moment.evidence)


async def test_live_director_decides_with_pacing_state() -> None:
    from app.agents.analyst import FoundryDirector, PacingTracker
    from app.agents.models import PacingState
    from app.agents.run_match import close_t

    events = simulate(7)
    moments = detect_all(events)[:3]
    workflow = live_workflow()
    pacing = PacingTracker()
    decisions = []
    for moment in moments:
        result = await run_moment(workflow, moment, pacing=pacing.state_for(moment, close_t(moment, events)))
        pacing.record(result.decision, close_t(moment, events))
        decisions.append(result.decision)
        assert result.decision.angle in ("control", "chance", "player", "pressure", None)
        assert (result.verdict is None) == (not result.decision.say)
    assert any(d.say for d in decisions)
    crowded = PacingState(seconds_since_last_cue=5, cues_last_2min=3, moments_last_2min=4, rank_among_recent=4, interest=1.0)
    director = workflow.executors["analyst"].director if hasattr(workflow, "executors") else None
    if isinstance(director, FoundryDirector):
        assert not (await director.decide(moments[0], {"team": "Kestrel Bay", "opponent": "Ironvale"}, crowded)).say


async def test_live_wording_judge_catches_a_swapped_team_and_planted_run_reaches_zero() -> None:
    """First 12 moments of the demo seed, 4 insight plants and 4 rendering plants: about 2 minutes of model calls."""
    import json

    from app.agents.run_match import run_planted

    results, report = await run_planted(30, 4, live=True, limit=12)
    swapped = report.insights["swapped_team"]
    missed_by_layer_2 = [line for line in report.reached_air_detail if "(swapped_team)" in line]
    detail = "\n".join([
        report.headline(),
        json.dumps(report.as_dict(), indent=1),
        "reached air:", *report.reached_air_detail,
        "swapped teams layer 2 missed:", *(missed_by_layer_2 or ["none"]),
        "verdicts:", *(f"  {r.moment_id}: {r.verdict.status if r.verdict else 'skipped'} L{r.verdict.layer if r.verdict else '-'} attempt {r.verdict.attempt if r.verdict else '-'}" for r in results),
    ])
    assert swapped.planted >= 1, detail
    assert report.reached_air == 0, detail
    assert report.caught == report.planted, detail


async def test_live_producer_renders_two_profiles_in_two_languages() -> None:
    from app.agents.models import FanProfile
    from app.agents.run_match import live_producer
    from app.ledger.labels import moment_labels

    events = simulate(30)
    moment = detect_all(events)[0]
    workflow = live_workflow()
    result = await run_moment(workflow, moment)
    assert result.verdict is not None and result.verdict.insight is not None
    profiles = [FanProfile(language="en", depth="casual", club_id="iva"), FanProfile(language="en", depth="analyst"),
                FanProfile(language="tr", depth="casual"), FanProfile(language="tr", depth="analyst", club_id="kby", player_id="kby-07")]
    output = await live_producer().render(result.verdict.insight, moment, moment_labels(moment), profiles)
    assert output.cue is not None and len(output.cue.headline) <= 60
    assert len(output.narratives) + len(output.dropped_profiles) == 4
    assert len(output.narratives) >= 3, output.checks
    assert all(c.gate == "producer" for c in output.checks)


async def test_live_first_attempt_verified_rate() -> None:
    """Most claims should pass both layers unchanged at attempt 1 (descriptive prompt, hinted judge)."""
    from app.agents.analyst import PacingTracker
    from app.agents.run_match import close_t

    events = simulate(30)
    moments = detect_all(events)[:10]
    workflow = live_workflow()
    pacing = PacingTracker()
    said, first_attempt_verified, lines = 0, 0, []
    for moment in moments:
        result = await run_moment(workflow, moment, pacing=pacing.state_for(moment, close_t(moment, events)))
        pacing.record(result.decision, close_t(moment, events))
        if result.verdict is None:
            continue
        said += 1
        v = result.verdict
        first_attempt_verified += v.status == "verified" and v.attempt == 1
        lines.append(f"{v.status:9} attempt {v.attempt} L{'1' if v.layer == 'code' else '2'}: {result.attempts[0].claim}  {v.reasons}")
    rate = first_attempt_verified / said if said else 0.0
    assert said >= 5, lines
    assert rate >= 0.7, f"first-attempt verified rate {rate:.0%} ({first_attempt_verified}/{said})\n" + "\n".join(lines)


async def test_live_qa_agent_answers_through_the_ledger_mcp_server() -> None:
    """Needs the app running with a shown match: `AGENT_MODE=template python -m uvicorn app.api.main:app --port 8010`,
    a started match that has aired at least one cue, and QA_MCP_URL (default http://localhost:8010/mcp)."""
    import os

    import httpx

    from app.agents.fact_checker import FactChecker
    from app.agents.fakes import AlwaysVerifies
    from app.agents.models import FanProfile
    from app.agents.run_match import live_qa_agent
    from app.ledger.mcp_server import LedgerTools
    from app.voice.qa import NO_DATA, QaPipeline, new_question

    base = os.environ.get("QA_MCP_URL", "http://localhost:8010/mcp").rsplit("/mcp", 1)[0]
    moments = httpx.get(f"{base}/api/match/moments", timeout=10).json()["moments"]
    assert any(m["displayed"] == "shown" for m in moments), "start a match and let a cue air first"

    class RemoteView:
        def events(self):
            return []

        def shown_moments(self):
            return [{**m, "team": m["team_id"], "claim": m["verdict"]["insight"]["claim"], "why_it_matters": m["verdict"]["insight"]["why_it_matters"], "narrative_tr": None} for m in moments if m["displayed"] == "shown" and m["verdict"]]

    agent = live_qa_agent(f"{base}/mcp")
    pipeline = QaPipeline(agent, FactChecker(AlwaysVerifies()), LedgerTools(RemoteView()))
    profile = FanProfile(club_id="iva", player_id="iva-06", language="en")
    answer = await pipeline.answer(new_question(profile.key(), "How is Remy Tallis doing so far?"), profile)
    assert answer.tool_calls, "the agent must call a ledger tool over MCP (the tool-call span in the trace)"
    assert answer.text and answer.verdict is not None
    nothing = await pipeline.answer(new_question(profile.key(), "Who will win the league this season?"), profile)
    assert nothing.text == NO_DATA["en"] or "data" in nothing.text.casefold()


async def test_live_voice_live_transcribes_its_own_speech() -> None:
    """Speak a line verbatim, feed the audio back as a push-to-talk utterance, expect the same words."""
    from app.voice.session import open_voice_live_speaker

    speaker = await open_voice_live_speaker()
    try:
        pcm = bytearray()

        async def collect(chunk: bytes) -> None:
            pcm.extend(chunk)

        line = "How is my player doing in this match?"
        spoken = await speaker.speak(line, "en", collect)
        assert spoken.casefold().startswith("how is my player")
        heard = await speaker.transcribe(bytes(pcm), "en")
        assert "player" in heard.casefold(), heard
        await speaker.cancel()
    finally:
        await speaker.close()
