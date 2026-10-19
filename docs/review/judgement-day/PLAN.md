# Judgement day simulation (our entry only)

Goal: score Matchday Companion the way the hackathon judges will, find the weakest points per criterion, and turn them into a ranked fix list for T14 (README) and T15 (video) before the 2026-10-26 submission.

Scope: only our own materials. No other entrants' content is collected or stored.

## Inputs (what a judge sees on submission day)

A dossier built by `scripts/judge_panel.py` from the repo:

- The official criteria and category from `requirements.md` (five criteria, 20% each; Best Use of Microsoft Foundry).
- `README.md` (still the pre-T14 version, judged as is so the gap shows), `docs/demo-script.md` (the 2-minute video as scripted), `docs/eval-results.md`, `docs/performance.md` (summary), SPEC objective and pipeline design rules, ADR titles, deploy facts (public URL, limits), repo map and test counts.
- Short, factual descriptions of the UI screenshots in `docs/design/screenshots/`.

## Panel

Four judge personas, each run separately on the Foundry frontier deployment (`FRONTIER_MODEL_DEPLOYMENT`) with a structured output schema:

1. Microsoft Foundry product lead: category fit, depth of Foundry use (agents, evaluation, tracing, Voice Live, hosting).
2. Football broadcast and media innovation lead: real-world impact, would a broadcaster or league use it.
3. Senior engineer and developer advocate: technical implementation, code and architecture, synthetic data quality, reproducibility.
4. Product and UX judge: video clarity, UI, how fast the idea lands.

Each judge returns, per criterion: score 1 to 10 and a two-sentence reason; then the three biggest weaknesses, three concrete fixes with effort (S, M, L) and the criterion each lifts, what would make the entry memorable, and an estimate of top-3-in-category likelihood (low, medium, high) with the reason.

Two runs per judge (temperature default) to see how stable the scores are; disagreements bigger than 2 points are flagged.

## Outputs

- `docs/review/judgement-day/results.json`: raw panel output.
- `docs/review/judgement-day/REPORT.md`: score table (judge by criterion, weighted total), consensus weaknesses, the ranked fix list (impact per effort, mapped to T14 or T15 or a code task), and what to emphasise as the outlier story.

## Limits

- An AI panel approximates human judges; it cannot watch the video or click the app, so it judges the script and the descriptions. Treat scores as relative signals, not predictions.
- No information about other entries is used, so the panel says where our entry is weak against the rubric, not where it ranks.
