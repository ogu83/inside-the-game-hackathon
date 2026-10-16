"""Opt-in: one small Foundry evaluation (2 items), judged by SMALL_MODEL_DEPLOYMENT. `python -m pytest tests/eval -m live`."""

import pytest

from app.eval.export_runs import CONDITIONS, build_records
from app.eval.run_eval import foundry_evaluator, results_to_dict, to_eval_items

pytestmark = [pytest.mark.live, pytest.mark.timeout(0)]


async def test_live_two_items_are_scored_by_foundry() -> None:
    from app.agents.run_match import run
    from app.ledger.state import detect_all
    from app.simulator.engine import simulate

    moments = detect_all(simulate(30))[:2]
    results = await run(30, live=False, jsonl=None, limit=2)
    records, _ = build_records(results, moments, 30)
    items = to_eval_items([r for r in records if r.condition == "checker_on"][:2] or records[:2])
    evaluator = foundry_evaluator(timeout=600)
    raw = await evaluator.evaluate(items, eval_name="matchday-live-smoke")
    result = results_to_dict(raw)
    assert result["status"] == "completed", result
    assert result["run_id"] and result["items"], result
    names = {s["name"].casefold() for item in result["items"] for s in item["scores"]}
    assert any(n.startswith("groundedness") for n in names), names
    assert set(CONDITIONS) == {"checker_on", "checker_off", "planted_on", "planted_off"}
