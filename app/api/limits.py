"""Per-visitor and global daily live-run limits (SPEC design rule 7).

Judges' clicks spend Foundry tokens. The per-visitor limit prevents single-visitor exhaustion;
the global total limit caps total daily token spend across all visitors on the public instance.
"""

import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime


def live_runs_per_day() -> int:
    """0 means unlimited (local development)."""
    return int(os.environ.get("PUBLIC_LIVE_RUNS_PER_DAY", "2"))


def live_runs_total_per_day() -> int:
    """0 means unlimited (local development). Default 40 for public demo."""
    return int(os.environ.get("PUBLIC_LIVE_RUNS_TOTAL_PER_DAY", "40"))


@dataclass
class RunLimiter:
    per_day: int = 2
    total_per_day: int = 0
    _counts: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    _total_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def check_allow(self, visitor: str, now: datetime | None = None) -> tuple[bool, str | None]:
        """Check if a live run is allowed, recording the run and returning (allowed, reason_if_denied)."""
        day = (now or datetime.now(UTC)).strftime("%Y-%m-%d")
        if self.total_per_day > 0 and self._total_counts[day] >= self.total_per_day:
            return False, "Live runs for today are used up, playing with offline agents"
        if self.per_day > 0 and self._counts[(visitor, day)] >= self.per_day:
            return False, f"live-run limit reached ({self.per_day} per visitor per day); continuing with offline agents"
        if self.total_per_day > 0:
            self._total_counts[day] += 1
        if self.per_day > 0:
            self._counts[(visitor, day)] += 1
        return True, None

    def allow(self, visitor: str, now: datetime | None = None) -> bool:
        """Convenience method returning bool for backward compatibility."""
        allowed, _ = self.check_allow(visitor, now)
        return allowed

    def remaining(self, visitor: str, now: datetime | None = None) -> int | None:
        """Returns remaining runs for the visitor, bounded by both per-visitor and global caps."""
        day = (now or datetime.now(UTC)).strftime("%Y-%m-%d")
        visitor_rem = None if self.per_day <= 0 else max(0, self.per_day - self._counts[(visitor, day)])
        total_rem = None if self.total_per_day <= 0 else max(0, self.total_per_day - self._total_counts[day])
        if visitor_rem is None:
            return total_rem
        if total_rem is None:
            return visitor_rem
        return min(visitor_rem, total_rem)
