# Prompt: P4 code review and small safe fixes (Matchday Companion)

You are working in the repository at `C:\Users\oguz\source\repos\inside-the-game-hackathon` (Windows, PowerShell, Python 3.11 venv in `.venv`). You have an Azure login and a filled `.env`. Read `CLAUDE.md` and `SPEC.md` first; their hard rules and boundaries apply.

## Goal

The repo becomes public for judging. Make the Python code read like a careful senior engineer wrote it: fix the known defects below, review the rest against a checklist, apply only small and safe fixes, and record the main design decisions as ADRs. No new features, no behaviour changes beyond the listed fixes, no rewrites.

## Checklist source

Build a short checklist (about 20 items) from these files in `C:\Users\oguz\source\repos\professional-programming\antipatterns\` (MIT-licensed reference; read it, do not copy text from it into this repo beyond short item names):

- `code-antipatterns.md`
- `error-handling-antipatterns.md` (and `python-examples/reraise_exceptions_*.py`)
- `tests-antipatterns.md`
- `scalability-antipatterns.md` (only what applies to an asyncio FastAPI app with one replica)

Skip the database, SQLAlchemy and MVC files (this app has no database). Save the checklist as `docs/review/checklist.md`, one line per item with a one-line "how it applies here".

## Known items (fix these first, one commit each, with a test)

1. **Retry loops.** The retry loop is copied three times in `app/agents/workflow.py` and `app/agents/producer.py`; each catches every exception and sleeps up to 6 s. Replace them with one shared helper (for example `app/agents/retry.py`) that retries only transient errors (timeouts, connection errors, HTTP 429 and 5xx from the OpenAI/Foundry client), with exponential backoff, full jitter, a cap, and `Retry-After` honoured when present (SPEC tech stack). Everything else propagates at once. Tests: transient error retried then succeeds; non-transient error raised on the first try; `Retry-After` respected (inject the sleep function, no real sleeping in tests).
2. **Actor check hole.** In `app/agents/fact_check_rules.py`, a clause starting `And Ironvale string together 12 passes` on a Kestrel Bay moment passes, because `and` is in the opponent-before word list. Tighten the rule so a clause whose subject is the opponent fails, without bringing back the T10b false positives (opponent named as a place or object, possessives). Add this case and the T10b false-positive cases as tests.
3. **Health payload.** `/api/health` in `app/api/main.py` mixes the per-visitor registry with the legacy single `app.state.run` (the public app returned `"running": true` with `"active_runs": 0`). Decide whether `app.state.run` is still needed after T13 sessions; if not, remove the legacy path; either way make `running` mean `active_runs > 0`. Test it.

4. **Live-run limit can be bypassed.** `visitor_id` in `app/api/main.py` takes the *first* `X-Forwarded-For` entry, which the client controls, so a forged header gets unlimited live runs. Use the entry added by the Container Apps ingress (the last one) or the connecting address, and document why in a comment. Tests: a forged first entry does not change the visitor; two different real addresses are two visitors.
5. **Global daily cap on live runs.** The public URL is a demo for judging only. Add `PUBLIC_LIVE_RUNS_TOTAL_PER_DAY` (default 40; 0 means no cap) next to the per-visitor limit in `app/api/limits.py`: once the day's total is reached, every new match uses offline agents with the visible notice "Live runs for today are used up, playing with offline agents". Add the env var to `infra/deploy.ps1` and `docs/deploy.md`. Tests: the 41st live start of a day falls back; the count resets the next UTC day.

## Review pass (after the known items)

Walk `app/` against the checklist, file by file, largest first (`fact_check_rules.py`, `streams.py`, `main.py`, `voice/session.py`, `voice_ws.py`, `voice/qa.py`, `simulator/engine.py`, then the rest). For each finding write one line in `docs/review/findings.md`: file and line, checklist item, what is wrong, and one of **fixed** (commit hash), **won't fix** (reason, for example risk this close to the deadline) or **later** (moved to `tasks/todo.md`).

Fix only what is small and safe:
- bare or overly broad `except` that hides errors (log with context and re-raise, or catch the specific type);
- swallowed asyncio task exceptions (tasks created without keeping a reference or reading the result);
- dead code, unused imports and parameters, commented-out code;
- magic numbers that belong in a named constant next to their use;
- unclear names in public functions;
- missing type hints on public functions;
- tests that test the mock instead of the behaviour, or that sleep for real.

Do not change: prompts and agent instructions, ledger metrics and their numbers, the Fact-Checker's verdict semantics (except item 2), the voice protocol, the frontend (P3 owns it), `infra/`.

## ADRs (in `docs/adr/`, same format as `0001-per-visitor-sessions.md`, short: context, decision, consequences)

- `0002-numbers-by-code.md`: agents cite ledger keys, deterministic code owns every statistic; the two-layer Fact-Checker (code checks numbers and actors, the LLM judges wording).
- `0003-verbatim-voice.md`: Voice Live speaks a pre-generated, checked message verbatim, and every spoken line is audited against its transcript; barge-in by `response.cancel` plus dropping browser playback at press time.
- `0004-broadcast-delay.md`: the 20 s broadcast delay buys time for analysis, checking and rewriting before a cue airs.
- `0005-mcp-ledger-tools.md`: fan questions are answered through ledger tools over MCP, so the answer agent can only cite ledger values.
- `0006-transient-retry.md`: the retry policy from item 1.

Base each ADR on what the code and `SPEC.md` actually do; if they disagree, say so in the ADR and in `findings.md` instead of guessing.

## Rules

- Branch `p4-review` from `main` (after P3 is merged, if it has been; otherwise from current `main` and avoid `frontend/`). Push it; do not push to `main`; no pull request.
- One commit per fix or per ADR. No Co-Authored-By trailers, no em dashes, fictional league only.
- Before every commit: `.venv\Scripts\python.exe -m pytest tests -q` must pass. After items 1 and 2, also run the live tests once: `.venv\Scripts\python.exe -m pytest tests -q -m live` (costs tokens; about 2 minutes) and report the result.
- Update `task_state.md` and `tasks/todo.md` (P4 result line) in the last commit.

## Reporting rule

Only report something as done when you ran it and can show the evidence (test output, diff summary). Say "not done" otherwise.

## Done when

- Items 1 to 5 are fixed with tests; the review pass is recorded in `docs/review/findings.md`; the five ADRs exist; the offline suite passes and the live suite result is reported.
- Report back: the branch, the commit list (one line each), the count of findings by status, anything moved to "later", and the test totals (offline and live).
