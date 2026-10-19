import asyncio

import pytest

from app.agents.fact_checker import FactChecker
from app.agents.fakes import AlwaysVerifies
from app.agents.models import FanProfile, QaDraft
from app.api.streams import MatchRun
from app.voice.qa import NO_DATA, QaPipeline, RuleQaAgent, intents_of, new_question, players_named, qa_evidence


@pytest.fixture(scope="module")
def finished_run() -> MatchRun:
    async def make():
        run = MatchRun(seed=30, speed=2000, delay_s=10, minutes=20, precompute=True)
        await run.start()
        await asyncio.wait_for(run.finished.wait(), timeout=10)
        return run

    return asyncio.run(make())


def pipeline(run: MatchRun, agent=None) -> QaPipeline:
    return QaPipeline(agent or RuleQaAgent(), FactChecker(AlwaysVerifies()), run.tools())


def test_players_named_in_a_transcript() -> None:
    assert players_named("how is Remy Tallis doing") == ["iva-06"]
    assert players_named("what about tallis today") == ["iva-06"]
    assert players_named("how is the match going") == []


def test_qa_evidence_covers_both_clubs_the_fan_player_and_recent_moments(finished_run: MatchRun) -> None:
    evidence, calls = qa_evidence(finished_run.tools(), FanProfile(club_id="iva", player_id="iva-06"), "why does that matter")
    assert {"kby_possession_pct", "iva_possession_pct", "iva_last10_shots", "iva-06_passes", "score_minute", "moment0_minute"} <= evidence.keys()
    assert all(isinstance(v, float) for v in evidence.values())
    assert "player_stats" in calls and "recent_moments" in calls


async def test_rule_agent_answers_about_my_player_from_the_ledger(finished_run: MatchRun) -> None:
    profile = FanProfile(club_id="iva", player_id="iva-06", language="en")
    answer = await pipeline(finished_run).answer(new_question(profile.key(), "how is my player doing?"), profile)
    assert "Remy Tallis" in answer.text and "passes" in answer.text
    assert answer.verdict is not None and answer.verdict.status == "verified"
    assert {"iva-06_passes", "iva-06_pass_accuracy_pct", "iva-06_shots"} <= set(answer.evidence_refs)
    assert "player_stats" in answer.tool_calls and set(answer.evidence) == set(answer.evidence_refs)


async def test_rule_agent_answers_in_turkish(finished_run: MatchRun) -> None:
    profile = FanProfile(club_id="kby", language="tr")
    answer = await pipeline(finished_run).answer(new_question(profile.key(), "Kestrel Bay topa ne kadar sahip?"), profile)
    assert "Kestrel Bay" in answer.text and "%" in answer.text and "topa sahip" in answer.text
    assert answer.verdict is not None and answer.verdict.status == "verified"
    why = await pipeline(finished_run).answer(new_question(profile.key(), "bu neden önemli?"), profile)
    assert why.text != NO_DATA["tr"] and "dakikada" in why.text


async def test_rule_agent_explains_why_and_the_score(finished_run: MatchRun) -> None:
    profile = FanProfile(language="en")
    why = await pipeline(finished_run).answer(new_question(profile.key(), "why does that matter?"), profile)
    latest = finished_run.shown_moments()[-1]
    assert why.text.startswith(latest["claim"]) and "recent_moments" in why.tool_calls
    score = await pipeline(finished_run).answer(new_question(profile.key(), "what is the score?"), profile)
    assert score.text.startswith("It is Kestrel Bay") and score.verdict.status == "verified"


async def test_unanswerable_questions_get_no_data(finished_run: MatchRun) -> None:
    for lang, question in (("en", "what is the weather like?"), ("tr", "hava nasıl?")):
        profile = FanProfile(language=lang)
        answer = await pipeline(finished_run).answer(new_question(profile.key(), question), profile)
        assert answer.text == NO_DATA[lang] and answer.evidence_refs == [] and answer.verdict.status == "verified"


class InventingAgent:
    def __init__(self) -> None:
        self.feedback: list[list[str]] = []

    async def draft(self, question, profile, labels, tools, feedback):
        self.feedback.append(list(feedback))
        return QaDraft(text="Ironvale have had 99 shots and 77% of the ball.", tool_calls=["team_stats"], language="en")


async def test_an_agent_that_invents_numbers_is_gated_to_no_data(finished_run: MatchRun) -> None:
    agent = InventingAgent()
    answer = await pipeline(finished_run, agent).answer(new_question("-|-|casual|en", "how are Ironvale doing?"), FanProfile())
    assert answer.text == NO_DATA["en"] and answer.verdict.status == "rejected" and answer.verdict.layer == "code"
    assert len(agent.feedback) == 2 and "99 not in cited evidence" in agent.feedback[1][0]


class WordyAgent:
    async def draft(self, question, profile, labels, tools, feedback):
        return QaDraft(text="Ironvale have been dominant and are dictating the tempo.", tool_calls=["team_stats"], language="en")


async def test_answers_without_numbers_still_pass_the_wording_judge(finished_run: MatchRun) -> None:
    answer = await pipeline(finished_run, WordyAgent()).answer(new_question("-|-|casual|en", "how are Ironvale doing?"), FanProfile())
    assert answer.verdict.status == "verified" and answer.verdict.layer == "llm"  # AlwaysVerifies stands in for the live judge


async def test_no_match_shown_yet_gives_no_data() -> None:
    run = MatchRun(seed=30, speed=1, delay_s=600, minutes=10, precompute=True)
    await run.start()
    try:
        answer = await pipeline(run).answer(new_question("-|-|casual|en", "what is the score?"), FanProfile())
        assert answer.text == NO_DATA["en"]
    finally:
        await run.stop()


def test_intents_tolerate_misrecognised_speech() -> None:
    assert intents_of("Scarne.") == {"score"} and intents_of("Skorne.") == {"score"} and intents_of("Skagne.") == set()
    assert intents_of("skor ne") == {"score"} and intents_of("what's the score") == {"score"}
    assert intents_of("oyuncum nasıl") >= {"player"} and intents_of("how is my player doing") >= {"player"}
    assert intents_of("gol var mı") == {"team"} and intents_of("any goals") == {"team"}
    assert intents_of("how is the weather") == set() and intents_of("hava nasıl") == {"team"}, "nasıl alone is a team question; the rule agent still needs a club"
    assert players_named("how is Callaway doing") == ["iva-07"] and players_named("Remi Tallis") == ["iva-06"]
    assert players_named("Skorne.") == [] and players_named("Scarne.") == [], "a garbled 'skor ne' is not a surname (Thorne)"


@pytest.mark.parametrize(("transcript", "answered"), [("Scarne.", True), ("Skorne.", True), ("Skagne.", False)])
async def test_oguz_three_skor_ne_transcripts(finished_run: MatchRun, transcript: str, answered: bool) -> None:
    profile = FanProfile(club_id="iva", player_id="iva-07", language="tr")
    answer = await pipeline(finished_run).answer(new_question(profile.key(), transcript), profile)
    if answered:
        assert answer.text.startswith("Skor Kestrel Bay") and answer.verdict.status == "verified", transcript
    else:
        assert answer.text == NO_DATA["tr"], "a transcript with no recognisable intent still gets the no-data reply"


class AdvancingTools:
    """The ledger moves on while the agent drafts: after `advance()`, Ironvale's shot count is one higher."""

    def __init__(self, tools) -> None:
        self._tools, self.advanced = tools, False

    def advance(self) -> None:
        self.advanced = True

    def team_stats(self, team_id, *args, **kwargs):
        stats = dict(self._tools.team_stats(team_id, *args, **kwargs))
        if self.advanced and team_id == "iva" and not args and "shots" in stats:
            stats["shots"] = stats["shots"] + 1
        return stats

    def __getattr__(self, name):
        return getattr(self._tools, name)


class LatestNumbersAgent:
    """Calls the tools itself after the pipeline's snapshot, as the Foundry agent does, and quotes what it saw."""

    async def draft(self, question, profile, labels, tools, feedback):
        tools.advance()
        shots = tools.team_stats("iva")["shots"]
        return QaDraft(text=f"Ironvale have had {shots} shots.", tool_calls=["team_stats"], language="en")


async def test_numbers_newer_than_the_snapshot_are_accepted(finished_run: MatchRun) -> None:
    """Live take 2026-10-18: the match moved on during drafting, the true newer number was rejected as unsupported."""
    tools = AdvancingTools(finished_run.tools())
    answer = await QaPipeline(LatestNumbersAgent(), FactChecker(AlwaysVerifies()), tools).answer(new_question("-|-|casual|en", "how many shots have Ironvale had?"), FanProfile())
    assert answer.verdict.status != "rejected", answer.verdict.reasons
    assert any(ref.endswith("_latest") for ref in answer.evidence_refs)
