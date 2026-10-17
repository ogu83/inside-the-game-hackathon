"""Director -> Commentator -> Fact-Checker graph workflow with one retry (Agent Framework).

Messages between executors are JSON-safe dicts (the hosted checkpoint store refuses custom classes);
each executor re-validates them into the SPEC models before doing anything with them. The director
runs first and may end the run with a skip decision (no Commentator call).
"""

import asyncio
import json
from typing import Any

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler

from app.agents.analyst import Director, RuleDirector
from app.agents.commentator import InsightWriter
from app.agents.fact_checker import FactChecker
from app.agents.models import DirectorDecision, Insight, MomentResult, NumberCheck, PacingState, Verdict
from app.agents.retry import retry_call
from app.ledger.labels import moment_labels
from app.ledger.models import CandidateMoment

MAX_RETRIES = 1


def is_rejected(message: Any) -> bool:
    return isinstance(message, dict) and message.get("status") == "rejected"


def is_said(message: Any) -> bool:
    return isinstance(message, dict) and message.get("decision", {}).get("say") is True


class DirectorExecutor(Executor):
    def __init__(self, director: Director) -> None:
        super().__init__(id="analyst")
        self.director = director

    @handler
    async def start(self, request: str, ctx: WorkflowContext[dict, dict]) -> None:
        payload = json.loads(request)
        moment = CandidateMoment.model_validate(payload["moment"])
        labels = dict(payload.get("labels") or moment_labels(moment))
        pacing = PacingState.model_validate(payload.get("pacing") or {})
        decision = await self.director.decide(moment, labels, pacing)
        if decision.angle:
            labels["angle"] = decision.angle
        message = {"moment": moment.model_dump(), "labels": labels, "decision": decision.model_dump()}
        if decision.say:
            await ctx.send_message(message)
        else:
            await ctx.yield_output({**message, "moment_id": moment.moment_id, "verdict": None, "attempts": [], "checks": [], "rejections": []})


class CommentatorExecutor(Executor):
    def __init__(self, writer: InsightWriter) -> None:
        super().__init__(id="commentator")
        self.writer = writer

    @handler
    async def write(self, draft: dict, ctx: WorkflowContext[dict]) -> None:
        moment = CandidateMoment.model_validate(draft["moment"])
        feedback = list(draft.get("reasons", []))
        insight = await self.writer.write(moment, draft["labels"], feedback)
        attempt = draft.get("attempt", 0) + 1
        await ctx.send_message({
            **{k: draft[k] for k in ("moment", "labels", "decision")},
            "checks": draft.get("checks", []), "rejections": draft.get("rejections", []),
            "insight": insight.model_dump(), "attempt": attempt, "attempts": draft.get("attempts", []) + [insight.model_dump()],
        })


class FactCheckerExecutor(Executor):
    def __init__(self, checker: FactChecker) -> None:
        super().__init__(id="fact_checker")
        self.checker = checker

    @handler
    async def check(self, draft: dict, ctx: WorkflowContext[dict, dict]) -> None:
        moment = CandidateMoment.model_validate(draft["moment"])
        insight = Insight.model_validate(draft["insight"])
        verdict, checks = await self.checker.check(insight, moment, draft["labels"], draft["attempt"])
        all_checks = draft["checks"] + [c.model_dump() for c in checks]
        rejections = draft.get("rejections", [])
        if verdict.status == "rejected" and draft["attempt"] <= MAX_RETRIES:
            await ctx.send_message({**draft, "checks": all_checks, "status": "rejected", "reasons": verdict.reasons, "rejections": rejections + [verdict.model_dump()]})
            return
        await ctx.yield_output({"moment_id": moment.moment_id, "decision": draft["decision"], "verdict": verdict.model_dump(), "attempts": draft["attempts"], "checks": all_checks, "rejections": rejections})


def build_workflow(writer: InsightWriter, checker: FactChecker, director: Director | None = None) -> Workflow:
    analyst = DirectorExecutor(director or RuleDirector())
    commentator = CommentatorExecutor(writer)
    fact_checker = FactCheckerExecutor(checker)
    return (
        WorkflowBuilder(name="commentary", start_executor=analyst, output_from=[analyst, fact_checker])
        .add_edge(analyst, commentator, condition=is_said)
        .add_edge(commentator, fact_checker)
        .add_edge(fact_checker, commentator, condition=is_rejected)
        .build()
    )


async def run_moment(workflow: Workflow, moment: CandidateMoment, labels: dict[str, str] | None = None, pacing: PacingState | None = None) -> MomentResult:
    request = json.dumps({"moment": moment.model_dump(), "labels": labels or moment_labels(moment), "pacing": (pacing or PacingState()).model_dump()})
    result = await retry_call(lambda: workflow.run(request))
    assert result is not None
    [output] = result.get_outputs()
    return MomentResult(
        moment_id=output["moment_id"],
        decision=DirectorDecision.model_validate(output["decision"]),
        verdict=Verdict.model_validate(output["verdict"]) if output["verdict"] else None,
        attempts=[Insight.model_validate(a) for a in output["attempts"]],
        checks=[NumberCheck.model_validate(c) for c in output["checks"]],
        rejections=[Verdict.model_validate(r) for r in output.get("rejections", [])],
    )
