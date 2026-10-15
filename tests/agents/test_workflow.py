import json

import pytest

from app.agents.fact_checker import FactChecker
from app.agents.fakes import AlwaysVerifies, ScriptedCommentator, TemplateCommentator, TemplateRenderer
from app.agents.models import FanProfile, Insight, MomentResult
from app.agents.producer import Producer
from app.agents.run_match import run, summary
from app.agents.workflow import build_workflow, run_moment
from app.ledger.labels import moment_labels
from app.ledger.state import detect_all
from app.simulator.engine import simulate
from tests.agents.test_fact_checker import MOMENT, insight


@pytest.fixture(scope="module")
def moments():
    return detect_all(simulate(7))


async def test_template_commentator_passes_both_layers_on_real_moments(moments) -> None:
    workflow = build_workflow(TemplateCommentator(), FactChecker(AlwaysVerifies()))
    results = [await run_moment(workflow, m) for m in moments[:8]]
    assert all(r.verdict.status == "verified" and r.verdict.attempt == 1 for r in results)
    assert all(c.ok for r in results for c in r.checks)
    assert "Kestrel Bay" in results[0].attempts[0].claim or "Ironvale" in results[0].attempts[0].claim


async def test_template_commentator_handles_pressing_traps(moments) -> None:
    trap = next(m for m in moments if m.kind == "pressing_trap")
    result = await run_moment(build_workflow(TemplateCommentator(), FactChecker(None)), trap)
    assert result.verdict.status == "verified"
    assert "pressed" in result.attempts[0].claim and "won the ball" in result.attempts[0].claim
    output = await Producer(TemplateRenderer()).render(result.attempts[0], trap, moment_labels(trap), [FanProfile(language="tr")])
    assert output.cue is not None and output.cue.priority == "high" and all(c.ok for c in output.checks)
    assert len(output.narratives) == 1 and "baskı" in output.narratives[0].text


async def test_rejected_insight_is_retried_once_with_feedback() -> None:
    writer = ScriptedCommentator([insight("Ironvale have had 6 shots."), insight("Kestrel Bay have 68% of the ball.")])
    result = await run_moment(build_workflow(writer, FactChecker(AlwaysVerifies())), MOMENT)
    assert result.verdict.status == "verified" and result.verdict.attempt == 2
    assert len(result.attempts) == 2
    assert writer.calls[1] == ["6 not in cited evidence (pass_streak_passes = 14, team_possession_pct_window = 67.6)"]
    assert [c.ok for c in result.checks] == [False, True]


async def test_second_rejection_is_final() -> None:
    writer = ScriptedCommentator([insight("Ironvale have had 6 shots."), insight("Ironvale have had six shots.")])
    result = await run_moment(build_workflow(writer, FactChecker(AlwaysVerifies())), MOMENT)
    assert result.verdict.status == "rejected" and result.verdict.attempt == 2 and result.verdict.layer == "code"
    assert len(writer.calls) == 2
    assert result.verdict.reasons == ["number written as word: six"]


async def test_workflow_output_is_json_safe_and_revalidates() -> None:
    result = await run_moment(build_workflow(TemplateCommentator(), FactChecker(None)), MOMENT)
    roundtrip = MomentResult.model_validate(json.loads(result.model_dump_json()))
    assert roundtrip == result
    assert result.verdict.layer == "code"


def test_labels_name_teams_not_ids() -> None:
    labels = moment_labels(MOMENT)
    assert labels["team"] == "Kestrel Bay" and labels["opponent"] == "Ironvale"
    assert "top_player" not in labels
    assert moment_labels(MOMENT.model_copy(update={"top_player_id": "kby-02"}))["top_player"] == "Tomas Vire"


async def test_template_producer_renders_cue_and_narratives(moments) -> None:
    moment = moments[1]
    ins = Insight(moment_id=moment.moment_id, claim="c", why_it_matters="w", evidence_refs=list(moment.evidence), confidence=1)
    profiles = [FanProfile(language="en"), FanProfile(language="tr", depth="analyst", club_id="iva")]
    output = await Producer(TemplateRenderer()).render(ins, moment, moment_labels(moment), profiles)
    assert output.cue is not None and output.cue.show_at_seq == moment.window[1] and len(output.cue.headline) <= 60
    assert [n.profile_key for n in output.narratives] == [p.key() for p in profiles]
    assert all(c.ok for c in output.checks) and output.dropped_profiles == [] and output.regenerated == 0
    assert FanProfile(language="tr", depth="analyst", club_id="iva").key() == "iva|-|analyst|tr"


async def test_producer_gate_drops_a_rendering_that_cites_nothing(moments) -> None:
    moment = moments[0]
    ins = Insight(moment_id=moment.moment_id, claim="14 passes", why_it_matters="w", evidence_refs=[], confidence=1)
    output = await Producer(TemplateRenderer()).render(ins, moment, {}, [FanProfile()])
    assert output.narratives == [] and output.dropped_profiles == [FanProfile().key()]
    assert output.cue is None  # the fallback headline carries the uncited 14
    no_numbers = Insight(moment_id=moment.moment_id, claim="patient play", why_it_matters="w", evidence_refs=[], confidence=1)
    output = await Producer(TemplateRenderer()).render(no_numbers, moment, {}, [FanProfile()])
    assert output.cue is not None and len(output.narratives) == 1


async def test_run_match_offline_summary_and_jsonl(tmp_path) -> None:
    out = tmp_path / "7.jsonl"
    results = await run(7, live=False, jsonl=out, limit=5)
    report = summary(results)
    assert report["moments"] == 5 and report["verified"] == 5 and report["number_checks_failed"] == 0
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 5 and {"moment", "verdict", "attempts", "checks"} <= rows[0].keys()
