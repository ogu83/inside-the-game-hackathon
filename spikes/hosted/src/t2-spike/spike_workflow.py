"""T2 spike workflow: Commentator -> Fact-Checker with a conditional reject edge.

Shared by the local runner (spikes/two_agents.py) and the Foundry Hosted Agent (main.py).
The start executor takes the request text. JSON inside it is used as the evidence dict,
otherwise EVIDENCE is used. Text containing "inject-false" replaces the first draft with a
contradicted claim, to prove the reject edge fires.

Messages between executors are plain JSON dicts: hosted checkpoint storage only
deserializes allow-listed types, so custom dataclasses fail the run there.
"""

import json
from typing import Literal

from agent_framework import Agent, Executor, Workflow, WorkflowBuilder, WorkflowContext, handler
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


def parse_request(text: str) -> tuple[dict, bool]:
    inject_false = "inject-false" in text
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1]), inject_false
        except json.JSONDecodeError:
            pass
    return EVIDENCE, inject_false


def is_rejected(message: dict) -> bool:
    return message.get("status") == "rejected"


class Commentator(Executor):
    def __init__(self, agent: Agent) -> None:
        super().__init__(id="commentator")
        self.agent = agent

    @handler
    async def start(self, text: str, ctx: WorkflowContext[dict]) -> None:
        evidence, inject_false = parse_request(text)
        if inject_false:
            insight = Insight(claim=FALSE_CLAIM, evidence_refs=["away_shots_last_10min"])
        else:
            insight = await self._write(evidence, [])
        await self._send(ctx, evidence, insight, attempt=1)

    @handler
    async def retry(self, verdict: dict, ctx: WorkflowContext[dict]) -> None:
        insight = await self._write(verdict["evidence"], verdict["reasons"])
        await self._send(ctx, verdict["evidence"], insight, attempt=verdict["attempt"] + 1)

    async def _write(self, evidence: dict, feedback: list[str]) -> Insight:
        prompt = f"Evidence: {json.dumps(evidence)}"
        if feedback:
            prompt += f"\nYour previous claim was rejected: {feedback}. Write a corrected claim."
        response = await self.agent.run(prompt, options={"response_format": Insight})
        return response.value

    async def _send(self, ctx: WorkflowContext[dict], evidence: dict, insight: Insight, attempt: int) -> None:
        print(f"[commentator] attempt {attempt}: {insight.claim}  refs={insight.evidence_refs}")
        await ctx.send_message({"evidence": evidence, "insight": insight.model_dump(), "attempt": attempt})


class FactChecker(Executor):
    def __init__(self, agent: Agent) -> None:
        super().__init__(id="fact_checker")
        self.agent = agent

    @handler
    async def check(self, draft: dict, ctx: WorkflowContext[dict, str]) -> None:
        prompt = f"Evidence: {json.dumps(draft['evidence'])}\nClaim: {json.dumps(draft['insight'])}"
        response = await self.agent.run(prompt, options={"response_format": Check})
        check: Check = response.value
        print(f"[fact_checker] attempt {draft['attempt']}: {check.status}  {check.reasons}")
        if check.status == "rejected" and draft["attempt"] <= MAX_RETRIES:
            await ctx.send_message({**draft, "status": check.status, "reasons": check.reasons})
        else:
            await ctx.yield_output(f"{check.status} after {draft['attempt']} attempt(s): {draft['insight']['claim']}")


def build_workflow(commentator_agent: Agent, fact_checker_agent: Agent) -> Workflow:
    commentator = Commentator(commentator_agent)
    fact_checker = FactChecker(fact_checker_agent)
    return (
        WorkflowBuilder(name="t2_spike", start_executor=commentator, output_from=[fact_checker])
        .add_edge(commentator, fact_checker)
        .add_edge(fact_checker, commentator, condition=is_rejected)
        .build()
    )
