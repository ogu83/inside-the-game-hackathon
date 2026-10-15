from pathlib import Path

import pytest

from app.simulator.emitter import simulate_match
from app.simulator.export import default_path, read_jsonl, write_jsonl
from app.simulator.run import main

DATA = Path(__file__).resolve().parents[2] / "data"


def test_export_round_trip(tmp_path: Path) -> None:
    events = simulate_match(3)
    path = tmp_path / "nested" / "match_3.jsonl"
    assert write_jsonl(events, path) == len(events)
    assert read_jsonl(path) == events


def test_cli_export(tmp_path: Path) -> None:
    path = tmp_path / "m.jsonl"
    main(["--seed", "5", "--export", str(path)])
    assert read_jsonl(path) == simulate_match(5)


def test_default_path() -> None:
    assert default_path(7) == Path("data") / "match_7.jsonl"


@pytest.mark.parametrize("seed", [7, 8, 9])
def test_committed_samples_validate_and_match_simulator(seed: int) -> None:
    events = read_jsonl(DATA / f"match_{seed}.jsonl")
    assert events[0].type == "kickoff" and events[-1].type == "full_time"
    assert events == simulate_match(seed), (
        f"data/match_{seed}.jsonl is stale; regenerate with "
        f"python -m app.simulator.run --seed {seed} --export data/match_{seed}.jsonl"
    )
