"""Dataset export: one MatchEvent per line as JSON (JSONL), re-loadable and validated.

    python -m app.simulator.export --seed 30                    # writes data/match_30.jsonl
    python -m app.simulator.export --seed 7 --out /tmp/m.jsonl
"""

import argparse
from pathlib import Path

from app.simulator.engine import simulate
from app.simulator.models import MatchEvent

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SAMPLE_SEEDS = (7, 30, 42)


def export_match(events: list[MatchEvent], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for event in events:
            f.write(event.model_dump_json(exclude_none=True) + "\n")
    return path


def load_match(path: Path) -> list[MatchEvent]:
    """Validate every line; raises on a malformed row."""
    with path.open(encoding="utf-8") as f:
        return [MatchEvent.model_validate_json(line) for line in f if line.strip()]


def sample_path(seed: int) -> Path:
    return DATA_DIR / f"match_{seed}.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=30)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--minutes", type=int, default=90)
    args = parser.parse_args()
    events = simulate(args.seed, minutes=args.minutes)
    path = export_match(events, args.out or sample_path(args.seed))
    print(f"{len(events)} events -> {path}")


if __name__ == "__main__":
    main()
