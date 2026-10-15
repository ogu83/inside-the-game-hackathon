import random

from app.agents.fact_check_rules import check_rendering
from app.agents.fakes import TemplateProducer
from app.agents.models import FanProfile, Insight
from app.agents.planted_errors import PlantPlan, corrupt_insight, corrupt_text, make_tamper, number_to_words
from app.agents.run_match import run_planted
from app.ledger.labels import moment_labels
from app.ledger.state import detect_all
from app.simulator.engine import simulate
from tests.agents.test_fact_checker import MOMENT, insight

LABELS = {"team": "Kestrel Bay", "opponent": "Ironvale"}


def test_number_words_in_both_languages() -> None:
    assert number_to_words(6, "en") == "six" and number_to_words(22, "en") == "twenty two" and number_to_words(100, "en") == "one hundred"
    assert number_to_words(6, "tr") == "altı" and number_to_words(68, "tr") == "altmış sekiz" and number_to_words(10, "tr") == "on"


def test_text_corruptions_are_caught_by_the_producer_gate() -> None:
    rng = random.Random(1)
    cited = {"pass_streak_passes": 14.0, "pass_streak_duration_s": 52.0}
    source = "Kestrel Bay have strung together 14 passes in 52 seconds."
    for lang, text in (("en", source), ("tr", "Kestrel Bay 14 pası 52 saniyede art arda tamamladı.")):
        changed = corrupt_text(text, lang, "changed_number", rng)
        dropped = corrupt_text(text, lang, "dropped_number", rng)
        words = corrupt_text(text, lang, "number_as_word", rng)
        assert changed != text and dropped != text and words != text
        assert "14" not in dropped and ("fourteen" in words or "on dört" in words)
        for corrupted in (changed, dropped, words):
            check = check_rendering(corrupted, cited, source, moment_id="m", profile_key="p", lang=lang, coverage="all")
            assert not check.ok, corrupted
    assert corrupt_text("no numbers here", "en", "changed_number", rng) == "no numbers here"


def test_dropped_number_is_tolerated_for_casual_but_not_analyst_depth() -> None:
    cited = {"pass_streak_passes": 14.0, "pass_streak_players": 8.0}
    source = "14 passes through 8 players"
    assert check_rendering("8 players kept the ball", cited, source, moment_id="m", profile_key="c", coverage="any").ok
    analyst = check_rendering("8 players kept the ball", cited, source, moment_id="m", profile_key="a", coverage="all")
    assert not analyst.ok and analyst.mismatches == ["dropped number: 14"]
    assert not check_rendering("they kept the ball", cited, source, moment_id="m", profile_key="c", coverage="any").ok
    assert check_rendering("they kept the ball", cited, "no numbers", moment_id="m", profile_key="c", coverage="any").ok


def test_insight_corruptions() -> None:
    rng = random.Random(3)
    base = insight("Kestrel Bay have 68% of the ball after a 14-pass move.")
    wrong = corrupt_insight(base, MOMENT, LABELS, "wrong_number", rng)
    assert wrong.claim != base.claim and "68" not in wrong.claim.split("%")[0][-3:]
    missing = corrupt_insight(base, MOMENT, LABELS, "missing_key", rng)
    assert "team_shots_last_10min" in missing.evidence_refs and "6 shots" in missing.claim
    swapped = corrupt_insight(base, MOMENT, LABELS, "swapped_team", rng)
    assert swapped.claim.startswith("Ironvale have 68%")


def test_plan_is_reproducible_and_covers_every_kind() -> None:
    ids = [f"m{i}" for i in range(12)]
    plan = PlantPlan.build(ids, 3, 3, seed=5)
    assert plan == PlantPlan.build(ids, 3, 3, seed=5)
    assert set(plan.insights.values()) == {"wrong_number", "missing_key", "swapped_team"}
    assert set(plan.renderings.values()) == {"changed_number", "dropped_number", "number_as_word"}
    assert not set(plan.insights) & set(plan.renderings)


def test_tamper_hook_only_touches_planned_moments() -> None:
    moments = detect_all(simulate(7))[:2]
    plan = PlantPlan(renderings={moments[0].moment_id: "changed_number"})
    log: list = []
    producer = TemplateProducer(tamper=make_tamper(plan, 0, log))
    for moment in moments:
        ins = Insight(moment_id=moment.moment_id, claim="c", why_it_matters="w", evidence_refs=list(moment.evidence), confidence=1)
        cue, check = producer.cue(ins, moment, moment_labels(moment))
        planned = moment.moment_id in plan.renderings
        assert (cue is None) == planned and check.ok != planned
        narrative, check = producer.narrative(ins, moment, moment_labels(moment), FanProfile(language="tr", depth="analyst"))
        assert (narrative is None) == planned
    assert log and all(m == moments[0].moment_id for m, _, _ in log)


async def test_offline_harness_catches_every_number_error_by_code() -> None:
    results, report = await run_planted(30, 6, live=False)
    assert report.planted >= 12
    for kind in ("wrong_number", "missing_key"):
        count = report.insights[kind]
        assert count.planted >= 1 and count.caught_by_code == count.planted and count.reached_air == 0
    for kind, count in report.renderings.items():
        assert count.planted >= 1, kind
        assert count.caught_by_code == count.planted and count.reached_air == 0, kind
    swapped = report.insights["swapped_team"]
    assert swapped.planted >= 1 and swapped.caught_by_code == 0, "a swapped team keeps every number right: only layer 2 can catch it"
    assert report.reached_air == swapped.reached_air, "offline mode has no wording judge; the live harness must bring this to 0"
    assert sum(len(r.attempts) - 1 for r in results) >= report.insights["wrong_number"].planted
    assert "caught" in report.headline()
