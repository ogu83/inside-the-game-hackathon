"""Tests for analyst voice delivery and casual fallback (P5 Task 3)."""

import pytest
import asyncio
from app.agents.models import (
    DirectorDecision,
    FanNarrative,
    FanProfile,
    Insight,
    MomentResult,
    OverlayCue,
    Verdict,
)
from app.ledger.models import CandidateMoment
from app.api.streams import MatchRun, Processed
from app.simulator.models import MatchEvent


def test_analyst_profile_falls_back_to_casual_when_dropped():
    analyst_profile = FanProfile(club_id="kby", player_id="kby-07", depth="analyst", language="en")
    casual_profile = FanProfile(club_id="kby", depth="casual", language="en")

    run = MatchRun(seed=30, profiles=[casual_profile, analyst_profile])

    moment = CandidateMoment(
        moment_id="m1",
        window=(1, 5),
        kind="pass_streak",
        team_id="kby",
        minute=2,
        evidence={"pass_streak_passes": 12},
    )
    insight = Insight(
        moment_id="m1",
        claim="Kestrel Bay completed 12 passes.",
        why_it_matters="Control established.",
        evidence_refs=["pass_streak_passes"],
        confidence=0.8,
    )
    verdict = Verdict(moment_id="m1", status="verified", insight=insight, reasons=[], layer="code", attempt=1)
    result = MomentResult(
        moment_id="m1",
        decision=DirectorDecision(moment_id="m1", say=True, angle="control", reason="good"),
        verdict=verdict,
        attempts=[insight],
        checks=[],
    )
    cue = OverlayCue(moment_id="m1", show_at_seq=5, duration_s=8, priority="normal", headline="12 passes")
    casual_narrative = FanNarrative(moment_id="m1", profile_key=casual_profile.key(), text="Kestrel Bay completed 12 passes.")

    # Processed moment has casual narrative, but analyst narrative was dropped
    processed = Processed(
        moment=moment,
        result=result,
        cue=cue,
        narratives=[casual_narrative],
        ready_wall=1.0,
        dropped_profiles=[analyst_profile.key()],
    )
    run.processed["m1"] = processed

    # Open broadcast queues for both
    q_casual = run.broadcast.open(f"fan:{casual_profile.key()}")
    q_analyst = run.broadcast.open(f"fan:{analyst_profile.key()}")

    from app.simulator.engine import simulate
    run.events = simulate(30)[:5]
    event = run.events[4]

    asyncio.run(run._show_or_drop(moment, event))

    # Verify both queues received a narrative
    assert not q_casual.empty()
    assert not q_analyst.empty()

    analyst_item = q_analyst.get_nowait()
    assert analyst_item["event"] == "narrative"
    import json
    data = json.loads(analyst_item["data"])
    assert data["profile_key"] == analyst_profile.key()
    assert data["text"] == casual_narrative.text  # Fell back to verified casual line!


def test_render_latest_falls_back_for_analyst_when_rendering_fails():
    analyst_profile = FanProfile(club_id="kby", player_id="kby-07", depth="analyst", language="en")
    casual_profile = FanProfile(club_id="kby", depth="casual", language="en")

    run = MatchRun(seed=30, profiles=[casual_profile, analyst_profile])

    moment = CandidateMoment(
        moment_id="m2",
        window=(1, 5),
        kind="pass_streak",
        team_id="kby",
        minute=2,
        evidence={"pass_streak_passes": 14},
    )
    insight = Insight(
        moment_id="m2",
        claim="Kestrel Bay completed 14 passes.",
        why_it_matters="Good tempo.",
        evidence_refs=["pass_streak_passes"],
        confidence=0.8,
    )
    verdict = Verdict(moment_id="m2", status="verified", insight=insight, reasons=[], layer="code", attempt=1)
    result = MomentResult(
        moment_id="m2",
        decision=DirectorDecision(moment_id="m2", say=True, angle="control", reason="good"),
        verdict=verdict,
        attempts=[insight],
        checks=[],
    )
    cue = OverlayCue(moment_id="m2", show_at_seq=5, duration_s=8, priority="normal", headline="14 passes")
    casual_narrative = FanNarrative(moment_id="m2", profile_key=casual_profile.key(), text="Kestrel Bay completed 14 passes.")

    processed = Processed(
        moment=moment,
        result=result,
        cue=cue,
        narratives=[casual_narrative],
        ready_wall=1.0,
    )
    processed.displayed = "shown"
    run.processed["m2"] = processed
    event = MatchEvent(seq=5, t=10.0, minute=2, second=30, type="pass", team_id="kby", player_id="kby-07", match_id="kby-iva-30", x=50.0, y=30.0)
    run.events = [event]

    # Mock producer that drops analyst profile
    from unittest.mock import AsyncMock
    from app.agents.producer import ProducerOutput
    run.producer.render = AsyncMock(return_value=ProducerOutput(
        moment_id="m2", cue=cue, narratives=[], checks=[], dropped_profiles=[analyst_profile.key()]
    ))

    latest = asyncio.run(run.render_latest(analyst_profile))
    assert latest is not None
    assert latest.profile_key == analyst_profile.key()
    assert latest.text == casual_narrative.text
