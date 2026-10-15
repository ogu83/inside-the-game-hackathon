import pytest

from app.ledger.metrics import (
    distance_with_ball_m,
    max_shot_speed,
    pass_accuracy,
    pass_difficulty,
    possession_pct,
    possession_seconds,
    pressure_nearby,
    sprint_count,
    top_speed_kmh,
)
from app.ledger.state import LedgerState
from app.simulator.emitter import simulate_match
from tests.ledger.helpers import Seq


def test_possession_counts_time_until_the_ball_changes_hands() -> None:
    s = Seq()
    s.add(0, "kickoff", "vel", "vel-09")
    s.pass_(10, "vel", "vel-09")
    s.add(30, "possession_change", "sal", "sal-04", reason="interception")
    s.pass_(40, "sal", "sal-04")
    s.add(45, "goal", "sal", "sal-04")
    s.add(100, "kickoff", "vel", "vel-09")
    s.pass_(110, "vel", "vel-09")
    assert possession_seconds(s.events) == {"vel": 40, "sal": 15}
    assert possession_pct(s.events) == {"vel": 72.7, "sal": 27.3}


def test_possession_pct_empty() -> None:
    assert possession_pct([]) == {}


def test_pass_accuracy_by_team_and_player() -> None:
    s = Seq()
    s.pass_(1, "vel", "vel-04")
    s.pass_(2, "vel", "vel-04", ok=False)
    s.pass_(3, "vel", "vel-08")
    s.pass_(4, "sal", "sal-04", ok=False)
    assert pass_accuracy(s.events) == 50.0
    assert pass_accuracy(s.events, team_id="vel") == 66.7
    assert pass_accuracy(s.events, player_id="vel-04") == 50.0
    assert pass_accuracy(s.events, team_id="emb") is None


def test_pass_difficulty_components() -> None:
    s = Seq()
    easy = s.pass_(1, "vel", "vel-04", x=40, end_x=38, length=5)
    hard = s.pass_(2, "vel", "vel-04", x=40, end_x=75, length=45)
    assert pass_difficulty(easy, 0) == 0.05
    assert pass_difficulty(hard, 0) == 0.7
    assert pass_difficulty(hard, 3) == 1.0
    assert pass_difficulty(hard, 9) == 1.0


def test_pressure_nearby_counts_only_recent_opponent_pressure() -> None:
    s = Seq()
    s.add(0, "pressure", "sal", "sal-09")
    s.add(5, "pressure", "sal", "sal-10")
    s.add(6, "pressure", "vel", "vel-08")
    s.add(7, "pressure", "sal", "sal-11")
    s.pass_(8, "vel", "vel-04")
    assert pressure_nearby(s.events, 4) == 2


def test_shot_speed() -> None:
    s = Seq()
    s.add(1, "shot", "vel", "vel-09", outcome="fail", xg=0.1, speed_kmh=88.0)
    s.add(2, "shot", "vel", "vel-10", outcome="success", xg=0.3, speed_kmh=101.5)
    s.add(3, "shot", "sal", "sal-09", outcome="fail", xg=0.05, speed_kmh=70.0)
    assert max_shot_speed(s.events) == 101.5
    assert max_shot_speed(s.events, "sal") == 70.0
    assert max_shot_speed(s.events, "emb") is None


def test_player_distance_speed_and_sprints() -> None:
    s = Seq()
    s.pass_(1, "vel", "vel-07", carry=6.5, speed=22.0)
    s.pass_(4, "vel", "vel-07", carry=12.0, speed=27.4)
    s.add(6, "pressure", "vel", "vel-07", speed_kmh=30.1)
    s.add(7, "shot", "vel", "vel-07", outcome="fail", xg=0.1, speed_kmh=95.0)
    assert distance_with_ball_m(s.events, "vel-07") == 18.5
    assert top_speed_kmh(s.events, "vel-07") == 30.1
    assert sprint_count(s.events, "vel-07") == 2
    assert sprint_count(s.events, "vel-07", threshold_kmh=21) == 3
    assert top_speed_kmh(s.events, "vel-01") is None


def test_state_evidence_on_hand_built_sequence() -> None:
    s = Seq()
    s.add(0, "kickoff", "vel", "vel-09")
    s.add(2, "pressure", "sal", "sal-09", x=60, speed_kmh=26.0)
    s.pass_(3, "vel", "vel-09", x=40, end_x=70, length=40, carry=4.0, speed=24.0, receiver="vel-10")
    s.add(9, "shot", "vel", "vel-10", x=88, outcome="success", xg=0.4, speed_kmh=99.0)
    s.add(10, "goal", "vel", "vel-10", xg=0.4)
    s.add(60, "kickoff", "sal", "sal-09")
    s.pass_(70, "sal", "sal-09", ok=False)
    state = LedgerState.from_events(s.events)
    ev = state.evidence()
    assert ev["match.score_home"] == 1.0 and ev["match.score_away"] == 0.0
    assert ev["team.vel.possession_pct"] == 50.0
    assert ev["team.vel.pass_accuracy"] == 100.0
    assert ev["team.sal.pass_accuracy"] == 0.0
    assert ev["team.vel.avg_pass_difficulty"] == 0.8
    assert state.difficulty[2] == 0.8
    assert ev["player.vel-09.hard_passes_completed"] == 1.0
    assert ev["player.sal-09.sprints"] == 1.0
    assert ev["player.vel-10.goals"] == 1.0
    assert ev["team.vel.max_shot_speed_kmh"] == 99.0
    assert state.value("team.vel.xg") == 0.4
    with pytest.raises(KeyError):
        state.value("player.vel-99.goals")


def test_state_rejects_out_of_order_events() -> None:
    s = Seq()
    a = s.add(0, "kickoff", "vel", "vel-09")
    state = LedgerState.from_events(s.events)
    with pytest.raises(ValueError):
        state.apply(a)


def test_incremental_state_matches_batch_calculators() -> None:
    events = simulate_match(7)
    state = LedgerState.from_events(events)
    ev = state.evidence()
    batch = possession_pct(events)
    home, away = events[0].match_id.split("-")[1:]
    for team in (home, away):
        assert ev[f"team.{team}.possession_pct"] == pytest.approx(batch[team], abs=0.1)
        assert ev[f"team.{team}.pass_accuracy"] == pass_accuracy(events, team_id=team)
        assert ev[f"team.{team}.max_shot_speed_kmh"] == max_shot_speed(events, team)
    assert ev["team." + home + ".possession_pct"] + ev["team." + away + ".possession_pct"] == pytest.approx(100, abs=0.2)
    for player_id in ("cor-09", "vel-08"):
        assert ev[f"player.{player_id}.distance_with_ball_m"] == distance_with_ball_m(events, player_id)
        assert ev[f"player.{player_id}.top_speed_kmh"] == top_speed_kmh(events, player_id)
        assert ev[f"player.{player_id}.sprints"] == sprint_count(events, player_id)
    for i, e in enumerate(events):
        if e.type == "pass":
            assert state.difficulty[e.seq] == pass_difficulty(e, pressure_nearby(events, i))
    assert ev["match.score_home"] == events[-1].meta["score_home"]
