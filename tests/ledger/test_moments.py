from collections import Counter

import pytest

from app.ledger.moments import CandidateMoment, MomentDetector, detect_moments
from app.ledger.state import LedgerState
from app.simulator.emitter import simulate_match
from tests.ledger.helpers import Seq


def kinds(moments: list[CandidateMoment]) -> list[str]:
    return [m.kind for m in moments]


def test_pressing_trap_needs_pressures_and_a_high_regain() -> None:
    s = Seq()
    s.add(0, "kickoff", "vel", "vel-09")
    s.add(3, "pressure", "sal", "sal-09", x=72, speed_kmh=27.0)
    s.add(5, "pressure", "sal", "sal-10", x=74, speed_kmh=29.5)
    s.add(6, "interception", "sal", "sal-10", x=75, outcome="success")
    moments = [m for m in detect_moments(s.events) if m.kind == "pressing_trap"]
    assert len(moments) == 1
    ev = moments[0].evidence
    assert ev["moment.team.sal.pressures_in_sequence"] == 2
    assert ev["moment.team.sal.seconds_to_regain"] == 3
    assert ev["moment.team.sal.top_closing_speed_kmh"] == 29.5
    assert ev["moment.team.sal.pressers"] == 2
    assert ev["moment.team.sal.regain_distance_to_goal_m"] == 26.2
    assert moments[0].window == (1, 3)


@pytest.mark.parametrize("pressures, regain_x", [(1, 75), (2, 40)])
def test_no_pressing_trap_without_enough_pressure_or_deep_regain(pressures: int, regain_x: float) -> None:
    s = Seq()
    s.add(0, "kickoff", "vel", "vel-09")
    for i in range(pressures):
        s.add(3 + i, "pressure", "sal", "sal-09", x=regain_x, speed_kmh=25.0)
    s.add(6, "tackle", "sal", "sal-09", x=regain_x, outcome="success")
    assert "pressing_trap" not in kinds(detect_moments(s.events))


def _streak(n: int) -> Seq:
    s = Seq()
    s.add(0, "kickoff", "vel", "vel-09")
    for i in range(n):
        s.pass_(1 + 3 * i, "vel", f"vel-0{2 + i % 7}", x=30 + i, end_x=32 + i, receiver=f"vel-0{2 + (i + 1) % 7}")
        s.add(2 + 3 * i, "pressure", "sal", "sal-09", speed_kmh=20.0)
    s.add(3 * n + 2, "possession_change", "sal", "sal-04", reason="interception")
    return s


def test_pass_streak_detected_at_eleven_passes() -> None:
    moments = [m for m in detect_moments(_streak(11).events) if m.kind == "pass_streak"]
    assert len(moments) == 1
    ev = moments[0].evidence
    assert ev["moment.team.vel.consecutive_passes"] == 11
    assert ev["moment.team.vel.players_involved"] == 7
    assert ev["moment.team.vel.ended_in_shot"] == 0
    assert ev["moment.team.vel.duration_s"] == 34


def test_short_streak_is_not_a_moment() -> None:
    assert "pass_streak" not in kinds(detect_moments(_streak(10).events))


def test_goal_moment_cites_the_shot() -> None:
    s = Seq()
    s.add(0, "kickoff", "vel", "vel-09")
    s.add(20, "shot", "vel", "vel-09", x=86, outcome="success", xg=0.31, speed_kmh=102.0, build_up_passes=4.0)
    s.add(21, "goal", "vel", "vel-09", xg=0.31)
    (goal,) = [m for m in detect_moments(s.events) if m.kind == "goal"]
    assert goal.window == (1, 2)
    assert goal.evidence["moment.player.vel-09.shot_xg"] == 0.31
    assert goal.evidence["moment.player.vel-09.distance_to_goal_m"] == 14.7
    assert goal.evidence["player.vel-09.goals"] == 1
    assert goal.evidence["match.score_home"] == 1


def test_player_milestone_fires_once_per_threshold() -> None:
    s = Seq()
    s.add(0, "kickoff", "vel", "vel-09")
    for i in range(6):
        s.add(10 + i, "tackle", "sal", "sal-04", x=30, outcome="success")
    moments = [m for m in detect_moments(s.events) if m.kind == "player_milestone"]
    assert len(moments) == 1
    assert moments[0].evidence["player.sal-04.tackles"] == 4
    assert moments[0].evidence["moment.player.sal-04.tackles_threshold"] == 4


def test_momentum_shift_when_threat_swings() -> None:
    s = Seq()
    s.add(0, "kickoff", "vel", "vel-09")
    for minute in range(22):
        attacker = "vel" if minute < 10 else "sal"
        t = minute * 60 + 5
        s.pass_(t, attacker, f"{attacker}-08", x=60, end_x=80, receiver=f"{attacker}-09")
        s.add(t + 10, "shot", attacker, f"{attacker}-09", x=85, outcome="fail", xg=0.1, speed_kmh=80.0)
        s.add(t + 20, "possession_change", "vel" if attacker == "sal" else "sal", None, reason="goal_kick")
    moments = [m for m in detect_moments(s.events) if m.kind == "momentum_shift"]
    assert len(moments) == 1
    ev = moments[0].evidence
    assert ev["match.minute"] == 20
    assert ev["moment.team.sal.threat_share_now_pct"] == 100
    assert ev["moment.team.sal.threat_share_before_pct"] == 0
    assert ev["moment.team.sal.shots_in_window"] == 10


def test_lull_after_six_minutes_without_a_shot() -> None:
    s = Seq()
    s.add(0, "kickoff", "vel", "vel-09")
    for minute in range(9):
        s.pass_(minute * 60 + 30, "vel", "vel-04", receiver="vel-05")
        s.pass_(minute * 60 + 40, "vel", "vel-05", ok=False)
        s.add(minute * 60 + 41, "possession_change", "sal", "sal-04", reason="out_of_play")
        s.add(minute * 60 + 50, "foul", "vel", "vel-06")
    moments = [m for m in detect_moments(s.events) if m.kind == "lull"]
    assert len(moments) == 1
    ev = moments[0].evidence
    assert ev["moment.match.minutes_without_shot"] == 6
    assert ev["moment.team.vel.pass_accuracy_in_window"] == pytest.approx(100 * 7 / 13, abs=0.1)
    assert ev["moment.team.vel.fouls_in_window"] == 6


@pytest.fixture(scope="module")
def seed7() -> tuple[list[CandidateMoment], LedgerState]:
    events = simulate_match(7)
    return detect_moments(events), LedgerState.from_events(events)


def test_seeded_match_yields_30_to_60_moments(seed7: tuple[list[CandidateMoment], LedgerState]) -> None:
    moments, _ = seed7
    counts = Counter(kinds(moments))
    print(f"seed 7: {len(moments)} moments {dict(counts)}")
    assert 30 <= len(moments) <= 60
    assert {"pass_streak", "pressing_trap", "player_milestone", "goal", "momentum_shift", "lull"} <= set(counts)


def test_moments_are_well_formed(seed7: tuple[list[CandidateMoment], LedgerState]) -> None:
    moments, final = seed7
    ledger_keys = set(final.evidence())
    assert len({m.moment_id for m in moments}) == len(moments)
    ends = [m.window[1] for m in moments]
    assert ends == sorted(ends)
    for m in moments:
        assert m.window[0] <= m.window[1]
        assert m.evidence
        for key in m.evidence:
            assert key.startswith("moment.") or key in ledger_keys, key


def test_detector_is_incremental(seed7: tuple[list[CandidateMoment], LedgerState]) -> None:
    moments, _ = seed7
    detector = MomentDetector()
    live = []
    for ev in simulate_match(7):
        for m in detector.feed(ev):
            assert m.window[1] == ev.seq
            live.append(m)
    assert live == moments
