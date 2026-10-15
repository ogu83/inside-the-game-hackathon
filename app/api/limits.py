"""Per-visitor live-run limit (SPEC design rule 7): judges' clicks spend Foundry tokens."""

import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime


def live_runs_per_day() -> int:
    """0 means unlimited (local development)."""
    return int(os.environ.get("PUBLIC_LIVE_RUNS_PER_DAY", "2"))


@dataclass
class RunLimiter:
    per_day: int
    _counts: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))

    def allow(self, visitor: str, now: datetime | None = None) -> bool:
        if self.per_day <= 0:
            return True
        day = (now or datetime.now(UTC)).strftime("%Y-%m-%d")
        if self._counts[(visitor, day)] >= self.per_day:
            return False
        self._counts[(visitor, day)] += 1
        return True

    def remaining(self, visitor: str, now: datetime | None = None) -> int | None:
        if self.per_day <= 0:
            return None
        day = (now or datetime.now(UTC)).strftime("%Y-%m-%d")
        return max(0, self.per_day - self._counts[(visitor, day)])
