from collections import Counter

import pytest

from app.ledger.state import detect_all
from app.simulator.engine import DEMO_SEED, SUBS_PER_TEAM, simulate
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
    assert 12 <= sum(shots.values()) <= 48
    assert 0 <= goals <= 9
    for club_id in ("kby", "iva"):
        assert 0.3 <= share[club_id] / len(passes) <= 0.7


def test_league_is_fictional_and_complete() -> None:
    for club in CLUBS.values():
        assert len(club.players) == 14
        assert [p.position for p in club.starters].count("GK") == 1
    assert CLUBS["iva"].pressing > CLUBS["kby"].pressing


def test_scoreline_meta_matches_the_goals(match: list[MatchEvent]) -> None:
    goals = Counter(e.team_id for e in match if e.type == "goal")
    final = match[-1]
    assert final.meta["home_goals"] == float(goals["kby"]) and final.meta["away_goals"] == float(goals["iva"])
    half = next(e for e in match if e.type == "half_time")
    first_half_goals = Counter(e.team_id for e in match[: match.index(half)] if e.type == "goal")
    assert half.meta["home_goals"] == float(first_half_goals["kby"])


def test_end_coordinates_stay_on_the_pitch(match: list[MatchEvent]) -> None:
    for event in match:
        if event.end_x is not None:
            assert 0 <= event.end_x <= 100 and 0 <= (event.end_y or 0) <= 100


def test_each_club_makes_like_for_like_substitutions(match: list[MatchEvent]) -> None:
    subs = [e for e in match if e.type == "substitution"]
    assert Counter(e.team_id for e in subs) == {"kby": SUBS_PER_TEAM, "iva": SUBS_PER_TEAM}
    for sub in subs:
        on, off = PLAYERS[str(sub.meta["player_on"])], PLAYERS[str(sub.meta["player_off"])]
        assert sub.player_id == on.id and on in CLUBS[sub.team_id].subs and off in CLUBS[sub.team_id].starters
        assert on.position != "GK" and off.position != "GK"
        assert 55 <= sub.minute <= 85
        later = match[match.index(sub) + 1 :]
        assert all(e.player_id != off.id for e in later), "a substituted player acted again"
        assert any(e.player_id == on.id for e in later), "the substitute never touched the ball"


def test_every_foul_is_followed_by_a_free_kick(match: list[MatchEvent]) -> None:
    fouls = [i for i, e in enumerate(match) if e.type == "foul"]
    assert fouls
    for i in fouls:
        following = [e for e in match[i + 1 : i + 4] if e.type == "pass"]
        assert following and following[0].meta.get("restart") == "free_kick"
        assert following[0].team_id != match[i].team_id
        assert following[0].t - match[i].t >= 8


@pytest.mark.parametrize("seed", [1, 7, 42])
def test_pressing_trait_shows_in_the_event_counts(seed: int) -> None:
    pressures = Counter(e.team_id for e in simulate(seed) if e.type == "pressure")
    assert pressures["iva"] > pressures["kby"]


def test_demo_seed_has_three_moments_in_the_first_five_minutes() -> None:
    early = [m for m in detect_all(simulate(DEMO_SEED)) if m.minute <= 4]
    assert len(early) >= 3
    assert {m.team_id for m in early} == {"kby", "iva"}
    assert any(m.evidence["pass_streak_ended_in_shot"] == 1.0 for m in early)
