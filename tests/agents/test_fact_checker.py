import pytest

from app.agents.fact_check_rules import check_insight
from app.agents.fact_checker import FactChecker
from app.agents.fakes import AlwaysVerifies, ScriptedJudge
from app.agents.models import Insight, WordingVerdict
from app.ledger.models import CandidateMoment

MOMENT = CandidateMoment(
    moment_id="kby-iva-7-120-pass_streak", window=(100, 120), kind="pass_streak", team_id="kby", minute=11,
    evidence={"pass_streak_passes": 14.0, "pass_streak_duration_s": 52.0, "team_possession_pct_window": 67.6, "window_minutes": 5.0, "minute": 11.0},
)
LABELS = {"team": "Kestrel Bay", "opponent": "Ironvale"}


def insight(claim: str, why: str = "It matters.", refs: list[str] | None = None) -> Insight:
    return Insight(moment_id=MOMENT.moment_id, claim=claim, why_it_matters=why, evidence_refs=refs if refs is not None else ["pass_streak_passes", "team_possession_pct_window"], confidence=0.8)


def test_layer_1_accepts_an_insight_whose_numbers_are_cited() -> None:
    verdict, check = check_insight(insight("Kestrel Bay have 68% of the ball after a 14-pass move."), MOMENT, 1)
    assert verdict is None
    assert check.ok and check.gate == "insight"


def test_layer_1_rejects_a_missing_key_without_a_model() -> None:
    verdict, _ = check_insight(insight("Kestrel Bay are flying.", refs=["pass_streak_passes", "home_shots"]), MOMENT, 1)
    assert verdict is not None
    assert verdict.status == "rejected" and verdict.layer == "code" and verdict.attempt == 1
    assert verdict.reasons == ["unknown evidence key: home_shots"]


def test_layer_1_rejects_a_mismatched_number() -> None:
    verdict, check = check_insight(insight("Kestrel Bay have had 6 shots in this spell."), MOMENT, 2)
    assert verdict is not None and verdict.attempt == 2
    assert not check.ok
    assert verdict.reasons == ["6 not in cited evidence (pass_streak_passes = 14, team_possession_pct_window = 67.6)"]


def test_layer_1_rejects_an_uncited_but_true_number() -> None:
    verdict, _ = check_insight(insight("A 52-second spell of 14 passes.", refs=["pass_streak_passes"]), MOMENT, 1)
    assert verdict is not None
    assert verdict.reasons == ["52 not in cited evidence (pass_streak_passes = 14)"]


def test_layer_1_rejects_the_wrong_moment() -> None:
    other = insight("Kestrel Bay keep the ball.").model_copy(update={"moment_id": "other"})
    verdict, _ = check_insight(other, MOMENT, 1)
    assert verdict is not None and verdict.reasons[0].startswith("insight is about other")


def test_claims_without_numbers_pass_layer_1() -> None:
    verdict, check = check_insight(insight("Kestrel Bay are controlling the tempo.", refs=[]), MOMENT, 1)
    assert verdict is None and check.ok


async def test_layer_2_verifies_wording() -> None:
    checker = FactChecker(AlwaysVerifies())
    verdict, checks = await checker.check(insight("Kestrel Bay have 68% of the ball."), MOMENT, LABELS, 1)
    assert verdict.status == "verified" and verdict.layer == "llm"
    assert len(checks) == 1


async def test_layer_2_is_skipped_when_code_rejects() -> None:
    judge = ScriptedJudge([WordingVerdict(status="verified")])
    verdict, _ = await FactChecker(judge).check(insight("Kestrel Bay have 70% of the ball."), MOMENT, LABELS, 1)
    assert verdict.status == "rejected" and verdict.layer == "code"
    assert judge.calls == 0


async def test_layer_2_rewrite_is_number_checked_again() -> None:
    good = WordingVerdict(status="rewritten", reasons=["'dominated' overstates 68%"], claim="Kestrel Bay have 68% of the ball and are in control.")
    verdict, checks = await FactChecker(ScriptedJudge([good])).check(insight("Kestrel Bay have dominated with 68% of the ball."), MOMENT, LABELS, 1)
    assert verdict.status == "rewritten" and verdict.layer == "llm"
    assert verdict.insight is not None and verdict.insight.claim == good.claim
    assert len(checks) == 2 and all(c.ok for c in checks)

    bad = WordingVerdict(status="rewritten", claim="Kestrel Bay have 70% of the ball.")
    verdict, checks = await FactChecker(ScriptedJudge([bad])).check(insight("Kestrel Bay have dominated with 68% of the ball."), MOMENT, LABELS, 1)
    assert verdict.status == "rejected" and verdict.layer == "code"
    assert verdict.reasons[0] == "rewrite failed the number check"
    assert [c.ok for c in checks] == [True, False]


async def test_layer_2_can_reject_wording() -> None:
    judge = ScriptedJudge([WordingVerdict(status="rejected", reasons=["'one-way' is not supported by 68%"])])
    verdict, _ = await FactChecker(judge).check(insight("It has been one-way traffic, 68% of the ball."), MOMENT, LABELS, 1)
    assert verdict.status == "rejected" and verdict.layer == "llm"


def test_insight_confidence_is_bounded() -> None:
    with pytest.raises(ValueError):
        Insight(moment_id="m", claim="x", why_it_matters="y", evidence_refs=[], confidence=1.5)


from app.agents.fact_check_rules import check_actors  # noqa: E402

IVA_TRAP = CandidateMoment(
    moment_id="kby-iva-30-474-pressing_trap", window=(470, 474), kind="pressing_trap", team_id="iva", minute=20, top_player_id="iva-10",
    evidence={"pressing_trap_pressures": 2.0, "pressing_trap_window_s": 21.0, "pressing_trap_regain_distance_to_goal_m": 25.5},
)
IVA_LABELS = {"team": "Ironvale", "opponent": "Kestrel Bay", "top_player": "Jory Calloway"}
KBY_LABELS = {"team": "Kestrel Bay", "opponent": "Ironvale"}


def test_swapped_team_is_rejected_by_code_the_live_case() -> None:
    claim = Insight(moment_id=IVA_TRAP.moment_id, claim="Kestrel Bay set a pressing trap with 2 pressures in 21 seconds and Jory Calloway led the action.",
                    why_it_matters="Winning it 25.5 metres from goal is a chance.", evidence_refs=list(IVA_TRAP.evidence), confidence=0.8)
    verdict, check = check_insight(claim, IVA_TRAP, 1, IVA_LABELS)
    assert check.ok, "the numbers are right; the attribution is wrong"
    assert verdict is not None and verdict.layer == "code"
    assert verdict.reasons == ["Kestrel Bay named as the actor, but the moment is Ironvale's (name Ironvale as the actor, or use opponent phrasing such as 'against Kestrel Bay')"]
    assert check_insight(claim, IVA_TRAP, 1)[0] is None, "without labels the attribution check cannot run"


def test_opponent_allowed_only_as_the_one_acted_upon_en() -> None:
    assert check_actors("Ironvale sprung a pressing trap against Kestrel Bay and won it 25.5 metres from goal.", IVA_TRAP, IVA_LABELS) == []
    assert check_actors("Ironvale won the ball from Luca Brightwater high up the pitch.", IVA_TRAP, IVA_LABELS) == []
    assert check_actors("Ironvale pressed Kestrel Bay into a mistake.", IVA_TRAP, IVA_LABELS) == []
    assert check_actors("It comes with 68% of the ball, so Kestrel Bay are chasing.", IVA_TRAP, IVA_LABELS) == []
    assert check_actors("Kestrel Bay could not get out of their half.", IVA_TRAP, IVA_LABELS) == []
    assert check_actors("Luca Brightwater led the press and Ironvale won it.", IVA_TRAP, IVA_LABELS) == ["Luca Brightwater plays for Kestrel Bay, not Ironvale (name one of Ironvale's players, or use opponent phrasing)"]
    assert check_actors("Kestrel Bay have strung together 22 passes.", IVA_TRAP, IVA_LABELS)[0].startswith("Kestrel Bay named as the actor")
    assert check_actors("Jory Calloway won the ball for Ironvale.", IVA_TRAP, IVA_LABELS) == [], "the moment's own player is fine"
    assert check_actors("Ironvale have strung together 10 passes.", IVA_TRAP, KBY_LABELS)[0].startswith("Ironvale named as the actor")


def test_opponent_allowed_only_as_the_one_acted_upon_tr() -> None:
    assert check_actors("Kestrel Bay 21 saniyede 2 kez baskı yaptı ve topu kazandı.", IVA_TRAP, IVA_LABELS, "tr")[0].startswith("Kestrel Bay named as the actor")
    assert check_actors("Ironvale, Kestrel Bay'a karşı 21 saniyede 2 kez baskı yaptı.", IVA_TRAP, IVA_LABELS, "tr") == []
    assert check_actors("Ironvale Kestrel Bay savunmasında topu kazandı.", IVA_TRAP, IVA_LABELS, "tr") == []
    assert check_actors("Ironvale topu Luca Brightwater'dan kazandı.", IVA_TRAP, IVA_LABELS, "tr") == []
    assert check_actors("Luca Brightwater baskıya öncülük etti.", IVA_TRAP, IVA_LABELS, "tr")[0].startswith("Luca Brightwater plays for Kestrel Bay")


async def test_fact_checker_passes_labels_so_the_rewrite_is_checked_too() -> None:
    judge = ScriptedJudge([WordingVerdict(status="rewritten", claim="Kestrel Bay set the trap with 2 pressures in 21 seconds.")])
    good = Insight(moment_id=IVA_TRAP.moment_id, claim="Ironvale set a pressing trap with 2 pressures in 21 seconds.", why_it_matters="w", evidence_refs=list(IVA_TRAP.evidence), confidence=0.8)
    verdict, checks = await FactChecker(judge).check(good, IVA_TRAP, IVA_LABELS, 1)
    assert verdict.status == "rejected" and verdict.reasons[0] == "rewrite failed the number check" and "Kestrel Bay named as the actor" in verdict.reasons[1]


def test_opponent_as_place_or_object_passes_layer_1_live_cases() -> None:
    # 6 real cases from Foundry evaluation
    s1 = "The regain comes 38.2 m from goal, which can leave Ironvale starting again in their own half."
    assert check_actors(s1, MOMENT, KBY_LABELS) == []
    s2 = "That turn-over happened in Ironvale territory and can set up the next action nearer the attacking end."
    assert check_actors(s2, MOMENT, KBY_LABELS) == []
    s3 = "That sequence turns possession into a shot and carries the ball 49.4 m into Kestrel Bay territory."
    assert check_actors(s3, IVA_TRAP, IVA_LABELS) == []
    s4 = "The move carried the ball 69.5 m into Ironvale territory, but it ended without a shot."
    assert check_actors(s4, MOMENT, KBY_LABELS) == []
    s5 = "That spell gave Ironvale a longer spell in Kestrel Bay territory."
    assert check_actors(s5, IVA_TRAP, IVA_LABELS) == []
    s6 = "That turnover leaves Ironvale starting from 45.9 metres out, which can push the next action into Kestrel Bay territory."
    assert check_actors(s6, MOMENT, KBY_LABELS) == []


def test_opponent_possessive_and_locative_place_mentions() -> None:
    # English place nouns and possessives
    assert check_actors("Kestrel Bay kept the ball in Ironvale's half.", MOMENT, KBY_LABELS) == []
    assert check_actors("The attack reached Ironvale's territory.", MOMENT, KBY_LABELS) == []
    assert check_actors("They pushed into Ironvale's box.", MOMENT, KBY_LABELS) == []
    assert check_actors("The ball was delivered into the Ironvale area.", MOMENT, KBY_LABELS) == []
    assert check_actors("Kestrel Bay threatened the Ironvale goal.", MOMENT, KBY_LABELS) == []
    assert check_actors("They probed the Ironvale defence.", MOMENT, KBY_LABELS) == []
    assert check_actors("A shot tested the Ironvale defense.", MOMENT, KBY_LABELS) == []
    assert check_actors("Action stayed at the Ironvale end of the pitch.", MOMENT, KBY_LABELS) == []
    assert check_actors("The move developed on the Ironvale side.", MOMENT, KBY_LABELS) == []
    assert check_actors("Possession was contested in the Ironvale third.", MOMENT, KBY_LABELS) == []
    assert check_actors("Ironvale were pinned in their own half.", MOMENT, KBY_LABELS) == []
    assert check_actors("That tackle puts Ironvale under pressure.", MOMENT, KBY_LABELS) == []
    assert check_actors("Kestrel Bay keep Ironvale penned in.", MOMENT, KBY_LABELS) == []
    assert check_actors("The press will force Ironvale to clear long.", MOMENT, KBY_LABELS) == []

    # Turkish place nouns and possessives
    assert check_actors("Kestrel Bay, Ironvale'in yarı sahasında baskı kurdu.", MOMENT, KBY_LABELS, "tr") == []
    assert check_actors("Kestrel Bay, Ironvale yarı sahasında topu kazandı.", MOMENT, KBY_LABELS, "tr") == []
    assert check_actors("Kestrel Bay topu Ironvale ceza sahasına taşıdı.", MOMENT, KBY_LABELS, "tr") == []
    assert check_actors("Ironvale kalesinde tehlike yaşandı.", MOMENT, KBY_LABELS, "tr") == []
    assert check_actors("Kestrel Bay, Ironvale savunmasını zorladı.", MOMENT, KBY_LABELS, "tr") == []
    assert check_actors("Oyun Ironvale bölgesinde geçti.", MOMENT, KBY_LABELS, "tr") == []
    assert check_actors("Ironvale'i kendi yarı sahasında bıraktı.", MOMENT, KBY_LABELS, "tr") == []
    assert check_actors("Ironvale'i baskı altında tuttu.", MOMENT, KBY_LABELS, "tr") == []


def test_opponent_acting_still_fails_layer_1() -> None:
    # Swapped team as actor must still fail
    assert check_actors("Kestrel Bay set a pressing trap with 2 pressures.", IVA_TRAP, IVA_LABELS)[0].startswith("Kestrel Bay named as the actor")
    assert check_actors("Kestrel Bay's pressing trap caught Ironvale.", IVA_TRAP, IVA_LABELS)[0].startswith("Kestrel Bay named as the actor")
    assert check_actors("Kestrel Bay have strung together 22 passes.", IVA_TRAP, IVA_LABELS)[0].startswith("Kestrel Bay named as the actor")
    assert check_actors("Luca Brightwater led the press and Ironvale won it.", IVA_TRAP, IVA_LABELS)[0].startswith("Luca Brightwater plays for Kestrel Bay")
    assert check_actors("Luca Brightwater's pass opened up the defence.", IVA_TRAP, IVA_LABELS)[0].startswith("Luca Brightwater plays for Kestrel Bay")

    # Turkish swapped team as actor must still fail
    assert check_actors("Kestrel Bay 21 saniyede 2 kez baskı yaptı.", IVA_TRAP, IVA_LABELS, "tr")[0].startswith("Kestrel Bay named as the actor")
    assert check_actors("Kestrel Bay'in baskısı sonuç verdi.", IVA_TRAP, IVA_LABELS, "tr")[0].startswith("Kestrel Bay named as the actor")
    assert check_actors("Luca Brightwater baskıya öncülük etti.", IVA_TRAP, IVA_LABELS, "tr")[0].startswith("Luca Brightwater plays for Kestrel Bay")


def test_insight_minute_passes_without_evidence_refs() -> None:
    # Minute is in candidate moment (minute=11)
    ins = insight("At minute 11, Kestrel Bay had 14 passes.", refs=["pass_streak_passes"])
    verdict, check = check_insight(ins, MOMENT, 1)
    assert verdict is None and check.ok

    # Wrong minute fails
    wrong = insight("At minute 20, Kestrel Bay had 14 passes.", refs=["pass_streak_passes"])
    verdict_wrong, check_wrong = check_insight(wrong, MOMENT, 1)
    assert verdict_wrong is not None and not check_wrong.ok

