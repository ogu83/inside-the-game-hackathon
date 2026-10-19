# Prompt: T10b fixes (honest headline, actor-check false positives, minute citations)

You are working in the repository at `the repository root` (Windows, PowerShell, Python 3.11 venv in `.venv`). You have an Azure login (`az`) and a filled `.env`, so live Foundry calls work on this machine.

## Context

Read first: `CLAUDE.md` (house rules), `SPEC.md` design rule 2 (two-layer Fact-Checker), `app/agents/fact_check_rules.py` (layer 1: `check_numbers`, `check_actors`, `check_insight`), `app/eval/export_runs.py` and `app/eval/run_eval.py` (T10b evaluation), `runs/eval/` (local, gitignored: the exported items, `results_*.json` from the Foundry runs, and `eval-results.generated.md`).

The first live Foundry evaluation ran on 2026-10-16 (seeds 7, 30, 42, 12 moments each). Results are in `runs/eval/results_*.json`. Three problems were found:

1. **The generated headline is wrong.** `run_eval.py` wrote "Groundedness rose from 4.63 to 4.56". 4.63 (checker off) to 4.56 (checker on) is a small drop, not a rise. The headline template assumes improvement.
2. **The actor check has false positives.** 6 of the 9 checker-off first drafts that failed layer 1 were correct sentences that mention the opponent as a place or an object, not as the actor. Real examples (moment team in brackets):
   - [Kestrel Bay] "The regain comes 38.2 m from goal, which can leave Ironvale starting again in their own half."
   - [Kestrel Bay] "That turn-over happened in Ironvale territory and can set up the next action nearer the attacking end."
   - [Ironvale] "That sequence turns possession into a shot and carries the ball 49.4 m into Kestrel Bay territory."
   - [Kestrel Bay] "The move carried the ball 69.5 m into Ironvale territory, but it ended without a shot."
   - [Ironvale] "...gave Ironvale a longer spell in Kestrel Bay territory."
   - [Kestrel Bay] "That turnover leaves Ironvale starting from 45.9 metres out, which can push the next action into Kestrel Bay territory."

   These cause unnecessary rewrites and occasional rejections of correct lines in the live app.
3. **Minute numbers count as uncited.** 3 of the 9 failed only because of "At minute 24", "Ironvale's press at 37", "At minute 21": the minute is correct and is in the moment evidence (`minute`), but the Commentator did not list it in `evidence_refs`.

None of the 9 contained a wrong fact. Do not describe them as errors anywhere.

## Tasks (one commit each, in this order)

1. **Actor check: possessive and locative mentions are not actors.** In `check_actors`, a team or player name is not the actor when it is used as a place or an object: followed by territory, half, box, area, goal, defence, defense, end, side, third (and Turkish equivalents such as yarı saha, ceza sahası, kale, savunma, bölge), in a possessive ("Ironvale's half", "Ironvale'in yarı sahası"), or as the object of verbs like leave, keep, push, pin, force, put under pressure (and simple Turkish object forms). Keep the swapped-team protection: "Kestrel Bay set a pressing trap ..." on an Ironvale moment must still be rejected, and the existing tests must still pass. Add tests with every example sentence above (they must pass) plus negative cases that must still fail.
2. **Minute is always citable.** A number equal to `moment.minute` that appears in a minute context ("minute 24", "at 37", "24th minute", "24. dakika", "dakika 24") passes without being in `evidence_refs`. Any other use of that number still needs a cited key. Tests in en and tr.
3. **Honest headline and wording.** `run_eval.py` must derive words from the numbers: "rose" or "fell" only when the change is at least 0.1 on the 1 to 5 scale, otherwise "was unchanged (X vs Y)". Lead the headline with the planted-error result when the planted conditions ran, for example: "With planted errors, the Fact-Checker kept Groundedness at 4.55 (100% pass) against 3.75 (75% pass) without it, and 0 of 4 planted errors reached air against 4 of 4; in normal play both conditions scored about 4.6 because first drafts were already accurate." Describe the number-check column as "layer 1 pass (numbers and actors)", not as factual errors. Add tests for rose, fell and unchanged.
4. **Re-run the evaluation with the fixed checks.** Run `python -m app.eval.export_runs --seeds 7 30 42 --limit 12 --live` and then `python -m app.eval.run_eval runs/eval` (about 290 model calls for the export and about 280 judge calls in Foundry; the evaluation polls for several minutes). Review the regenerated `docs/eval-results.md` by hand: every number must come from the run, and the headline must read correctly. Commit `docs/eval-results.md` (not `runs/`).

## Rules

- Branch: create `t10b-fixes` from `main`; push it; do not push to `main`; do not open a pull request.
- Before every commit: `.venv\Scripts\python.exe -m pytest tests -q` must pass (about 230 tests, about 20 s; a 30 s per-test guard is configured). Live tests run with `python -m pytest tests -m live` (no extra flags needed).
- No em dashes in code comments, docs or UI text. No Co-Authored-By trailers. Fictional league only.
- Do not change `SPEC.md` interfaces. If the actor or minute rule changes the wording of SPEC design rule 2, write the proposed wording in `docs/reviews/2026-10-16-t10b-fixes.md` instead.
- Update `task_state.md` and `tasks/todo.md` (T10b) when done.

## Done when

- All four commits are pushed to `t10b-fixes`.
- The suite passes; the six example sentences pass layer 1; swapped-team cases still fail.
- `docs/eval-results.md` has real numbers from the re-run and an accurate headline.
- Report back: the new results table, the headline, how many checker-off first drafts still fail layer 1 and why (quote them), and the commands you ran.
