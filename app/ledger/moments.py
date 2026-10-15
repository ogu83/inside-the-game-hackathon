"""Candidate-moment detectors. Each detector sees every event and may return a moment.

Evidence values are floats only. Possession share is omitted while the match is under 3 minutes old,
because "100% possession" after one minute reads as broken on screen.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from app.ledger.metrics import in_window, possession_pct, pressure_count, progress_m, regains_after_pressure
from app.ledger.models import CandidateMoment
from app.simulator.engine import metres
from app.simulator.models import MatchEvent

POSSESSION_WINDOW_S = 300
MIN_POSSESSION_WINDOW_MIN = 3.0
PRESS_WINDOW_S = 600


class Detector(Protocol):
    def on_event(self, event: MatchEvent, history: list[MatchEvent]) -> CandidateMoment | None: ...


def _window_minutes(t: int, seconds: int) -> float:
    return round(min(seconds, t) / 60, 1)


def _possession_keys(history: list[MatchEvent], team: str, t: int) -> dict[str, float]:
    minutes = _window_minutes(t, POSSESSION_WINDOW_S)
    keys = {"window_minutes": minutes}
    if minutes >= MIN_POSSESSION_WINDOW_MIN:
        keys["team_possession_pct_window"] = possession_pct(in_window(history, t, POSSESSION_WINDOW_S), team)
    return keys


@dataclass
class PassStreakDetector:
    """A team strings together at least `min_passes` completed passes without losing the ball."""

    min_passes: int = 10
    _team: str | None = None
    _passes: list[MatchEvent] = field(default_factory=list)

    def on_event(self, event: MatchEvent, history: list[MatchEvent]) -> CandidateMoment | None:
        if event.type == "pass" and event.outcome == "success":
            if event.team_id != self._team:
                self._team, self._passes = event.team_id, []
            self._passes.append(event)
            return None
        if event.type in ("pressure", "foul", "substitution") or not self._passes:
            return None
        ended_in_shot = event.type == "shot" and event.team_id == self._team
        moment = self._close(event, history, ended_in_shot) if len(self._passes) >= self.min_passes else None
        self._team, self._passes = None, []
        return moment

    def _close(self, end: MatchEvent, history: list[MatchEvent], ended_in_shot: bool) -> CandidateMoment:
        first, last = self._passes[0], self._passes[-1]
        team = self._team or end.team_id
        counts = Counter(p.player_id for p in self._passes if p.player_id)
        top_player_id, top_passes = counts.most_common(1)[0] if counts else (None, 0)
        return CandidateMoment(
            moment_id=f"{first.match_id}-{last.seq}-pass_streak",
            window=(first.seq, last.seq),
            kind="pass_streak",
            team_id=team,
            minute=last.minute,
            top_player_id=top_player_id,
            evidence={
                "pass_streak_passes": float(len(self._passes)),
                "pass_streak_duration_s": float(last.t - first.t),
                "pass_streak_players": float(len(counts)),
                "top_player_passes": float(top_passes),
                "pass_streak_progress_m": progress_m(first.x, last.end_x if last.end_x is not None else last.x),
                "pass_streak_ended_in_shot": 1.0 if ended_in_shot else 0.0,
                **_possession_keys(history, team, last.t),
                "minute": float(last.minute),
            },
        )


@dataclass
class PressingTrapDetector:
    """A team presses the opponent's build-up (`min_pressures` pressures high up the pitch inside `window_s`)
    and wins the ball there. Coordinates are in the pressing team's frame, so high up means x >= `high_x`."""

    min_pressures: int = 2
    window_s: int = 30
    high_x: float = 55.0
    _recent: dict[str, list[MatchEvent]] = field(default_factory=dict)

    def on_event(self, event: MatchEvent, history: list[MatchEvent]) -> CandidateMoment | None:
        if event.type == "pressure":
            if event.x >= self.high_x:
                self._recent.setdefault(event.team_id, []).append(event)
            return None
        if event.type not in ("tackle", "interception") or event.x < self.high_x:
            return None
        presses = [p for p in self._recent.get(event.team_id, []) if event.t - p.t <= self.window_s]
        self._recent[event.team_id] = []
        if len(presses) < self.min_pressures:
            return None
        first = presses[0]
        counts = Counter(p.player_id for p in presses if p.player_id)
        top_player_id = event.player_id or counts.most_common(1)[0][0]
        recent = in_window(history, event.t, PRESS_WINDOW_S)
        return CandidateMoment(
            moment_id=f"{event.match_id}-{event.seq}-pressing_trap",
            window=(first.seq, event.seq),
            kind="pressing_trap",
            team_id=event.team_id,
            minute=event.minute,
            top_player_id=top_player_id,
            evidence={
                "pressing_trap_pressures": float(len(presses)),
                "pressing_trap_window_s": float(event.t - first.t),
                "pressing_trap_players": float(len(counts)),
                "top_player_pressures": float(counts.get(top_player_id, 0)),
                "pressing_trap_regain_distance_to_goal_m": round(metres(100 - event.x, event.y - 50), 1),
                "team_pressures_last_10min": float(pressure_count(recent, event.team_id)),
                "team_regains_last_10min": float(regains_after_pressure(recent, event.team_id)),
                "window_minutes": _window_minutes(event.t, PRESS_WINDOW_S),
                "minute": float(event.minute),
            },
        )
