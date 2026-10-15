"""Seeded match simulator built on a small phase model, plus a timed event stream.

Phases: build_up (patient play from deep), transition (after a turnover, fast and
vertical), pressing (opponent pushes high), set_piece (after a foul in the final
third). Each team's intensity changes in windows of 8-15 minutes, which is what
gives a match its momentum swings. The first half ends at exactly 45:00 so the
match clock never runs backwards; stoppage time only happens in the second half.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from collections.abc import AsyncIterator, Callable, Iterable, Iterator
from typing import Literal

from app.simulator.league import LEAGUE, Club, Player, fixture_for_seed
from app.simulator.model import (
    MATCH_TEAM_ID,
    PITCH_LENGTH_M,
    PITCH_WIDTH_M,
    EventType,
    MatchEvent,
)

Phase = Literal["build_up", "transition", "pressing", "set_piece"]

HALF_S = 45 * 60


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(min(hi, max(lo, v)), 1)


def distance_m(x: float, y: float, end_x: float, end_y: float) -> float:
    dx = (end_x - x) / 100 * PITCH_LENGTH_M
    dy = (end_y - y) / 100 * PITCH_WIDTH_M
    return math.hypot(dx, dy)


def expected_goals(x: float, y: float) -> float:
    dist = distance_m(x, y, 100.0, 50.0)
    centrality = 1 - min(abs(y - 50) / 50, 1)
    return round(min(0.8, max(0.01, 0.8 * math.exp(-dist / 8.0) * (0.5 + 0.5 * centrality))), 3)


class _Match:
    def __init__(self, seed: int, home: Club, away: Club) -> None:
        self.rng = random.Random(seed)
        self.home, self.away = home, away
        self.match_id = f"m{seed:04d}-{home.club_id}-{away.club_id}"
        self.events: list[MatchEvent] = []
        self.clock = 0
        self.period = 1
        self.score = {home.club_id: 0, away.club_id: 0}
        self.on_pitch = {c.club_id: [p.player_id for p in c.starters] for c in (home, away)}
        self.bench = {c.club_id: [p.player_id for p in c.bench if p.position != "GK"] for c in (home, away)}
        self.subs_left = {home.club_id: 3, away.club_id: 3}
        self.sub_minutes = {
            c.club_id: sorted(self.rng.sample(range(56, 84), 3)) for c in (home, away)
        }
        self.intensity = {home.club_id: 0.6, away.club_id: 0.55}
        self.next_window = 0

    def club(self, club_id: str) -> Club:
        return self.home if club_id == self.home.club_id else self.away

    def opponent(self, club_id: str) -> str:
        return self.away.club_id if club_id == self.home.club_id else self.home.club_id

    def player(self, player_id: str) -> Player:
        return self.club(player_id.split("-", 1)[0]).player(player_id)

    def emit(self, type_: EventType, team_id: str, player_id: str | None, x: float, y: float,
             end_x: float | None = None, end_y: float | None = None,
             outcome: Literal["success", "fail"] | None = None, **meta: float | str) -> MatchEvent:
        meta.setdefault("period", float(self.period))
        ev = MatchEvent(
            match_id=self.match_id, seq=len(self.events), minute=self.clock // 60, second=self.clock % 60,
            type=type_, team_id=team_id, player_id=player_id, x=_clamp(x), y=_clamp(y),
            end_x=None if end_x is None else _clamp(end_x), end_y=None if end_y is None else _clamp(end_y),
            outcome=outcome, meta=meta,
        )
        self.events.append(ev)
        return ev

    def tick(self, lo: int, hi: int) -> None:
        self.clock += self.rng.randint(lo, hi)
        if self.clock >= self.next_window:
            for club_id in self.intensity:
                style = self.club(club_id).style
                base = {"pressing": 0.7, "possession": 0.55, "direct": 0.5, "balanced": 0.55}[style]
                self.intensity[club_id] = round(min(0.95, max(0.2, base + self.rng.uniform(-0.3, 0.3))), 2)
            self.next_window = self.clock + self.rng.randint(8 * 60, 15 * 60)

    def pick(self, team_id: str, x: float, exclude: str | None = None) -> str:
        weights_by_zone = {"GK": (6, 0.2, 0), "DF": (5, 2, 0.6), "MF": (3, 5, 3), "FW": (0.3, 2, 6)}
        zone = 0 if x < 33 else (1 if x < 66 else 2)
        ids = [pid for pid in self.on_pitch[team_id] if pid != exclude]
        weights = [weights_by_zone[self.player(pid).position][zone] + 0.05 for pid in ids]
        return self.rng.choices(ids, weights=weights)[0]

    def goalkeeper(self, team_id: str) -> str:
        return next(pid for pid in self.on_pitch[team_id] if self.player(pid).position == "GK")

    def maybe_substitute(self) -> None:
        minute = self.clock // 60
        for team_id in (self.home.club_id, self.away.club_id):
            while self.subs_left[team_id] and self.sub_minutes[team_id][3 - self.subs_left[team_id]] <= minute:
                outfield = [pid for pid in self.on_pitch[team_id][1:] if self.player(pid).starter]
                off = self.rng.choice(outfield or self.on_pitch[team_id][1:])
                on = self.bench[team_id].pop(0)
                self.on_pitch[team_id][self.on_pitch[team_id].index(off)] = on
                self.subs_left[team_id] -= 1
                self.emit("substitution", team_id, on, 50, 0, off=off)

    def kickoff(self, team_id: str) -> tuple[str, float, float, Phase]:
        fw = [pid for pid in self.on_pitch[team_id] if self.player(pid).position == "FW"]
        taker = self.rng.choice(fw or self.on_pitch[team_id][1:])
        self.emit("kickoff", team_id, taker, 50, 50, score_home=float(self.score[self.home.club_id]),
                  score_away=float(self.score[self.away.club_id]))
        return taker, 50.0, 50.0, "build_up"

    def turnover(self, new_team: str, player_id: str, x: float, y: float, reason: str) -> None:
        self.emit("possession_change", new_team, player_id, x, y, reason=reason)

    def possession(self, team_id: str, carrier: str, x: float, y: float, phase: Phase,
                   half_end: int) -> tuple[str, str, float, float, Phase]:
        """Play one possession; return who has the ball next, where, and in which phase."""
        opp = self.opponent(team_id)
        rng = self.rng
        streak = 0
        while self.clock < half_end:
            self.maybe_substitute()
            if carrier not in self.on_pitch[team_id]:
                carrier = self.pick(team_id, x)
            p = self.player(carrier)
            press_level = self.intensity[opp] * (1.25 if phase == "pressing" else 1.0)
            if phase == "build_up" and x < 40 and self.intensity[opp] > 0.7:
                phase = "pressing"

            carry_m = rng.uniform(0, 4 + 10 * p.pace) if phase != "set_piece" else 0.0
            speed_kmh = round(12 + 20 * p.pace * rng.uniform(0.6, 1.05), 1)
            x = _clamp(x + carry_m / PITCH_LENGTH_M * 100 * rng.uniform(0.3, 0.9))
            y = _clamp(y + rng.uniform(-6, 6), 3, 97)

            pressed = rng.random() < 0.08 + 0.42 * press_level * (0.6 + 0.4 * (1 - x / 100))
            if pressed:
                presser = self.pick(opp, 100 - x)
                pspeed = round(18 + 14 * self.player(presser).pressing * rng.uniform(0.7, 1.05), 1)
                self.emit("pressure", opp, presser, 100 - x, 100 - y, speed_kmh=pspeed, phase=phase)
                if rng.random() < 0.18 * press_level + 0.1 * (1 - p.pace):
                    self.tick(1, 2)
                    self.emit("tackle", opp, presser, 100 - x, 100 - y, outcome="success", phase=phase)
                    self.turnover(opp, presser, 100 - x, 100 - y, "tackle")
                    return opp, presser, 100 - x, 100 - y, "transition"

            if rng.random() < 0.022 + (0.02 if pressed else 0):
                fouler = self.pick(opp, 100 - x)
                self.emit("foul", opp, fouler, 100 - x, 100 - y, phase=phase)
                self.tick(15, 40)
                phase = "set_piece" if x > 62 else "build_up"
                continue

            shot_chance = 0.0 if x < 76 else (0.02 + 0.22 * ((x - 76) / 24) ** 2)
            if phase == "set_piece":
                shot_chance = max(shot_chance, 0.25 if x > 70 else 0.0)
            if rng.random() < shot_chance:
                return self.shoot(team_id, carrier, x, y, phase, streak)

            forward = {"build_up": (-7, 12), "transition": (0, 22), "pressing": (-5, 15), "set_piece": (0, 15)}[phase]
            if self.club(team_id).style == "direct":
                forward = (forward[0] + 3, forward[1] + 8)
            end_x = _clamp(x + rng.uniform(*forward), 1, 99)
            end_y = _clamp(y + rng.uniform(-28, 28), 2, 98)
            receiver = self.pick(team_id, end_x, exclude=carrier)
            length = distance_m(x, y, end_x, end_y)
            p_success = (0.9 + 0.25 * (p.passing - 0.6) - 0.004 * max(0.0, length - 15)
                         - (0.12 if pressed else 0.0) - 0.3 * max(0.0, end_x - 68) / 32)
            ok = rng.random() < p_success
            self.emit("pass", team_id, carrier, x, y, end_x, end_y, "success" if ok else "fail",
                      pass_length_m=round(length, 1), carry_m=round(carry_m, 1), speed_kmh=speed_kmh,
                      under_pressure=1.0 if pressed else 0.0, phase=phase,
                      receiver_id=receiver if ok else "")
            self.tick(2, 5)
            if ok:
                carrier, x, y = receiver, end_x, end_y
                streak += 1
                if phase in ("set_piece", "pressing") and x > 45:
                    phase = "build_up"
                continue
            ix, iy = 100 - end_x, 100 - end_y
            winner = self.pick(opp, ix)
            if rng.random() < 0.6:
                self.emit("interception", opp, winner, ix, iy, outcome="success", phase=phase)
                self.turnover(opp, winner, ix, iy, "interception")
                return opp, winner, ix, iy, "transition"
            self.tick(4, 15)
            self.turnover(opp, winner, ix, iy, "out_of_play")
            return opp, winner, ix, iy, "build_up"
        return team_id, carrier, x, y, phase

    def shoot(self, team_id: str, shooter: str, x: float, y: float, phase: Phase,
              streak: int) -> tuple[str, str, float, float, Phase]:
        rng = self.rng
        opp = self.opponent(team_id)
        p = self.player(shooter)
        xg = expected_goals(x, y)
        scored = rng.random() < xg * (0.6 + 0.5 * p.finishing)
        on_target = scored or rng.random() < 0.2 + 0.25 * p.finishing
        speed = round(55 + 60 * p.finishing * rng.uniform(0.7, 1.1), 1)
        self.emit("shot", team_id, shooter, x, y, 100, _clamp(50 + rng.uniform(-8, 8)),
                  "success" if on_target else "fail", xg=xg, speed_kmh=speed, phase=phase,
                  build_up_passes=float(streak))
        self.tick(1, 3)
        if scored:
            self.score[team_id] += 1
            self.emit("goal", team_id, shooter, x, y, xg=xg,
                      score_home=float(self.score[self.home.club_id]),
                      score_away=float(self.score[self.away.club_id]))
            self.tick(40, 75)
            taker, kx, ky, kphase = self.kickoff(opp)
            return opp, taker, kx, ky, kphase
        gk = self.goalkeeper(opp)
        self.tick(5, 20)
        self.turnover(opp, gk, 6, 50, "save" if on_target else "goal_kick")
        return opp, gk, 6.0, 50.0, "build_up"

    def play(self) -> list[MatchEvent]:
        team = self.home.club_id
        for period, start, end in ((1, 0, HALF_S), (2, HALF_S, 2 * HALF_S + self.rng.randint(60, 300))):
            self.period = period
            self.clock = start
            carrier, x, y, phase = self.kickoff(team)
            while self.clock < end:
                team, carrier, x, y, phase = self.possession(team, carrier, x, y, phase, end)
            self.clock = end
            if period == 1:
                self.emit("half_time", MATCH_TEAM_ID, None, 50, 50,
                          score_home=float(self.score[self.home.club_id]),
                          score_away=float(self.score[self.away.club_id]))
                team = self.away.club_id
        self.emit("full_time", MATCH_TEAM_ID, None, 50, 50,
                  score_home=float(self.score[self.home.club_id]),
                  score_away=float(self.score[self.away.club_id]))
        return self.events


def simulate_match(seed: int, home_id: str | None = None, away_id: str | None = None) -> list[MatchEvent]:
    """Full 90-minute match; same seed and clubs always give the identical event list."""
    if home_id is None or away_id is None:
        home_id, away_id = fixture_for_seed(seed)
    if home_id == away_id:
        raise ValueError("a club cannot play itself")
    return _Match(seed, LEAGUE[home_id], LEAGUE[away_id]).play()


def stream(events: Iterable[MatchEvent], speed: float,
           sleep: Callable[[float], None] = time.sleep) -> Iterator[MatchEvent]:
    """Yield events paced by the match clock; speed 20 means 20 match seconds per real second, 0 means no pacing."""
    prev: int | None = None
    for ev in events:
        if speed > 0 and prev is not None and ev.clock_s > prev:
            sleep((ev.clock_s - prev) / speed)
        prev = ev.clock_s
        yield ev


async def astream(events: Iterable[MatchEvent], speed: float) -> AsyncIterator[MatchEvent]:
    prev: int | None = None
    for ev in events:
        if speed > 0 and prev is not None and ev.clock_s > prev:
            await asyncio.sleep((ev.clock_s - prev) / speed)
        prev = ev.clock_s
        yield ev
