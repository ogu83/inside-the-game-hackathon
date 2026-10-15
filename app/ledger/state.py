"""Incremental match ledger: apply events one at a time, read flat evidence keys.

Evidence keys are the only vocabulary agents may cite:
  match.minute, match.score_home, match.score_away
  team.<club>.<stat>          e.g. team.vel.possession_pct
  player.<player_id>.<stat>   e.g. player.vel-09.top_speed_kmh
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from pydantic import BaseModel, Field

from app.ledger.metrics import (
    HARD_PASS,
    PRESSURE_WINDOW_S,
    SPRINT_KMH,
    next_owner,
    pass_difficulty,
    player_speeds,
)
from app.simulator.model import MATCH_TEAM_ID, MatchEvent


class TeamStats(BaseModel):
    possession_s: float = 0.0
    passes: int = 0
    passes_completed: int = 0
    difficulty_sum: float = 0.0
    shots: int = 0
    shots_on_target: int = 0
    xg: float = 0.0
    goals: int = 0
    max_shot_speed_kmh: float = 0.0
    pressures: int = 0
    tackles: int = 0
    interceptions: int = 0
    fouls: int = 0


class PlayerStats(BaseModel):
    team_id: str
    passes: int = 0
    passes_completed: int = 0
    hard_passes_completed: int = 0
    distance_with_ball_m: float = 0.0
    top_speed_kmh: float = 0.0
    sprints: int = 0
    shots: int = 0
    goals: int = 0
    xg: float = 0.0
    max_shot_speed_kmh: float = 0.0
    pressures: int = 0
    tackles: int = 0
    interceptions: int = 0


class LedgerState(BaseModel):
    match_id: str | None = None
    teams: dict[str, TeamStats] = Field(default_factory=dict)
    players: dict[str, PlayerStats] = Field(default_factory=dict)
    home_id: str | None = None
    away_id: str | None = None
    owner: str | None = None
    last_seq: int = -1
    clock_s: int = 0
    score: dict[str, int] = Field(default_factory=dict)
    difficulty: dict[int, float] = Field(default_factory=dict)
    recent_pressures: deque[tuple[int, str]] = Field(default_factory=deque)

    @classmethod
    def from_events(cls, events: Iterable[MatchEvent]) -> LedgerState:
        state = cls()
        for ev in events:
            state.apply(ev)
        return state

    def _team(self, team_id: str) -> TeamStats:
        return self.teams.setdefault(team_id, TeamStats())

    def _player(self, player_id: str, team_id: str) -> PlayerStats:
        return self.players.setdefault(player_id, PlayerStats(team_id=team_id))

    def apply(self, ev: MatchEvent) -> None:
        if ev.seq <= self.last_seq:
            raise ValueError(f"event seq {ev.seq} is not after {self.last_seq}")
        if self.match_id is None:
            self.match_id = ev.match_id
            _, self.home_id, self.away_id = ev.match_id.split("-")
            for team_id in (self.home_id, self.away_id):
                self._team(team_id)
                self.score[team_id] = 0
        if self.owner is not None and self.last_seq >= 0:
            self.teams[self.owner].possession_s += ev.clock_s - self.clock_s
        self.last_seq, self.clock_s = ev.seq, ev.clock_s
        self.owner = next_owner(self.owner, ev)

        while self.recent_pressures and ev.clock_s - self.recent_pressures[0][0] > PRESSURE_WINDOW_S:
            self.recent_pressures.popleft()
        if ev.team_id == MATCH_TEAM_ID or ev.player_id is None:
            return
        team = self._team(ev.team_id)
        player = self._player(ev.player_id, ev.team_id)

        speed = player_speeds(ev)
        if speed is not None:
            player.top_speed_kmh = max(player.top_speed_kmh, speed)
            player.sprints += speed >= SPRINT_KMH

        if ev.type == "pass":
            nearby = sum(1 for _, t in self.recent_pressures if t != ev.team_id)
            diff = pass_difficulty(ev, nearby)
            self.difficulty[ev.seq] = diff
            team.passes += 1
            team.difficulty_sum += diff
            player.passes += 1
            player.distance_with_ball_m = round(player.distance_with_ball_m + float(ev.meta.get("carry_m", 0.0)), 1)
            if ev.outcome == "success":
                team.passes_completed += 1
                player.passes_completed += 1
                player.hard_passes_completed += diff >= HARD_PASS
        elif ev.type == "shot":
            xg = float(ev.meta.get("xg", 0.0))
            shot_speed = float(ev.meta.get("speed_kmh", 0.0))
            team.shots += 1
            team.shots_on_target += ev.outcome == "success"
            team.xg += xg
            team.max_shot_speed_kmh = max(team.max_shot_speed_kmh, shot_speed)
            player.shots += 1
            player.xg += xg
            player.max_shot_speed_kmh = max(player.max_shot_speed_kmh, shot_speed)
        elif ev.type == "goal":
            team.goals += 1
            player.goals += 1
            self.score[ev.team_id] += 1
        elif ev.type == "pressure":
            team.pressures += 1
            player.pressures += 1
            self.recent_pressures.append((ev.clock_s, ev.team_id))
        elif ev.type == "tackle":
            team.tackles += 1
            player.tackles += 1
        elif ev.type == "interception":
            team.interceptions += 1
            player.interceptions += 1
        elif ev.type == "foul":
            team.fouls += 1

    def possession_pct(self, team_id: str) -> float:
        total = sum(t.possession_s for t in self.teams.values())
        return round(100 * self.teams[team_id].possession_s / total, 1) if total else 0.0

    def evidence(self) -> dict[str, float]:
        """Flat snapshot of every citable number."""
        out: dict[str, float] = {"match.minute": float(self.clock_s // 60)}
        if self.home_id and self.away_id:
            out["match.score_home"] = float(self.score[self.home_id])
            out["match.score_away"] = float(self.score[self.away_id])
        for team_id, t in self.teams.items():
            p = f"team.{team_id}."
            out[p + "possession_pct"] = self.possession_pct(team_id)
            out[p + "passes"] = float(t.passes)
            out[p + "pass_accuracy"] = round(100 * t.passes_completed / t.passes, 1) if t.passes else 0.0
            out[p + "avg_pass_difficulty"] = round(t.difficulty_sum / t.passes, 3) if t.passes else 0.0
            out[p + "shots"] = float(t.shots)
            out[p + "shots_on_target"] = float(t.shots_on_target)
            out[p + "xg"] = round(t.xg, 2)
            out[p + "goals"] = float(t.goals)
            out[p + "max_shot_speed_kmh"] = t.max_shot_speed_kmh
            out[p + "pressures"] = float(t.pressures)
            out[p + "tackles"] = float(t.tackles)
            out[p + "interceptions"] = float(t.interceptions)
            out[p + "fouls"] = float(t.fouls)
        for player_id, s in self.players.items():
            p = f"player.{player_id}."
            out[p + "passes"] = float(s.passes)
            out[p + "pass_accuracy"] = round(100 * s.passes_completed / s.passes, 1) if s.passes else 0.0
            out[p + "hard_passes_completed"] = float(s.hard_passes_completed)
            out[p + "distance_with_ball_m"] = s.distance_with_ball_m
            out[p + "top_speed_kmh"] = s.top_speed_kmh
            out[p + "sprints"] = float(s.sprints)
            out[p + "shots"] = float(s.shots)
            out[p + "goals"] = float(s.goals)
            out[p + "xg"] = round(s.xg, 2)
            out[p + "max_shot_speed_kmh"] = s.max_shot_speed_kmh
            out[p + "pressures"] = float(s.pressures)
            out[p + "tackles"] = float(s.tackles)
            out[p + "interceptions"] = float(s.interceptions)
        return out

    def value(self, key: str) -> float:
        """Look up one evidence key; KeyError if the ledger has no such number."""
        return self.evidence()[key]
