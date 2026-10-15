"""Commentator -> Fact-Checker graph workflow with one retry (Agent Framework).

Messages between executors are JSON-safe dicts (the hosted checkpoint store refuses custom classes);
each executor re-validates them into the SPEC models before doing anything with them.
"""

import json
from typing import Any

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler

from app.agents.commentator import InsightWriter
from app.agents.fact_checker import FactChecker
from app.agents.models import Insight, MomentResult, NumberCheck, Verdict
from app.ledger.labels import moment_labels
from app.ledger.models import CandidateMoment

MAX_RETRIES = 1


def is_rejected(message: Any) -> bool:
    return isinstance(message, dict) and message.get("status") == "rejected"


class CommentatorExecutor(Executor):
    def __init__(self, writer: InsightWriter) -> None:
        super().__init__(id="commentator")
        self.writer = writer

    @handler
    async def start(self, request: str, ctx: WorkflowContext[dict]) -> None:
        payload = json.loads(request)
        moment = CandidateMoment.model_validate(payload["moment"])
        labels = dict(payload.get("labels") or moment_labels(moment))
        insight = await self.writer.write(moment, labels, [])
        await ctx.send_message({"moment": moment.model_dump(), "labels": labels, "insight": insight.model_dump(), "attempt": 1, "attempts": [insight.model_dump()], "checks": []})

    @handler
    async def retry(self, draft: dict, ctx: WorkflowContext[dict]) -> None:
        moment = CandidateMoment.model_validate(draft["moment"])
        insight = await self.writer.write(moment, draft["labels"], list(draft["reasons"]))
        await ctx.send_message({
            **{k: draft[k] for k in ("moment", "labels", "checks")},
            "insight": insight.model_dump(), "attempt": draft["attempt"] + 1, "attempts": draft["attempts"] + [insight.model_dump()],
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
        if verdict.status == "rejected" and draft["attempt"] <= MAX_RETRIES:
            await ctx.send_message({**draft, "checks": all_checks, "status": "rejected", "reasons": verdict.reasons})
            return
        await ctx.yield_output({"moment_id": moment.moment_id, "verdict": verdict.model_dump(), "attempts": draft["attempts"], "checks": all_checks})


def build_workflow(writer: InsightWriter, checker: FactChecker) -> Workflow:
    commentator = CommentatorExecutor(writer)
    fact_checker = FactCheckerExecutor(checker)
    return (
        WorkflowBuilder(name="commentary", start_executor=commentator, output_from=[fact_checker])
        .add_edge(commentator, fact_checker)
        .add_edge(fact_checker, commentator, condition=is_rejected)
        .build()
    )


async def run_moment(workflow: Workflow, moment: CandidateMoment, labels: dict[str, str] | None = None) -> MomentResult:
    request = json.dumps({"moment": moment.model_dump(), "labels": labels or moment_labels(moment)})
    result = await workflow.run(request)
    [output] = result.get_outputs()
    return MomentResult(
        moment_id=output["moment_id"],
        verdict=Verdict.model_validate(output["verdict"]),
        attempts=[Insight.model_validate(a) for a in output["attempts"]],
        checks=[NumberCheck.model_validate(c) for c in output["checks"]],
    )
