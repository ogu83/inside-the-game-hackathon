from typing import Any

from app.agents.analyst import FoundryDirector, PacingState
from app.agents.commentator import FoundryCommentator
from app.agents.fact_checker import FoundryWordingJudge
from app.agents.models import DirectorDecision, FanProfile, Insight, Question, WordingVerdict
from app.agents.producer import CueDraft, FoundryRenderer
from app.agents.recap import FoundryRecapWriter
from app.voice.qa import FoundryQaAgent
from tests.agents.test_fact_checker import MOMENT


class OptionRecordingAgent:
    def __init__(self, return_value: Any = None, text: str = "") -> None:
        self.return_value = return_value
        self.text = text
        self.recorded_options: list[dict] = []
        self.recorded_prompts: list[str] = []

    async def run(self, prompt: str, options: dict | None = None, **kwargs) -> Any:
        self.recorded_prompts.append(prompt)
        self.recorded_options.append(dict(options or {}))
        return type("MockResponse", (), {"value": self.return_value, "text": self.text})()


async def test_foundry_director_caps_max_tokens() -> None:
    agent = OptionRecordingAgent(DirectorDecision(moment_id=MOMENT.moment_id, say=True, angle="control", reason="room"))
    director = FoundryDirector(agent)
    await director.decide(MOMENT, {"team": "Kestrel Bay"}, PacingState())
    assert len(agent.recorded_options) == 1
    assert agent.recorded_options[0].get("max_tokens") == 100
    assert agent.recorded_options[0].get("response_format") == DirectorDecision


async def test_foundry_commentator_caps_max_tokens() -> None:
    agent = OptionRecordingAgent(Insight(moment_id=MOMENT.moment_id, claim="Good streak.", why_it_matters="Control.", evidence_refs=[], confidence=0.8))
    commentator = FoundryCommentator(agent)
    await commentator.write(MOMENT, {"team": "Kestrel Bay"}, [])
    assert len(agent.recorded_options) == 1
    assert agent.recorded_options[0].get("max_tokens") == 250
    assert agent.recorded_options[0].get("response_format") == Insight


async def test_foundry_wording_judge_caps_max_tokens() -> None:
    agent = OptionRecordingAgent(WordingVerdict(status="verified", reasons=[]))
    judge = FoundryWordingJudge(agent)
    insight = Insight(moment_id=MOMENT.moment_id, claim="Good streak.", why_it_matters="Control.", evidence_refs=[], confidence=0.8)
    await judge.judge(insight, {}, {"team": "Kestrel Bay"})
    assert len(agent.recorded_options) == 1
    assert agent.recorded_options[0].get("max_tokens") == 250
    assert agent.recorded_options[0].get("response_format") == WordingVerdict


async def test_foundry_renderer_caps_max_tokens() -> None:
    agent = OptionRecordingAgent(
        return_value={"headline": "Ironvale 22 passes", "metric_label": "passes", "metric_value": "22", "priority": "normal"},
        text="Ironvale completed 22 passes.",
    )
    renderer = FoundryRenderer(agent)
    insight = Insight(moment_id=MOMENT.moment_id, claim="Good streak.", why_it_matters="Control.", evidence_refs=[], confidence=0.8)
    profile = FanProfile(language="en", depth="casual")

    await renderer.cue(insight, MOMENT, {"team": "Ironvale"}, [])
    assert agent.recorded_options[-1].get("max_tokens") == 120
    assert agent.recorded_options[-1].get("response_format") == CueDraft

    await renderer.narrative(insight, MOMENT, {"team": "Ironvale"}, profile, [])
    assert agent.recorded_options[-1].get("max_tokens") == 180


async def test_foundry_recap_writer_caps_max_tokens() -> None:
    agent = OptionRecordingAgent(text="Full time recap text.")
    writer = FoundryRecapWriter(agent)
    profile = FanProfile(language="en", depth="casual")
    await writer.write_recap({"home_goals": 1.0}, {"home": "Kestrel Bay"}, profile, [])
    assert len(agent.recorded_options) == 1
    assert agent.recorded_options[0].get("max_tokens") == 300


async def test_foundry_qa_agent_caps_max_tokens() -> None:
    agent = OptionRecordingAgent(text="The score is 0-0.")
    qa_agent = FoundryQaAgent(agent)
    profile = FanProfile(language="en", depth="casual")
    question = Question(question_id="q1", profile_key=profile.key(), transcript="What is the score?")
    draft = await qa_agent.draft(question, profile, {}, None, [])
    assert draft.text == "The score is 0-0."
    assert len(agent.recorded_options) == 1
    assert agent.recorded_options[0].get("max_tokens") == 150

