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
    from app.agents.run_match import run_planted

    results, report = await run_planted(30, 4, live=True)
    swapped = report.insights["swapped_team"]
    assert swapped.planted >= 1
    assert report.reached_air == 0, report.reached_air_detail
    assert report.caught == report.planted
