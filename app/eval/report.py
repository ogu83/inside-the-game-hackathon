"""Render docs/eval-results.md from saved evaluation results. Never invents numbers: without results it says so."""

from __future__ import annotations

from datetime import UTC, datetime
from statistics import mean
from typing import Any

from app.eval.export_runs import CONDITIONS, EvalRecord

EVALUATORS = ("groundedness", "relevance", "coherence")
LABELS = {"checker_on": "Fact-Checker on (what aired)", "checker_off": "Fact-Checker off (first drafts aired)",
          "planted_on": "Planted errors, Fact-Checker on", "planted_off": "Planted errors, Fact-Checker off"}


def own_metrics(records: list[EvalRecord]) -> dict[str, Any]:
    """Deterministic metrics over the same aired texts: layer 1 pass rate and planted errors that reached air."""
    planted = [r for r in records if r.planted_kind]
    return {
        "n": len(records),
        "number_check_pass_rate": (sum(r.number_check_ok for r in records) / len(records)) if records else None,
        "planted_n": len(planted),
        "planted_reached_air": sum(bool(r.planted_reached_air) for r in planted),
        "planted_caught": sum(not r.planted_reached_air for r in planted),
    }


def evaluator_stats(result: dict[str, Any] | None) -> dict[str, dict[str, float | int | None]]:
    """Mean score and pass rate per evaluator from a saved EvalResults dict (items[*].scores[*])."""
    stats: dict[str, dict[str, float | int | None]] = {}
    if not result:
        return stats
    for name in EVALUATORS:
        scores = [s["score"] for item in result.get("items", []) for s in item.get("scores", []) if s.get("name", "").casefold().startswith(name) and s.get("score") is not None]
        passed = [s["passed"] for item in result.get("items", []) for s in item.get("scores", []) if s.get("name", "").casefold().startswith(name) and s.get("passed") is not None]
        if scores or passed:
            stats[name] = {"n": len(scores), "mean": round(mean(scores), 2) if scores else None, "pass_rate": (sum(passed) / len(passed)) if passed else None}
    return stats


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.0f}%"


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def groundedness_change(on_mean: float, off_mean: float) -> str:
    """Describe how Groundedness changed between checker-off and checker-on."""
    diff = round(on_mean - off_mean, 4)
    if diff >= 0.1:
        return f"rose from {_num(off_mean)} to {_num(on_mean)}"
    if diff <= -0.1:
        return f"fell from {_num(off_mean)} to {_num(on_mean)}"
    return f"was unchanged ({_num(on_mean)} vs {_num(off_mean)})"


def headline(records: dict[str, list[EvalRecord]], results: dict[str, dict[str, Any]]) -> str:
    on = evaluator_stats(results.get("checker_on")).get("groundedness", {})
    off = evaluator_stats(results.get("checker_off")).get("groundedness", {})
    p_on_eval = evaluator_stats(results.get("planted_on")).get("groundedness", {})
    p_off_eval = evaluator_stats(results.get("planted_off")).get("groundedness", {})
    p_on_mean, p_off_mean = p_on_eval.get("mean"), p_off_eval.get("mean")
    p_on_pass, p_off_pass = p_on_eval.get("pass_rate"), p_off_eval.get("pass_rate")
    p_on_rec, p_off_rec = own_metrics(records.get("planted_on", [])), own_metrics(records.get("planted_off", []))

    if not results or on.get("mean") is None or off.get("mean") is None:
        return "Not run yet: the evaluation has not been executed against Foundry, so there are no scores to report."

    on_mean, off_mean = on["mean"], off["mean"]
    diff = round(on_mean - off_mean, 4)

    has_planted = (
        results.get("planted_on") is not None
        and results.get("planted_off") is not None
        and p_on_mean is not None
        and p_off_mean is not None
        and p_off_rec["planted_n"] > 0
    )

    if has_planted:
        if diff >= 0.1:
            normal = f"in normal play Groundedness rose from {_num(off_mean)} to {_num(on_mean)}"
        elif diff <= -0.1:
            normal = f"in normal play Groundedness fell from {_num(off_mean)} to {_num(on_mean)}"
        elif f"{on_mean:.1f}" == f"{off_mean:.1f}":
            normal = f"in normal play both conditions scored about {on_mean:.1f} because first drafts were already accurate"
        else:
            normal = f"in normal play Groundedness was unchanged ({_num(on_mean)} vs {_num(off_mean)}) because first drafts were already accurate"
        return (
            f"With planted errors, the Fact-Checker kept Groundedness at {_num(p_on_mean)} ({_pct(p_on_pass)} pass) "
            f"against {_num(p_off_mean)} ({_pct(p_off_pass)} pass) without it, and {p_on_rec['planted_reached_air']} of "
            f"{p_on_rec['planted_n']} planted errors reached air against {p_off_rec['planted_reached_air']} of {p_off_rec['planted_n']}; "
            f"{normal}."
        )

    return f"With the Fact-Checker on, Groundedness {groundedness_change(on_mean, off_mean)}."


def render_markdown(records: dict[str, list[EvalRecord]], results: dict[str, dict[str, Any]], manifest: dict[str, Any] | None, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    ran = bool(results)
    lines = [
        "# Evaluation results: Fact-Checker on versus off",
        "",
        f"Generated {now.strftime('%Y-%m-%d %H:%M UTC')} by `python -m app.eval.run_eval`. "
        + (f"Seeds {', '.join(str(s) for s in manifest['seeds'])}, first {manifest['limit']} moments each, agents {'live (Foundry)' if manifest.get('live') else 'offline (templates)'}, exported {manifest['exported_at']}."
           if manifest else "No export manifest found."),
        "",
        f"**Headline:** {headline(records, results)}",
        "",
        "Foundry evaluators (judge model from `SMALL_MODEL_DEPLOYMENT`): Groundedness, Relevance, Coherence, scored 1 to 5 by the service; "
        "pass rate is the service's threshold. Our own deterministic metric over the same aired texts: the layer 1 number and actor check, and for the planted conditions how many planted insights reached air.",
        "",
        "| Condition | Items | Groundedness mean | pass | Relevance mean | pass | Coherence mean | pass | Layer 1 pass (numbers and actors) | Planted caught / reached air | Status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for condition in CONDITIONS:
        recs = records.get(condition, [])
        own = own_metrics(recs)
        result = results.get(condition)
        stats = evaluator_stats(result)
        cells = [LABELS[condition], str(own["n"])]
        for name in EVALUATORS:
            st = stats.get(name, {})
            cells += [_num(st.get("mean")), _pct(st.get("pass_rate"))]
        cells.append(_pct(own["number_check_pass_rate"]))
        cells.append(f"{own['planted_caught']} / {own['planted_reached_air']} of {own['planted_n']}" if own["planted_n"] else "no plants")
        cells.append(result.get("status", "unknown") if result else "not run yet")
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "## Runs", ""]
    if not ran:
        lines.append("Not run yet. `python -m app.eval.run_eval runs/eval` submits one evaluation per condition and fills this section with run ids and portal links.")
    for condition in CONDITIONS:
        result = results.get(condition)
        if result:
            link = f" [portal]({result['report_url']})" if result.get("report_url") else ""
            lines.append(f"- {LABELS[condition]}: eval `{result.get('eval_id', '')}`, run `{result.get('run_id', '')}`, status {result.get('status', '')}{link}"
                         + (f", error: {result['error']}" if result.get("error") else ""))
    if manifest:
        lines += ["", "## Export", "", f"Rejected by the Fact-Checker (did not air, so absent from the on conditions): {manifest.get('rejected_by_seed', {})}. "
                  f"Skipped by the director: {manifest.get('skipped_by_seed', {})}. Planted run: {manifest.get('planted', {})}."]
    lines += ["", "Rejected moments do not air and are therefore not evaluated in the on conditions; the off conditions evaluate every first draft the director let through. "
              "Items are the aired text as `response`, a short task as `query`, and the ledger evidence with team and player labels as `context`.", ""]
    return "\n".join(lines)
