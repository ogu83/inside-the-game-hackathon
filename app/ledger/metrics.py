"""Pure stat calculators over event lists. Percentages are 0-100, rounded to 1 decimal."""

from collections.abc import Iterable

from app.simulator.engine import PITCH_LENGTH_M
from app.simulator.models import MatchEvent


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
