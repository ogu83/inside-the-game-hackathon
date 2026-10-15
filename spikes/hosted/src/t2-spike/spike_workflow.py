"""T2 spike workflow: Commentator -> Fact-Checker with a conditional reject edge.

Shared by the local runner (spikes/two_agents.py) and the Foundry Hosted Agent (main.py).
The start executor takes list[Message] so the workflow can be exposed with `.as_agent()`.
A user message containing JSON is used as the evidence dict; otherwise EVIDENCE is used.
A message containing "inject-false" replaces the first draft with a contradicted claim.
"""

import json
from dataclasses import dataclass, field
from typing import Literal

from agent_framework import Agent, Executor, Message, Workflow, WorkflowBuilder, WorkflowContext, handler
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
    evidence: dict
    insight: Insight
    attempt: int


@dataclass
class Verdict:
    evidence: dict
    status: str
    insight: Insight
    attempt: int
    reasons: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return f"{self.status} after {self.attempt} attempt(s): {self.insight.claim}"


def parse_request(messages: list[Message]) -> tuple[dict, bool]:
    text = messages[-1].text if messages else ""
    inject_false = "inject-false" in text
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1]), inject_false
        except json.JSONDecodeError:
            pass
    return EVIDENCE, inject_false


class Commentator(Executor):
    def __init__(self, agent: Agent) -> None:
        super().__init__(id="commentator")
        self.agent = agent

    @handler
    async def start(self, messages: list[Message], ctx: WorkflowContext[Draft]) -> None:
        evidence, inject_false = parse_request(messages)
        if inject_false:
            insight = Insight(claim=FALSE_CLAIM, evidence_refs=["away_shots_last_10min"])
        else:
            insight = await self._write(evidence, [])
        print(f"[commentator] attempt 1: {insight.claim}  refs={insight.evidence_refs}")
        await ctx.send_message(Draft(evidence, insight, attempt=1))

    @handler
    async def retry(self, verdict: Verdict, ctx: WorkflowContext[Draft]) -> None:
        insight = await self._write(verdict.evidence, verdict.reasons)
        attempt = verdict.attempt + 1
        print(f"[commentator] attempt {attempt}: {insight.claim}  refs={insight.evidence_refs}")
        await ctx.send_message(Draft(verdict.evidence, insight, attempt))

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
    async def check(self, draft: Draft, ctx: WorkflowContext[Verdict, str]) -> None:
        prompt = f"Evidence: {json.dumps(draft.evidence)}\nClaim: {draft.insight.model_dump_json()}"
        response = await self.agent.run(prompt, options={"response_format": Check})
        check: Check = response.value
        verdict = Verdict(draft.evidence, check.status, draft.insight, draft.attempt, check.reasons)
        print(f"[fact_checker] attempt {draft.attempt}: {check.status}  {check.reasons}")
        if check.status == "rejected" and draft.attempt <= MAX_RETRIES:
            await ctx.send_message(verdict)
        else:
            await ctx.yield_output(verdict.summary())


def build_workflow(commentator_agent: Agent, fact_checker_agent: Agent) -> Workflow:
    commentator = Commentator(commentator_agent)
    fact_checker = FactChecker(fact_checker_agent)
    return (
        WorkflowBuilder(name="t2_spike", start_executor=commentator, output_from=[fact_checker])
        .add_edge(commentator, fact_checker)
        .add_edge(fact_checker, commentator, condition=lambda v: isinstance(v, Verdict) and v.status == "rejected")
        .build()
    )
