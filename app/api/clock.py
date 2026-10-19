"""Broadcast delay clock: events are ingested on the event clock and displayed `delay_s` later."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BroadcastClock:
    """All times in seconds. `started_at` is the wall (monotonic) time of match second 0 on the event clock.

    speed > 1 runs the match faster than real time; `delay_s` is in match seconds, so the wall-clock
    delay is delay_s / speed.
    """

    started_at: float
    speed: float = 1.0
    delay_s: float = 10.0

    def ingest_wall(self, t_match: float) -> float:
        return self.started_at + t_match / self.speed

    def display_wall(self, t_match: float) -> float:
        return self.started_at + (t_match + self.delay_s) / self.speed

    def event_t(self, now: float) -> float:
        return (now - self.started_at) * self.speed

    def playback_t(self, now: float) -> float:
        return self.event_t(now) - self.delay_s

    def as_dict(self, now: float) -> dict[str, float]:
        return {"speed": self.speed, "delay_s": self.delay_s, "event_t": round(self.event_t(now), 1), "playback_t": round(self.playback_t(now), 1)}
