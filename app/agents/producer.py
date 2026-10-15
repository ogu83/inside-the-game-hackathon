"""Producer: one verified insight, many renderings (SPEC design rules 2b and 5).

The overlay cue is rendered once; fan narratives are rendered once per active profile, in parallel.
Every rendering passes the producer gate (`check_rendering`); a failed rendering is regenerated once
with the gate's reasons as feedback, then dropped for that profile only. A `Renderer` produces text;
the `Producer` owns gating, retries and the planted-error tamper hook.
"""

import asyncio
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel

from app.agents.fact_check_rules import check_rendering, cited_evidence
from app.agents.models import FanNarrative, FanProfile, Insight, NumberCheck, OverlayCue
from app.agents.prompts import cue_prompt, narrative_prompt
from app.ledger.labels import profile_labels
from app.ledger.models import CandidateMoment

Tamper = Callable[[str, str, str, str], str]  # (text, moment_id, profile_key, lang) -> text


class CueDraft(BaseModel):
    headline: str
    metric_label: str | None = None
    metric_value: str | None = None
    priority: str = "normal"


class Renderer(Protocol):
    async def cue(self, insight: Insight, moment: CandidateMoment, labels: dict[str, str], feedback: list[str]) -> CueDraft: ...

    async def narrative(self, insight: Insight, moment: CandidateMoment, labels: dict[str, str], profile: FanProfile, feedback: list[str]) -> str: ...


class FoundryRenderer:
    """Model renderer with digits-only prompts; structured output for the cue."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    async def cue(self, insight: Insight, moment: CandidateMoment, labels: dict[str, str], feedback: list[str]) -> CueDraft:
        response = await self.agent.run(cue_prompt(insight, moment, labels, feedback), options={"response_format": CueDraft})
        value = response.value
        return CueDraft.model_validate(value if isinstance(value, dict) else value.model_dump())

    async def narrative(self, insight: Insight, moment: CandidateMoment, labels: dict[str, str], profile: FanProfile, feedback: list[str]) -> str:
        response = await self.agent.run(narrative_prompt(insight, moment, labels, profile, feedback))
        return (response.text or "").strip()


class ProducerOutput(BaseModel):
    moment_id: str
    cue: OverlayCue | None
    narratives: list[FanNarrative]
    checks: list[NumberCheck]
    dropped_profiles: list[str]
    regenerated: int = 0


class Producer:
    def __init__(self, renderer: Renderer, tamper: Tamper | None = None, max_regenerations: int = 1) -> None:
        self.renderer = renderer
        self.tamper = tamper
        self.max_regenerations = max_regenerations

    def _text(self, text: str, moment_id: str, profile_key: str, lang: str) -> str:
        return self.tamper(text, moment_id, profile_key, lang) if self.tamper else text

    async def render(self, insight: Insight, moment: CandidateMoment, labels: dict[str, str], profiles: list[FanProfile]) -> ProducerOutput:
        cited, _ = cited_evidence(insight, moment)
        cue_task = self._render_cue(insight, moment, labels, cited)
        narrative_tasks = [self._render_narrative(insight, moment, labels, cited, p) for p in profiles]
        cue_result, *narrative_results = await asyncio.gather(cue_task, *narrative_tasks)
        cue, cue_checks = cue_result
        checks = list(cue_checks)
        narratives, dropped = [], []
        for profile, (narrative, profile_checks) in zip(profiles, narrative_results, strict=True):
            checks += profile_checks
            if narrative is None:
                dropped.append(profile.key())
            else:
                narratives.append(narrative)
        regenerated = sum(len(group) - 1 for group in [cue_checks, *(pc for _, pc in narrative_results)])
        return ProducerOutput(moment_id=moment.moment_id, cue=cue, narratives=narratives, checks=checks, dropped_profiles=dropped, regenerated=regenerated)

    async def _render_cue(self, insight: Insight, moment: CandidateMoment, labels: dict[str, str], cited: dict[str, float]) -> tuple[OverlayCue | None, list[NumberCheck]]:
        checks: list[NumberCheck] = []
        feedback: list[str] = []
        for _ in range(self.max_regenerations + 1):
            draft = await self.renderer.cue(insight, moment, labels, feedback)
            source = f"{draft.headline} {draft.metric_value or ''}"
            metric = self._text(draft.metric_value, moment.moment_id, "broadcast", "en") if draft.metric_value is not None else None
            headline = self._text(draft.headline, moment.moment_id, "broadcast", "en")[:60]
            check = check_rendering(f"{headline} {metric or ''}", cited, source, moment_id=moment.moment_id, profile_key="broadcast", coverage="all")
            checks.append(check)
            if check.ok:
                priority = draft.priority if draft.priority in ("low", "normal", "high") else "normal"
                cue = OverlayCue(moment_id=moment.moment_id, show_at_seq=moment.window[1], duration_s=8, priority=priority,
                                 headline=headline, metric_label=draft.metric_label, metric_value=metric)
                return cue, checks
            feedback = check.mismatches
        return None, checks

    async def _render_narrative(self, insight: Insight, moment: CandidateMoment, labels: dict[str, str], cited: dict[str, float], profile: FanProfile) -> tuple[FanNarrative | None, list[NumberCheck]]:
        checks: list[NumberCheck] = []
        feedback: list[str] = []
        coverage = "all" if profile.depth == "analyst" else "any"
        labels = profile_labels(labels, profile.club_id, profile.player_id)
        for _ in range(self.max_regenerations + 1):
            text = await self.renderer.narrative(insight, moment, labels, profile, feedback)
            text = self._text(text, moment.moment_id, profile.key(), profile.language)
            check = check_rendering(text, cited, insight.claim, moment_id=moment.moment_id, profile_key=profile.key(), lang=profile.language, coverage=coverage)
            checks.append(check)
            if check.ok:
                return FanNarrative(moment_id=moment.moment_id, profile_key=profile.key(), text=text), checks
            feedback = check.mismatches
        return None, checks
