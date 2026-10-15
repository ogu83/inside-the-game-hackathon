from collections import Counter

import pytest

from app.simulator.engine import simulate
from app.simulator.league import CLUBS, PLAYERS
from app.simulator.models import MatchEvent


@pytest.fixture(scope="module")
def match() -> list[MatchEvent]:
    return simulate(7)


def test_same_seed_same_events() -> None:
    assert simulate(7) == simulate(7)


def test_different_seed_different_events() -> None:
    assert simulate(7) != simulate(8)


def test_events_validate_as_match_event(match: list[MatchEvent]) -> None:
    for event in match:
        MatchEvent.model_validate(event.model_dump())


def test_sequence_and_clock_are_monotonic(match: list[MatchEvent]) -> None:
    assert [e.seq for e in match] == list(range(1, len(match) + 1))
    assert all(a.t <= b.t for a, b in zip(match, match[1:]))


def test_match_structure(match: list[MatchEvent]) -> None:
    types = [e.type for e in match]
    assert types[0] == "kickoff"
    assert types[-1] == "full_time"
    assert types.count("half_time") == 1
    assert match[-1].t >= 90 * 60


def test_players_belong_to_acting_team(match: list[MatchEvent]) -> None:
    for event in match:
        if event.player_id:
            assert event.player_id in PLAYERS
            assert event.player_id.startswith(event.team_id + "-")


@pytest.mark.parametrize("seed", [1, 7, 42])
def test_stats_look_like_football(seed: int) -> None:
    events = simulate(seed)
    passes = [e for e in events if e.type == "pass"]
    completion = sum(e.outcome == "success" for e in passes) / len(passes)
    shots = Counter(e.team_id for e in events if e.type == "shot")
    share = Counter(e.team_id for e in passes)
    goals = sum(e.type == "goal" for e in events)
    assert 700 <= len(passes) <= 1300
    assert 0.72 <= completion <= 0.92
    assert 12 <= sum(shots.values()) <= 40
    assert 0 <= goals <= 9
    for club_id in ("kby", "iva"):
        assert 0.3 <= share[club_id] / len(passes) <= 0.7


def test_league_is_fictional_and_complete() -> None:
    for club in CLUBS.values():
        assert len(club.players) == 14
        assert [p.position for p in club.starters].count("GK") == 1
