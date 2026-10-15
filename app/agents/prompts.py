"""Prompt constants and builders. Agents never compute numbers; they cite evidence keys."""

import json

from app.agents.models import Insight, PacingState
from app.ledger.models import CandidateMoment

COMMENTATOR_INSTRUCTIONS = (
    "You are a football colour commentator for a fictional league. You receive one notable moment "
    "with its evidence: a dict of ledger numbers. Write one short claim (one sentence, broadcast "
    "register) and one sentence on why it matters. Rules: use only numbers that appear in the "
    "evidence, copied exactly as digits (never as words, never rounded, never approximated with "
    "'about' or 'over'); every number you use must come from a key you list in evidence_refs; "
    "cite only keys that exist; name teams by the names given, never by ids; no scorelines or "
    "clock times unless they are in the evidence. If the possession window is under 3 minutes, "
    "do not talk about possession."
)

ANALYST_INSTRUCTIONS = (
    "You are the match director for a football broadcast. For each candidate moment you decide whether "
    "the co-commentator should say something now (say=true) or stay quiet (say=false), and which angle "
    "to take: control, chance, player or pressure. You receive the moment's evidence and a pacing state "
    "computed for you (seconds since the last cue, cues and moments in the last 2 minutes, this moment's "
    "rank among them). Stay quiet when commentary would pile up: 3 cues in 2 minutes is the ceiling, and a "
    "moment inside 30 seconds of the last cue must be exceptional (rank 1) to be said. Never compute or "
    "quote numbers; give a short reason."
)

FACT_CHECKER_INSTRUCTIONS = (
    "You are a strict broadcast fact-checker. The numbers in the claim were already verified by "
    "code; you judge only the wording. Compare qualitative words (dominated, one-way, control, "
    "pressure, struggling) with the evidence. Return verified if the wording is a fair reading, "
    "rewritten with corrected claim and why_it_matters if a word overstates the evidence (keep "
    "every number exactly as it is, as digits), or rejected if the claim cannot be made fair. "
    "List reasons as short phrases."
)


def evidence_for_prompt(evidence: dict[str, float]) -> dict[str, int | float]:
    """Integral values are shown as integers so a model copies "14", not "14.0"; the number check accepts both."""
    return {k: int(v) if float(v).is_integer() else v for k, v in evidence.items()}


def commentator_prompt(moment: CandidateMoment, labels: dict[str, str], feedback: list[str]) -> str:
    lines = [
        f"League: {labels.get('league', 'fictional league')}. Team: {labels.get('team')}. Opponent: {labels.get('opponent')}.",
        f"Moment kind: {labels.get('kind', moment.kind)}, minute {moment.minute}, moment_id {moment.moment_id}.",
        *([f"Most involved player: {labels['top_player']} (top_player_passes or top_player_pressures)."] if labels.get("top_player") else []),
        *([f"Angle to take: {labels['angle']}."] if labels.get("angle") else []),
        f"Evidence: {json.dumps(evidence_for_prompt(moment.evidence))}",
        "Return an Insight with moment_id, claim, why_it_matters, evidence_refs and confidence (0 to 1).",
    ]
    if feedback:
        lines.append(f"Your previous attempt was rejected for these reasons: {feedback}. Write a corrected insight.")
    return "\n".join(lines)


def wording_prompt(insight: Insight, cited: dict[str, float], labels: dict[str, str]) -> str:
    return (
        f"Team: {labels.get('team')}. Opponent: {labels.get('opponent')}.\n"
        f"Evidence cited: {json.dumps(evidence_for_prompt(cited))}\n"
        f"Claim: {insight.claim}\nWhy it matters: {insight.why_it_matters}\n"
        "Judge the wording only."
    )


def director_prompt(moment: CandidateMoment, labels: dict[str, str], pacing: PacingState) -> str:
    return (
        f"Team: {labels.get('team')}. Opponent: {labels.get('opponent')}. Moment kind: {labels.get('kind', moment.kind)}, "
        f"minute {moment.minute}, moment_id {moment.moment_id}.\n"
        f"Evidence: {json.dumps(evidence_for_prompt(moment.evidence))}\n"
        f"Pacing: {json.dumps(pacing.model_dump())}\n"
        "Return a DirectorDecision with moment_id, say, angle and reason."
    )
