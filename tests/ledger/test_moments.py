from app.ledger.models import CandidateMoment
from app.ledger.moments import PassStreakDetector, PressingTrapDetector
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
    assert "team_possession_pct_window" not in moment.evidence, "possession is not citable in the first 3 minutes"


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
    f.t = 200  # past the 3-minute mark, so possession is citable
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
    assert 25 <= len(moments) <= 45
    assert {m.kind for m in moments} == {"pass_streak", "pressing_trap"}
    assert len({m.moment_id for m in moments}) == len(moments)
    assert [m.window[1] for m in moments] == sorted(m.window[1] for m in moments)
    for kind in ("pass_streak", "pressing_trap"):
        same = [m for m in moments if m.kind == kind]
        assert all(a.window[1] < b.window[0] for a, b in zip(same, same[1:])), f"{kind} windows overlap"
    for m in moments:
        assert all(isinstance(v, float) for v in m.evidence.values())
        assert m.top_player_id is not None and m.top_player_id.startswith(m.team_id + "-")


def test_ledger_runs_both_detectors() -> None:
    assert [type(d) for d in Ledger().detectors] == [PassStreakDetector, PressingTrapDetector]


def press(f: EventFactory, team: str, *, dt: int = 5, x: float = 70, player: int = 6):
    return f.make("pressure", team, dt=dt, x=x, player=player)


def test_pressing_trap_closes_on_a_high_regain_after_repeated_pressure() -> None:
    f = EventFactory()
    f.t = 600
    events = [press(f, "bbb", player=6), f.make("pass", "aaa", x=25, end_x=30), press(f, "bbb", player=8, x=72),
              f.make("tackle", "bbb", dt=2, x=73, player=8, outcome="success")]
    moments = [m for m in feed(events) if m.kind == "pressing_trap"]
    [moment] = moments
    assert moment.team_id == "bbb" and moment.window == (1, 4) and moment.top_player_id == "bbb-08"
    e = moment.evidence
    assert e["pressing_trap_pressures"] == 2.0 and e["pressing_trap_players"] == 2.0 and e["top_player_pressures"] == 1.0
    assert e["pressing_trap_window_s"] == 10.0
    assert e["pressing_trap_regain_distance_to_goal_m"] == round(27 * 1.05, 1)  # 27 pitch units from goal along 105 m
    assert e["team_pressures_last_10min"] == 2.0 and e["team_regains_last_10min"] == 1.0
    assert e["window_minutes"] == 10.0 and e["minute"] == 10.0


def test_pressing_trap_needs_pressures_inside_the_window_and_a_high_regain() -> None:
    f = EventFactory()
    stale = [press(f, "bbb"), press(f, "bbb", dt=40), f.make("interception", "bbb", dt=3, x=70, outcome="success")]
    assert [m for m in feed(stale) if m.kind == "pressing_trap"] == []
    f = EventFactory()
    low = [press(f, "bbb"), press(f, "bbb"), f.make("interception", "bbb", dt=3, x=30, outcome="success")]
    assert [m for m in feed(low) if m.kind == "pressing_trap"] == []
    f = EventFactory()
    deep_pressure = [press(f, "bbb", x=30), press(f, "bbb", x=35), f.make("tackle", "bbb", dt=3, x=70, outcome="success")]
    assert [m for m in feed(deep_pressure) if m.kind == "pressing_trap"] == []


def test_pressing_trap_resets_after_it_fires() -> None:
    f = EventFactory()
    events = [press(f, "bbb"), press(f, "bbb"), f.make("tackle", "bbb", dt=2, x=70, outcome="success"),
              f.make("interception", "bbb", dt=4, x=72, outcome="success")]
    assert len([m for m in feed(events) if m.kind == "pressing_trap"]) == 1


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
        if m.kind == "pass_streak":
            assert 1 <= m.evidence["top_player_passes"] <= m.evidence["pass_streak_passes"]
        else:
            assert 0 <= m.evidence["top_player_pressures"] <= m.evidence["pressing_trap_pressures"]
