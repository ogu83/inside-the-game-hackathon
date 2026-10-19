"""Full-time match recap: deterministic evidence from the ledger, gated wording (en and tr)."""

import os
from typing import Any, Protocol

from app.agents.analyst import interest
from app.agents.fact_check_rules import check_rendering
from app.agents.models import FanProfile, FullTimeRecap, NumberCheck
from app.agents.prompts import RECAP_INSTRUCTIONS, recap_prompt
from app.ledger.metrics import player_stats, possession_pct, shot_count
from app.ledger.models import CandidateMoment
from app.simulator.league import CLUBS, PLAYERS
from app.simulator.models import MatchEvent


def build_recap_evidence(
    events: list[MatchEvent],
    moments: list[CandidateMoment] | None = None,
    home: str = "kby",
    away: str = "iva",
    profile: FanProfile | None = None,
) -> tuple[dict[str, float], dict[str, str]]:
    """Build deterministic recap evidence from ledger events and candidate moments."""
    home_goals = float(sum(e.type == "goal" and e.team_id == home for e in events))
    away_goals = float(sum(e.type == "goal" and e.team_id == away for e in events))
    hp = possession_pct(events, home)
    ap = possession_pct(events, away)
    hs = float(shot_count(events, home))
    as_ = float(shot_count(events, away))

    evidence: dict[str, float] = {
        "home_goals": home_goals,
        "away_goals": away_goals,
        "home_possession_pct": hp,
        "away_possession_pct": ap,
        "home_shots": hs,
        "away_shots": as_,
    }

    home_club = CLUBS.get(home)
    away_club = CLUBS.get(away)
    labels: dict[str, str] = {
        "home": home_club.short if home_club else home,
        "away": away_club.short if away_club else away,
        "home_full": home_club.name if home_club else home,
        "away_full": away_club.name if away_club else away,
    }

    if moments:
        scored = sorted(moments, key=interest, reverse=True)
        if scored:
            top = scored[0]
            evidence["top_moment_minute"] = float(top.minute)
            labels["top_moment_kind"] = top.kind.replace("_", " ")

    if profile and profile.player_id:
        pstats = player_stats(events, profile.player_id)
        evidence["player_passes_completed"] = pstats["passes_completed"]
        evidence["player_shots"] = pstats["shots"]
        evidence["player_tackles"] = pstats["tackles"]
        labels["player_name"] = PLAYERS[profile.player_id].name if profile.player_id in PLAYERS else profile.player_id

    if profile and profile.club_id and profile.club_id in CLUBS:
        labels["fan_club"] = CLUBS[profile.club_id].short

    return evidence, labels


class RecapWriter(Protocol):
    async def write_recap(
        self, evidence: dict[str, float], labels: dict[str, str], profile: FanProfile, feedback: list[str]
    ) -> str: ...


class TemplateRecapWriter:
    """Offline deterministic recap writer in en and tr for casual and analyst depths."""

    async def write_recap(
        self, evidence: dict[str, float], labels: dict[str, str], profile: FanProfile, feedback: list[str]
    ) -> str:
        home = labels.get("home", "Home")
        away = labels.get("away", "Away")
        hg = int(evidence.get("home_goals", 0.0))
        ag = int(evidence.get("away_goals", 0.0))
        hp = evidence.get("home_possession_pct", 50.0)
        ap = evidence.get("away_possession_pct", 50.0)
        hs = int(evidence.get("home_shots", 0.0))
        as_ = int(evidence.get("away_shots", 0.0))
        player_name = labels.get("player_name")
        has_player = player_name and "player_passes_completed" in evidence
        top_min = int(evidence["top_moment_minute"]) if "top_moment_minute" in evidence else None

        if profile.language == "tr":
            if profile.depth == "analyst":
                text = f"Maç sonu analizi: {home} {hg} - {ag} {away}. {home} %{hp} topla oynama ve {hs} şut kaydetti ({away} %{ap}, {as_} şut)."
                if top_min is not None:
                    text += f" En önemli sekans {top_min}. dakikada gerçekleşti."
                if has_player:
                    pc = int(evidence["player_passes_completed"])
                    pt = int(evidence.get("player_tackles", 0.0))
                    text += f" {player_name} {pc} isabetli pas ve {pt} müdahale yaptı."
                return text
            # casual tr
            text = f"Maç sonucu: {home} {hg} - {ag} {away}. {home} %{hp} topla oynadı ve {hs} şut attı, {away} {as_} şutta kaldı."
            if has_player:
                pc = int(evidence["player_passes_completed"])
                text += f" {player_name} {pc} isabetli pas verdi."
            return text

        # English
        if profile.depth == "analyst":
            text = f"Full time analysis: {home} {hg} - {ag} {away}. {home} held {hp}% possession ({hs} shots) to {away}'s {ap}% ({as_} shots)."
            if top_min is not None:
                text += f" Top action at minute {top_min}."
            if has_player:
                pc = int(evidence["player_passes_completed"])
                pt = int(evidence.get("player_tackles", 0.0))
                text += f" {player_name} recorded {pc} completed passes and {pt} tackles."
            return text

        # casual en
        text = f"Full time: {home} {hg} - {ag} {away}. {home} held {hp}% possession with {hs} shots to {away}'s {as_}."
        if has_player:
            pc = int(evidence["player_passes_completed"])
            text += f" {player_name} completed {pc} passes."
        return text


class FoundryRecapWriter:
    """Model-based recap writer using Foundry agent."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    async def write_recap(
        self, evidence: dict[str, float], labels: dict[str, str], profile: FanProfile, feedback: list[str]
    ) -> str:
        prompt = recap_prompt(evidence, labels, profile, feedback)
        response = await self.agent.run(prompt, options={"max_tokens": 300})
        return (response.text or "").strip()


async def generate_recap(
    writer: RecapWriter,
    evidence: dict[str, float],
    labels: dict[str, str],
    profile: FanProfile,
    max_retries: int = 1,
) -> tuple[FullTimeRecap, list[NumberCheck]]:
    """Produce a full-time recap and pass it through the Producer number gate with 1 retry."""
    checks: list[NumberCheck] = []
    feedback: list[str] = []
    for _ in range(max_retries + 1):
        text = await writer.write_recap(evidence, labels, profile, feedback)
        check = check_rendering(
            text,
            evidence,
            source_text=text,
            moment_id="recap",
            profile_key=profile.key(),
            lang=profile.language,
            coverage="none",
        )
        checks.append(check)
        if check.ok:
            return FullTimeRecap(profile_key=profile.key(), text=text, evidence=evidence, ok=True), checks
        feedback = check.mismatches
    return FullTimeRecap(profile_key=profile.key(), text="Recap unavailable", evidence=evidence, ok=False), checks


def recap_writer_from_env() -> RecapWriter:
    if os.environ.get("AGENT_MODE", "template").lower() == "foundry":
        from app.agents.run_match import live_agent

        return FoundryRecapWriter(live_agent("SMALL_MODEL_DEPLOYMENT", "recap", RECAP_INSTRUCTIONS))
    return TemplateRecapWriter()
