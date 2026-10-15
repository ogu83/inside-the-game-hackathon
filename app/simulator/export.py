"""JSONL dataset export: one MatchEvent per line, in seq order."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from app.simulator.model import MatchEvent


def default_path(seed: int, directory: Path = Path("data")) -> Path:
    return directory / f"match_{seed}.jsonl"


def write_jsonl(events: Iterable[MatchEvent], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for ev in events:
            f.write(ev.model_dump_json() + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[MatchEvent]:
    with path.open(encoding="utf-8") as f:
        return [MatchEvent.model_validate_json(line) for line in f if line.strip()]
