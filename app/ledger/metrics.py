"""Pure stat calculators over event lists. Percentages are 0-100, rounded to 1 decimal.

Every number an agent may say comes from here or from a detector; nothing is computed in a prompt.
Possession is pass-attempt share (the common broadcast method). Player distance is a proxy: metres
between the positions of a player's consecutive events (event data has no tracking).
"""

from collections.abc import Iterable

from app.simulator.engine import PITCH_LENGTH_M, metres
from app.simulator.models import MatchEvent

REGAIN_WINDOW_S = 6


def in_window(events: Iterable[MatchEvent], end_t: int, seconds: int) -> list[MatchEvent]:
    return [e for e in events if end_t - seconds < e.t <= end_t]


def possession_pct(events: Iterable[MatchEvent], team_id: str) -> float:
    """Share of all pass attempts made by `team_id`; 50.0 when there are no passes."""
    passes = [e for e in events if e.type == "pass"]
    if not passes:
        return 50.0
    return round(100 * sum(e.team_id == team_id for e in passes) / len(passes), 1)


def pass_accuracy_pct(events: Iterable[MatchEvent], team_id: str) -> float:
    passes = [e for e in events if e.type == "pass" and e.team_id == team_id]
    if not passes:
        return 0.0
    return round(100 * sum(e.outcome == "success" for e in passes) / len(passes), 1)


def progress_m(start_x: float, end_x: float) -> float:
    """Forward distance in metres along the pitch, in the attacking team's frame."""
    return round((end_x - start_x) * PITCH_LENGTH_M / 100, 1)


def pass_difficulty(event: MatchEvent, pressure_nearby: int | None = None) -> float:
    """0..1, higher is harder: long, forward and under pressure."""
    length = float(event.meta.get("pass_length_m", 0.0))
    forward = max(0.0, (event.end_x if event.end_x is not None else event.x) - event.x)
    if pressure_nearby is None:
        pressure_nearby = 1 if event.meta.get("pressured") == "yes" else 0
    score = 0.4 * min(length / 40, 1) + 0.3 * min(forward / 30, 1) + 0.3 * min(pressure_nearby / 3, 1)
    return round(score, 3)


def avg_pass_difficulty(events: Iterable[MatchEvent], team_id: str) -> float:
    passes = [e for e in events if e.type == "pass" and e.team_id == team_id]
    if not passes:
        return 0.0
    return round(sum(pass_difficulty(e) for e in passes) / len(passes), 3)


def shot_count(events: Iterable[MatchEvent], team_id: str) -> int:
    return sum(e.type == "shot" and e.team_id == team_id for e in events)


def xg_total(events: Iterable[MatchEvent], team_id: str) -> float:
    return round(sum(float(e.meta.get("xg", 0.0)) for e in events if e.type == "shot" and e.team_id == team_id), 2)


def max_shot_speed_kmh(events: Iterable[MatchEvent], team_id: str) -> float:
    speeds = [float(e.meta.get("speed_kmh", 0.0)) for e in events if e.type == "shot" and e.team_id == team_id]
    return max(speeds, default=0.0)


def pressure_count(events: Iterable[MatchEvent], team_id: str) -> int:
    return sum(e.type == "pressure" and e.team_id == team_id for e in events)


def regains_after_pressure(events: Iterable[MatchEvent], team_id: str, within_s: int = REGAIN_WINDOW_S) -> int:
    """Ball wins (tackle or interception) by `team_id` within `within_s` seconds of one of its pressures."""
    items = list(events)
    press_times = [e.t for e in items if e.type == "pressure" and e.team_id == team_id]
    wins = [e for e in items if e.type in ("tackle", "interception") and e.team_id == team_id]
    return sum(any(0 <= w.t - t <= within_s for t in press_times) for w in wins)


def player_distance_m(events: Iterable[MatchEvent], player_id: str) -> float:
    """Proxy for distance covered: metres between the positions of the player's consecutive events."""
    points = [(e.x, e.y) for e in events if e.player_id == player_id]
    return round(sum(metres(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])), 1)


def player_stats(events: Iterable[MatchEvent], player_id: str) -> dict[str, float]:
    items = [e for e in events if e.player_id == player_id]
    passes = [e for e in items if e.type == "pass"]
    completed = [e for e in passes if e.outcome == "success"]
    return {
        "passes": float(len(passes)),
        "passes_completed": float(len(completed)),
        "pass_accuracy_pct": round(100 * len(completed) / len(passes), 1) if passes else 0.0,
        "progress_m": round(sum(progress_m(e.x, e.end_x if e.end_x is not None else e.x) for e in completed), 1),
        "shots": float(sum(e.type == "shot" for e in items)),
        "goals": float(sum(e.type == "goal" for e in items)),
        "pressures": float(sum(e.type == "pressure" for e in items)),
        "tackles": float(sum(e.type == "tackle" for e in items)),
        "interceptions": float(sum(e.type == "interception" for e in items)),
        "distance_m": player_distance_m(items, player_id),
    }


def team_stats(events: Iterable[MatchEvent], team_id: str) -> dict[str, float]:
    items = list(events)
    return {
        "possession_pct": possession_pct(items, team_id),
        "pass_accuracy_pct": pass_accuracy_pct(items, team_id),
        "passes": float(sum(e.type == "pass" and e.team_id == team_id for e in items)),
        "avg_pass_difficulty": avg_pass_difficulty(items, team_id),
        "shots": float(shot_count(items, team_id)),
        "xg": xg_total(items, team_id),
        "goals": float(sum(e.type == "goal" and e.team_id == team_id for e in items)),
        "max_shot_speed_kmh": max_shot_speed_kmh(items, team_id),
        "pressures": float(pressure_count(items, team_id)),
        "regains_after_pressure": float(regains_after_pressure(items, team_id)),
    }
