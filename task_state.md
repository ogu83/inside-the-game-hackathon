# Task State

<!-- Claude maintains this file during the session.
     Update it after every significant step so the state survives compaction.
     The compaction_save.ps1 hook timestamps each compaction automatically. -->

## Current task
Phase B on cloud branch `claude/gracious-goldberg-9u16ny` (merged with main at fd2f5fe, S5 included): T3 to T8 done; working T9, T6, T7, T8, T9, T11, T12 with offline agents. T10, T10b, T12b, T13 stay local.

## Done
- [x] Registered for the hackathon (2026-10-14), confirmation email received
- [x] IDEA.md one-pager (idea-refine skill)
- [x] SPEC.md, requirements.md, tasks/plan.md, tasks/todo.md, CLAUDE.md, hooks, .claude/settings.json
- [x] Access email received 2026-10-15; B2B Connect terms (docs/document.md) and Event Confidentiality Agreement accepted; rules recorded in CLAUDE.md

- [x] 2026-10-15: Innovation Studio profile + registration done; project "Matchday Companion" created (project 126542), minimal public text, not open to join, Gemini-generated cover image (docs/assets/thumbnail.jpg)
- [x] 2026-10-15: competition scan (docs/private/competition.md, gitignored) -> voice-first pivot written into SPEC.md, IDEA.md, tasks/todo.md
- [x] 2026-10-15: T1 repo scaffold: app/{simulator,ledger,agents,api} packages, requirements.txt, .env.example, tests/test_placeholder.py (5 pass), .venv (3.11), git init on `main`, private repo ogu83/inside-the-game-hackathon. docs/document.{md,pdf} gitignored (agreement text stays local).
- [x] 2026-10-15: T2 Foundry spike: eastus2 rg-matchday with Foundry resource + project `matchday`, Foundry User role, App Insights linked, $50/month budget alert (`hackathon-monthly`). gpt-5.4-mini deployed. Local 2-agent workflow with reject edge, same workflow deployed as hosted agent `t2-spike` via azd and invoked remotely, spans in App Insights, Voice Live hello world (cancel ~0.4 s). Findings + pins in SPEC.md.
- [x] 2026-10-15: post-T2 review applied: SPEC.md (pitch line, pipeline design rules: broadcast delay, two-layer Fact-Checker, Analyst as director, ledger over MCP, parallel Producer; Verdict gains layer/attempt; criteria 3, 8, 10 revised/added), tasks/plan.md rewritten with Must/Should/Cut table, tasks/todo.md reordered (D1, S1-S5 skeleton), IDEA.md annotated.
- [x] 2026-10-15: second review applied: number check at every gate (insight, Producer incl. Turkish, speech) with en/tr parser and `NumberCheck` records; voice speaks only approved text via Voice Live `pre_generated_assistant_message` (verified verbatim in en and tr), speech transcript audit; planted errors at the translation step; T16 adds tenant ID and Foundry resource name cleanup.

- [x] 2026-10-15: D1 demo script (docs/demo-script.md); S1 thin simulator (Meridian League, Kestrel Bay vs Ironvale); S2 thin ledger + pass_streak detector (17-26 moments per match). 28 tests pass.
- [x] 2026-10-15 (cloud session): review committed (docs/reviews/2026-10-15-fable-review.md): top findings are the Analyst 60 s window vs 10 s delay conflict, the judge path needing an offline mode plus public URL, and the evaluation scheduled last. S3 done: `app/agents/{models,fact_check_rules,commentator,fact_checker,fakes,prompts,workflow,run_match}.py`, `app/ledger/labels.py`, 52 tests; `tests/agents/test_live.py` (3 real moments) is `-m live`, not yet run. 80 tests pass.
- [x] 2026-10-15 (cloud session): S4 done: `app/api/{clock,streams,main}.py`, `frontend/index.html`, `tests/api/test_api.py`; requirements.txt gains fastapi, uvicorn, sse-starlette, httpx; `python -m uvicorn app.api.main:app --port 8010` then `POST /api/match/start {"seed":7,"speed":1,"delay_s":10}`; streams verified with curl on the real server; the Vue page could not be rendered in the sandbox (CDN blocked), verify locally. 89 tests pass.
- [x] 2026-10-15 (Oguz, local): S3/S4 verified on Windows: 89 tests, `-m live` passes against Foundry (21 s), `run_match --live` on 5 moments gave 4 verified, 1 rewritten, 0 rejected, 0 failed number checks; page renders in Chrome with a real Foundry cue in en and tr. All four review decisions approved.
- [x] 2026-10-15 (cloud session): decisions applied: SPEC.md revision (director per moment with `DirectorDecision`, 20 s delay with live/precomputed modes, public Container App as Must with managed identity, `PUBLIC_LIVE_RUNS_PER_DAY` limit and offline fallback, docker compose offline mode, `Question`/`Answer`/`SpeechAudit`, `profile_key`, `top_player_*`, rounding and digits-only rules, Linux commands, criteria 1/3/6 revised and 11 added); plan.md scope table and phases; todo.md T3, T6, T7, T10, T12b, T13, T14, T15; demo script (3x to 4x recording, English captions, agent timeline in scene 2, immediate re-render in scene 3, impact sentence in scene 1, pre-recorded portal clips). Code: integral evidence shown as integers in prompts (fixes "14.0 passes"); pass_streak carries `top_player_id` and `top_player_passes`. 97 tests pass.

- [x] 2026-10-15 (cloud session): T3 simulator v1 (pressing trait, substitutions, free-kick restarts, S1 code notes, DEMO_SEED 30). 113 tests.
- [x] 2026-10-15 (cloud session): T4 dataset export, 3 samples in data/, README.md with the schema. 116 tests.
- [x] 2026-10-15 (cloud session): T5 ledger metrics (pass difficulty, shots, xG, pressing regains, player and team stats). 122 tests.
- [x] 2026-10-15 (cloud session): T6 pressing_trap detector, Detector Protocol, possession omitted under 3 minutes. 127 tests.
- [x] 2026-10-15 (cloud session): T7 director per moment (DirectorDecision, PacingState, RuleDirector, FoundryDirector) as the workflow start executor. 134 tests, 2 live.
- [x] 2026-10-15 (cloud session): T8 planted-error harness (insight and rendering corruptions incl. Turkish, per-kind report, coverage rule), spec proposals in docs/reviews/2026-10-15-phase-b-notes.md. 141 tests, 3 live.

## Next step
Locally (T3 and later not started): `python -m pytest tests/agents -q -m live`, `python -m app.agents.run_match --seed 7 --live --jsonl runs/7.jsonl`, merge `claude/gracious-goldberg-9u16ny` into `main`; S5 (thin voice) by Oct 19; then Phase B in todo.md order (T3 with the cut scope, T10b can start from the S3 run log as soon as the live run log exists). Then deepen T3 to T12b. Live agent work uses `FOUNDRY_PROJECT_ENDPOINT` from .env (local, gitignored) and `az login --tenant ...`; azd reuses the az login.

## Working in a cloud session (claude.ai/code)
Cloud sessions are useful for reviews and Azure-free implementation. They have no Azure login, no `.env`, no `azd`, and run Linux.
- **Can do in the cloud:** code reviews of the repo against SPEC.md; S3 Fact-Checker layer 1 (number parser, gates, `NumberCheck`) and the workflow wiring with fake agents; S4 API, broadcast delay clock, page; T3-T6 simulator and ledger; T11 API; T12 frontend. Mark anything needing a model with `@pytest.mark.live` and leave it unrun.
- **Leave for the local Windows session:** running `pytest -m live`, anything calling Foundry or Voice Live (S3 live check, S5 voice, T12b), `azd deploy` (T10), cloud evaluation (T10b), Azure resource changes.
- **Hooks do not run there:** `.claude/settings.json` points at `C:/Users/oguz/...` and uses `pwsh`. Run `python -m pytest tests/ -q` yourself before every commit.
- **Setup:** `python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt` (Python 3.11+; `azure-*` and `agent-framework-*` packages install fine without credentials).
- **Branching:** cloud sessions push to their own `claude/...` branch; merge into `main` locally after review, then `git pull`. Same rules as here: work in todo.md order, update this file and todo.md after each task, no em dashes, no Co-Authored-By trailers, fictional league only.

## Blockers / open decisions
- Azure: subscription is **Enabled** again (2026-10-15). CLI login needs `az login --tenant 09c5e5e8-d9dd-4923-bbf2-9749f2e8082c` (MFA; plain `az login` skips the tenant). Ignore the "Microsoft" tenant (hackathon B2B guest). Budget alert set 2026-10-15. Still open: find what drove the July bill (Portal > Cost analysis, Jun-Jul by service). SPEC approved 2026-10-15.
- Innovation Studio submission form fields still to be noted in requirements.md
- Pre-publish (T16): squash to fresh history before going public (c28e1c0 has billing details) and remove text from entrants-only hackathon pages; checklist in tasks/todo.md T16
- Hosted agent confirmed in T2 (see SPEC.md). Frontier quota: gpt-5.5 has 0 quota in eastus2; Oguz to file a quota request. Until then FRONTIER_MODEL_DEPLOYMENT=gpt-5.4-mini.
- Trace screenshot from the Foundry portal Tracing tab: Oguz, manual.

## Notes
- Deadline 2026-10-27 23:59 PT; internal target 2026-10-26
- Fictional league only; no StatsBomb data; no trademarks in video
