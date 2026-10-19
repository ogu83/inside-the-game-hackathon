# Evaluation results: Fact-Checker on versus off

Generated 2026-10-16 17:20 UTC by `python -m app.eval.run_eval`. Seeds 7, 30, 42, first 12 moments each, agents live (Foundry), exported 2026-10-16T17:15:18+00:00.

**Headline:** With planted errors, the Fact-Checker kept Groundedness at 4.75 (100% pass) against 3.83 (75% pass) without it, and 0 of 4 planted errors reached air against 4 of 4; in normal play both conditions scored about 4.6 because first drafts were already accurate.

Foundry evaluators (judge model from `SMALL_MODEL_DEPLOYMENT`): Groundedness, Relevance, Coherence, scored 1 to 5 by the service; pass rate is the service's threshold. Our own deterministic metric over the same aired texts: the layer 1 number and actor check, and for the planted conditions how many planted insights reached air.

| Condition | Items | Groundedness mean | pass | Relevance mean | pass | Coherence mean | pass | Layer 1 pass (numbers and actors) | Planted caught / reached air | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fact-Checker on (what aired) | 35 | 4.57 | 100% | 4.49 | 100% | 4.06 | 100% | 100% | no plants | completed |
| Fact-Checker off (first drafts aired) | 35 | 4.60 | 97% | 4.51 | 100% | 4.14 | 100% | 97% | no plants | completed |
| Planted errors, Fact-Checker on | 12 | 4.75 | 100% | 4.50 | 100% | 4.00 | 100% | 100% | 4 / 0 of 4 | completed |
| Planted errors, Fact-Checker off | 12 | 3.83 | 75% | 4.67 | 100% | 4.08 | 100% | 67% | 0 / 4 of 4 | completed |

## Runs

- Fact-Checker on (what aired): eval `eval_7715e42d8fbf4e25867a0248bc0b9bba`, run `evalrun_47c210b2c1ea4ee786d68c8a79bcf699`, status completed [portal](https://ai.azure.com/nextgen/r/dD2eNplVR0O3Y7tFFMlrjQ,rg-matchday,,matchday-foundry-ok,matchday/build/evaluations/eval_7715e42d8fbf4e25867a0248bc0b9bba/run/evalrun_47c210b2c1ea4ee786d68c8a79bcf699)
- Fact-Checker off (first drafts aired): eval `eval_85c5ca41f8984d4ba4337566d4f5f4f4`, run `evalrun_c187d7838852412089c0d40336d962ee`, status completed [portal](https://ai.azure.com/nextgen/r/dD2eNplVR0O3Y7tFFMlrjQ,rg-matchday,,matchday-foundry-ok,matchday/build/evaluations/eval_85c5ca41f8984d4ba4337566d4f5f4f4/run/evalrun_c187d7838852412089c0d40336d962ee)
- Planted errors, Fact-Checker on: eval `eval_fffc023824b64e4a8bd7b5c4f347529f`, run `evalrun_cea904e7398e4bfbb5500244158b342c`, status completed [portal](https://ai.azure.com/nextgen/r/dD2eNplVR0O3Y7tFFMlrjQ,rg-matchday,,matchday-foundry-ok,matchday/build/evaluations/eval_fffc023824b64e4a8bd7b5c4f347529f/run/evalrun_cea904e7398e4bfbb5500244158b342c)
- Planted errors, Fact-Checker off: eval `eval_602530cf9272400c903cc07316dac80e`, run `evalrun_45301bcfe1364fc888eedbefe124d468`, status completed [portal](https://ai.azure.com/nextgen/r/dD2eNplVR0O3Y7tFFMlrjQ,rg-matchday,,matchday-foundry-ok,matchday/build/evaluations/eval_602530cf9272400c903cc07316dac80e/run/evalrun_45301bcfe1364fc888eedbefe124d468)

## Export

Rejected by the Fact-Checker (did not air, so absent from the on conditions): {'7': 0, '30': 0, '42': 0}. Skipped by the director: {'7': 1, '30': 0, '42': 0}. Planted run: {'insight_plants': 4, 'rendering_plants': 22, 'caught': 26, 'reached_air': 0}.

Rejected moments do not air and are therefore not evaluated in the on conditions; the off conditions evaluate every first draft the director let through. Items are the aired text as `response`, a short task as `query`, and the ledger evidence with team and player labels as `context`.

## Latency from traces

Telemetry extracted from Azure Application Insights (`appi-matchday`, operation id `840499343095f9544b921f75c730cf5c` for live moment, `f135de636c7820ee5ce4e810202362fe` for Q&A):

- Moment-to-cue latency (Analyst + Commentator + Fact-Checker + Producer):
  - p50: 13.6 s
  - p90: 14.8 s
  - Share of cues ready before display in live mode at 1x (broadcast delay 20.0 s): 100% (cues ready 5.2 to 6.4 s ahead of broadcast display time).
- Q&A latency (ledger query + answer synthesis + fact check gate):
  - Rule-based ledger Q&A: 3 ms
  - Live Foundry agent Q&A: median 2.8 s (within SPEC success criterion 9 of about 3 s median from press to spoken answer).

