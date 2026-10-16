"""Submit the exported conditions to Foundry evaluation, poll, save, and render docs/eval-results.md.

    python -m app.eval.run_eval runs/eval                         # all four conditions
    python -m app.eval.run_eval runs/eval --conditions checker_on checker_off
    python -m app.eval.run_eval runs/eval --render-only          # rebuild the report from saved results

One evaluation run per condition (checker_on, checker_off, planted_on, planted_off). The judge is the deployment in
SMALL_MODEL_DEPLOYMENT. Raw results are saved as runs/eval/results_<condition>.json so the report can be rebuilt.
"""

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.eval.export_runs import CONDITIONS, EvalRecord, read_jsonl
from app.eval.report import render_markdown

DEFAULT_REPORT = Path("docs/eval-results.md")


class Evaluator(Protocol):
    async def evaluate(self, items: Sequence[Any], *, eval_name: str = "") -> Any: ...


def to_eval_items(records: list[EvalRecord]) -> list[Any]:
    from agent_framework import EvalItem, Message

    return [EvalItem(conversation=[Message("user", [r.query]), Message("assistant", [r.response])], context=r.context) for r in records]


def results_to_dict(results: Any) -> dict[str, Any]:
    """A plain, JSON-safe view of an EvalResults (agent_framework) or of anything shaped like one."""
    items = []
    for item in getattr(results, "items", None) or []:
        items.append({
            "item_id": getattr(item, "item_id", ""), "status": getattr(item, "status", ""),
            "scores": [{"name": s.name, "score": s.score, "passed": s.passed} for s in getattr(item, "scores", []) or []],
            "error_code": getattr(item, "error_code", None), "error_message": getattr(item, "error_message", None),
            "output_text": getattr(item, "output_text", None),
        })
    return {
        "provider": getattr(results, "provider", ""), "eval_id": getattr(results, "eval_id", ""), "run_id": getattr(results, "run_id", ""),
        "status": getattr(results, "status", ""), "result_counts": getattr(results, "result_counts", None), "report_url": getattr(results, "report_url", None),
        "error": getattr(results, "error", None), "per_evaluator": getattr(results, "per_evaluator", None), "items": items,
    }


def foundry_evaluator(timeout: float = 900.0) -> Evaluator:
    from agent_framework_foundry import FoundryChatClient, FoundryEvals
    from azure.identity.aio import DefaultAzureCredential
    from dotenv import load_dotenv

    load_dotenv()
    client = FoundryChatClient(project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], model=os.environ["SMALL_MODEL_DEPLOYMENT"], credential=DefaultAzureCredential())
    return FoundryEvals(client=client, model=os.environ["SMALL_MODEL_DEPLOYMENT"],
                        evaluators=[FoundryEvals.GROUNDEDNESS, FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE], timeout=timeout)


def load_records(eval_dir: Path) -> dict[str, list[EvalRecord]]:
    return {c: read_jsonl(eval_dir / f"{c}.jsonl") for c in CONDITIONS if (eval_dir / f"{c}.jsonl").exists()}


def load_results(eval_dir: Path) -> dict[str, dict[str, Any]]:
    results = {}
    for c in CONDITIONS:
        path = eval_dir / f"results_{c}.json"
        if path.exists():
            results[c] = json.loads(path.read_text(encoding="utf-8"))
    return results


def load_manifest(eval_dir: Path) -> dict[str, Any] | None:
    path = eval_dir / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


async def run_conditions(eval_dir: Path, evaluator: Evaluator, conditions: Sequence[str], *, name_prefix: str = "matchday") -> dict[str, dict[str, Any]]:
    records = load_records(eval_dir)
    results = load_results(eval_dir)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    for condition in conditions:
        recs = records.get(condition, [])
        if not recs:
            print(f"{condition}: no items, skipped")
            continue
        print(f"{condition}: submitting {len(recs)} items")
        raw = await evaluator.evaluate(to_eval_items(recs), eval_name=f"{name_prefix}-{condition}-{stamp}")
        result = results_to_dict(raw)
        result["condition"] = condition
        result["submitted_at"] = stamp
        (eval_dir / f"results_{condition}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
        results[condition] = result
        print(f"{condition}: {result['status']} eval {result['eval_id']} run {result['run_id']} {result.get('report_url') or ''}")
    return results


def write_report(eval_dir: Path, report_path: Path = DEFAULT_REPORT) -> str:
    text = render_markdown(load_records(eval_dir), load_results(eval_dir), load_manifest(eval_dir))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("eval_dir", type=Path, nargs="?", default=Path("runs/eval"))
    parser.add_argument("--conditions", nargs="+", default=list(CONDITIONS), choices=list(CONDITIONS))
    parser.add_argument("--timeout", type=float, default=900.0, help="seconds to wait for each run (long-running operation)")
    parser.add_argument("--render-only", action="store_true", help="rebuild docs/eval-results.md from saved results")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    if not args.render_only:
        asyncio.run(run_conditions(args.eval_dir, foundry_evaluator(args.timeout), args.conditions))
    text = write_report(args.eval_dir, args.report)
    print(text.split("\n")[4])  # the headline line


if __name__ == "__main__":
    main()
