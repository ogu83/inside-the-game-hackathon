from pathlib import Path

from app.simulator.engine import simulate
from app.simulator.export import SAMPLE_SEEDS, export_match, load_match, sample_path
from app.simulator.models import MatchEvent


def test_export_round_trips_every_event(tmp_path: Path) -> None:
    events = simulate(3, minutes=10)
    path = export_match(events, tmp_path / "m.jsonl")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(events)
    assert load_match(path) == events


def test_committed_samples_validate_and_match_their_seed() -> None:
    for seed in SAMPLE_SEEDS:
        path = sample_path(seed)
        assert path.exists(), f"run python -m app.simulator.export --seed {seed}"
        loaded = load_match(path)
        assert all(isinstance(e, MatchEvent) for e in loaded)
        assert loaded == simulate(seed), f"data/match_{seed}.jsonl is stale; regenerate it"


def test_samples_cover_every_event_type() -> None:
    types = {e.type for seed in SAMPLE_SEEDS for e in load_match(sample_path(seed))}
    assert types == {"pass", "shot", "tackle", "interception", "pressure", "possession_change", "substitution", "foul", "goal", "kickoff", "half_time", "full_time"}
