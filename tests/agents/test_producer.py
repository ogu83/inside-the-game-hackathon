import asyncio
import time

from app.agents.fakes import TemplateRenderer
from app.agents.models import FanProfile, Insight
from app.agents.producer import CueDraft, FoundryRenderer, Producer
from app.agents.prompts import PRODUCER_INSTRUCTIONS, cue_prompt, narrative_prompt
from app.ledger.labels import moment_labels
from app.ledger.state import detect_all
from app.simulator.engine import simulate
from tests.agents.test_analyst import FakeAgent

PROFILES = [FanProfile(language="en", depth="casual"), FanProfile(language="en", depth="analyst"),
            FanProfile(language="tr", depth="casual"), FanProfile(language="tr", depth="analyst")]


def streak_moment():
    return next(m for m in detect_all(simulate(30)) if m.kind == "pass_streak" and m.evidence.get("top_player_passes", 0) >= 4)


def full_insight(moment) -> Insight:
    return Insight(moment_id=moment.moment_id, claim=f"Team kept {moment.evidence['pass_streak_passes']:g} passes in {moment.evidence['pass_streak_duration_s']:g} seconds.",
                   why_it_matters="Control.", evidence_refs=list(moment.evidence), confidence=0.9)


async def test_depth_and_language_change_the_rendering() -> None:
    moment = streak_moment()
    output = await Producer(TemplateRenderer()).render(full_insight(moment), moment, moment_labels(moment), PROFILES)
    texts = {n.profile_key: n.text for n in output.narratives}
    assert len(texts) == 4 and all(c.ok for c in output.checks)
    assert len(texts["-|-|analyst|en"]) > len(texts["-|-|casual|en"])
    assert len(texts["-|-|analyst|tr"]) > len(texts["-|-|casual|tr"])
    assert "pası" in texts["-|-|casual|tr"] and "pası" not in texts["-|-|casual|en"]


async def test_fan_player_focus_only_with_a_number_about_them() -> None:
    moment = streak_moment()
    labels = moment_labels(moment)
    fan_of_top = FanProfile(language="en", depth="casual", club_id=moment.team_id, player_id=moment.top_player_id)
    other_club = next(cid for cid in ("kby", "iva") if cid != moment.team_id)
    fan_of_other = FanProfile(language="en", depth="casual", club_id=other_club, player_id=f"{other_club}-09")
    output = await Producer(TemplateRenderer()).render(full_insight(moment), moment, labels, [fan_of_top, fan_of_other])
    texts = {n.profile_key: n.text for n in output.narratives}
    assert "Your player" in texts[fan_of_top.key()] and labels["top_player"] in texts[fan_of_top.key()]
    assert "Your player" not in texts[fan_of_other.key()]


class SlowRenderer(TemplateRenderer):
    async def narrative(self, *args, **kwargs):
        await asyncio.sleep(0.2)
        return await super().narrative(*args, **kwargs)


async def test_profiles_render_in_parallel() -> None:
    moment = streak_moment()
    started = time.perf_counter()
    output = await Producer(SlowRenderer()).render(full_insight(moment), moment, moment_labels(moment), PROFILES)
    assert len(output.narratives) == 4
    assert time.perf_counter() - started < 0.6, "four 0.2 s renderings should overlap"


class FlakyRenderer(TemplateRenderer):
    """First narrative attempt per profile carries a wrong number; the retry is clean. The cue always fails."""

    def __init__(self) -> None:
        self.feedback_seen: list[list[str]] = []

    async def cue(self, insight, moment, labels, feedback):
        self.feedback_seen.append(list(feedback))
        return CueDraft(headline="Team: 99-pass move", metric_label="passes", metric_value="99")

    async def narrative(self, insight, moment, labels, profile, feedback):
        text = await super().narrative(insight, moment, labels, profile, feedback)
        return text if feedback else text.replace(f"{moment.evidence['pass_streak_passes']:g}", "99", 1)


async def test_failed_rendering_is_regenerated_once_with_feedback_then_dropped() -> None:
    moment = streak_moment()
    renderer = FlakyRenderer()
    output = await Producer(renderer).render(full_insight(moment), moment, moment_labels(moment), PROFILES[:2])
    assert output.cue is None and len(renderer.feedback_seen) == 2 and renderer.feedback_seen[1] and "99 not in cited evidence" in renderer.feedback_seen[1][0]
    assert len(output.narratives) == 2 and output.dropped_profiles == []
    assert output.regenerated == 3  # cue once, each narrative once
    assert [c.ok for c in output.checks if c.profile_key == "broadcast"] == [False, False]
    assert sum(not c.ok for c in output.checks) == 4 and sum(c.ok for c in output.checks) == 2


async def test_foundry_renderer_prompts_are_digits_only_and_parse_structured_cues() -> None:
    moment = streak_moment()
    insight = full_insight(moment)
    agent = FakeAgent({"headline": "Ironvale: 22-pass move", "metric_label": "passes", "metric_value": "22", "priority": "high"})
    draft = await FoundryRenderer(agent).cue(insight, moment, moment_labels(moment), [])
    assert draft.headline.endswith("move") and draft.priority == "high"
    assert "digits only" in agent.prompts[0] and "22" in agent.prompts[0] and "22.0" not in agent.prompts[0]
    prompt = narrative_prompt(insight, moment, {"team": "Ironvale", "fan_player": "Remy Tallis"}, FanProfile(language="tr", depth="analyst", player_id="iva-06"), ["99 not in cited evidence"])
    assert "Turkish" in prompt and "keeping every number" in prompt and "Remy Tallis" in prompt and "failed the number check" in prompt
    assert "digits" in PRODUCER_INSTRUCTIONS and "never as words" in PRODUCER_INSTRUCTIONS
    assert cue_prompt(insight, moment, {}, []).count("\n") >= 3
