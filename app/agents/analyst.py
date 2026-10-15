"""Analyst as director: one DirectorDecision per candidate moment (SPEC design rule 3).

Code computes the pacing state and an interest score; the director (a model, or the rule-based
offline version) only decides say or skip and the angle. It never computes numbers.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.agents.models import DirectorDecision, PacingState
from app.agents.prompts import director_prompt
from app.ledger.models import CandidateMoment

RECENT_WINDOW_S = 120
QUIET_PERIOD_S = 30
MAX_CUES_PER_2MIN = 3
HIGH_INTEREST = 1.8


def interest(moment: CandidateMoment) -> float:
    """Deterministic interest score; higher means more worth saying. Compared, never spoken."""
    e = moment.evidence
    if moment.kind == "pass_streak":
        score = e.get("pass_streak_passes", 0.0) / 10 + (1.0 if e.get("pass_streak_ended_in_shot") else 0.0)
        return round(score + (0.3 if e.get("top_player_passes", 0.0) >= 4 else 0.0), 2)
    if moment.kind == "pressing_trap":
        distance = min(e.get("pressing_trap_regain_distance_to_goal_m", 40.0), 40.0)
        return round(1.2 + (40.0 - distance) / 40.0, 2)
    return 0.5


def angle_for(moment: CandidateMoment) -> str:
    e = moment.evidence
    if moment.kind == "pressing_trap":
        return "pressure"
    if e.get("pass_streak_ended_in_shot"):
        return "chance"
    if e.get("top_player_passes", 0.0) >= 4:
        return "player"
    return "control"


@dataclass
class PacingTracker:
    """Per-match memory of what was said; owned by code, read by the director."""

    said_at: list[int] = field(default_factory=list)          # match seconds of cues the director said yes to
    recent: list[tuple[int, float]] = field(default_factory=list)  # (match second, interest) of recent moments

    def state_for(self, moment: CandidateMoment, t: int) -> PacingState:
        score = interest(moment)
        self.recent = [(rt, ri) for rt, ri in self.recent if t - rt <= RECENT_WINDOW_S] + [(t, score)]
        cues = [st for st in self.said_at if t - st <= RECENT_WINDOW_S]
        return PacingState(
            seconds_since_last_cue=float(t - self.said_at[-1]) if self.said_at else None,
            cues_last_2min=len(cues),
            moments_last_2min=len(self.recent),
            rank_among_recent=1 + sum(ri > score for _, ri in self.recent),
            interest=score,
        )

    def record(self, decision: DirectorDecision, t: int) -> None:
        if decision.say:
            self.said_at.append(t)


class Director(Protocol):
    async def decide(self, moment: CandidateMoment, labels: dict[str, str], pacing: PacingState) -> DirectorDecision: ...


class RuleDirector:
    """Offline director: the same pacing rules a model is asked to apply, as code."""

    async def decide(self, moment: CandidateMoment, labels: dict[str, str], pacing: PacingState) -> DirectorDecision:
        angle = angle_for(moment)
        if pacing.cues_last_2min >= MAX_CUES_PER_2MIN:
            return DirectorDecision(moment_id=moment.moment_id, say=False, angle=angle, reason=f"{pacing.cues_last_2min} cues already in the last 2 minutes")
        too_soon = pacing.seconds_since_last_cue is not None and pacing.seconds_since_last_cue < QUIET_PERIOD_S
        if too_soon and pacing.interest < HIGH_INTEREST:
            return DirectorDecision(moment_id=moment.moment_id, say=False, angle=angle, reason=f"only {pacing.seconds_since_last_cue:g} s since the last cue and this moment is not exceptional")
        reason = "exceptional moment" if pacing.interest >= HIGH_INTEREST else "room to speak"
        return DirectorDecision(moment_id=moment.moment_id, say=True, angle=angle, reason=reason)


class FoundryDirector:
    def __init__(self, agent: Any) -> None:
        self.agent = agent

    async def decide(self, moment: CandidateMoment, labels: dict[str, str], pacing: PacingState) -> DirectorDecision:
        response = await self.agent.run(director_prompt(moment, labels, pacing), options={"response_format": DirectorDecision})
        value = response.value
        decision = DirectorDecision.model_validate(value if isinstance(value, dict) else value.model_dump())
        return decision.model_copy(update={"moment_id": moment.moment_id})
