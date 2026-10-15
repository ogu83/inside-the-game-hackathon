"""T2 spike: Commentator -> Fact-Checker graph workflow with a conditional reject edge.

The Fact-Checker routes a rejected draft back to the Commentator once (max 1 retry),
then the workflow yields the final verdict. `--inject-false` replaces the first draft
with a claim that contradicts the evidence, to prove the reject edge fires.

    python spikes/two_agents.py [--inject-false] [--trace]
"""

import argparse
import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Literal

from agent_framework import Agent, Executor, WorkflowBuilder, WorkflowContext, handler
from agent_framework_foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv
from pydantic import BaseModel

EVIDENCE = {
    "home_possession_pct_last_10min": 68.0,
    "home_passes_completed_last_10min": 74.0,
    "away_shots_last_10min": 0.0,
    "home_press_regains_last_10min": 5.0,
}
FALSE_CLAIM = "The away side has dominated the last ten minutes with six shots on goal."
MAX_RETRIES = 1

COMMENTATOR_INSTRUCTIONS = (
    "You are a football co-commentator. Write one short claim about the moment and why it matters. "
    "Only use numbers that appear in the evidence, and list the evidence keys you cite."
)
FACT_CHECKER_INSTRUCTIONS = (
    "You are a strict fact-checker. Compare the claim with the evidence. "
    "Reject if any number or statement is missing from or contradicted by the evidence."
)


class Insight(BaseModel):
    claim: str
    evidence_refs: list[str]


class Check(BaseModel):
    status: Literal["verified", "rejected"]
    reasons: list[str]


@dataclass
class Draft:
    insight: Insight
    attempt: int
    feedback: list[str] = field(default_factory=list)


@dataclass
class Verdict:
    status: str
    insight: Insight
    attempt: int
    reasons: list[str]


class Commentator(Executor):
    def __init__(self, agent: Agent, inject_false: bool) -> None:
        super().__init__(id="commentator")
        self.agent = agent
        self.inject_false = inject_false

    @handler
    async def start(self, evidence: dict, ctx: WorkflowContext[Draft]) -> None:
        if self.inject_false:
            insight = Insight(claim=FALSE_CLAIM, evidence_refs=["away_shots_last_10min"])
        else:
            insight = await self._write(evidence, [])
        print(f"[commentator] attempt 1: {insight.claim}  refs={insight.evidence_refs}")
        await ctx.send_message(Draft(insight=insight, attempt=1))

    @handler
    async def retry(self, verdict: Verdict, ctx: WorkflowContext[Draft]) -> None:
        insight = await self._write(EVIDENCE, verdict.reasons)
        attempt = verdict.attempt + 1
        print(f"[commentator] attempt {attempt}: {insight.claim}  refs={insight.evidence_refs}")
        await ctx.send_message(Draft(insight=insight, attempt=attempt))

    async def _write(self, evidence: dict, feedback: list[str]) -> Insight:
        prompt = f"Evidence: {json.dumps(evidence)}"
        if feedback:
            prompt += f"\nYour previous claim was rejected: {feedback}. Write a corrected claim."
        response = await self.agent.run(prompt, options={"response_format": Insight})
        return response.value


class FactChecker(Executor):
    def __init__(self, agent: Agent) -> None:
        super().__init__(id="fact_checker")
        self.agent = agent

    @handler
    async def check(self, draft: Draft, ctx: WorkflowContext[Verdict, Verdict]) -> None:
        prompt = f"Evidence: {json.dumps(EVIDENCE)}\nClaim: {draft.insight.model_dump_json()}"
        response = await self.agent.run(prompt, options={"response_format": Check})
        check: Check = response.value
        verdict = Verdict(check.status, draft.insight, draft.attempt, check.reasons)
        print(f"[fact_checker] attempt {draft.attempt}: {check.status}  {check.reasons}")
        if check.status == "rejected" and draft.attempt <= MAX_RETRIES:
            await ctx.send_message(verdict)
        else:
            await ctx.yield_output(verdict)


def configure_tracing(connection_string: str) -> None:
    from agent_framework.observability import enable_instrumentation
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(connection_string=connection_string)
    enable_instrumentation(enable_sensitive_data=True)


async def main(inject_false: bool, trace: bool) -> None:
    load_dotenv()
    async with DefaultAzureCredential() as credential:
        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        if trace:
            from azure.ai.projects.aio import AIProjectClient

            async with AIProjectClient(endpoint=endpoint, credential=credential) as project:
                configure_tracing(await project.telemetry.get_application_insights_connection_string())

        def client(model_env: str) -> FoundryChatClient:
            return FoundryChatClient(project_endpoint=endpoint, model=os.environ[model_env], credential=credential)

        commentator = Commentator(
            client("FRONTIER_MODEL_DEPLOYMENT").as_agent(name="commentator", instructions=COMMENTATOR_INSTRUCTIONS),
            inject_false,
        )
        fact_checker = FactChecker(
            client("SMALL_MODEL_DEPLOYMENT").as_agent(name="fact_checker", instructions=FACT_CHECKER_INSTRUCTIONS)
        )
        workflow = (
            WorkflowBuilder(name="t2_spike", start_executor=commentator, output_from=[fact_checker])
            .add_edge(commentator, fact_checker)
            .add_edge(fact_checker, commentator, condition=lambda v: isinstance(v, Verdict) and v.status == "rejected")
            .build()
        )
        result = await workflow.run(EVIDENCE)
        for verdict in result.get_outputs():
            print(f"FINAL: {verdict.status} after {verdict.attempt} attempt(s): {verdict.insight.claim}")

    if trace:
        from opentelemetry import trace as otel_trace

        otel_trace.get_tracer_provider().force_flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inject-false", action="store_true")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.inject_false, args.trace))
