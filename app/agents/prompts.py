"""Prompt constants and builders. Agents never compute numbers; they cite evidence keys."""

import json

from app.agents.models import FanProfile, Insight, PacingState
from app.ledger.models import CandidateMoment

COMMENTATOR_INSTRUCTIONS = (
    "You are a football colour commentator for a fictional league. You receive one notable moment "
    "with its evidence: a dict of ledger numbers. Write one short claim (one sentence, broadcast "
    "register) and one sentence on why it matters. Number rules: use only numbers that appear in the "
    "evidence, copied exactly as digits (never as words, never rounded, never approximated with 'about' "
    "or 'over'); every number you use must come from a key you list in evidence_refs; cite only keys that "
    "exist; name teams by the names given, never by ids; no scorelines or clock times unless they are in "
    "the evidence. If the possession window is under 3 minutes, do not talk about possession.\n"
    "Wording rules: be descriptive, not evaluative. Say what the numbers show (how many passes, how long, "
    "how many players, where the ball was won) and let the viewer judge. Do not use control, dominance or "
    "tempo language (controlled, dominated, dictating the tempo, one-way, in charge, bossing) unless a cited "
    "number supports it: possession of 60% or more over at least 3 minutes, or a streak of 15 passes or more. "
    "Do not call pressing suffocating or relentless without 3 or more pressures or regains in the evidence. "
    "Do not call finishing clinical without a shot in the evidence. 'Why it matters' states a consequence "
    "(a shot, territory gained, a tired opponent) rather than a verdict on the team."
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

PRODUCER_INSTRUCTIONS = (
    "You are the broadcast producer. You turn one verified insight into renderings for different audiences. "
    "Hard rules: every number must be written as digits, copied exactly from the insight or its cited evidence "
    "(never as words, never rounded, never approximated); do not add numbers that are not in the cited evidence; "
    "keep every number of the insight when the depth is analyst; name teams and players only as given. "
    "Write in the requested language. Return only the requested text."
)

FACT_CHECKER_INSTRUCTIONS = (
    "You are a strict broadcast fact-checker. The numbers in the claim were already verified by "
    "code; you judge only the wording. A descriptive claim that states what the numbers show is "
    "verified: do not rewrite for style. Return rewritten only when an evaluative word (dominated, "
    "controlled, dictating the tempo, one-way, suffocating, clinical) is not supported by the cited "
    "evidence, and then change only that wording, keeping every number exactly as it is, as digits. "
    "Return rejected only when the claim cannot be made fair. You may receive hints from code naming "
    "unsupported words; treat them as the main thing to fix. List reasons as short phrases."
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


def wording_prompt(insight: Insight, cited: dict[str, float], labels: dict[str, str], flags: list[str] | None = None) -> str:
    hint = f"Code flagged unsupported words: {'; '.join(flags)}.\n" if flags else "Code found no unsupported evaluative words; verify unless something else is unfair.\n"
    return (
        f"Team: {labels.get('team')}. Opponent: {labels.get('opponent')}.\n"
        f"Evidence cited: {json.dumps(evidence_for_prompt(cited))}\n"
        f"Claim: {insight.claim}\nWhy it matters: {insight.why_it_matters}\n"
        + hint + "Judge the wording only."
    )


def director_prompt(moment: CandidateMoment, labels: dict[str, str], pacing: PacingState) -> str:
    return (
        f"Team: {labels.get('team')}. Opponent: {labels.get('opponent')}. Moment kind: {labels.get('kind', moment.kind)}, "
        f"minute {moment.minute}, moment_id {moment.moment_id}.\n"
        f"Evidence: {json.dumps(evidence_for_prompt(moment.evidence))}\n"
        f"Pacing: {json.dumps(pacing.model_dump())}\n"
        "Return a DirectorDecision with moment_id, say, angle and reason."
    )


def cue_prompt(insight: Insight, moment: CandidateMoment, labels: dict[str, str], feedback: list[str]) -> str:
    lines = [
        f"Team: {labels.get('team')}. Opponent: {labels.get('opponent')}. Moment kind: {labels.get('kind', moment.kind)}.",
        f"Verified insight: {insight.claim} {insight.why_it_matters}",
        f"Cited evidence: {json.dumps(evidence_for_prompt({k: moment.evidence[k] for k in insight.evidence_refs if k in moment.evidence}))}",
        "Return a CueDraft: headline (at most 60 characters, digits only for numbers), metric_label and metric_value "
        "(the single most telling cited number as digits, or null), priority (low, normal or high).",
    ]
    if feedback:
        lines.append(f"Your previous rendering failed the number check: {feedback}. Fix it.")
    return "\n".join(lines)


def narrative_prompt(insight: Insight, moment: CandidateMoment, labels: dict[str, str], profile: FanProfile, feedback: list[str]) -> str:
    language = "English" if profile.language == "en" else "Turkish"
    depth = ("one short sentence for a casual fan" if profile.depth == "casual"
             else "two sentences for an analytically minded fan, keeping every number of the insight")
    focus = []
    if profile.club_id and labels.get("fan_club"):
        focus.append(f"the fan supports {labels['fan_club']}")
    if profile.player_id and labels.get("fan_player"):
        focus.append(f"the fan's favourite player is {labels['fan_player']} (mention them only if the insight or evidence has a number about them)")
    lines = [
        f"Team: {labels.get('team')}. Opponent: {labels.get('opponent')}. Moment kind: {labels.get('kind', moment.kind)}.",
        f"Verified insight: {insight.claim} {insight.why_it_matters}",
        f"Cited evidence: {json.dumps(evidence_for_prompt({k: moment.evidence[k] for k in insight.evidence_refs if k in moment.evidence}))}",
        f"Write the fan narrative in {language}: {depth}." + (f" Context: {'; '.join(focus)}." if focus else ""),
        "Numbers as digits only (in Turkish use %62 and 68,5 forms), copied exactly. Return only the narrative text.",
    ]
    if feedback:
        lines.append(f"Your previous rendering failed the number check: {feedback}. Fix it.")
    return "\n".join(lines)
