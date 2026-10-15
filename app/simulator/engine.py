"""Seeded match engine with a small phase model (build-up and transition).

Same seed and clubs -> identical event list. Coordinates follow MatchEvent: each event is in
the acting team's frame, so a turnover at x maps to 100 - x for the team that wins the ball.
v1 (T3): per-club pressing trait, substitutions, free-kick restarts after fouls.
"""

import math
import random
from dataclasses import dataclass, field

from app.simulator.league import CLUBS, NOMINAL_X, NOMINAL_Y, Club, Player
from app.simulator.models import EventType, MatchEvent

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
SUBS_PER_TEAM = 2  # the bench has 3, one of them the reserve keeper, who only plays if the starter is sent off (not simulated)
SUB_WINDOW_MIN = (58, 82)
DEMO_SEED = 30  # 3 pass_streak moments inside the first 5 minutes, both clubs, one ending in a shot (docs/demo-script.md)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def metres(dx: float, dy: float) -> float:
    return math.hypot(dx * PITCH_LENGTH_M / 100, dy * PITCH_WIDTH_M / 100)


@dataclass
class _State:
    rng: random.Random
    match_id: str
    clubs: dict[str, Club]
    events: list[MatchEvent] = field(default_factory=list)
    t: float = 0.0
    team: str = ""
    holder: Player | None = None
    x: float = 50.0
    y: float = 50.0
    phase: str = "build_up"
    score: dict[str, int] = field(default_factory=dict)
    lineup: dict[str, list[Player]] = field(default_factory=dict)
    bench: dict[str, list[Player]] = field(default_factory=dict)
    subs_due: dict[str, list[float]] = field(default_factory=dict)  # match seconds at which each club makes a change
    restart: str | None = None  # "free_kick" marks the next pass as a restart

    def other(self, team_id: str) -> str:
        return next(cid for cid in self.clubs if cid != team_id)

    def emit(
        self,
        type_: EventType,
        team_id: str,
        player: Player | None,
        x: float,
        y: float,
        *,
        end: tuple[float, float] | None = None,
        outcome: str | None = None,
        **meta: float | str,
    ) -> None:
        seconds = int(self.t)
        self.events.append(
            MatchEvent(
                match_id=self.match_id,
                seq=len(self.events) + 1,
                minute=seconds // 60,
                second=seconds % 60,
                type=type_,
                team_id=team_id,
                player_id=player.id if player else None,
                x=round(clamp(x, 0, 100), 1),
                y=round(clamp(y, 0, 100), 1),
                end_x=round(clamp(end[0], 0, 100), 1) if end else None,
                end_y=round(clamp(end[1], 0, 100), 1) if end else None,
                outcome=outcome,
                meta=meta,
            )
        )


def _pick_player(state: _State, team_id: str, target_x: float, exclude: Player | None = None) -> Player:
    candidates = [p for p in state.lineup[team_id] if p != exclude]
    weights = [
        (0.0 if p.position == "GK" and target_x > 15 else 1.0) * math.exp(-abs(NOMINAL_X[p.position] - target_x) / 15)
        for p in candidates
    ]
    return state.rng.choices(candidates, weights=weights)[0]


def _keeper(state: _State, team_id: str) -> Player:
    return next(p for p in state.lineup[team_id] if p.position == "GK")


def _change_possession(state: _State, new_team: str, x: float, y: float, player: Player | None = None) -> None:
    state.team = new_team
    state.x, state.y = x, y
    state.holder = player or _pick_player(state, new_team, x)
    state.phase = "transition" if x >= 40 else "build_up"
    state.emit("possession_change", new_team, state.holder, x, y, phase=state.phase)


def _kickoff(state: _State, team_id: str) -> None:
    state.team = team_id
    state.x, state.y = 50.0, 50.0
    state.holder = next(p for p in state.lineup[team_id] if p.position == "ST")
    state.phase = "build_up"
    state.emit("kickoff", team_id, state.holder, 50, 50)


def _shot(state: _State) -> None:
    rng = state.rng
    dist = metres(100 - state.x, state.y - 50)
    xg = round(clamp(0.42 * math.exp(-dist / 8), 0.02, 0.6), 2)
    speed = round(rng.uniform(70, 115), 1)
    scored = rng.random() < xg
    state.emit(
        "shot", state.team, state.holder, state.x, state.y,
        end=(100.0, clamp(50 + rng.gauss(0, 6), 40, 60)),
        outcome="success" if scored else "fail",
        xg=xg, speed_kmh=speed, distance_m=round(dist, 1), phase=state.phase,
    )
    if scored:
        state.score[state.team] += 1
        state.emit("goal", state.team, state.holder, state.x, state.y, xg=xg)
        state.t += rng.uniform(40, 70)
        _kickoff(state, state.other(state.team))
    else:
        state.t += rng.uniform(6, 15)
        _change_possession(state, state.other(state.team), 6.0, 50.0, _keeper(state, state.other(state.team)))


def _substitutions(state: _State) -> None:
    """Like-for-like changes when a club's scheduled time has passed; the holder is never taken off mid-move."""
    for team_id, due in state.subs_due.items():
        while due and state.t >= due[0] and state.bench[team_id]:
            due.pop(0)
            incoming = next((p for p in state.bench[team_id] if p.position != "GK"), None)
            if incoming is None:
                return
            same_position = [p for p in state.lineup[team_id] if p.position == incoming.position and p != state.holder]
            outfield = [p for p in state.lineup[team_id] if p.position != "GK" and p != state.holder]
            outgoing = state.rng.choice(same_position or outfield)
            state.bench[team_id].remove(incoming)
            state.lineup[team_id] = [incoming if p == outgoing else p for p in state.lineup[team_id]]
            state.emit("substitution", team_id, incoming, 50, 0, player_off=outgoing.id, player_on=incoming.id, position=incoming.position)


def _step(state: _State) -> None:
    rng = state.rng
    transition = state.phase == "transition"
    state.t += rng.uniform(2.0, 4.0) if transition else rng.uniform(2.5, 6.0)
    _substitutions(state)
    opponent = state.other(state.team)
    restart = state.restart
    state.restart = None

    pressured = False
    if restart is None:
        press_chance = ((0.25 if state.x > 60 else 0.12) + (0.08 if transition else 0)) * state.clubs[opponent].pressing
        pressured = rng.random() < press_chance
    if pressured:
        presser = _pick_player(state, opponent, 100 - state.x)
        state.emit("pressure", opponent, presser, 100 - state.x, 100 - state.y)
        if rng.random() < 0.22:
            state.emit("tackle", opponent, presser, 100 - state.x, 100 - state.y, outcome="success")
            _change_possession(state, opponent, 100 - state.x, 100 - state.y, presser)
            return

    if restart is None and rng.random() < 0.015:
        fouler = _pick_player(state, opponent, 100 - state.x)
        state.emit("foul", opponent, fouler, 100 - state.x, 100 - state.y)
        state.t += rng.uniform(8, 20)
        state.restart = "free_kick"
        state.holder = _pick_player(state, state.team, state.x)
        return

    shot_chance = 0.0 if state.x < 72 else 0.035 + (state.x - 72) * 0.006 + (0.04 if transition else 0)
    if restart is None and rng.random() < shot_chance:
        _shot(state)
        return

    for _ in range(5):
        advance = rng.gauss(12, 10) if transition else rng.gauss(5, 8)
        end_x = clamp(state.x + advance, 2, 97)
        end_y = clamp(state.y + rng.gauss(0, 18), 3, 97)
        receiver = _pick_player(state, state.team, end_x, exclude=state.holder)
        end_y = clamp((end_y + NOMINAL_Y[receiver.position]) / 2, 3, 97)
        length = metres(end_x - state.x, end_y - state.y)
        if length >= 5:
            break
    p_success = (0.80 if transition else 0.91) - 0.004 * max(0.0, length - 15) - (0.10 if pressured else 0)
    p_success -= 0.14 if end_x > 70 else 0
    if restart:
        p_success = 0.93
    success = rng.random() < p_success
    meta: dict[str, float | str] = {"pass_length_m": round(length, 1), "phase": state.phase, "pressured": "yes" if pressured else "no"}
    if restart:
        meta["restart"] = restart
    state.emit(
        "pass", state.team, state.holder, state.x, state.y,
        end=(end_x, end_y), outcome="success" if success else "fail", **meta,
    )
    if success:
        state.holder, state.x, state.y = receiver, end_x, end_y
        if transition and rng.random() < 0.25:
            state.phase = "build_up"
    else:
        interceptor = _pick_player(state, opponent, 100 - end_x)
        state.emit("interception", opponent, interceptor, 100 - end_x, 100 - end_y, outcome="success")
        _change_possession(state, opponent, 100 - end_x, 100 - end_y, interceptor)


def simulate(seed: int, home_id: str = "kby", away_id: str = "iva", minutes: int = 90) -> list[MatchEvent]:
    """Simulate a full match. `minutes` must be even (two equal halves)."""
    rng = random.Random(seed)
    clubs = {home_id: CLUBS[home_id], away_id: CLUBS[away_id]}
    scale = minutes / 90
    state = _State(
        rng=rng,
        match_id=f"{home_id}-{away_id}-{seed}",
        clubs=clubs,
        score={home_id: 0, away_id: 0},
        lineup={cid: list(c.starters) for cid, c in clubs.items()},
        bench={cid: list(c.subs) for cid, c in clubs.items()},
        subs_due={
            cid: sorted(rng.uniform(SUB_WINDOW_MIN[0] * 60 * scale, SUB_WINDOW_MIN[1] * 60 * scale) for _ in range(SUBS_PER_TEAM))
            for cid in clubs
        },
    )
    half_seconds = minutes * 60 // 2
    for half_index, kicker in enumerate((home_id, away_id)):
        state.t = half_index * half_seconds
        state.restart = None
        _kickoff(state, kicker)
        end = (half_index + 1) * half_seconds
        while state.t < end - 5:
            _step(state)
        state.t = max(state.t, end)
        state.emit(
            "half_time" if half_index == 0 else "full_time", home_id, None, 50, 50,
            home_goals=float(state.score[home_id]), away_goals=float(state.score[away_id]),
        )
    return state.events
