import json

from app.agents.models import DirectorDecision, Insight, MomentResult, Verdict
from app.eval.export_runs import CONDITIONS, EvalRecord, build_records, read_jsonl, render_context, write_jsonl
from app.ledger.labels import moment_labels
from app.ledger.state import detect_all
from app.simulator.engine import simulate

MOMENTS = detect_all(simulate(30))[:4]


def claim_for(moment) -> str:
    e = moment.evidence
    if "pass_streak_passes" in e:
        return f"First draft {e['pass_streak_passes']:g} passes in {e['pass_streak_duration_s']:g} seconds."
    return f"First draft {e['pressing_trap_pressures']:g} pressures in {e['pressing_trap_window_s']:g} seconds."


def result(moment, say=True, status="verified", first_claim=None, final_claim=None, refs=None):
    first_claim = first_claim or claim_for(moment)
    refs = refs if refs is not None else list(moment.evidence)
    first = Insight(moment_id=moment.moment_id, claim=first_claim, why_it_matters="Why.", evidence_refs=refs, confidence=0.8)
    decision = DirectorDecision(moment_id=moment.moment_id, say=say, angle="control", reason="r")
    if not say:
        return MomentResult(moment_id=moment.moment_id, decision=decision)
    final = first if final_claim is None else first.model_copy(update={"claim": final_claim})
    verdict = Verdict(moment_id=moment.moment_id, status=status, insight=None if status == "rejected" else final, reasons=[], layer="code" if status == "rejected" else "llm", attempt=1)
    return MomentResult(moment_id=moment.moment_id, decision=decision, verdict=verdict, attempts=[first] if final_claim is None else [first, final])


def test_two_records_per_said_moment_off_uses_the_first_draft() -> None:
    m = MOMENTS[0]
    records, counts = build_records([result(m, final_claim=claim_for(m).replace("First draft", "Rewritten claim"), status="rewritten")], [m], 30)
    assert counts == {"said": 1, "rejected": 0, "skipped": 0}
    off, on = [r for r in records if r.condition == "checker_off"][0], [r for r in records if r.condition == "checker_on"][0]
    assert off.response.startswith("First draft") and off.status == "first_draft"
    assert on.response.startswith("Rewritten claim") and on.status == "rewritten"
    assert off.query == on.query and off.context == on.context and off.seed == 30 and off.moment_id == m.moment_id


def test_context_contains_every_cited_key_and_the_labels() -> None:
    m = MOMENTS[0]
    [off, on] = build_records([result(m)], [m], 30)[0]
    labels = moment_labels(m)
    for key in on.cited_keys:
        assert f"{key}: " in on.context, key
    assert f"team: {labels['team']}" in on.context and f"opponent: {labels['opponent']}" in on.context
    assert "most involved player: " in on.context and ".0\n" not in on.context + "\n", "integral values render as integers"
    assert render_context(m, labels) == on.context


def test_rejected_moments_are_excluded_from_on_and_counted() -> None:
    m1, m2 = MOMENTS[0], MOMENTS[1]
    records, counts = build_records([result(m1, status="rejected", first_claim="Kestrel Bay had 9 shots."), result(m2)], [m1, m2], 30)
    assert counts["rejected"] == 1 and counts["said"] == 2
    on_ids = [r.moment_id for r in records if r.condition == "checker_on"]
    off_ids = [r.moment_id for r in records if r.condition == "checker_off"]
    assert on_ids == [m2.moment_id] and off_ids == [m1.moment_id, m2.moment_id], "the rejected first draft still airs in the off condition"
    bad = next(r for r in records if r.moment_id == m1.moment_id)
    assert bad.number_check_ok is False and all(r.number_check_ok for r in records if r.moment_id == m2.moment_id)


def test_skipped_moments_produce_no_records() -> None:
    m = MOMENTS[2]
    records, counts = build_records([result(m, say=False)], [m], 30)
    assert records == [] and counts == {"said": 0, "rejected": 0, "skipped": 1}


def test_planted_conditions_mark_the_plant_and_whether_it_aired() -> None:
    m = MOMENTS[0]
    planted_claim = "Ironvale have strung together 22 passes in 85 seconds."  # swapped team on a Kestrel Bay moment
    planted = Insight(moment_id=m.moment_id, claim=planted_claim, why_it_matters="Why.", evidence_refs=list(m.evidence), confidence=0.8)
    caught = result(m, first_claim=planted_claim, final_claim="Kestrel Bay have strung together 22 passes in 85 seconds.")
    records, _ = build_records([caught], [m], 30, on="planted_on", off="planted_off", planted={m.moment_id: ("swapped_team", planted)})
    off, on = [r for r in records if r.condition == "planted_off"][0], [r for r in records if r.condition == "planted_on"][0]
    assert off.planted_kind == on.planted_kind == "swapped_team"
    assert off.planted_reached_air is True and on.planted_reached_air is False
    missed = result(m, first_claim=planted_claim)  # the checker let it through
    [off2, on2] = build_records([missed], [m], 30, on="planted_on", off="planted_off", planted={m.moment_id: ("swapped_team", planted)})[0]
    assert on2.planted_reached_air is True


def test_jsonl_round_trip(tmp_path) -> None:
    m = MOMENTS[0]
    records, _ = build_records([result(m)], [m], 30)
    paths = write_jsonl(records, tmp_path)
    assert set(paths) == set(CONDITIONS)
    assert read_jsonl(paths["checker_on"]) == [r for r in records if r.condition == "checker_on"]
    assert read_jsonl(paths["planted_on"]) == []
    row = json.loads(paths["checker_off"].read_text(encoding="utf-8").splitlines()[0])
    assert {"query", "response", "context", "condition", "number_check_ok"} <= row.keys()
    EvalRecord.model_validate(row)
