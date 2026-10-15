"""Cross-module payloads for the agent pipeline (SPEC.md "Interfaces")."""

from typing import Literal

from pydantic import BaseModel, Field

Gate = Literal["insight", "producer", "speech"]


class Insight(BaseModel):
    moment_id: str
    claim: str
    why_it_matters: str
    evidence_refs: list[str]
    confidence: float = Field(ge=0, le=1)


class Verdict(BaseModel):
    moment_id: str
    status: Literal["verified", "rewritten", "rejected"]
    insight: Insight | None
    reasons: list[str]
    layer: Literal["code", "llm"]
    attempt: int


class NumberCheck(BaseModel):
    """One record per gate pass; logged and counted in the run report."""

    gate: Gate
    moment_id: str
    profile_key: str | None = None
    text: str
    ok: bool
    mismatches: list[str]


class OverlayCue(BaseModel):
    moment_id: str
    show_at_seq: int
    duration_s: int
    priority: Literal["low", "normal", "high"]
    headline: str = Field(max_length=60)
    metric_label: str | None = None
    metric_value: str | None = None


class FanProfile(BaseModel):
    club_id: str | None = None
    player_id: str | None = None
    depth: Literal["casual", "analyst"] = "casual"
    language: Literal["en", "tr"] = "en"

    def key(self) -> str:
        return f"{self.club_id or '-'}|{self.player_id or '-'}|{self.depth}|{self.language}"


class FanNarrative(BaseModel):
    moment_id: str
    profile_key: str
    text: str


class WordingVerdict(BaseModel):
    """Layer 2 (LLM) output: a judgment on wording only. Rewrites re-enter the code layer."""

    status: Literal["verified", "rewritten", "rejected"]
    reasons: list[str] = Field(default_factory=list)
    claim: str | None = None
    why_it_matters: str | None = None


class MomentResult(BaseModel):
    """What one workflow run returns for one moment."""

    moment_id: str
    verdict: Verdict
    attempts: list[Insight]
    checks: list[NumberCheck]
