"""Candidate-moment detection: turns the event stream into moments worth talking about.

Each CandidateMoment carries an evidence dict of numbers the agents may cite. Keys
are either ledger keys (team.<club>.*, player.<id>.*, match.*) or moment-local keys
of the form moment.<subject>.<stat>, where subject is team.<club> or player.<id>,
so the subject of a moment is always readable from its evidence keys.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable

from pydantic import BaseModel

from app.ledger.metrics import pass_accuracy, possession_pct
from app.ledger.state import LedgerState
from app.simulator.model import MATCH_TEAM_ID, PITCH_LENGTH_M, MatchEvent

PRESS_LOOKBACK_S = 8
PRESS_MIN_PRESSURES = 2
PRESS_COOLDOWN_S = 3 * 60
STREAK_MIN_PASSES = 11
MOMENTUM_WINDOW_S = 10 * 60
MOMENTUM_COOLDOWN_S = 10 * 60
MOMENTUM_NOW = 0.65
MOMENTUM_BEFORE = 0.45
LULL_AFTER_S = 6 * 60
LULL_COOLDOWN_S = 8 * 60
FINAL_THIRD_X = 67.0

MILESTONES: dict[str, list[float]] = {
    "hard_passes_completed": [4],
    "sprints": [20],
    "tackles": [4],
    "interceptions": [7],
    "distance_with_ball_m": [300],
    "shots": [4],
}


class CandidateMoment(BaseModel):
    moment_id: str
    window: tuple[int, int]
    kind: str
    evidence: dict[str, float]


class MomentDetector:
    """Feed events in seq order; each call returns the moments that event completed."""

    def __init__(self) -> None:
        self.ledger = LedgerState()
        self.events: list[MatchEvent] = []
        self.clocks: list[int] = []
        self.streak: list[MatchEvent] = []
        self.last_press: dict[str, int] = {}
        self.last_momentum = -MOMENTUM_COOLDOWN_S
        self.last_action_s = 0
        self.last_lull = -LULL_COOLDOWN_S
        self.checked_minute = -1
        self.milestones_hit: set[tuple[str, str, float]] = set()

    def feed(self, ev: MatchEvent) -> list[CandidateMoment]:
        self.ledger.apply(ev)
        self.events.append(ev)
        self.clocks.append(ev.clock_s)
        found: list[CandidateMoment] = []
        found += self._pass_streak(ev)
        if ev.type == "goal":
            found.append(self._goal(ev))
        if ev.type in ("tackle", "interception"):
            found += self._pressing_trap(ev)
        if ev.player_id and ev.team_id != MATCH_TEAM_ID:
            found += self._milestones(ev)
        if ev.type in ("shot", "kickoff"):
            self.last_action_s = ev.clock_s
        if ev.minute != self.checked_minute and ev.team_id != MATCH_TEAM_ID:
            self.checked_minute = ev.minute
            found += self._momentum(ev)
            found += self._lull(ev)
        return found

    def _moment(self, kind: str, start_seq: int, evidence: dict[str, float],
                ledger_keys: Iterable[str] = ()) -> CandidateMoment:
        ledger = self.ledger.evidence()
        merged = {k: ledger[k] for k in ("match.minute", "match.score_home", "match.score_away")}
        merged.update({k: ledger[k] for k in ledger_keys if k in ledger})
        merged.update({k: round(v, 3) for k, v in evidence.items()})
        end_seq = self.events[-1].seq
        return CandidateMoment(
            moment_id=f"{self.events[-1].match_id}-{kind}-{end_seq}",
            window=(start_seq, end_seq), kind=kind, evidence=merged,
        )

    def _window(self, start_s: int, end_s: int) -> list[MatchEvent]:
        lo = bisect.bisect_left(self.clocks, start_s)
        hi = bisect.bisect_right(self.clocks, end_s)
        return self.events[lo:hi]

    def _teams(self) -> tuple[str, str]:
        assert self.ledger.home_id and self.ledger.away_id
        return self.ledger.home_id, self.ledger.away_id

    def _pass_streak(self, ev: MatchEvent) -> list[CandidateMoment]:
        completed = ev.type == "pass" and ev.outcome == "success"
        if ev.type in ("pressure", "foul", "substitution"):
            return []
        if completed and (not self.streak or self.streak[0].team_id == ev.team_id):
            self.streak.append(ev)
            return []
        streak, self.streak = self.streak, ([ev] if completed else [])
        if len(streak) < STREAK_MIN_PASSES:
            return []
        team = streak[0].team_id
        subj = f"moment.team.{team}."
        players = {e.player_id for e in streak} | {str(e.meta["receiver_id"]) for e in streak}
        ended_in_shot = ev.type == "shot" and ev.team_id == team
        evidence = {
            subj + "consecutive_passes": float(len(streak)),
            subj + "duration_s": float(ev.clock_s - streak[0].clock_s),
            subj + "players_involved": float(len(players)),
            subj + "metres_gained": round(sum((e.end_x or e.x) - e.x for e in streak) / 100 * PITCH_LENGTH_M, 1),
            subj + "ended_in_shot": 1.0 if ended_in_shot else 0.0,
        }
        if ended_in_shot:
            evidence[subj + "shot_xg"] = float(ev.meta["xg"])
        return [self._moment("pass_streak", streak[0].seq, evidence,
                             [f"team.{team}.possession_pct", f"team.{team}.pass_accuracy"])]

    def _goal(self, ev: MatchEvent) -> CandidateMoment:
        shot = next(e for e in reversed(self.events[:-1]) if e.type == "shot" and e.player_id == ev.player_id)
        subj = f"moment.player.{ev.player_id}."
        evidence = {
            subj + "shot_xg": float(shot.meta["xg"]),
            subj + "shot_speed_kmh": float(shot.meta["speed_kmh"]),
            subj + "distance_to_goal_m": round((100 - shot.x) / 100 * PITCH_LENGTH_M, 1),
            subj + "build_up_passes": float(shot.meta.get("build_up_passes", 0.0)),
        }
        team = ev.team_id
        keys = [f"player.{ev.player_id}.goals", f"player.{ev.player_id}.shots",
                f"team.{team}.xg", f"team.{team}.shots", f"team.{team}.possession_pct"]
        return self._moment("goal", shot.seq, evidence, keys)

    def _pressing_trap(self, ev: MatchEvent) -> list[CandidateMoment]:
        team = ev.team_id
        if ev.x < 50 or ev.clock_s - self.last_press.get(team, -PRESS_COOLDOWN_S) < PRESS_COOLDOWN_S:
            return []
        window = self._window(ev.clock_s - PRESS_LOOKBACK_S, ev.clock_s)
        presses = [e for e in window if e.type == "pressure" and e.team_id == team]
        if len(presses) < PRESS_MIN_PRESSURES:
            return []
        self.last_press[team] = ev.clock_s
        subj = f"moment.team.{team}."
        evidence = {
            subj + "pressures_in_sequence": float(len(presses)),
            subj + "seconds_to_regain": float(ev.clock_s - presses[0].clock_s),
            subj + "regain_distance_to_goal_m": round((100 - ev.x) / 100 * PITCH_LENGTH_M, 1),
            subj + "top_closing_speed_kmh": max(float(e.meta["speed_kmh"]) for e in presses),
            subj + "pressers": float(len({e.player_id for e in presses})),
        }
        keys = [f"team.{team}.pressures", f"team.{team}.tackles", f"team.{team}.interceptions",
                f"player.{ev.player_id}.tackles", f"player.{ev.player_id}.interceptions"]
        return [self._moment("pressing_trap", presses[0].seq, evidence, keys)]

    def _milestones(self, ev: MatchEvent) -> list[CandidateMoment]:
        assert ev.player_id
        found = []
        ledger = self.ledger.evidence()
        for stat, thresholds in MILESTONES.items():
            key = f"player.{ev.player_id}.{stat}"
            value = ledger.get(key)
            if value is None:
                continue
            for threshold in thresholds:
                mark = (ev.player_id, stat, threshold)
                if value >= threshold and mark not in self.milestones_hit:
                    self.milestones_hit.add(mark)
                    evidence = {f"moment.player.{ev.player_id}.{stat}_threshold": threshold}
                    keys = [key, f"player.{ev.player_id}.top_speed_kmh", f"player.{ev.player_id}.pass_accuracy"]
                    found.append(self._moment("player_milestone", ev.seq, evidence, keys))
        return found

    def _momentum(self, ev: MatchEvent) -> list[CandidateMoment]:
        now = ev.clock_s
        if now < 2 * MOMENTUM_WINDOW_S or now - self.last_momentum < MOMENTUM_COOLDOWN_S:
            return []
        recent = self._window(now - MOMENTUM_WINDOW_S, now)
        before = self._window(now - 2 * MOMENTUM_WINDOW_S, now - MOMENTUM_WINDOW_S - 1)
        home, away = self._teams()
        for team in (home, away):
            share_now, stats_now = _threat_share(recent, team, (home, away))
            share_before, _ = _threat_share(before, team, (home, away))
            if share_now >= MOMENTUM_NOW and share_before <= MOMENTUM_BEFORE:
                self.last_momentum = now
                subj = f"moment.team.{team}."
                evidence = {
                    subj + "threat_share_now_pct": round(100 * share_now, 1),
                    subj + "threat_share_before_pct": round(100 * share_before, 1),
                    subj + "window_minutes": MOMENTUM_WINDOW_S / 60,
                    subj + "shots_in_window": stats_now["shots"],
                    subj + "xg_in_window": round(stats_now["xg"], 2),
                    subj + "final_third_passes_in_window": stats_now["final_third_passes"],
                    subj + "possession_pct_in_window": possession_pct(recent).get(team, 0.0),
                }
                return [self._moment("momentum_shift", recent[0].seq, evidence,
                                     [f"team.{team}.shots", f"team.{team}.xg", f"team.{team}.possession_pct"])]
        return []

    def _lull(self, ev: MatchEvent) -> list[CandidateMoment]:
        now = ev.clock_s
        quiet = now - self.last_action_s
        if quiet < LULL_AFTER_S or now - self.last_lull < LULL_COOLDOWN_S:
            return []
        self.last_lull = now
        window = self._window(self.last_action_s, now)
        home, away = self._teams()
        possession = possession_pct(window)
        evidence: dict[str, float] = {"moment.match.minutes_without_shot": float(quiet // 60)}
        for team in (home, away):
            subj = f"moment.team.{team}."
            evidence[subj + "possession_pct_in_window"] = possession.get(team, 0.0)
            evidence[subj + "pass_accuracy_in_window"] = pass_accuracy(window, team_id=team) or 0.0
            evidence[subj + "fouls_in_window"] = float(sum(e.type == "foul" and e.team_id == team for e in window))
            evidence[subj + "final_third_passes_in_window"] = float(sum(
                e.type == "pass" and e.team_id == team and e.outcome == "success" and (e.end_x or 0) >= FINAL_THIRD_X
                for e in window))
            evidence[subj + "turnovers_in_window"] = float(sum(
                e.type == "possession_change" and e.team_id != team for e in window))
        return [self._moment("lull", window[0].seq, evidence)]


def _threat_share(window: list[MatchEvent], team: str, teams: tuple[str, str]) -> tuple[float, dict[str, float]]:
    def stats(t: str) -> dict[str, float]:
        shots = [e for e in window if e.type == "shot" and e.team_id == t]
        ft = sum(1 for e in window if e.type == "pass" and e.team_id == t and e.outcome == "success"
                 and (e.end_x or 0) >= FINAL_THIRD_X)
        return {"shots": float(len(shots)), "xg": sum(float(e.meta["xg"]) for e in shots),
                "final_third_passes": float(ft)}

    def threat(s: dict[str, float]) -> float:
        return s["shots"] + 3 * s["xg"] + 0.2 * s["final_third_passes"]

    mine = stats(team)
    total = sum(threat(stats(t)) for t in teams)
    return (threat(mine) / total if total else 0.5), mine


def detect_moments(events: Iterable[MatchEvent]) -> list[CandidateMoment]:
    detector = MomentDetector()
    return [m for ev in events for m in detector.feed(ev)]


if __name__ == "__main__":
    import argparse
    from collections import Counter

    from app.simulator.emitter import simulate_match

    parser = argparse.ArgumentParser(description="Print candidate moments for a seeded match.")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    moments = detect_moments(simulate_match(args.seed))
    if args.verbose:
        for m in moments:
            print(f"{int(m.evidence['match.minute']):>3}'  {m.kind:<17} {m.moment_id}")
    print(f"seed {args.seed}: {len(moments)} moments {dict(Counter(m.kind for m in moments))}")
