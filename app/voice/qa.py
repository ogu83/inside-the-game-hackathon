"""Voice Q&A, text first (SPEC design rules 4 and 6): question transcript -> Q&A agent over the ledger tools ->
Fact-Checker gates -> approved text that the voice speaks verbatim.

The gate evidence is the set of numbers the ledger holds right now for this fan (both clubs, the fan's player
and any player named in the question, the score, the recent moments). An answer may only contain numbers from
that set, whichever agent wrote it. An answer that fails both attempts becomes "I don't have data on that".
"""

import re
import uuid
from typing import Any, Protocol

from app.agents.fact_checker import FactChecker
from app.agents.models import Answer, FanProfile, Insight, QaDraft, Question
from app.ledger.labels import profile_labels
from app.ledger.mcp_server import LedgerTools
from app.ledger.models import CandidateMoment
from app.simulator.league import CLUBS, PLAYERS

NO_DATA = {"en": "I don't have data on that.", "tr": "Bu konuda elimde veri yok."}
MAX_ATTEMPTS = 2
_NUMERIC = (int, float)


def _flatten(prefix: str, data: dict[str, Any], out: dict[str, float]) -> None:
    for key, value in data.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, _NUMERIC):
            out[f"{prefix}{key}"] = float(value)
        elif isinstance(value, dict):
            _flatten(f"{prefix}{key}_", value, out)


def players_named(transcript: str) -> list[str]:
    lowered = transcript.casefold()
    return [p.id for p in PLAYERS.values() if p.name.casefold() in lowered or p.name.split()[-1].casefold() in lowered.split()]


def qa_evidence(tools: LedgerTools, profile: FanProfile, transcript: str) -> tuple[dict[str, float], list[str]]:
    """Every number the fan may be told right now, as a flat evidence dict, plus the tool names used to gather it."""
    evidence: dict[str, float] = {}
    calls = ["score", "team_stats", "recent_moments"]
    _flatten("score_", tools.score(), evidence)
    for team_id in CLUBS:
        _flatten(f"{team_id}_", tools.team_stats(team_id), evidence)
        _flatten(f"{team_id}_last10_", tools.team_stats(team_id, 10), evidence)
    players = list(dict.fromkeys(([profile.player_id] if profile.player_id else []) + players_named(transcript)))
    for player_id in players:
        calls.append("player_stats")
        _flatten(f"{player_id}_", tools.player_stats(player_id), evidence)
    for i, moment in enumerate(tools.recent_moments(3)["moments"]):
        _flatten(f"moment{i}_", {"minute": moment["minute"], **moment["evidence"]}, evidence)
    return evidence, calls


class QaAgent(Protocol):
    async def draft(self, question: Question, profile: FanProfile, labels: dict[str, str], tools: LedgerTools, feedback: list[str]) -> QaDraft: ...


def _n(value: float) -> str:
    return f"{value:g}"


def _pct(value: float, lang: str) -> str:
    text = _n(value).replace(".", ",") if lang == "tr" else _n(value)
    return f"%{text}" if lang == "tr" else f"{text}%"


class RuleQaAgent:
    """Offline Q&A: keyword rules in English and Turkish over the same ledger tools the MCP server exposes."""

    async def draft(self, question: Question, profile: FanProfile, labels: dict[str, str], tools: LedgerTools, feedback: list[str]) -> QaDraft:
        lang = profile.language
        text = question.transcript.casefold()
        calls: list[str] = []
        has = lambda *words: any(w in text for w in words)  # noqa: E731
        named = players_named(question.transcript)
        player_id = named[0] if named else profile.player_id if has("my player", "oyuncum", "favourite", "favorite", "how is he", "nasıl oynuyor") else None
        if player_id:
            calls.append("player_stats")
            stats = tools.player_stats(player_id)
            if "error" in stats:
                return QaDraft(text=NO_DATA[lang], tool_calls=calls, language=lang)
            name = stats["player"]
            if lang == "tr":
                body = f"{name} {_n(stats['passes'])} pas denedi, {_pct(stats['pass_accuracy_pct'], lang)} isabetle, {_n(stats['shots'])} şut."
            else:
                shots = f"{_n(stats['shots'])} shot" + ("" if stats["shots"] == 1 else "s")
                body = f"{name} has attempted {_n(stats['passes'])} passes at {_pct(stats['pass_accuracy_pct'], lang)} accuracy, with {shots}."
            return QaDraft(text=body, tool_calls=calls, language=lang)
        if has("why", "neden", "niye", "matter", "önemli"):
            calls.append("recent_moments")
            moments = tools.recent_moments(1)["moments"]
            if not moments:
                return QaDraft(text=NO_DATA[lang], tool_calls=calls, language=lang)
            m = moments[0]
            if lang == "tr":
                body = f"{m['team']} {_n(m['minute'])}. dakikada: {m.get('narrative_tr') or m['claim']}"
            else:
                body = f"{m['claim']} {m['why_it_matters']}"
            return QaDraft(text=body, tool_calls=calls, language=lang)
        team_id = next((cid for cid, c in CLUBS.items() if c.short.casefold() in text or cid in text), profile.club_id)
        if has("score", "skor", "durum", "winning", "kim önde"):
            calls.append("score")
            score = tools.score()
            if "error" in score:
                return QaDraft(text=NO_DATA[lang], tool_calls=calls, language=lang)
            home, away = list(CLUBS)
            body = (f"Skor {CLUBS[home].short} {_n(score[f'{home}_goals'])}, {CLUBS[away].short} {_n(score[f'{away}_goals'])}, {_n(score['minute'])}. dakika."
                    if lang == "tr" else f"It is {CLUBS[home].short} {_n(score[f'{home}_goals'])}, {CLUBS[away].short} {_n(score[f'{away}_goals'])} after {_n(score['minute'])} minutes.")
            return QaDraft(text=body, tool_calls=calls, language=lang)
        if team_id and has("possession", "top", "topa", "shots", "şut", "pass", "pas", "press", "baskı", "xg", "how are", "nasıl"):
            calls.append("team_stats")
            stats = tools.team_stats(team_id, 10)
            if "error" in stats:
                return QaDraft(text=NO_DATA[lang], tool_calls=calls, language=lang)
            team = stats["team"]
            if lang == "tr":
                body = f"{team} son {_n(stats['window_minutes'])} dakikada {_pct(stats['possession_pct'], lang)} topa sahip, {_n(stats['shots'])} şut ve {_n(stats['pressures'])} baskı."
            else:
                shots = f"{_n(stats['shots'])} shot" + ("" if stats["shots"] == 1 else "s")
                body = f"{team} have had {_pct(stats['possession_pct'], lang)} of the ball in the last {_n(stats['window_minutes'])} minutes, with {shots} and {_n(stats['pressures'])} pressures."
            return QaDraft(text=body, tool_calls=calls, language=lang)
        return QaDraft(text=NO_DATA[lang], tool_calls=calls, language=lang)


class FoundryQaAgent:
    """Live Q&A: an Agent Framework agent that calls the ledger MCP server (MCPStreamableHTTPTool), text in, text out."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    async def draft(self, question: Question, profile: FanProfile, labels: dict[str, str], tools: LedgerTools, feedback: list[str]) -> QaDraft:
        language = "English" if profile.language == "en" else "Turkish"
        prompt = (
            f"Fan profile: club {labels.get('fan_club', 'none')}, favourite player {labels.get('fan_player', 'none')} "
            f"(id {profile.player_id or 'none'}), depth {profile.depth}. Answer in {language}.\nQuestion: {question.transcript}"
        )
        if feedback:
            prompt += f"\nYour previous answer failed the number check: {feedback}. Use only numbers from the tools."
        response = await self.agent.run(prompt)
        calls = [str(getattr(c, "name", "")) for m in getattr(response, "messages", []) for c in getattr(m, "contents", []) if getattr(c, "type", "") == "function_call"]
        return QaDraft(text=(response.text or "").strip(), tool_calls=calls or ["ledger (via MCP)"], language=profile.language)


class QaPipeline:
    def __init__(self, agent: QaAgent, fact_checker: FactChecker, tools: LedgerTools) -> None:
        self.agent = agent
        self.fact_checker = fact_checker
        self.tools = tools

    async def answer(self, question: Question, profile: FanProfile, labels: dict[str, str] | None = None) -> Answer:
        labels = profile_labels(labels or {"team": "", "opponent": ""}, profile.club_id, profile.player_id)
        evidence, gather_calls = qa_evidence(self.tools, profile, question.transcript)
        moment = CandidateMoment(moment_id=f"qa-{question.question_id}", window=(question.asked_at_seq, question.asked_at_seq), kind="qa",
                                 team_id=profile.club_id or "", minute=int(evidence.get("score_minute", 0)), evidence=evidence)
        feedback: list[str] = []
        verdict = None
        draft = QaDraft(text=NO_DATA[profile.language], language=profile.language)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            draft = await self.agent.draft(question, profile, labels, self.tools, feedback)
            refs = self._refs(draft.text, evidence, profile.language)
            insight = Insight(moment_id=moment.moment_id, claim=draft.text, why_it_matters="", evidence_refs=refs, confidence=0.8)
            verdict, _ = await self.fact_checker.check(insight, moment, labels, attempt)
            if verdict.status != "rejected":
                text = verdict.insight.claim if verdict.insight else draft.text
                return Answer(question_id=question.question_id, text=text, evidence_refs=refs, tool_calls=list(dict.fromkeys(draft.tool_calls + gather_calls)),
                              verdict=verdict, evidence={k: evidence[k] for k in refs})
            feedback = verdict.reasons
        return Answer(question_id=question.question_id, text=NO_DATA[profile.language], evidence_refs=[], tool_calls=list(dict.fromkeys(draft.tool_calls + gather_calls)), verdict=verdict)

    @staticmethod
    def _refs(text: str, evidence: dict[str, float], lang: str) -> list[str]:
        """Cite every evidence key whose value appears as a number in the text (rounded to the text's precision)."""
        from app.agents.fact_check_rules import extract_numbers, round_half_up

        found = extract_numbers(text, lang)
        refs = []
        for key, value in evidence.items():
            for n in found:
                if abs(round_half_up(value, n.decimals) - n.value) < 1e-9 or (n.unit == "min" and key.endswith("_s") and abs(round_half_up(value / 60, n.decimals) - n.value) < 1e-9):
                    refs.append(key)
                    break
        return refs


def new_question(profile_key: str, transcript: str, asked_at_seq: int = 0) -> Question:
    return Question(question_id=uuid.uuid4().hex[:8], profile_key=profile_key, transcript=re.sub(r"\s+", " ", transcript).strip(), asked_at_seq=asked_at_seq)
