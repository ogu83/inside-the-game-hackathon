from datetime import datetime, timezone
import pytest
from app.api.limits import RunLimiter


def test_global_cap_blocks_after_max_allowed():
    limiter = RunLimiter(per_day=0, total_per_day=40)
    now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)

    # 40 starts across various visitors succeed
    for i in range(40):
        allowed, reason = limiter.check_allow(f"visitor-{i}", now=now)
        assert allowed is True
        assert reason is None

    # The 41st live start falls back with exact expected message
    allowed, reason = limiter.check_allow("visitor-41", now=now)
    assert allowed is False
    assert reason == "Live runs for today are used up, playing with offline agents"


def test_global_cap_resets_next_utc_day():
    limiter = RunLimiter(per_day=0, total_per_day=2)
    day1 = datetime(2026, 10, 17, 23, 59, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 10, 18, 0, 1, 0, tzinfo=timezone.utc)

    # Exhaust day 1
    assert limiter.allow("v1", now=day1) is True
    assert limiter.allow("v2", now=day1) is True
    assert limiter.allow("v3", now=day1) is False

    # Day 2 resets count
    allowed, reason = limiter.check_allow("v3", now=day2)
    assert allowed is True
    assert reason is None


def test_visitor_cap_and_global_cap_interaction():
    # 2 per visitor, 3 total per day
    limiter = RunLimiter(per_day=2, total_per_day=3)
    now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)

    # Visitor A uses 2 runs
    assert limiter.check_allow("vA", now=now) == (True, None)
    assert limiter.check_allow("vA", now=now) == (True, None)
    # Visitor A reaches per-visitor limit
    allowed, reason = limiter.check_allow("vA", now=now)
    assert allowed is False
    assert "live-run limit reached (2 per visitor per day)" in (reason or "")

    # Visitor B can still use 1 run
    assert limiter.check_allow("vB", now=now) == (True, None)

    # Now global total (3) is reached, visitor B or C gets global cap message
    allowed, reason = limiter.check_allow("vB", now=now)
    assert allowed is False
    assert reason == "Live runs for today are used up, playing with offline agents"

    allowed, reason = limiter.check_allow("vC", now=now)
    assert allowed is False
    assert reason == "Live runs for today are used up, playing with offline agents"


def test_zero_means_unlimited():
    limiter = RunLimiter(per_day=0, total_per_day=0)
    now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
    for _ in range(50):
        allowed, reason = limiter.check_allow("v1", now=now)
        assert allowed is True
        assert reason is None
    assert limiter.remaining("v1", now=now) is None


def test_remaining_reports_minimum_of_visitor_and_global():
    limiter = RunLimiter(per_day=5, total_per_day=3)
    now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)

    assert limiter.remaining("v1", now=now) == 3
    limiter.allow("v1", now=now)
    assert limiter.remaining("v1", now=now) == 2
    limiter.allow("v2", now=now)
    # v1 has 4 left individually, but global has 1 left
    assert limiter.remaining("v1", now=now) == 1
    limiter.allow("v3", now=now)
    assert limiter.remaining("v1", now=now) == 0
