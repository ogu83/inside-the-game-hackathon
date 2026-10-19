from app.agents.analyst import HIGH_INTEREST, MAX_CUES_PER_2MIN, QUIET_PERIOD_S, FoundryDirector, PacingTracker, RuleDirector, angle_for, interest
from app.agents.fact_checker import FactChecker
from app.agents.fakes import ScriptedCommentator, TemplateCommentator
from app.agents.models import DirectorDecision, PacingState
from app.agents.prompts import director_prompt
from app.agents.run_match import close_t, run, summary
from app.agents.workflow import build_workflow, run_moment
from app.ledger.models import CandidateMoment
from app.ledger.state import detect_all
from app.simulator.engine import simulate
from tests.agents.test_fact_checker import MOMENT, insight


def streak(passes: float, shot: float = 0.0, top: float = 2.0) -> CandidateMoment:
    evidence = {**MOMENT.evidence, "pass_streak_passes": passes, "pass_streak_ended_in_shot": shot, "top_player_passes": top, "pass_streak_players": 7.0}
    return MOMENT.model_copy(update={"evidence": evidence})


def trap(distance: float) -> CandidateMoment:
    return MOMENT.model_copy(update={"kind": "pressing_trap", "evidence": {"pressing_trap_pressures": 2.0, "pressing_trap_regain_distance_to_goal_m": distance}})


def test_interest_and_angle_follow_the_evidence() -> None:
    assert interest(streak(10)) == 1.0 and interest(streak(22, shot=1.0)) == 3.2 and interest(streak(10, top=4)) == 1.3
    assert interest(trap(20.0)) == 1.7 and interest(trap(60.0)) == 1.2
    assert angle_for(streak(10)) == "control" and angle_for(streak(10, shot=1.0)) == "chance"
    assert angle_for(streak(10, top=5)) == "player" and angle_for(trap(20.0)) == "pressure"


def test_pacing_tracker_counts_recent_cues_and_ranks_moments() -> None:
    tracker = PacingTracker()
    first = tracker.state_for(streak(10), t=100)
    assert first == PacingState(seconds_since_last_cue=None, cues_last_2min=0, moments_last_2min=1, rank_among_recent=1, interest=1.0)
    tracker.record(DirectorDecision(moment_id="m", say=True, reason="r"), t=100)
    second = tracker.state_for(streak(14), t=150)
    assert second.seconds_since_last_cue == 50.0 and second.cues_last_2min == 1 and second.moments_last_2min == 2 and second.rank_among_recent == 1
    third = tracker.state_for(streak(10), t=160)
    assert third.rank_among_recent == 2
    tracker.record(DirectorDecision(moment_id="m", say=False, reason="r"), t=160)
    late = tracker.state_for(streak(10), t=400)
    assert late.cues_last_2min == 0 and late.moments_last_2min == 1 and late.seconds_since_last_cue == 300.0


async def test_rule_director_paces_the_commentary() -> None:
    director = RuleDirector()
    fresh = PacingState()
    assert (await director.decide(streak(10), {}, fresh)).say
    soon = PacingState(seconds_since_last_cue=QUIET_PERIOD_S - 1, cues_last_2min=1, interest=1.0)
    skipped = await director.decide(streak(10), {}, soon)
    assert not skipped.say and "since the last cue" in skipped.reason and skipped.angle == "control"
    exceptional = PacingState(seconds_since_last_cue=5, cues_last_2min=1, interest=HIGH_INTEREST)
    assert (await director.decide(streak(22, shot=1.0), {}, exceptional)).reason == "exceptional moment"
    full = PacingState(seconds_since_last_cue=60, cues_last_2min=MAX_CUES_PER_2MIN, interest=3.0)
    assert not (await director.decide(streak(22, shot=1.0), {}, full)).say


class SkipDirector:
    async def decide(self, moment, labels, pacing):
        return DirectorDecision(moment_id=moment.moment_id, say=False, angle="control", reason="scripted skip")


async def test_skipped_moment_never_reaches_the_commentator() -> None:
    writer = ScriptedCommentator([insight("x")])
    result = await run_moment(build_workflow(writer, FactChecker(None), SkipDirector()), MOMENT)
    assert result.verdict is None and result.attempts == [] and result.checks == []
    assert result.decision.say is False and result.decision.reason == "scripted skip"
    assert writer.calls == []


async def test_angle_reaches_the_commentator() -> None:
    result = await run_moment(build_workflow(TemplateCommentator(), FactChecker(None), RuleDirector()), streak(14, top=5.0), {"team": "Kestrel Bay", "opponent": "Ironvale", "top_player": "Tomas Vire"})
    assert result.decision.angle == "player"
    assert result.verdict is not None and "Tomas Vire" in result.verdict.insight.claim and result.verdict.status == "verified"


async def test_seeded_match_is_paced_and_still_produces_enough_cues() -> None:
    events = simulate(7)
    moments = detect_all(events)
    results = await run(7, live=False, jsonl=None, limit=None)
    said = [(close_t(m, events), r) for m, r in zip(moments, results, strict=True) if r.decision.say]
    assert len(said) >= 15, summary(results)
    assert summary(results)["skipped"] >= 1
    for (t_prev, _), (t, r) in zip(said, said[1:]):
        assert t - t_prev >= QUIET_PERIOD_S or r.decision.reason == "exceptional moment"
    for t, _ in said:
        assert sum(t - 120 <= other <= t for other, _ in said) <= MAX_CUES_PER_2MIN


class FakeAgent:
    def __init__(self, value):
        self.value = value
        self.prompts = []

    async def run(self, prompt, options=None):
        self.prompts.append(prompt)
        return type("R", (), {"value": self.value})()


async def test_foundry_director_parses_the_model_output_and_prompts_with_pacing() -> None:
    agent = FakeAgent({"moment_id": "wrong", "say": True, "angle": "control", "reason": "fine"})
    decision = await FoundryDirector(agent).decide(MOMENT, {"team": "Kestrel Bay"}, PacingState(cues_last_2min=2))
    assert decision.moment_id == MOMENT.moment_id and decision.say
    prompt = agent.prompts[0]
    assert '"cues_last_2min": 2' in prompt and '"pass_streak_passes": 14,' in prompt and "Kestrel Bay" in prompt
    assert director_prompt(MOMENT, {}, PacingState()).startswith("Team:")
