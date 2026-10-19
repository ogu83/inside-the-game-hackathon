"""Two-layer Fact-Checker: code first (numbers, keys), then a model for wording only."""

from typing import Any, Protocol

from app.agents.fact_check_rules import check_insight, cited_evidence, wording_flags
from app.agents.models import Insight, NumberCheck, Verdict, WordingVerdict
from app.agents.prompts import wording_prompt
from app.ledger.models import CandidateMoment


class WordingJudge(Protocol):
    async def judge(self, insight: Insight, cited: dict[str, float], labels: dict[str, str]) -> WordingVerdict: ...


class FoundryWordingJudge:
    def __init__(self, agent: Any) -> None:
        self.agent = agent

    async def judge(self, insight: Insight, cited: dict[str, float], labels: dict[str, str]) -> WordingVerdict:
        flags = wording_flags(f"{insight.claim} {insight.why_it_matters}", cited)
        response = await self.agent.run(
            wording_prompt(insight, cited, labels, flags),
            options={"response_format": WordingVerdict, "max_tokens": 250},
        )
        value = response.value
        return WordingVerdict.model_validate(value if isinstance(value, dict) else value.model_dump())


class FactChecker:
    def __init__(self, judge: WordingJudge | None) -> None:
        self.judge = judge

    async def check(self, insight: Insight, moment: CandidateMoment, labels: dict[str, str], attempt: int) -> tuple[Verdict, list[NumberCheck]]:
        rejected, check = check_insight(insight, moment, attempt, labels)
        checks = [check]
        if rejected is not None:
            return rejected, checks
        if self.judge is None:
            return Verdict(moment_id=moment.moment_id, status="verified", insight=insight, reasons=[], layer="code", attempt=attempt), checks

        cited, _ = cited_evidence(insight, moment)
        wording = await self.judge.judge(insight, cited, labels)
        if wording.status == "rejected":
            return Verdict(moment_id=moment.moment_id, status="rejected", insight=insight, reasons=wording.reasons or ["wording rejected"], layer="llm", attempt=attempt), checks
        if wording.status == "rewritten":
            rewritten = insight.model_copy(update={"claim": wording.claim or insight.claim, "why_it_matters": wording.why_it_matters or insight.why_it_matters})
            rejected_rewrite, recheck = check_insight(rewritten, moment, attempt, labels)
            checks.append(recheck)
            if rejected_rewrite is not None:
                reasons = ["rewrite failed the number check"] + rejected_rewrite.reasons
                return Verdict(moment_id=moment.moment_id, status="rejected", insight=insight, reasons=reasons, layer="code", attempt=attempt), checks
            return Verdict(moment_id=moment.moment_id, status="rewritten", insight=rewritten, reasons=wording.reasons, layer="llm", attempt=attempt), checks
        return Verdict(moment_id=moment.moment_id, status="verified", insight=insight, reasons=wording.reasons, layer="llm", attempt=attempt), checks
