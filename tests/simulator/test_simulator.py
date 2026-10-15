from collections import Counter

import pytest

from app.simulator.emitter import expected_goals, simulate_match, stream
from app.simulator.league import FIXTURES, LEAGUE, fixture_for_seed, player_by_id
from app.simulator.model import MATCH_TEAM_ID, MatchEvent


@pytest.fixture(scope="module")
def match7() -> list[MatchEvent]:
    return simulate_match(7)


def test_league_has_four_clubs_with_18_player_squads() -> None:
    assert len(LEAGUE) == 4
    for club in LEAGUE.values():
        assert len(club.players) == 18
        assert len(club.starters) == 11
        assert sum(p.position == "GK" for p in club.starters) == 1
        assert len({p.shirt for p in club.players}) == 18


def test_player_names_and_ids_are_unique() -> None:
    players = [p for c in LEAGUE.values() for p in c.players]
    assert len({p.player_id for p in players}) == 72
    assert len({p.name for p in players}) == 72
    assert player_by_id("vel-09").club_id == "vel"


def test_fixtures_cover_every_pairing() -> None:
    assert len(FIXTURES) == 6
    assert {frozenset(fixture_for_seed(s)) for s in range(6)} == {frozenset(f) for f in FIXTURES}


def test_same_seed_gives_identical_events(match7: list[MatchEvent]) -> None:
    again = simulate_match(7)
    assert [e.model_dump() for e in again] == [e.model_dump() for e in match7]


def test_different_seeds_differ(match7: list[MatchEvent]) -> None:
    other = simulate_match(13, *fixture_for_seed(7))
    assert [e.model_dump() for e in other] != [e.model_dump() for e in match7]


def test_events_validate_and_are_ordered(match7: list[MatchEvent]) -> None:
    for ev in match7:
        MatchEvent.model_validate(ev.model_dump())
    assert [e.seq for e in match7] == list(range(len(match7)))
    clocks = [e.clock_s for e in match7]
    assert clocks == sorted(clocks)
    assert len({e.match_id for e in match7}) == 1


def test_match_structure(match7: list[MatchEvent]) -> None:
    assert match7[0].type == "kickoff"
    assert match7[-1].type == "full_time"
    assert match7[-1].minute >= 90
    counts = Counter(e.type for e in match7)
    assert counts["half_time"] == 1 and counts["full_time"] == 1
    assert counts["substitution"] == 6
    assert 600 <= counts["pass"] <= 1400
    assert 10 <= counts["shot"] <= 60
    goals = counts["goal"]
    assert match7[-1].meta["score_home"] + match7[-1].meta["score_away"] == goals


def test_team_and_player_ids_belong_to_the_fixture(match7: list[MatchEvent]) -> None:
    home, away = match7[0].match_id.split("-")[1:]
    for ev in match7:
        assert ev.team_id in (home, away, MATCH_TEAM_ID)
        if ev.player_id:
            assert player_by_id(ev.player_id).club_id == ev.team_id


def test_successful_pass_names_a_teammate_receiver(match7: list[MatchEvent]) -> None:
    for ev in (e for e in match7 if e.type == "pass" and e.outcome == "success"):
        receiver = str(ev.meta["receiver_id"])
        assert player_by_id(receiver).club_id == ev.team_id
        assert receiver != ev.player_id
        assert ev.meta["pass_length_m"] >= 0


def test_turnovers_are_followed_by_possession_change(match7: list[MatchEvent]) -> None:
    for i, ev in enumerate(match7):
        if ev.type in ("interception", "tackle"):
            nxt = match7[i + 1]
            assert nxt.type == "possession_change" and nxt.team_id == ev.team_id


def test_plausible_scorelines_across_seeds() -> None:
    goals = [sum(e.type == "goal" for e in simulate_match(s)) for s in range(12)]
    assert max(goals) <= 10
    assert 1.5 <= sum(goals) / len(goals) <= 5


def test_expected_goals_falls_with_distance() -> None:
    assert expected_goals(95, 50) > expected_goals(85, 50) > expected_goals(70, 50)
    assert expected_goals(90, 50) > expected_goals(90, 10)


def test_stream_paces_by_match_clock(match7: list[MatchEvent]) -> None:
    slept: list[float] = []
    first_minute = [e for e in match7 if e.minute < 1]
    out = list(stream(first_minute, speed=20, sleep=slept.append))
    assert out == first_minute
    assert sum(slept) == pytest.approx((first_minute[-1].clock_s - first_minute[0].clock_s) / 20)
    slept.clear()
    list(stream(first_minute, speed=0, sleep=slept.append))
    assert slept == []
