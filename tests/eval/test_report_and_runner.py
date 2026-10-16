import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.agents.models import DirectorDecision, Insight, MomentResult, Verdict
from app.eval.export_runs import build_records, write_jsonl
from app.eval.report import evaluator_stats, headline, own_metrics, render_markdown
from app.eval.run_eval import load_results, results_to_dict, run_conditions, to_eval_items, write_report
from app.ledger.state import detect_all
from app.simulator.engine import simulate

MOMENTS = detect_all(simulate(30))[:3]


def make_records(tmp_path: Path):
    results = []
    for m in MOMENTS:
        ins = Insight(moment_id=m.moment_id, claim=f"Team kept {m.evidence['pass_streak_passes']:g} passes." if "pass_streak_passes" in m.evidence else "A trap closed.", why_it_matters="Why.", evidence_refs=list(m.evidence), confidence=0.9)
        results.append(MomentResult(moment_id=m.moment_id, decision=DirectorDecision(moment_id=m.moment_id, say=True, reason="r"),
                                    verdict=Verdict(moment_id=m.moment_id, status="verified", insight=ins, reasons=[], layer="llm", attempt=1), attempts=[ins]))
    records, _ = build_records(results, MOMENTS, 30)
    # planted run: moment 0's first draft carried a wrong number, the checker sent it back and the clean retry aired
    planted_insight = results[0].attempts[0].model_copy(update={"claim": "Team kept 99 passes."})
    planted_results = [results[0].model_copy(update={"attempts": [planted_insight, results[0].attempts[0]]}), *results[1:]]
    planted, _ = build_records(planted_results, MOMENTS, 30, on="planted_on", off="planted_off",
                               planted={MOMENTS[0].moment_id: ("wrong_number", planted_insight)})
    write_jsonl(records + planted, tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"exported_at": "2026-10-16T10:00:00+00:00", "live": False, "seeds": [30], "limit": 3,
                                                           "counts": {}, "rejected_by_seed": {"30": 0}, "skipped_by_seed": {"30": 0}, "planted": {}}), encoding="utf-8")
    return records


class FakeScore:
    def __init__(self, name, score, passed):
        self.name, self.score, self.passed = name, score, passed


class FakeItem:
    def __init__(self, i, scores):
        self.item_id, self.status, self.scores = f"item-{i}", "pass", scores
        self.error_code = self.error_message = self.output_text = None


class FakeResults:
    """Shaped like agent_framework's EvalResults."""

    def __init__(self, condition, n, groundedness):
        self.provider, self.eval_id, self.run_id, self.status = "fake", f"eval-{condition}", f"run-{condition}", "completed"
        self.result_counts, self.error, self.per_evaluator = {"passed": n}, None, {"groundedness": {"passed": n}}
        self.report_url = f"https://ai.azure.com/fake/{condition}"
        self.items = [FakeItem(i, [FakeScore("groundedness", groundedness, groundedness >= 3), FakeScore("relevance", 4.0, True), FakeScore("coherence", 5.0, True)]) for i in range(n)]


class FakeEvals:
    def __init__(self):
        self.calls = []

    async def evaluate(self, items, *, eval_name=""):
        self.calls.append((eval_name, len(items), [getattr(i, "context", None) for i in items]))
        condition = eval_name.split("-")[1] + ("_" + eval_name.split("-")[2] if eval_name.split("-")[2] in ("on", "off") else "")
        return FakeResults(condition, len(items), 5.0 if condition.endswith("_on") else 2.0)


def test_report_says_not_run_yet_without_results(tmp_path) -> None:
    make_records(tmp_path)
    text = write_report(tmp_path, tmp_path / "eval-results.md")
    assert "Not run yet" in text and "not run yet" in text and "n/a" in text
    assert "Fact-Checker on (what aired) | 3 |" in text
    assert "\u2014" not in text


async def test_runner_submits_each_condition_and_renders_the_report(tmp_path) -> None:
    make_records(tmp_path)
    fake = FakeEvals()
    results = await run_conditions(tmp_path, fake, ["checker_on", "checker_off", "planted_on", "planted_off"], name_prefix="matchday")
    assert [c[1] for c in fake.calls] == [3, 3, 3, 3]
    assert all(all(ctx for ctx in call[2]) for call in fake.calls), "every item carries its context"
    assert set(results) == {"checker_on", "checker_off", "planted_on", "planted_off"}
    saved = load_results(tmp_path)
    assert saved["checker_on"]["run_id"] == "run-checker_on" and saved["checker_on"]["report_url"].endswith("checker_on")
    assert saved["checker_on"]["items"][0]["scores"][0] == {"name": "groundedness", "score": 5.0, "passed": True}
    text = write_report(tmp_path, tmp_path / "eval-results.md")
    assert "Groundedness rose from 2.00 to 5.00" in text and "0 of 1 planted errors reached air; with it off, 1 did." in text
    assert "run `run-checker_on`" in text and "[portal](https://ai.azure.com/fake/checker_on)" in text
    assert "| Fact-Checker on (what aired) | 3 | 5.00 | 100% | 4.00 | 100% | 5.00 | 100% | 100% | no plants | completed |" in text
    assert "\u2014" not in text


def test_own_metrics_and_evaluator_stats() -> None:
    from app.eval.export_runs import EvalRecord

    rec = dict(seed=30, moment_id="m", kind="k", team="T", minute=1, query="q", response="r", context="c", cited_keys=[], status="verified")
    records = [EvalRecord(condition="planted_on", number_check_ok=True, planted_kind="wrong_number", planted_reached_air=False, **rec),
               EvalRecord(condition="planted_on", number_check_ok=False, planted_kind="swapped_team", planted_reached_air=True, **rec),
               EvalRecord(condition="planted_on", number_check_ok=True, **rec)]
    own = own_metrics(records)
    assert own == {"n": 3, "number_check_pass_rate": 2 / 3, "planted_n": 2, "planted_reached_air": 1, "planted_caught": 1}
    assert own_metrics([])["number_check_pass_rate"] is None
    stats = evaluator_stats({"items": [{"scores": [{"name": "Groundedness", "score": 4, "passed": True}, {"name": "groundedness", "score": 2, "passed": False}]}]})
    assert stats == {"groundedness": {"n": 2, "mean": 3.0, "pass_rate": 0.5}}
    assert evaluator_stats(None) == {}
    assert headline({}, {}).startswith("Not run yet")


def test_to_eval_items_and_results_to_dict(tmp_path) -> None:
    records = make_records(tmp_path)
    items = to_eval_items(records[:2])
    assert len(items) == 2 and items[0].context == records[0].context
    texts = [m.text for m in items[0].conversation]
    assert texts == [records[0].query, records[0].response]
    d = results_to_dict(FakeResults("checker_on", 1, 4.0))
    assert d["status"] == "completed" and d["items"][0]["scores"][1]["name"] == "relevance"


def test_render_is_deterministic_for_a_fixed_time(tmp_path) -> None:
    make_records(tmp_path)
    from app.eval.run_eval import load_manifest, load_records

    a = render_markdown(load_records(tmp_path), {}, load_manifest(tmp_path), now=datetime(2026, 10, 16, 12, 0, tzinfo=UTC))
    b = render_markdown(load_records(tmp_path), {}, load_manifest(tmp_path), now=datetime(2026, 10, 16, 12, 0, tzinfo=UTC))
    assert a == b and "Generated 2026-10-16 12:00 UTC" in a


async def test_offline_export_end_to_end(tmp_path) -> None:
    from app.eval.export_runs import export

    manifest = await export([30], 4, False, tmp_path)
    assert manifest.counts["checker_on"] >= 1 and manifest.counts["checker_off"] >= manifest.counts["checker_on"]
    assert manifest.counts["planted_off"] >= 1 and manifest.planted["insight_plants"] >= 1
    assert (tmp_path / "planted_off.jsonl").exists() and (tmp_path / "run_30.jsonl").exists()
    from app.eval.run_eval import load_records

    records = load_records(tmp_path)
    assert any(r.planted_kind for r in records["planted_off"]), "the planted first drafts are marked"
    assert all(r.number_check_ok for r in records["checker_on"]), "what airs with the checker on passes layer 1"
