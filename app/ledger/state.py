from dataclasses import dataclass, field

from app.ledger.models import CandidateMoment
from app.ledger.moments import Detector, PassStreakDetector, PressingTrapDetector
from app.simulator.models import MatchEvent


@dataclass
class Ledger:
    """Deterministic match state. Feed events in order; returns candidate moments as they close."""

    events: list[MatchEvent] = field(default_factory=list)
    score: dict[str, int] = field(default_factory=dict)
    detectors: list[Detector] = field(default_factory=lambda: [PassStreakDetector(), PressingTrapDetector()])

    def ingest(self, event: MatchEvent) -> list[CandidateMoment]:
        self.events.append(event)
        if event.type == "goal":
            self.score[event.team_id] = self.score.get(event.team_id, 0) + 1
        moments = [d.on_event(event, self.events) for d in self.detectors]
        return [m for m in moments if m is not None]


def detect_all(events: list[MatchEvent]) -> list[CandidateMoment]:
    ledger = Ledger()
    return [m for event in events for m in ledger.ingest(event)]


if __name__ == "__main__":
    import argparse

    from app.simulator.engine import simulate

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    found = detect_all(simulate(args.seed))
    print(f"seed {args.seed}: {len(found)} candidate moments")
    for m in found:
        print(f"  {m.minute:02d}' {m.team_id} {m.kind} {m.evidence}")
