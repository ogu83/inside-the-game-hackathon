"""Run every S2 moment of a seeded match through the Commentator -> Fact-Checker workflow.

    python -m app.agents.run_match --seed 7                      # offline template agents, summary
    python -m app.agents.run_match --seed 7 --jsonl runs/7.jsonl # also write one row per moment (eval export)
    python -m app.agents.run_match --seed 7 --live               # Foundry agents from .env (costs tokens)
    python -m app.agents.run_match --seed 30 --plant 6           # planted-error report (6 insights + 6 renderings)
    python -m app.agents.run_match --seed 30 --plant 4 --limit 12 --live   # the live check, about 2 minutes
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.agents.analyst import PacingTracker, RuleDirector
from app.agents.fact_checker import FactChecker
from app.agents.fakes import AlwaysVerifies, TemplateCommentator, TemplateRenderer
from app.agents.models import FanProfile, MomentResult
from app.agents.planted_errors import PlantedReport, PlantingCommentator, PlantPlan, make_tamper, report_insights
from app.agents.producer import FoundryRenderer, Producer
from app.agents.workflow import build_workflow, run_moment
from app.ledger.models import CandidateMoment
from app.ledger.state import detect_all
from app.observability import flush_tracing, init_observability
from app.simulator.engine import simulate
from app.simulator.models import MatchEvent


def close_t(moment: CandidateMoment, events: list[MatchEvent]) -> int:
    """Match second at which the moment closed (its last event)."""
    return events[moment.window[1] - 1].t


def offline_workflow(writer=None):
    return build_workflow(writer or TemplateCommentator(), FactChecker(AlwaysVerifies()), RuleDirector())


PLANT_PROFILES = [FanProfile(language="en", depth="casual"), FanProfile(language="tr", depth="analyst")]
LAST_PLANTING: list[PlantingCommentator] = []


async def run_planted(seed: int, n: int, live: bool = False, plan_seed: int = 0, limit: int | None = None) -> tuple[list[MomentResult], PlantedReport]:
    """Plant n insight errors and n rendering errors (en and tr) on a seeded match (or its first `limit` moments)
    and report what the gates caught."""
    events = simulate(seed)
    moments = detect_all(events)[:limit]
    plan = PlantPlan.build([m.moment_id for m in moments], n, n, plan_seed)
    if live:
        workflow = live_workflow()
        workflow.executors["commentator"].writer = PlantingCommentator(workflow.executors["commentator"].writer, plan, plan_seed)
        commentator = workflow.executors["commentator"].writer
    else:
        commentator = PlantingCommentator(TemplateCommentator(), plan, plan_seed)
        workflow = offline_workflow(commentator)
    tampered: list[tuple[str, str, str]] = []
    producer = (live_producer if live else offline_producer)(tamper=make_tamper(plan, plan_seed, tampered))
    LAST_PLANTING.clear()
    LAST_PLANTING.append(commentator)  # the eval export reads the plan and the planted insights from here
    pacing = PacingTracker()
    results: list[MomentResult] = []
    report = PlantedReport()
    for moment in moments:
        t = close_t(moment, events)
        result = await run_moment(workflow, moment, pacing=pacing.state_for(moment, t))
        pacing.record(result.decision, t)
        results.append(result)
        verdict = result.verdict
        if verdict is None or verdict.status == "rejected" or verdict.insight is None:
            continue
        labels = moment_labels_for(moment)
        before = len(tampered)
        output = await producer.render(verdict.insight, moment, labels, PLANT_PROFILES)
        shown_keys = {n.profile_key for n in output.narratives} | ({"broadcast"} if output.cue else set())
        for check in output.checks:
            kind = _tampered_kind(tampered[before:], check)
            if kind is None:
                continue
            count = report.renderings[kind]
            count.planted += 1
            if not check.ok:
                count.caught_by_code += 1
            elif check.profile_key in shown_keys:
                count.reached_air += 1
                report.reached_air_detail.append(f"rendering ({kind}) {check.profile_key}: {check.text}")
    report_insights(results, commentator, report)
    return results, report


def _tampered_kind(tampered: list[tuple[str, str, str]], check) -> str | None:
    return next((kind for m, p, kind in tampered if m == check.moment_id and p == check.profile_key), None)


def moment_labels_for(moment: CandidateMoment) -> dict[str, str]:
    from app.ledger.labels import moment_labels

    return moment_labels(moment)


def live_agent(model_env: str, name: str, instructions: str):
    import os

    from agent_framework_foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential
    from dotenv import load_dotenv

    load_dotenv()
    client = FoundryChatClient(project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], model=os.environ[model_env], credential=DefaultAzureCredential())
    return client.as_agent(name=name, instructions=instructions)


def live_producer(tamper=None) -> Producer:
    from app.agents.prompts import PRODUCER_INSTRUCTIONS

    return Producer(FoundryRenderer(live_agent("SMALL_MODEL_DEPLOYMENT", "producer", PRODUCER_INSTRUCTIONS)), tamper=tamper)


def offline_producer(tamper=None) -> Producer:
    return Producer(TemplateRenderer(), tamper=tamper)


def live_qa_agent(mcp_url: str):
    """Q&A agent over the ledger MCP server (live only). The MCP tool-call span is what the trace shows."""
    from agent_framework import MCPStreamableHTTPTool

    from app.agents.prompts import QA_INSTRUCTIONS
    from app.voice.qa import FoundryQaAgent

    client = live_agent("SMALL_MODEL_DEPLOYMENT", "qa", QA_INSTRUCTIONS)
    client.default_options = getattr(client, "default_options", None)
    tool = MCPStreamableHTTPTool(name="ledger", url=mcp_url)
    return FoundryQaAgent(_ToolBoundAgent(client, tool))


class _ToolBoundAgent:
    def __init__(self, agent, tool) -> None:
        self.agent, self.tool = agent, tool

    async def run(self, prompt: str, options=None):
        return await self.agent.run(prompt, tools=[self.tool], options=options)


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
    from opentelemetry import trace

    tracer = trace.get_tracer("app.agents.run_match")
    events = simulate(seed)
    moments = detect_all(events)[:limit]
    workflow = live_workflow() if live else offline_workflow()
    pacing = PacingTracker()
    results = []
    for moment in moments:
        t = close_t(moment, events)
        with tracer.start_as_current_span(f"moment {moment.moment_id}") as span:
            span.set_attribute("match.id", f"seed-{seed}")
            span.set_attribute("moment.id", moment.moment_id)
            span.set_attribute("moment.kind", moment.kind)
            span.set_attribute("moment.minute", float(moment.minute))
            t_start = asyncio.get_running_loop().time()
            result = await run_moment(workflow, moment, pacing=pacing.state_for(moment, t))
            pacing.record(result.decision, t)
            results.append(result)
            latency_ms = round((asyncio.get_running_loop().time() - t_start) * 1000, 2)
            span.set_attribute("moment.latency_ms", latency_ms)
            if result.verdict is None:
                span.set_attribute("cue.status", "skipped")
            else:
                span.set_attribute("cue.status", "aired" if result.verdict.status != "rejected" else "rejected")
                span.set_attribute("factcheck.layer", result.verdict.layer)
                span.set_attribute("factcheck.attempts", result.verdict.attempt)
    if jsonl:
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("w", encoding="utf-8") as f:
            for moment, result in zip(moments, results, strict=True):
                f.write(json.dumps({"seed": seed, "moment": moment.model_dump(), **result.model_dump()}, ensure_ascii=False) + "\n")
    return results


def main() -> None:
    init_observability()
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--seed", type=int, default=7)
        parser.add_argument("--live", action="store_true", help="use Foundry agents from .env")
        parser.add_argument("--jsonl", type=Path, default=None)
        parser.add_argument("--limit", type=int, default=None, help="only the first N moments")
        parser.add_argument("--plant", type=int, default=0, help="plant N insight and N rendering errors and report the catches")
        args = parser.parse_args()
        if args.plant:
            results, report = asyncio.run(run_planted(args.seed, args.plant, args.live, limit=args.limit))
            print(json.dumps(summary(results)))
            print(json.dumps(report.as_dict()))
            print(report.headline())
            for line in report.reached_air_detail:
                print("REACHED AIR:", line)
            return
        results = asyncio.run(run(args.seed, args.live, args.jsonl, args.limit))
        for r in results:
            v = r.verdict
            if v is None:
                print(f"skipped   director: {r.decision.reason}")
                continue
            print(f"{v.status:9} L{'1' if v.layer == 'code' else '2'} attempt {v.attempt} [{r.decision.angle}]: {(v.insight.claim if v.insight else '')}  {v.reasons if v.reasons else ''}")
        print(json.dumps(summary(results)))
    finally:
        flush_tracing()


if __name__ == "__main__":
    main()
