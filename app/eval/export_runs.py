"""Build evaluation items from real pipeline runs (SPEC criterion 8).

For every moment the director says, two aired texts come from the SAME run:
- checker_on:  what actually airs, the verified or rewritten insight (claim plus why it matters); rejected
               moments do not air and are counted separately;
- checker_off: the Commentator's first draft (attempt 1) aired unchanged.
The planted conditions do the same over the planted-error run (seed 30, first 12 moments, 4 insight plants and
4 rendering plants), so planted errors are visible to the evaluator: planted_on is what airs with the checker,
planted_off the corrupted first drafts.

Each item: query = a short task text for the moment, response = the aired text, context = the ledger evidence as
readable "key: value" lines plus team and player labels (what Groundedness judges against). A deterministic
layer 1 verdict (numbers and actor) is recorded per item next to the evaluator's.

    python -m app.eval.export_runs --seeds 7 30 42 --limit 12            # offline template agents
    python -m app.eval.export_runs --seeds 7 30 42 --limit 12 --live     # Foundry agents, costs tokens
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.fact_check_rules import check_insight
from app.agents.models import Insight, MomentResult
from app.agents.planted_errors import PlantingCommentator
from app.agents.prompts import evidence_for_prompt
from app.ledger.labels import moment_labels
from app.ledger.models import CandidateMoment

Condition = Literal["checker_on", "checker_off", "planted_on", "planted_off"]
CONDITIONS: tuple[Condition, ...] = ("checker_on", "checker_off", "planted_on", "planted_off")
DEFAULT_SEEDS = (7, 30, 42)
PLANTED_SEED = 30
PLANTED_N = 4
DEFAULT_OUT = Path("runs/eval")


class EvalRecord(BaseModel):
    """One evaluation item plus what we know about it ourselves."""

    condition: Condition
    seed: int
    moment_id: str
    kind: str
    team: str
    minute: int
    query: str
    response: str
    context: str
    cited_keys: list[str]
    status: str                       # verified | rewritten | first_draft
    number_check_ok: bool             # layer 1 (numbers and actor) on the aired text, deterministic
    planted_kind: str | None = None   # wrong_number | missing_key | swapped_team when this moment carried a plant
    planted_reached_air: bool | None = None  # for planted moments: did the planted claim air in this condition?


class ExportManifest(BaseModel):
    exported_at: str
    live: bool
    seeds: list[int]
    limit: int
    counts: dict[str, int]
    rejected_by_seed: dict[str, int]
    skipped_by_seed: dict[str, int]
    planted: dict[str, int] = Field(default_factory=dict)


def render_context(moment: CandidateMoment, labels: dict[str, str]) -> str:
    lines = [f"team: {labels.get('team', moment.team_id)}", f"opponent: {labels.get('opponent', 'the opposition')}"]
    if labels.get("top_player"):
        lines.append(f"most involved player: {labels['top_player']}")
    lines.append(f"moment kind: {labels.get('kind', moment.kind)}")
    lines += [f"{k}: {v}" for k, v in evidence_for_prompt(moment.evidence).items()]
    return "\n".join(lines)


def render_query(moment: CandidateMoment, labels: dict[str, str]) -> str:
    return (f"Commentate on this {labels.get('kind', moment.kind)} moment for {labels.get('team', moment.team_id)} in minute {moment.minute} "
            f"of the Meridian League match, using only the evidence given.")


def aired_text(insight: Insight) -> str:
    return f"{insight.claim} {insight.why_it_matters}".strip()


def _record(condition: Condition, seed: int, moment: CandidateMoment, labels: dict[str, str], insight: Insight, status: str,
            planted: Insight | None, planted_kind: str | None) -> EvalRecord:
    rejected, _ = check_insight(insight, moment, 1, labels)
    return EvalRecord(
        condition=condition, seed=seed, moment_id=moment.moment_id, kind=moment.kind, team=labels.get("team", moment.team_id), minute=moment.minute,
        query=render_query(moment, labels), response=aired_text(insight), context=render_context(moment, labels),
        cited_keys=list(insight.evidence_refs), status=status, number_check_ok=rejected is None,
        planted_kind=planted_kind, planted_reached_air=(insight.claim == planted.claim) if planted is not None else None,
    )


def build_records(results: list[MomentResult], moments: list[CandidateMoment], seed: int, *, on: Condition = "checker_on", off: Condition = "checker_off",
                  planted: dict[str, tuple[str, Insight]] | None = None) -> tuple[list[EvalRecord], dict[str, int]]:
    """Two records per said moment (on: aired, off: first draft). Returns (records, counts) with rejected and skipped totals.
    `planted` maps moment_id -> (kind, planted insight) for the planted conditions."""
    by_id = {m.moment_id: m for m in moments}
    records: list[EvalRecord] = []
    counts = {"said": 0, "rejected": 0, "skipped": 0}
    for result in results:
        moment = by_id[result.moment_id]
        labels = moment_labels(moment)
        if not result.decision.say:
            counts["skipped"] += 1
            continue
        counts["said"] += 1
        kind, planted_insight = (planted or {}).get(result.moment_id, (None, None))
        if result.attempts:
            records.append(_record(off, seed, moment, labels, result.attempts[0], "first_draft", planted_insight, kind))
        verdict = result.verdict
        if verdict is None or verdict.status == "rejected" or verdict.insight is None:
            counts["rejected"] += 1
            continue
        records.append(_record(on, seed, moment, labels, verdict.insight, verdict.status, planted_insight, kind))
    return records, counts


def write_jsonl(records: list[EvalRecord], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for condition in CONDITIONS:
        rows = [r for r in records if r.condition == condition]
        path = out_dir / f"{condition}.jsonl"
        path.write_text("".join(r.model_dump_json() + "\n" for r in rows), encoding="utf-8")
        paths[condition] = path
    return paths


def read_jsonl(path: Path) -> list[EvalRecord]:
    return [EvalRecord.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def export(seeds: list[int], limit: int, live: bool, out_dir: Path) -> ExportManifest:
    from app.agents.run_match import run, run_planted
    from app.ledger.state import detect_all
    from app.simulator.engine import simulate

    records: list[EvalRecord] = []
    rejected_by_seed: dict[str, int] = {}
    skipped_by_seed: dict[str, int] = {}
    for seed in seeds:
        moments = detect_all(simulate(seed))[:limit]
        results = await run(seed, live=live, jsonl=out_dir / f"run_{seed}.jsonl", limit=limit)
        recs, counts = build_records(results, moments, seed)
        records += recs
        rejected_by_seed[str(seed)] = counts["rejected"]
        skipped_by_seed[str(seed)] = counts["skipped"]

    planted_results, report = await run_planted(PLANTED_SEED, PLANTED_N, live=live, limit=limit)
    planted_moments = detect_all(simulate(PLANTED_SEED))[:limit]
    commentator = _planting_commentator(planted_results)
    plants = {mid: (commentator.plan.insights[mid], ins) for mid, ins in commentator.planted.items()} if commentator else {}
    recs, _ = build_records(planted_results, planted_moments, PLANTED_SEED, on="planted_on", off="planted_off", planted=plants)
    records += recs

    write_jsonl(records, out_dir)
    manifest = ExportManifest(
        exported_at=datetime.now(UTC).isoformat(timespec="seconds"), live=live, seeds=list(seeds), limit=limit,
        counts={c: sum(r.condition == c for r in records) for c in CONDITIONS},
        rejected_by_seed=rejected_by_seed, skipped_by_seed=skipped_by_seed,
        planted={"insight_plants": sum(c.planted for c in report.insights.values()), "rendering_plants": sum(c.planted for c in report.renderings.values()),
                 "caught": report.caught, "reached_air": report.reached_air},
    )
    (out_dir / "manifest.json").write_text(manifest.model_dump_json(indent=1), encoding="utf-8")
    return manifest


def _planting_commentator(results: list[MomentResult]) -> PlantingCommentator | None:
    """run_planted registers its PlantingCommentator so the export can read the plan and the planted insights."""
    from app.agents.run_match import LAST_PLANTING

    return LAST_PLANTING[-1] if LAST_PLANTING else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--live", action="store_true", help="Foundry agents from .env (costs tokens)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    manifest = asyncio.run(export(args.seeds, args.limit, args.live, args.out))
    print(json.dumps(manifest.model_dump(), indent=1))


if __name__ == "__main__":
    main()
