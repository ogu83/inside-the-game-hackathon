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
