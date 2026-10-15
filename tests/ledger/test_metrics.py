from app.ledger.metrics import in_window, pass_accuracy_pct, possession_pct, progress_m
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
