"""Candidate-moment detectors. Each detector sees every event and may return a moment."""

from collections import Counter
from dataclasses import dataclass, field

from app.ledger.metrics import in_window, possession_pct, progress_m
from app.ledger.models import CandidateMoment
from app.simulator.models import MatchEvent

POSSESSION_WINDOW_S = 300


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
        if event.type in ("pressure", "foul") or not self._passes:
            return None
        ended_in_shot = event.type == "shot" and event.team_id == self._team
        moment = self._close(event, history, ended_in_shot) if len(self._passes) >= self.min_passes else None
        self._team, self._passes = None, []
        return moment

    def _close(self, end: MatchEvent, history: list[MatchEvent], ended_in_shot: bool) -> CandidateMoment:
        first, last = self._passes[0], self._passes[-1]
        team = self._team or end.team_id
        recent = in_window(history, last.t, POSSESSION_WINDOW_S)
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
                "team_possession_pct_window": possession_pct(recent, team),
                "window_minutes": round(min(POSSESSION_WINDOW_S, last.t) / 60, 1),
                "minute": float(last.minute),
            },
        )
