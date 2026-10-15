"""Pure stat calculators over MatchEvent sequences. Every number an agent cites starts here."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from app.simulator.model import MatchEvent

SPRINT_KMH = 25.0
HARD_PASS = 0.5
PRESSURE_WINDOW_S = 3


def pass_difficulty(event: MatchEvent, pressure_nearby: int) -> float:
    """0..1, higher is harder."""
    length = float(event.meta.get("pass_length_m", 0.0))
    forward = max(0.0, (event.end_x or event.x) - event.x)
    score = 0.4 * min(length / 40, 1) + 0.3 * min(forward / 30, 1) + 0.3 * min(pressure_nearby / 3, 1)
    return round(score, 3)


def pressure_nearby(events: Sequence[MatchEvent], index: int, window_s: int = PRESSURE_WINDOW_S) -> int:
    """Opponent pressure events in the window_s seconds up to and including events[index]."""
    target = events[index]
    count = 0
    for ev in reversed(events[:index]):
        if target.clock_s - ev.clock_s > window_s:
            break
        if ev.type == "pressure" and ev.team_id != target.team_id:
            count += 1
    return count


def next_owner(owner: str | None, ev: MatchEvent) -> str | None:
    """Who has the ball after ev. Dead-ball spells (after a goal, at the breaks) belong to nobody."""
    if ev.type in ("kickoff", "possession_change"):
        return ev.team_id
    if ev.type == "pass" and ev.outcome == "success":
        return ev.team_id
    if ev.type in ("goal", "half_time", "full_time"):
        return None
    return owner


def possession_seconds(events: Sequence[MatchEvent]) -> dict[str, float]:
    seconds: dict[str, float] = defaultdict(float)
    owner: str | None = None
    prev: int | None = None
    for ev in events:
        if owner is not None and prev is not None:
            seconds[owner] += ev.clock_s - prev
        owner = next_owner(owner, ev)
        prev = ev.clock_s
    return dict(seconds)


def possession_pct(events: Sequence[MatchEvent]) -> dict[str, float]:
    seconds = possession_seconds(events)
    total = sum(seconds.values())
    if not total:
        return {team: 0.0 for team in seconds}
    return {team: round(100 * s / total, 1) for team, s in seconds.items()}


def pass_accuracy(events: Sequence[MatchEvent], team_id: str | None = None,
                  player_id: str | None = None) -> float | None:
    """Percent of completed passes, or None when there were no passes."""
    passes = [
        ev for ev in events
        if ev.type == "pass"
        and (team_id is None or ev.team_id == team_id)
        and (player_id is None or ev.player_id == player_id)
    ]
    if not passes:
        return None
    return round(100 * sum(ev.outcome == "success" for ev in passes) / len(passes), 1)


def max_shot_speed(events: Sequence[MatchEvent], team_id: str | None = None) -> float | None:
    speeds = [float(ev.meta["speed_kmh"]) for ev in events
              if ev.type == "shot" and (team_id is None or ev.team_id == team_id)]
    return max(speeds) if speeds else None


def player_speeds(ev: MatchEvent) -> float | None:
    """The speed this event records for its player: carry speed on passes, closing speed on pressures."""
    if ev.type in ("pass", "pressure") and "speed_kmh" in ev.meta:
        return float(ev.meta["speed_kmh"])
    return None


def distance_with_ball_m(events: Sequence[MatchEvent], player_id: str) -> float:
    return round(sum(float(ev.meta.get("carry_m", 0.0)) for ev in events
                     if ev.type == "pass" and ev.player_id == player_id), 1)


def top_speed_kmh(events: Sequence[MatchEvent], player_id: str) -> float | None:
    speeds = [s for ev in events if ev.player_id == player_id and (s := player_speeds(ev)) is not None]
    return max(speeds) if speeds else None


def sprint_count(events: Sequence[MatchEvent], player_id: str, threshold_kmh: float = SPRINT_KMH) -> int:
    return sum(1 for ev in events if ev.player_id == player_id
               and (s := player_speeds(ev)) is not None and s >= threshold_kmh)
