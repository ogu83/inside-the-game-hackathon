"""Fact-Checker layer 1: deterministic number rules, no model.

Used at every gate where a number can change (SPEC.md design rule 2): the Commentator's
Insight, each Producer rendering, and each text sent to the voice.

Parser rules (English and Turkish):
- `68%`, `%68`, `yüzde 68`, `yuzde 68`     -> 68 (percent marker ignored for matching)
- `68.5` (en) and `68,5` (tr) are decimals;  `1,250` (en) and `1.250` (tr) are thousands
- `23rd`, `14th`, `23.` (Turkish ordinal dot) -> 23;  `14'ü`, `%68'lik` (Turkish suffix) -> 14, 68
- a number glued to a letter or to a `letter-` prefix is an identifier, not a number (`kby-07`, `x2`)
- a number followed by minute(s)/min/dakika carries unit "min"; second(s)/saniye "s"
- number words fail the digits-only rule, except "one"/"bir" (articles and pronouns) and ordinal words

Matching rule: a text number matches a cited evidence value when that value, rounded half-up to the
text's number of decimals, equals it. Keys ending in `_s` also match in minutes (value / 60) when the
text says minutes. Qualified approximations ("over 50 metres" against 52.5) fail by design.
"""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.agents.models import Gate, Insight, NumberCheck, Verdict
from app.ledger.models import CandidateMoment

Lang = str  # "en" | "tr"

_PERCENT_PREFIX = r"(?:%\s?|(?:yüzde|yuzde|y[üu]zde)\s+)"
_NUMBER_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?<![A-Za-z]-)(?P<pct_pre>{_PERCENT_PREFIX})?"
    r"(?P<sign>-)?(?P<body>\d+(?:[.,]\d+)*)"
    r"(?P<tail>%|(?:st|nd|rd|th)\b|\.(?!\d)|'[^\s.,;:!?]*)?",
    re.IGNORECASE,
)
_UNIT_RE = re.compile(r"^\s*(?:-\s*)?(?P<unit>minutes?|mins?|dakika\w*|dk|seconds?|secs?|saniye\w*|sn|metres?|meters?|m)\b", re.IGNORECASE)

_EN_WORDS = {
    "zero", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
    "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
    "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "dozen",
}
# ASCII-folded Turkish number words; "bir" (one / a) is deliberately absent.
_TR_WORDS = {
    "sifir", "iki", "uc", "dort", "bes", "alti", "yedi", "sekiz", "dokuz", "on", "yirmi", "otuz", "kirk",
    "elli", "altmis", "yetmis", "seksen", "doksan", "yuz", "bin",
}
_TR_FOLD = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


@dataclass(frozen=True)
class FoundNumber:
    value: float
    raw: str
    decimals: int
    unit: str | None  # "pct", "min", "s", "m" or None


def _fold(word: str) -> str:
    return word.translate(_TR_FOLD).casefold()


def _parse_body(body: str, lang: Lang) -> tuple[float, int] | None:
    """Digits with separators -> (value, decimals), honouring the language's separator roles."""
    thousands, decimal = (".", ",") if lang == "tr" else (",", ".")
    if body.count(thousands) and re.fullmatch(rf"\d{{1,3}}(?:{re.escape(thousands)}\d{{3}})+", body):
        return float(body.replace(thousands, "")), 0
    if body.count(decimal) == 1 and thousands not in body:
        whole, frac = body.split(decimal)
        return float(f"{whole}.{frac}"), len(frac)
    if decimal not in body and thousands not in body:
        return float(body), 0
    # one separator of the "other" kind, e.g. 68,5 in English text: read it as a decimal
    other = thousands
    if body.count(other) == 1 and decimal not in body:
        whole, frac = body.split(other)
        if len(frac) != 3:
            return float(f"{whole}.{frac}"), len(frac)
        return float(whole + frac), 0
    return None


def extract_numbers(text: str, lang: Lang = "en") -> list[FoundNumber]:
    found: list[FoundNumber] = []
    for m in _NUMBER_RE.finditer(text):
        parsed = _parse_body(m.group("body"), lang)
        if parsed is None:
            continue
        value, decimals = parsed
        if m.group("sign"):
            value = -value
        tail = m.group("tail") or ""
        unit: str | None = None
        if m.group("pct_pre") or tail == "%":
            unit = "pct"
        else:
            unit_match = _UNIT_RE.match(text[m.end():])
            if unit_match:
                word = unit_match.group("unit").casefold()
                unit = "min" if word.startswith(("min", "dak", "dk")) else "s" if word.startswith(("sec", "san", "sn")) else "m"
        found.append(FoundNumber(value=value, raw=m.group(0).strip(), decimals=decimals, unit=unit))
    return found


def number_words(text: str, lang: Lang = "en") -> list[str]:
    """Runs of number words written out in letters, e.g. ["six", "altmış sekiz"]."""
    vocab = _TR_WORDS if lang == "tr" else _EN_WORDS
    runs: list[str] = []
    current: list[str] = []
    last_end = -1
    for m in _WORD_RE.finditer(text):
        word = m.group(0)
        if _fold(word) in vocab:
            if current and text[last_end:m.start()].strip() not in ("", "-"):
                runs.append(" ".join(current))
                current = []
            current.append(word)
            last_end = m.end()
        elif current:
            runs.append(" ".join(current))
            current = []
    if current:
        runs.append(" ".join(current))
    return runs


def round_half_up(value: float, decimals: int) -> float:
    quantum = Decimal(1).scaleb(-decimals)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def _candidates(key: str, value: float, unit: str | None) -> list[float]:
    values = [value]
    if unit == "min" and key.endswith("_s"):
        values.append(value / 60)
    if unit == "s" and (key.endswith("_min") or key.endswith("_minutes")):
        values.append(value * 60)
    return values


def matches(number: FoundNumber, cited: dict[str, float]) -> bool:
    for key, value in cited.items():
        for candidate in _candidates(key, value, number.unit):
            if abs(round_half_up(candidate, number.decimals) - number.value) < 1e-9:
                return True
    return False


def _describe(cited: dict[str, float]) -> str:
    if not cited:
        return "no evidence cited"
    return ", ".join(f"{k} = {v:g}" for k, v in list(cited.items())[:6])


def check_numbers(
    text: str,
    cited: dict[str, float],
    *,
    gate: Gate,
    moment_id: str,
    profile_key: str | None = None,
    lang: Lang = "en",
) -> NumberCheck:
    """The reusable gate: every digit number must match a cited value; number words are not allowed."""
    mismatches = [f"{n.raw} not in cited evidence ({_describe(cited)})" for n in extract_numbers(text, lang) if not matches(n, cited)]
    mismatches += [f"number written as word: {w}" for w in number_words(text, lang)]
    return NumberCheck(gate=gate, moment_id=moment_id, profile_key=profile_key, text=text, ok=not mismatches, mismatches=mismatches)


Coverage = str  # "all" | "any" | "none"

# Evaluative words a commentator reaches for; each needs a supporting number. Checked by code as a hint for layer 2.
EVALUATIVE_WORDS: dict[str, str] = {
    "control": "possession", "controlled": "possession", "controlling": "possession", "dominate": "possession", "dominated": "possession",
    "dominating": "possession", "dominant": "possession", "dominance": "possession", "dictate": "possession", "dictated": "possession",
    "dictating": "possession", "tempo": "possession", "one-way": "possession", "in charge": "possession", "bossing": "possession",
    "suffocating": "pressing", "relentless": "pressing", "swarmed": "pressing", "overwhelmed": "pressing",
    "clinical": "shot", "ruthless": "shot", "devastating": "shot", "unstoppable": "shot",
}


def wording_support(cited: dict[str, float]) -> set[str]:
    """Which evaluative families the cited numbers support."""
    support: set[str] = set()
    if cited.get("team_possession_pct_window", 0.0) >= 60 and cited.get("window_minutes", 0.0) >= 3:
        support.add("possession")
    if cited.get("pass_streak_passes", 0.0) >= 15:
        support.add("possession")
    if cited.get("pressing_trap_pressures", 0.0) >= 3 or cited.get("team_regains_last_10min", 0.0) >= 3:
        support.add("pressing")
    if cited.get("pass_streak_ended_in_shot", 0.0) >= 1:
        support.add("shot")
    return support


def wording_flags(text: str, cited: dict[str, float]) -> list[str]:
    """Evaluative words in `text` that no cited number supports, e.g. ["'dominated' (needs possession evidence)"]."""
    lowered = text.casefold()
    supported = wording_support(cited)
    flags = []
    for word, family in EVALUATIVE_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", lowered) and family not in supported:
            flags.append(f"'{word}' (needs {family} evidence)")
    return flags


def check_rendering(
    text: str,
    cited: dict[str, float],
    source_text: str,
    *,
    moment_id: str,
    profile_key: str | None,
    lang: Lang = "en",
    source_lang: Lang = "en",
    coverage: Coverage = "any",
) -> NumberCheck:
    """Producer gate: the number check plus a coverage rule against the verified source text.

    coverage "all": every number in the source must survive (analyst depth, overlay metric);
    "any": at least one must survive when the source has numbers (casual depth); "none": no rule.
    A dropped number is reported as "dropped number: 14".
    """
    check = check_numbers(text, cited, gate="producer", moment_id=moment_id, profile_key=profile_key, lang=lang)
    if coverage == "none":
        return check
    source = {round(n.value, 6) for n in extract_numbers(source_text, source_lang)}
    present = {round(n.value, 6) for n in extract_numbers(text, lang)}
    missing = sorted(source - present)
    if (coverage == "all" and missing) or (coverage == "any" and source and not present):
        dropped = [f"dropped number: {m:g}" for m in missing]
        return check.model_copy(update={"ok": False, "mismatches": check.mismatches + dropped})
    return check


def cited_evidence(insight: Insight, moment: CandidateMoment) -> tuple[dict[str, float], list[str]]:
    """Split the insight's refs into (cited values, unknown keys)."""
    cited = {k: moment.evidence[k] for k in insight.evidence_refs if k in moment.evidence}
    unknown = [k for k in insight.evidence_refs if k not in moment.evidence]
    return cited, unknown


def check_insight(insight: Insight, moment: CandidateMoment, attempt: int) -> tuple[Verdict | None, NumberCheck]:
    """Layer 1 on an Insight. Returns (rejected verdict or None, the NumberCheck record)."""
    reasons: list[str] = []
    if insight.moment_id != moment.moment_id:
        reasons.append(f"insight is about {insight.moment_id}, expected {moment.moment_id}")
    cited, unknown = cited_evidence(insight, moment)
    reasons += [f"unknown evidence key: {k}" for k in unknown]
    check = check_numbers(f"{insight.claim}\n{insight.why_it_matters}", cited, gate="insight", moment_id=moment.moment_id)
    reasons += check.mismatches
    if reasons:
        return Verdict(moment_id=moment.moment_id, status="rejected", insight=insight, reasons=reasons, layer="code", attempt=attempt), check
    return None, check


def check_speech(approved_text: str, transcript: str, cited: dict[str, float], *, moment_id: str, profile_key: str | None, lang: Lang) -> NumberCheck:
    """Speech gate: the transcript must be the approved text (ignoring case, spacing and end punctuation) and pass the number check."""
    check = check_numbers(transcript, cited, gate="speech", moment_id=moment_id, profile_key=profile_key, lang=lang)
    if _normalise(transcript) != _normalise(approved_text):
        check = check.model_copy(update={"ok": False, "mismatches": check.mismatches + ["transcript differs from approved text"]})
    return check


def _normalise(text: str) -> str:
    return re.sub(r"[\s\.\!\?,;:]+", " ", text).strip().casefold()
