"""Commentator: turns a CandidateMoment into an Insight. The Foundry version calls a model."""

from typing import Any, Protocol

from app.agents.models import Insight
from app.agents.prompts import commentator_prompt
from app.ledger.models import CandidateMoment


class InsightWriter(Protocol):
    async def write(self, moment: CandidateMoment, labels: dict[str, str], feedback: list[str]) -> Insight: ...


class FoundryCommentator:
    """Wraps an Agent Framework agent (FoundryChatClient.as_agent) with structured output."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    async def write(self, moment: CandidateMoment, labels: dict[str, str], feedback: list[str]) -> Insight:
        response = await self.agent.run(
            commentator_prompt(moment, labels, feedback),
            options={"response_format": Insight, "max_tokens": 250},
        )
        insight = Insight.model_validate(response.value if isinstance(response.value, dict) else response.value.model_dump())
        return insight.model_copy(update={"moment_id": moment.moment_id})
