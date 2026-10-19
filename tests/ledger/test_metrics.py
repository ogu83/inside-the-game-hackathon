from app.ledger.metrics import (
    avg_pass_difficulty, in_window, max_shot_speed_kmh, pass_accuracy_pct, pass_difficulty, player_distance_m,
    player_stats, possession_pct, pressure_count, progress_m, regains_after_pressure, shot_count, team_stats, xg_total,
)
from app.simulator.engine import simulate
from app.simulator.models import MatchEvent
from tests.ledger.helpers import EventFactory


def test_possession_is_share_of_pass_attempts() -> None:
    f = EventFactory()
    events = f.passes("aaa", 3) + f.passes("bbb", 1)
    assert possession_pct(events, "aaa") == 75.0
    assert possession_pct(events, "bbb") == 25.0


def test_possession_without_passes_is_even() -> None:
    assert possession_pct([], "aaa") == 50.0


def test_pass_accuracy_counts_only_that_team() -> None:
    f = EventFactory()
    events = f.passes("aaa", 4, fail_last=True) + f.passes("bbb", 2, fail_last=True)
    assert pass_accuracy_pct(events, "aaa") == 75.0
    assert pass_accuracy_pct(events, "bbb") == 50.0
    assert pass_accuracy_pct(events, "ccc") == 0.0


def test_in_window_is_half_open() -> None:
    f = EventFactory()
    events = [f.make("pass", "aaa", dt=10) for _ in range(5)]  # t = 10, 20, 30, 40, 50
    assert [e.t for e in in_window(events, 50, 20)] == [40, 50]


def test_progress_is_in_metres() -> None:
    assert progress_m(20, 40) == 21.0
    assert progress_m(60, 50) == -10.5


def pass_event(length: float, x: float, end_x: float, pressured: str = "no") -> MatchEvent:
    return MatchEvent(match_id="t", seq=1, minute=0, second=0, type="pass", team_id="aaa", player_id="aaa-01", x=x, y=50,
                      end_x=end_x, end_y=50, outcome="success", meta={"pass_length_m": length, "pressured": pressured})


def test_pass_difficulty_grows_with_length_forwardness_and_pressure() -> None:
    assert pass_difficulty(pass_event(0, 50, 50)) == 0.0
    assert pass_difficulty(pass_event(40, 20, 50)) == 0.7      # max length, max forward, no pressure
    assert pass_difficulty(pass_event(40, 20, 50, "yes")) == 0.8
    assert pass_difficulty(pass_event(20, 50, 40)) == 0.2      # backwards pass: only length counts
    assert pass_difficulty(pass_event(40, 20, 50), pressure_nearby=3) == 1.0


def test_shot_metrics_count_only_that_team() -> None:
    f = EventFactory()
    events = [f.make("shot", "aaa", x=85, outcome="fail"), f.make("shot", "aaa", x=90, outcome="success"), f.make("shot", "bbb", x=80, outcome="fail")]
    events[0].meta.update(xg=0.1, speed_kmh=90.0)
    events[1].meta.update(xg=0.35, speed_kmh=101.5)
    events[2].meta.update(xg=0.05, speed_kmh=110.0)
    assert shot_count(events, "aaa") == 2 and shot_count(events, "ccc") == 0
    assert xg_total(events, "aaa") == 0.45
    assert max_shot_speed_kmh(events, "aaa") == 101.5 and max_shot_speed_kmh(events, "ccc") == 0.0


def test_regains_after_pressure_need_a_pressure_shortly_before() -> None:
    f = EventFactory()
    events = [
        f.make("pressure", "bbb", dt=3), f.make("tackle", "bbb", dt=0, outcome="success"),       # regain at +0 s
        f.make("pass", "aaa", dt=20), f.make("interception", "bbb", dt=3, outcome="success"),  # no pressure within 6 s
        f.make("pressure", "bbb", dt=5), f.make("pass", "aaa", dt=4), f.make("interception", "bbb", dt=1, outcome="success"),  # +5 s
    ]
    assert pressure_count(events, "bbb") == 2
    assert regains_after_pressure(events, "bbb") == 2
    assert regains_after_pressure(events, "aaa") == 0


def test_player_distance_is_the_path_between_their_events() -> None:
    f = EventFactory()
    events = [f.make("pass", "aaa", player=1, x=20), f.make("pass", "aaa", player=2, x=50), f.make("pass", "aaa", player=1, x=40)]
    assert player_distance_m(events, "aaa-01") == 21.0  # 20 pitch units along 105 m
    assert player_distance_m(events, "aaa-09") == 0.0


def test_player_stats_on_a_hand_built_sequence() -> None:
    f = EventFactory()
    events = f.passes("aaa", 4, start_x=20, step=10, players=1, fail_last=True)
    events += [f.make("shot", "aaa", player=1, x=88, outcome="success"), f.make("goal", "aaa", player=1, x=88), f.make("pressure", "aaa", player=1, x=70)]
    stats = player_stats(events, "aaa-01")
    assert stats["passes"] == 4.0 and stats["passes_completed"] == 3.0 and stats["pass_accuracy_pct"] == 75.0
    assert stats["progress_m"] == 31.5 and stats["shots"] == 1.0 and stats["goals"] == 1.0 and stats["pressures"] == 1.0
    assert set(stats) == {"passes", "passes_completed", "pass_accuracy_pct", "progress_m", "shots", "goals", "pressures", "tackles", "interceptions", "distance_m"}


def test_team_stats_are_floats_from_a_seeded_match() -> None:
    events = simulate(7)
    stats = team_stats(events, "iva")
    assert all(isinstance(v, float) for v in stats.values())
    assert stats["passes"] > 300 and 0 < stats["avg_pass_difficulty"] < 1 and stats["pressures"] > stats["regains_after_pressure"] > 0
    assert team_stats(events, "kby")["possession_pct"] + stats["possession_pct"] == 100.0
    assert avg_pass_difficulty([], "iva") == 0.0
