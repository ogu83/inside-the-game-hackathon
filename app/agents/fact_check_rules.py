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
# The noun after a number names the fact it quotes; a family must match a cited key that carries it (key-aware matching).
_FAMILY_RE = re.compile(
    r"^\s*(?:-\s*|\s+)?(?:(?:completed|consecutive|straight|successful|quick|different|separate|high|more|fewer|art arda|ardışık|farklı|isabetli)\s+)?"
    r"(?P<noun>pass(?:es)?|pas\w*|pressures?|presses|bask[ıi]\w*|players?|oyuncu\w*|shots?|[şs]ut\w*|goals?|gol\w*|regains?|"
    r"interceptions?|tackles?|touches|touch|seconds?|secs?|saniye\w*|minutes?|mins?|dakika\w*|metres?|meters?|percent|yüzde|yuzde)\b",
    re.IGNORECASE,
)
_TIME = ("_s", "second", "duration", "minute", "_min")  # seconds and minutes cross-match through unit conversion
FAMILIES: dict[str, tuple[str, ...]] = {  # family -> fragments a cited key must contain ("_x" fragments must end the key)
    "passes": ("pass",), "pressures": ("pressure",), "players": ("player",), "shots": ("shot",), "goals": ("goal",),
    "regains": ("regain",), "interceptions": ("intercept",), "tackles": ("tackle",), "touches": ("touch",),
    "seconds": _TIME, "minutes": _TIME, "metres": ("_m", "metre", "distance", "progress"), "pct": ("pct", "percent"),
}
_NOUN_FAMILY = [
    (("pass", "pas"), "passes"), (("pressure", "press", "bask"), "pressures"), (("player", "oyuncu"), "players"), (("shot", "şut", "sut"), "shots"),
    (("goal", "gol"), "goals"), (("regain",), "regains"), (("intercept",), "interceptions"), (("tackle",), "tackles"), (("touch",), "touches"),
    (("sec", "san"), "seconds"), (("min", "dak"), "minutes"), (("met",), "metres"), (("percent", "yüzde", "yuzde"), "pct"),
]


def _family_of(noun: str) -> str | None:
    folded = noun.casefold()
    for prefixes, family in _NOUN_FAMILY:
        if folded.startswith(prefixes):
            return family
    return None

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
    family: str | None = None  # the fact the number quotes, from the noun after it: "passes", "pressures", "seconds", ...
    is_minute_context: bool = False


def _fold(word: str) -> str:
    return word.translate(_TR_FOLD).casefold()


_MINUTE_BEFORE_RE = re.compile(r"(?:\b(?:at|in|on)\s+)?\b(?:minutes?|mins?|dakika\w*|dk)\.?\s*$", re.IGNORECASE)
_AT_BEFORE_RE = re.compile(r"\bat\s+$", re.IGNORECASE)
_MINUTE_AFTER_RE = re.compile(r"^\s*(?:-\s*)?(?:minutes?|mins?|dakika\w*|dk\.?)\b", re.IGNORECASE)
_ORDINAL_TAIL_RE = re.compile(r"^(?:st|nd|rd|th|\.|\'?[ıiuü]nc[ıiuü]|\'?(?:d[ae]|t[ae]))\b", re.IGNORECASE)


def _check_minute_context(before: str, after: str, tail: str, unit: str | None, family: str | None) -> bool:
    if family is not None and family != "minutes":
        return False
    if unit is not None and unit != "min":
        return False
    if _MINUTE_BEFORE_RE.search(before):
        return True
    if _AT_BEFORE_RE.search(before):
        return True
    if _ORDINAL_TAIL_RE.match(tail) and (_MINUTE_AFTER_RE.match(after) or tail.startswith("'")):
        return True
    if _MINUTE_AFTER_RE.match(after):
        return True
    return False


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
        family: str | None = None
        after = text[m.end():]
        before = text[:m.start()]
        if m.group("pct_pre") or tail == "%":
            unit, family = "pct", "pct"
        else:
            unit_match = _UNIT_RE.match(after)
            if unit_match:
                word = unit_match.group("unit").casefold()
                unit = "min" if word.startswith(("min", "dak", "dk")) else "s" if word.startswith(("sec", "san", "sn")) else "m"
            noun = _FAMILY_RE.match(after)
            if noun:
                family = _family_of(noun.group("noun"))
            elif unit:
                family = {"min": "minutes", "s": "seconds", "m": "metres"}[unit]
        is_minute_context = _check_minute_context(before, after, tail, unit, family)
        if is_minute_context:
            if unit is None:
                unit = "min"
            if family is None:
                family = "minutes"
        found.append(FoundNumber(value=value, raw=m.group(0).strip(), decimals=decimals, unit=unit, family=family, is_minute_context=is_minute_context))
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


def _key_in_family(key: str, family: str) -> bool:
    lowered = key.casefold()
    return any(lowered.endswith(fragment) if fragment.startswith("_") else fragment in lowered for fragment in FAMILIES[family])


def matching_key(number: FoundNumber, cited: dict[str, float]) -> str | None:
    """The cited key that justifies the number. A number with a family ("13 pressures") must match a key of that
    family (`pressing_trap_pressures`), so a value borrowed from another fact (the 13-second window) does not count."""
    keys = list(cited)
    if number.family and any(_key_in_family(k, number.family) for k in keys):
        keys = [k for k in keys if _key_in_family(k, number.family)]
    elif number.family:
        return None  # the text quotes a fact that was not cited at all
    for key in keys:
        for candidate in _candidates(key, cited[key], number.unit):
            if abs(round_half_up(candidate, number.decimals) - number.value) < 1e-9:
                return key
    return None


def matches(number: FoundNumber, cited: dict[str, float]) -> bool:
    return matching_key(number, cited) is not None


def _describe(cited: dict[str, float]) -> str:
    if not cited:
        return "no evidence cited"
    return ", ".join(f"{k} = {v:g}" for k, v in list(cited.items())[:6])


_WINDOW_KEY_RE = re.compile(r"last_?(\d+)_?min")


def window_minutes_in_keys(cited: dict[str, float]) -> set[float]:
    """Window lengths written into cited key names, such as 10 in `team_shots_last_10min`."""
    return {float(m.group(1)) for key in cited for m in [_WINDOW_KEY_RE.search(key)] if m}


def check_numbers(
    text: str,
    cited: dict[str, float],
    *,
    gate: Gate,
    moment_id: str,
    profile_key: str | None = None,
    lang: Lang = "en",
    minute: int | float | None = None,
) -> NumberCheck:
    """The reusable gate: every digit number must match a cited value; number words are not allowed."""
    if minute is None and "minute" in cited:
        minute = cited["minute"]
    mismatches = []
    windows = window_minutes_in_keys(cited)
    for n in extract_numbers(text, lang):
        if minute is not None and n.is_minute_context and abs(n.value - minute) < 1e-9:
            continue
        if n.unit == "min" and n.value in windows:
            continue  # "in the last 10 minutes" names the window of a cited key (team_shots_last_10min), not a claim
        if matches(n, cited):
            continue
        if n.family and any(_key_in_family(k, n.family) for k in cited):
            own = ", ".join(f"{k} = {v:g}" for k, v in cited.items() if _key_in_family(k, n.family))
            mismatches.append(f"{n.raw} {n.family} does not match the cited {n.family} value ({own})")
        else:
            mismatches.append(f"{n.raw} not in cited evidence ({_describe(cited)})")
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
    minute: int | float | None = None,
) -> NumberCheck:
    """Producer gate: the number check plus a coverage rule against the verified source text.

    coverage "all": every number in the source must survive (analyst depth, overlay metric);
    "any": at least one must survive when the source has numbers (casual depth); "none": no rule.
    A dropped number is reported as "dropped number: 14".
    """
    check = check_numbers(text, cited, gate="producer", moment_id=moment_id, profile_key=profile_key, lang=lang, minute=minute)
    if coverage == "none":
        return check
    source = {round(n.value, 6) for n in extract_numbers(source_text, source_lang)}
    present = {round(n.value, 6) for n in extract_numbers(text, lang)}
    missing = sorted(source - present)
    if (coverage == "all" and missing) or (coverage == "any" and source and not present):
        dropped = [f"dropped number: {m:g}" for m in missing]
        return check.model_copy(update={"ok": False, "mismatches": check.mismatches + dropped})
    return check


# Opponent phrasing: the other club or its players may be named only as the ones acted upon or as places.
_EN_BEFORE = {
    "against", "on", "over", "past", "from", "versus", "vs", "to", "beat", "beating", "behind", "through", "around", "off", "by",
    "under", "at", "with", "than", "pressing", "pressed", "pressured", "pressure", "trapped", "trap", "caught", "forced", "forcing",
    "force", "forces", "denied", "stopped", "dispossessed", "robbed", "chasing", "pinned", "pin", "pins", "pinning", "outnumbered",
    "overran", "overrun", "squeezed", "hemmed", "leave", "leaves", "left", "leaving", "keep", "keeps", "kept", "keeping",
    "push", "pushes", "pushed", "pushing", "put", "puts", "putting", "for",
}
_EN_CONJUNCTIONS = {"and", "but", "so", "or", "while", "as", "whilst", "because"}
_EN_AFTER = {
    "chasing", "chase", "chased", "concede", "conceded", "conceding", "struggle", "struggled", "struggling", "pinned", "overrun",
    "could", "couldn't", "cannot", "can't", "failed", "fail", "lost", "lose", "losing", "defend", "defending", "defended",
    "sat", "sit", "sitting", "drop", "dropped", "dropping", "retreat", "retreated", "retreating", "scrambling", "scrambled",
    "are", "were", "have", "had", "did", "look", "looked",
}
_EN_AFTER_SUBJECT = {"are", "were", "have", "had", "did", "look", "looked"}  # these need a passive-sounding word right after
_EN_PASSIVE = {
    "chasing", "pinned", "overrun", "struggling", "scrambling", "stretched", "exposed", "tired", "tiring", "unable", "forced", "pushed",
    "penned", "second", "behind", "outnumbered", "powerless", "passive", "reactive", "deep", "defending", "sitting", "rattled", "on", "under",
}
_EN_PLACE = {
    "territory", "territories", "half", "halves", "box", "boxes", "area", "areas", "goal", "goals",
    "defence", "defense", "defences", "defenses", "end", "ends", "side", "sides", "third", "thirds",
}
_TR_AFTER = {
    "karsi", "karsisinda", "karsisina", "uzerinde", "uzerine", "onunde", "ardindan",
    "pesinden", "arkasindan", "gerisinde", "geriye", "zorlandi", "zorlaniyor", "zorlayan", "kosuyor", "kosturuyor",
    "kovaliyor", "yoruldu", "sikisti", "sikisiyor", "birakti", "birakiyor", "birakan", "tuttu", "tutuyor", "tutan",
    "itti", "itiyor", "iten", "hapsetti", "hapsediyor", "hapseden", "altinda", "altina",
}
_TR_PLACE_PREFIXES = ("yari", "ceza", "kale", "savunma", "bolge", "saha", "alan", "taraf")
_TR_OBJ_SUFFIX = re.compile(r"'(?:y?[aeıiuü]|d[ae]n|t[ae]n|y?l[ae]|d[ae]|t[ae])\b")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:'[^\W_]+)?", text, re.UNICODE)


def _name_positions(tokens: list[str], name: str) -> list[int]:
    parts = [p.casefold() for p in name.split()]
    folded = [t.casefold().split("'")[0] for t in tokens]
    return [i for i in range(len(folded) - len(parts) + 1) if folded[i:i + len(parts)] == parts]


def _is_place(tokens: list[str], start: int, length: int, lang: Lang) -> bool:
    if lang == "tr":
        after = [_fold(t) for t in tokens[start + length:start + length + 3]]
        if after and any(after[0].startswith(p) for p in _TR_PLACE_PREFIXES):
            return True
        if len(after) > 1 and after[0] in ("kendi", "kendi\u0307") and any(after[1].startswith(p) for p in _TR_PLACE_PREFIXES):
            return True
        return False
    after = [t.casefold() for t in tokens[start + length:start + length + 3]]
    if after and after[0] in _EN_PLACE:
        return True
    if len(after) > 1 and after[0] in ("own", "defensive", "attacking", "penalty", "18-yard") and after[1] in _EN_PLACE:
        return True
    return False


def _as_object(tokens: list[str], start: int, length: int, lang: Lang) -> bool:
    """True when the name at tokens[start:start+length] is acted upon rather than acting."""
    if _is_place(tokens, start, length, lang):
        return True
    before = [t.casefold() for t in tokens[max(0, start - 3):start]]
    after = [t.casefold() for t in tokens[start + length:start + length + 3]]
    last = tokens[start + length - 1]
    if lang == "tr":
        after_tr = [_fold(t) for t in tokens[start + length:start + length + 3]]
        before_tr = [_fold(t) for t in tokens[max(0, start - 3):start]]
        return (
            bool(_TR_OBJ_SUFFIX.search(last))
            or any(w in _TR_AFTER for w in after_tr[:2])
            or any(w in ("karsi", "karsisinda", "uzerinde") for w in before_tr)
        )
    if before and before[-1] not in _EN_CONJUNCTIONS:
        if any(w in _EN_BEFORE for w in before[-2:]):
            return True
    if after and after[0] in _EN_AFTER:
        if after[0] in _EN_AFTER_SUBJECT:
            return any(w in _EN_PASSIVE for w in after[1:3])
        return True
    return False


def check_actors(text: str, moment: CandidateMoment, labels: dict[str, str], lang: Lang = "en") -> list[str]:
    """Deterministic attribution: the moment belongs to `labels['team']`; the opponent and its players may appear only
    as the ones acted upon. Returns reasons, empty when the attribution is fine."""
    from app.simulator.league import CLUBS

    team, opponent = labels.get("team"), labels.get("opponent")
    if not team or not opponent or team == opponent:
        return []
    tokens = _tokens(text)
    reasons = []
    for start in _name_positions(tokens, opponent):
        if not _as_object(tokens, start, len(opponent.split()), lang):
            reasons.append(f"{opponent} named as the actor, but the moment is {team}'s (name {team} as the actor, or use opponent phrasing such as 'against {opponent}')")
            break
    other_club = next((c for c in CLUBS.values() if c.short == opponent or c.name == opponent), None)
    if other_club is not None:
        for player in other_club.players:
            for start in _name_positions(tokens, player.name):
                if not _as_object(tokens, start, len(player.name.split()), lang):
                    reasons.append(f"{player.name} plays for {opponent}, not {team} (name one of {team}'s players, or use opponent phrasing)")
                    break
            else:
                continue
            break
    return reasons


def cited_evidence(insight: Insight, moment: CandidateMoment) -> tuple[dict[str, float], list[str]]:
    """Split the insight's refs into (cited values, unknown keys)."""
    cited = {k: moment.evidence[k] for k in insight.evidence_refs if k in moment.evidence}
    unknown = [k for k in insight.evidence_refs if k not in moment.evidence]
    return cited, unknown


def check_insight(insight: Insight, moment: CandidateMoment, attempt: int, labels: dict[str, str] | None = None, lang: Lang = "en") -> tuple[Verdict | None, NumberCheck]:
    """Layer 1 on an Insight: keys, numbers (family-aware) and, with labels, the actor attribution.
    Returns (rejected verdict or None, the NumberCheck record)."""
    reasons: list[str] = []
    if insight.moment_id != moment.moment_id:
        reasons.append(f"insight is about {insight.moment_id}, expected {moment.moment_id}")
    cited, unknown = cited_evidence(insight, moment)
    reasons += [f"unknown evidence key: {k}" for k in unknown]
    check = check_numbers(f"{insight.claim}\n{insight.why_it_matters}", cited, gate="insight", moment_id=moment.moment_id, lang=lang, minute=moment.minute)
    reasons += check.mismatches
    if labels:
        reasons += check_actors(f"{insight.claim} {insight.why_it_matters}", moment, labels, lang)
    if reasons:
        return Verdict(moment_id=moment.moment_id, status="rejected", insight=insight, reasons=reasons, layer="code", attempt=attempt), check
    return None, check


def check_speech(approved_text: str, transcript: str, cited: dict[str, float], *, moment_id: str, profile_key: str | None, lang: Lang, minute: int | float | None = None) -> NumberCheck:
    """Speech gate: the transcript must be the approved text (ignoring case, spacing and end punctuation) and pass the number check."""
    check = check_numbers(transcript, cited, gate="speech", moment_id=moment_id, profile_key=profile_key, lang=lang, minute=minute)
    if _normalise(transcript) != _normalise(approved_text):
        check = check.model_copy(update={"ok": False, "mismatches": check.mismatches + ["transcript differs from approved text"]})
    return check


def _normalise(text: str) -> str:
    return re.sub(r"[\s\.\!\?,;:]+", " ", text).strip().casefold()
