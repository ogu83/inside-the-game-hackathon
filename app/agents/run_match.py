"""Run every S2 moment of a seeded match through the Commentator -> Fact-Checker workflow.

    python -m app.agents.run_match --seed 7                      # offline template agents, summary
    python -m app.agents.run_match --seed 7 --jsonl runs/7.jsonl # also write one row per moment (eval export)
    python -m app.agents.run_match --seed 7 --live               # Foundry agents from .env (costs tokens)
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.agents.analyst import PacingTracker, RuleDirector
from app.agents.fact_checker import FactChecker
from app.agents.fakes import AlwaysVerifies, TemplateCommentator
from app.agents.models import MomentResult
from app.agents.workflow import build_workflow, run_moment
from app.ledger.models import CandidateMoment
from app.ledger.state import detect_all
from app.simulator.engine import simulate
from app.simulator.models import MatchEvent


def close_t(moment: CandidateMoment, events: list[MatchEvent]) -> int:
    """Match second at which the moment closed (its last event)."""
    return events[moment.window[1] - 1].t


def offline_workflow():
    return build_workflow(TemplateCommentator(), FactChecker(AlwaysVerifies()), RuleDirector())


def live_workflow():
    import os

    from agent_framework_foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential
    from dotenv import load_dotenv

    from app.agents.analyst import FoundryDirector
    from app.agents.commentator import FoundryCommentator
    from app.agents.fact_checker import FoundryWordingJudge
    from app.agents.prompts import ANALYST_INSTRUCTIONS, COMMENTATOR_INSTRUCTIONS, FACT_CHECKER_INSTRUCTIONS

    load_dotenv()
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    credential = DefaultAzureCredential()

    def agent(model_env: str, name: str, instructions: str):
        return FoundryChatClient(project_endpoint=endpoint, model=os.environ[model_env], credential=credential).as_agent(name=name, instructions=instructions)

    return build_workflow(
        FoundryCommentator(agent("FRONTIER_MODEL_DEPLOYMENT", "commentator", COMMENTATOR_INSTRUCTIONS)),
        FactChecker(FoundryWordingJudge(agent("SMALL_MODEL_DEPLOYMENT", "fact_checker", FACT_CHECKER_INSTRUCTIONS))),
        FoundryDirector(agent("SMALL_MODEL_DEPLOYMENT", "analyst", ANALYST_INSTRUCTIONS)),
    )


def summary(results: list[MomentResult]) -> dict[str, int]:
    statuses = [r.verdict.status for r in results if r.verdict]
    checks = [c for r in results for c in r.checks]
    return {
        "moments": len(results),
        "skipped": sum(not r.decision.say for r in results),
        "verified": statuses.count("verified"),
        "rewritten": statuses.count("rewritten"),
        "rejected": statuses.count("rejected"),
        "retries": sum(len(r.attempts) - 1 for r in results),
        "number_checks": len(checks),
        "number_checks_failed": sum(not c.ok for c in checks),
    }


async def run(seed: int, live: bool, jsonl: Path | None, limit: int | None) -> list[MomentResult]:
    events = simulate(seed)
    moments = detect_all(events)[:limit]
    workflow = live_workflow() if live else offline_workflow()
    pacing = PacingTracker()
    results = []
    for moment in moments:
        t = close_t(moment, events)
        result = await run_moment(workflow, moment, pacing=pacing.state_for(moment, t))
        pacing.record(result.decision, t)
        results.append(result)
    if jsonl:
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("w", encoding="utf-8") as f:
            for moment, result in zip(moments, results, strict=True):
                f.write(json.dumps({"seed": seed, "moment": moment.model_dump(), **result.model_dump()}, ensure_ascii=False) + "\n")
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--live", action="store_true", help="use Foundry agents from .env")
    parser.add_argument("--jsonl", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None, help="only the first N moments")
    args = parser.parse_args()
    results = asyncio.run(run(args.seed, args.live, args.jsonl, args.limit))
    for r in results:
        v = r.verdict
        if v is None:
            print(f"skipped   director: {r.decision.reason}")
            continue
        print(f"{v.status:9} L{'1' if v.layer == 'code' else '2'} attempt {v.attempt} [{r.decision.angle}]: {(v.insight.claim if v.insight else '')}  {v.reasons if v.reasons else ''}")
    print(json.dumps(summary(results)))


if __name__ == "__main__":
    main()
