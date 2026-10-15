"""Planted-error harness (SPEC testing strategy): corrupt N insights and N renderings per match and count
what each gate catches. The target is 0 planted errors reaching a cue, a narrative or the voice.

Insight corruptions (attempt 1 only, so the retry can recover):
- wrong_number: a cited number in the claim is replaced by a value that is not in the evidence
- missing_key: the insight cites a key that does not exist and quotes a number for it
- swapped_team: the claim names the opponent instead of the team (numbers stay right: only layer 2 can catch it)

Rendering corruptions (applied through the Producer's tamper hook, before the producer gate):
- changed_number, dropped_number, number_as_word (English or Turkish, so translations are covered)
"""

import random
import re
from dataclasses import dataclass, field
from typing import Literal

from app.agents.fact_check_rules import extract_numbers
from app.agents.models import Insight, MomentResult
from app.ledger.models import CandidateMoment

InsightCorruption = Literal["wrong_number", "missing_key", "swapped_team"]
RenderingCorruption = Literal["changed_number", "dropped_number", "number_as_word"]
INSIGHT_KINDS: tuple[InsightCorruption, ...] = ("wrong_number", "missing_key", "swapped_team")
RENDERING_KINDS: tuple[RenderingCorruption, ...] = ("changed_number", "dropped_number", "number_as_word")

_EN = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
       "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_TR = ["sıfır", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_TR_TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]


def number_to_words(value: int, lang: str) -> str:
    value = abs(int(value))
    if value >= 100:
        return f"{number_to_words(value // 100, lang)} {'hundred' if lang == 'en' else 'yüz'}" + (f" {number_to_words(value % 100, lang)}" if value % 100 else "")
    if lang == "tr":
        return (_TR_TENS[value // 10] + (" " + _TR[value % 10] if value % 10 else "")).strip() if value >= 10 else _TR[value]
    if value < 20:
        return _EN[value]
    return _EN_TENS[value // 10] + (" " + _EN[value % 10] if value % 10 else "")


def _first_number(text: str, lang: str):
    found = extract_numbers(text, lang)
    return found[0] if found else None


def _replace_first(text: str, raw: str, replacement: str) -> str:
    return text.replace(raw, replacement, 1)


def corrupt_text(text: str, lang: str, kind: RenderingCorruption, rng: random.Random) -> str:
    """Return a corrupted copy, or the text unchanged when it has no number to corrupt."""
    number = _first_number(text, lang)
    if number is None:
        return text
    digits = re.search(r"-?\d+(?:[.,]\d+)?", number.raw)
    assert digits is not None
    if kind == "changed_number":
        bumped = number.value + rng.choice([1, 2, 3, 5, 10])
        new = f"{bumped:g}".replace(".", "," if lang == "tr" else ".")
        return _replace_first(text, digits.group(0), new)
    if kind == "dropped_number":
        return re.sub(r"\s{2,}", " ", _replace_first(text, number.raw, "")).strip()
    words = number_to_words(round(number.value), lang)
    return _replace_first(text, digits.group(0), words)


def corrupt_insight(insight: Insight, moment: CandidateMoment, labels: dict[str, str], kind: InsightCorruption, rng: random.Random) -> Insight:
    if kind == "wrong_number":
        number = _first_number(insight.claim, "en")
        if number is None:
            return insight.model_copy(update={"claim": f"{insight.claim} They have had 6 shots."})
        wrong = number.value + rng.choice([1, 2, 3, 5, 10])
        while any(abs(v - wrong) < 1e-9 for v in moment.evidence.values()):
            wrong += 1
        return insight.model_copy(update={"claim": _replace_first(insight.claim, number.raw, f"{wrong:g}")})
    if kind == "missing_key":
        return insight.model_copy(update={
            "claim": f"{insight.claim} They have had 6 shots in this spell.",
            "evidence_refs": [*insight.evidence_refs, "team_shots_last_10min"],
        })
    team, opponent = labels.get("team", moment.team_id), labels.get("opponent", "the opposition")
    swapped = insight.claim.replace(team, "\x00").replace(opponent, team).replace("\x00", opponent)
    return insight.model_copy(update={"claim": swapped})


@dataclass
class PlantPlan:
    """Which moments get which corruption. Built from a seed so runs are reproducible."""

    insights: dict[str, InsightCorruption] = field(default_factory=dict)      # moment_id -> kind
    renderings: dict[str, RenderingCorruption] = field(default_factory=dict)  # moment_id -> kind (every profile of that moment)

    @classmethod
    def build(cls, moment_ids: list[str], n_insights: int, n_renderings: int, seed: int = 0) -> "PlantPlan":
        rng = random.Random(seed)
        ids = list(moment_ids)
        rng.shuffle(ids)
        insights = {m: INSIGHT_KINDS[i % len(INSIGHT_KINDS)] for i, m in enumerate(ids[:n_insights])}
        rest = ids[n_insights:] or ids
        renderings = {m: RENDERING_KINDS[i % len(RENDERING_KINDS)] for i, m in enumerate(rest[:n_renderings])}
        return cls(insights=insights, renderings=renderings)


class PlantingCommentator:
    """Wraps an InsightWriter and corrupts attempt 1 of the planned moments."""

    def __init__(self, inner, plan: PlantPlan, seed: int = 0) -> None:
        self.inner = inner
        self.plan = plan
        self.rng = random.Random(seed)
        self.planted: dict[str, Insight] = {}

    async def write(self, moment: CandidateMoment, labels: dict[str, str], feedback: list[str]) -> Insight:
        insight = await self.inner.write(moment, labels, feedback)
        kind = self.plan.insights.get(moment.moment_id)
        if kind is None or feedback:
            return insight
        corrupted = corrupt_insight(insight, moment, labels, kind, self.rng)
        self.planted[moment.moment_id] = corrupted
        return corrupted


def make_tamper(plan: PlantPlan, seed: int = 0, log: list[tuple[str, str, str]] | None = None):
    """A Producer tamper hook that corrupts every rendering of the planned moments."""
    rng = random.Random(seed)

    def tamper(text: str, moment_id: str, profile_key: str, lang: str) -> str:
        kind = plan.renderings.get(moment_id)
        if kind is None or (kind == "dropped_number" and "|casual|" in profile_key):
            return text  # a casual narrative may legitimately drop numbers (coverage "any"), so there is nothing to catch
        corrupted = corrupt_text(text, lang, kind, rng)
        if corrupted != text and log is not None:
            log.append((moment_id, profile_key, kind))
        return corrupted

    return tamper


@dataclass
class KindCount:
    planted: int = 0
    caught_by_code: int = 0
    caught_by_llm: int = 0
    reached_air: int = 0


@dataclass
class PlantedReport:
    insights: dict[str, KindCount] = field(default_factory=lambda: {k: KindCount() for k in INSIGHT_KINDS})
    renderings: dict[str, KindCount] = field(default_factory=lambda: {k: KindCount() for k in RENDERING_KINDS})
    reached_air_detail: list[str] = field(default_factory=list)

    @property
    def planted(self) -> int:
        return sum(c.planted for c in [*self.insights.values(), *self.renderings.values()])

    @property
    def caught(self) -> int:
        return sum(c.caught_by_code + c.caught_by_llm for c in [*self.insights.values(), *self.renderings.values()])

    @property
    def reached_air(self) -> int:
        return sum(c.reached_air for c in [*self.insights.values(), *self.renderings.values()])

    def as_dict(self) -> dict:
        return {
            "planted": self.planted, "caught": self.caught, "reached_air": self.reached_air,
            "insights": {k: vars(v) for k, v in self.insights.items()},
            "renderings": {k: vars(v) for k, v in self.renderings.items()},
        }

    def headline(self) -> str:
        return f"caught {self.caught} of {self.planted} planted errors, {self.reached_air} reached air"


def report_insights(results: list[MomentResult], commentator: PlantingCommentator, report: PlantedReport) -> None:
    for result in results:
        planted = commentator.planted.get(result.moment_id)
        if planted is None or result.verdict is None:
            continue
        kind = commentator.plan.insights[result.moment_id]
        count = report.insights[kind]
        count.planted += 1
        verdict = result.verdict
        first = result.rejections[0] if result.rejections else (verdict if verdict.status == "rejected" else None)
        if first is not None and first.layer == "code":
            count.caught_by_code += 1
        elif first is not None or (verdict.status == "rewritten" and verdict.insight and verdict.insight.claim != planted.claim):
            count.caught_by_llm += 1
        elif verdict.insight is not None and verdict.insight.claim == planted.claim:
            count.reached_air += 1
            report.reached_air_detail.append(f"insight ({kind}) {result.moment_id}: {planted.claim}")
