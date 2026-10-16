# Evaluation results: Fact-Checker on versus off

Generated 2026-10-16 15:50 UTC by `python -m app.eval.run_eval`. Seeds 7, 30, 42, first 12 moments each, agents offline (templates), exported 2026-10-16T15:50:59+00:00.

**Headline:** Not run yet: the evaluation has not been executed against Foundry, so there are no scores to report.

Foundry evaluators (judge model from `SMALL_MODEL_DEPLOYMENT`): Groundedness, Relevance, Coherence, scored 1 to 5 by the service; pass rate is the service's threshold. Our own deterministic metric over the same aired texts: the layer 1 number and actor check, and for the planted conditions how many planted insights reached air.

| Condition | Items | Groundedness mean | pass | Relevance mean | pass | Coherence mean | pass | Number check pass | Planted caught / reached air | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fact-Checker on (what aired) | 35 | n/a | n/a | n/a | n/a | n/a | n/a | 100% | no plants | not run yet |
| Fact-Checker off (first drafts aired) | 35 | n/a | n/a | n/a | n/a | n/a | n/a | 100% | no plants | not run yet |
| Planted errors, Fact-Checker on | 12 | n/a | n/a | n/a | n/a | n/a | n/a | 100% | 4 / 0 of 4 | not run yet |
| Planted errors, Fact-Checker off | 12 | n/a | n/a | n/a | n/a | n/a | n/a | 67% | 0 / 4 of 4 | not run yet |

## Runs

Not run yet. `python -m app.eval.run_eval runs/eval` submits one evaluation per condition and fills this section with run ids and portal links.

## Export

Rejected by the Fact-Checker (did not air, so absent from the on conditions): {'7': 0, '30': 0, '42': 0}. Skipped by the director: {'7': 1, '30': 0, '42': 0}. Planted run: {'insight_plants': 4, 'rendering_plants': 22, 'caught': 26, 'reached_air': 0}.

Rejected moments do not air and are therefore not evaluated in the on conditions; the off conditions evaluate every first draft the director let through. Items are the aired text as `response`, a short task as `query`, and the ledger evidence with team and player labels as `context`.
