"""Tests for full-time recap: deterministic evidence, en/tr casual/analyst templates, number gating, and SSE delivery."""

import asyncio
import os
import pytest

from app.agents.fact_check_rules import check_rendering
from app.agents.models import FanProfile
from app.agents.recap import (
    TemplateRecapWriter,
    build_recap_evidence,
    generate_recap,
)
from app.ledger.state import detect_all
from app.simulator.engine import simulate


@pytest.fixture
def match_data():
    events = simulate(seed=7, minutes=90)
    moments = detect_all(events)
    return events, moments


@pytest.mark.asyncio
async def test_template_recap_in_en_and_tr_for_casual_and_analyst(match_data) -> None:
    events, moments = match_data
    writer = TemplateRecapWriter()

    profiles = [
        FanProfile(language="en", depth="casual"),
        FanProfile(language="en", depth="analyst", club_id="kby", player_id="kby-07"),
        FanProfile(language="tr", depth="casual"),
        FanProfile(language="tr", depth="analyst", club_id="iva", player_id="iva-06"),
    ]

    for profile in profiles:
        evidence, labels = build_recap_evidence(events, moments, home="kby", away="iva", profile=profile)
        assert "home_goals" in evidence and "away_goals" in evidence
        assert "home_possession_pct" in evidence and "away_possession_pct" in evidence
        assert "home_shots" in evidence and "away_shots" in evidence
        if profile.player_id:
            assert "player_passes_completed" in evidence
            assert "player_name" in labels

        recap, checks = await generate_recap(writer, evidence, labels, profile)
        assert recap.ok is True
        assert len(checks) == 1
        assert checks[0].ok is True
        assert checks[0].mismatches == []
        assert recap.text != "Recap unavailable"

        if profile.language == "en":
            assert "Full time" in recap.text
            assert str(int(evidence["home_goals"])) in recap.text
        else:
            assert "Maç sonu" in recap.text
            assert f"%{evidence['home_possession_pct']}" in recap.text


@pytest.mark.asyncio
async def test_recap_gate_rejects_wrong_number_and_marks_unavailable(match_data) -> None:
    events, moments = match_data
    profile = FanProfile(language="en", depth="casual")
    evidence, labels = build_recap_evidence(events, moments, home="kby", away="iva", profile=profile)

    class BadRecapWriter:
        def __init__(self) -> None:
            self.attempts = 0

        async def write_recap(self, evidence, labels, profile, feedback):
            self.attempts += 1
            # Injects 999 shots which does not exist in evidence
            return "Full time: Kestrel Bay 999 - 0 Ironvale with 999 shots."

    bad_writer = BadRecapWriter()
    recap, checks = await generate_recap(bad_writer, evidence, labels, profile, max_retries=1)

    assert bad_writer.attempts == 2, "must retry once on failure"
    assert recap.ok is False
    assert recap.text == "Recap unavailable"
    assert len(checks) == 2
    assert all(not c.ok for c in checks)
    assert any("999" in m for c in checks for m in c.mismatches)


@pytest.mark.live
@pytest.mark.asyncio
async def test_foundry_recap_in_both_languages(match_data) -> None:
    """Live Foundry agent generates recap in en and tr, verified by Producer gate."""
    events, moments = match_data
    from app.agents.prompts import RECAP_INSTRUCTIONS
    from app.agents.recap import FoundryRecapWriter
    from app.agents.run_match import live_agent

    live = live_agent("SMALL_MODEL_DEPLOYMENT", "recap", RECAP_INSTRUCTIONS)
    writer = FoundryRecapWriter(live)

    for lang in ("en", "tr"):
        profile = FanProfile(language=lang, depth="casual", club_id="kby")
        evidence, labels = build_recap_evidence(events, moments, home="kby", away="iva", profile=profile)
        recap, checks = await generate_recap(writer, evidence, labels, profile)
        assert recap.ok is True, f"Foundry recap failed gate: {recap.text}"
        assert checks[-1].ok is True
        print(f"\nLive recap ({lang}): {recap.text}")
