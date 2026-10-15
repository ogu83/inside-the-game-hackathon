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


class DirectorDecision(BaseModel):
    """The Analyst's call on one candidate moment: say it now, or stay quiet."""

    moment_id: str
    say: bool
    angle: str | None = None      # "control", "chance", "player", "pressure"
    reason: str


class PacingState(BaseModel):
    """Computed by code and handed to the director; the model never derives these numbers itself."""

    seconds_since_last_cue: float | None = None
    cues_last_2min: int = 0
    moments_last_2min: int = 0
    rank_among_recent: int = 1    # 1 = most interesting moment of the last 2 minutes
    interest: float = 0.0


class MomentResult(BaseModel):
    """What one workflow run returns for one moment. `verdict` is None when the director skipped it."""

    moment_id: str
    decision: DirectorDecision
    verdict: Verdict | None = None
    attempts: list[Insight] = Field(default_factory=list)
    checks: list[NumberCheck] = Field(default_factory=list)
