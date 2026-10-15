from app.ledger.models import CandidateMoment
from app.ledger.state import Ledger, detect_all
from app.simulator.engine import simulate
from tests.ledger.helpers import EventFactory


def feed(events) -> list[CandidateMoment]:
    ledger = Ledger()
    return [m for e in events for m in ledger.ingest(e)]


def test_streak_closes_when_the_ball_is_lost() -> None:
    f = EventFactory()
    events = f.passes("aaa", 10, start_x=20, step=5, players=4)
    events.append(f.make("interception", "bbb", x=30))
    [moment] = feed(events)
    assert moment.kind == "pass_streak"
    assert moment.team_id == "aaa"
    assert moment.window == (1, 10)
    assert moment.evidence["pass_streak_passes"] == 10.0
    assert moment.evidence["pass_streak_duration_s"] == 27.0
    assert moment.evidence["pass_streak_players"] == 4.0
    assert moment.top_player_id == "aaa-01" and moment.evidence["top_player_passes"] == 3.0
    assert moment.evidence["pass_streak_progress_m"] == 52.5
    assert moment.evidence["pass_streak_ended_in_shot"] == 0.0
    assert moment.evidence["team_possession_pct_window"] == 100.0


def test_failed_pass_ends_the_streak() -> None:
    f = EventFactory()
    events = f.passes("aaa", 11, fail_last=True)
    [moment] = feed(events)
    assert moment.evidence["pass_streak_passes"] == 10.0


def test_short_streak_is_not_a_moment() -> None:
    f = EventFactory()
    events = f.passes("aaa", 9) + [f.make("interception", "bbb")]
    assert feed(events) == []


def test_pressure_and_fouls_do_not_break_a_streak() -> None:
    f = EventFactory()
    events = f.passes("aaa", 5) + [f.make("pressure", "bbb"), f.make("foul", "bbb")] + f.passes("aaa", 5)
    events.append(f.make("tackle", "bbb", outcome="success"))
    [moment] = feed(events)
    assert moment.evidence["pass_streak_passes"] == 10.0


def test_streak_ending_in_a_shot_is_flagged() -> None:
    f = EventFactory()
    events = f.passes("aaa", 10) + [f.make("shot", "aaa", x=85, outcome="fail")]
    [moment] = feed(events)
    assert moment.evidence["pass_streak_ended_in_shot"] == 1.0


def test_other_team_passing_starts_a_new_streak() -> None:
    f = EventFactory()
    events = f.passes("aaa", 6) + f.passes("bbb", 10) + [f.make("interception", "aaa")]
    [moment] = feed(events)
    assert moment.team_id == "bbb"
    assert moment.evidence["team_possession_pct_window"] == 62.5


def test_window_shrinks_to_elapsed_time_early_in_the_match() -> None:
    f = EventFactory()
    events = f.passes("aaa", 10) + [f.make("interception", "bbb")]
    [moment] = feed(events)
    assert moment.evidence["window_minutes"] == 0.5


def test_seeded_match_yields_a_usable_number_of_moments() -> None:
    moments = detect_all(simulate(7))
    assert 10 <= len(moments) <= 40
    assert len({m.moment_id for m in moments}) == len(moments)
    for m in moments:
        assert all(isinstance(v, float) for v in m.evidence.values())


def test_top_player_is_the_most_frequent_passer_in_the_streak() -> None:
    f = EventFactory()
    events = [f.make("pass", "aaa", player=p, x=20, end_x=25, outcome="success") for p in (2, 3, 3, 1, 3, 2, 1, 3, 2, 1)]
    events.append(f.make("interception", "bbb"))
    [moment] = feed(events)
    assert moment.top_player_id == "aaa-03"
    assert moment.evidence["top_player_passes"] == 4.0
    assert moment.evidence["pass_streak_players"] == 3.0


def test_top_player_tie_goes_to_the_first_passer() -> None:
    f = EventFactory()
    events = [f.make("pass", "aaa", player=p, x=20, end_x=25, outcome="success") for p in (2, 1, 2, 1, 2, 1, 2, 1, 2, 1)]
    events.append(f.make("tackle", "bbb", outcome="success"))
    [moment] = feed(events)
    assert moment.top_player_id == "aaa-02" and moment.evidence["top_player_passes"] == 5.0


def test_seeded_moments_name_a_player_of_the_right_team() -> None:
    for m in detect_all(simulate(7)):
        assert m.top_player_id is not None and m.top_player_id.startswith(m.team_id + "-")
        assert 1 <= m.evidence["top_player_passes"] <= m.evidence["pass_streak_passes"]
