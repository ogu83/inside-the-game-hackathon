# Task State

<!-- Claude maintains this file during the session.
     Update it after every significant step so the state survives compaction.
     The compaction_save.ps1 hook timestamps each compaction automatically. -->

## Current task (2026-10-16)
T10b fixes and live evaluation completed on `t10b-fixes`. Next: merge `t10b-fixes` into `main`, then `docs/prompts/T13-deploy.md`, then Phase P (polish), T10, T14 to T16. Order and dates in tasks/plan.md "Revised order from 2026-10-16".

## Workflow from 2026-10-16
- The Fable cloud session's usage credits are used up; it is no longer used for development (maybe a final cross-check review at the end).
- This Claude Code session writes one prompt per task into `docs/prompts/` (self-contained: context, tasks, rules, done-when). Oguz runs it with another agent on this machine (it has the `az` login and `.env`, so it can run live Foundry, Voice Live and azd steps). This session then reviews: pull the branch, suite, live tests, browser checks, merge into `main`.
- Prompts are in the repo and become public at T16: keep them free of secrets; include `docs/prompts/` in the T16 leak scan.

## T10b live evaluation completed (2026-10-16, seeds 7, 30, 42, 12 moments each)
- Foundry Groundedness (judge gpt-5.4-mini):
  - Fact-Checker on: Groundedness mean 4.57 (100% pass, 35 items), Layer 1 pass 100% (35/35).
  - Fact-Checker off: Groundedness mean 4.60 (97% pass, 35 items), Layer 1 pass 97% (34/35; caught confused opponent attribution in attempt 1 of moment `kby-iva-42-15-pressing_trap`).
  - Planted on: Groundedness mean 4.75 (100% pass, 12 items), Layer 1 pass 100% (12/12), 4 of 4 caught, 0 reached air.
  - Planted off: Groundedness mean 3.83 (75% pass, 12 items), Layer 1 pass 67% (8/12), 0 of 4 caught, 4 reached air.
  - Planted export: 4 insight plants + 22 rendering plants = 26 planted, 26 caught, 0 reached air.
- Headline: "With planted errors, the Fact-Checker kept Groundedness at 4.75 (100% pass) against 3.83 (75% pass) without it, and 0 of 4 planted errors reached air against 4 of 4; in normal play both conditions scored about 4.6 because first drafts were already accurate."
- Fixed actor-check false positives (possessive and locative opponent mentions e.g. "in Ironvale territory") and minute citations without needing explicit evidence refs.
- SPEC design rule 2 proposed wording saved in `docs/reviews/2026-10-16-t10b-fixes.md`.

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
- [x] 2026-10-15 (cloud session): T9 async Producer (parallel per profile, regenerate once, FoundryRenderer, TemplateRenderer). 146 tests, 4 live.
- [x] 2026-10-15 (cloud session): T11 API full (profiles, fan stream with immediate re-render, moment timelines, live-run limit, offline fallback). 153 tests, 4 live.
- [x] 2026-10-15 (cloud session): T12 frontend (SVG pitch, cue banner, fan panel with immediate re-render, agent timeline drawer, voice kept). 157 tests, 4 live. Browser check pending locally.
- [x] 2026-10-15 (cloud session): post-review items: SPEC proposals applied, planted live test limited to 12 moments with a full report, descriptive Commentator prompt with code wording hints and a first-attempt-rate live test, voice follows the profile and speaks the re-rendered line first, small clamped pitch label, phone-width CSS. T12b: ledger MCP server, text-first Q&A with gates, push-to-talk, SpeechAudit records. 184 tests in about 14 s, 7 live.
- [x] 2026-10-15 (cloud session, after Oguz's live push-to-talk run): Voice Live transcription on a separate listening connection (the server refuses turn-detection type changes mid-session; the listener keeps the created VAD type with create_response off, azure-speech transcription), speech and transcription errors isolated and reported; voice-on questions always over the socket with reconnect, no text fallback; PushToTalk state machine, pointer events only, one final recognition result, server guards; every answer spoken and audited (mid-match test); moments detected after their closing event aired count as late (deterministic test replaces the flaky one); mcp pinned to >=1.24,<2 and the server ported to FastMCP; layer 1 matches numbers to the fact they quote and rejects a swapped actor in en and tr (offline planted run: 26 of 26 caught, 0 on air); SPEC wording proposed in docs/reviews/2026-10-15-phase-b-notes.md items 5 and 6. 202 tests, 7 live.
- [x] 2026-10-15 (cloud session, after Oguz's second live run): listening connection's first session.update is exactly the payload verified on the service (pcm16, azure_semantic_vad with create_response false, azure-speech in the fan's language; VOICE_LISTEN_VAD_TR override), no more copying the server's VAD type; speak() gives up after 15 s without an event and transcribe() after 20 s (SpeechError / TranscriptionError), tests inject socket failures through the fake's queue so nothing can hang, pytest-timeout guards every test (30 s, thread method for Windows); barge-in is audible at press time (PlaybackGate mutes and drops scheduled audio before any await, chunks of the interrupted line are ignored until the next speaking message, talk_start cancels the speaker server-side). 204 tests, 7 live.
- [x] 2026-10-15 (cloud session, after push-to-talk worked end to end): mic opened once when the voice is turned on and kept warm; empty utterances and commit_empty fail at once with 'I did not catch that, try again'; transcription in its own task, a new press supersedes it; a line cut off in the browser is audited as interrupted (page names it, server marks it); QaTiming with pressed/transcribed/answered/spoken marks, p50 metrics and 'answered in X.X s' on the card (SPEC proposal 7); transcription bias with en-US/tr-TR and a football plus league-name phrase list (fallback if rejected); tolerant intents in the offline Q&A (Scarne/Skorne answered, Skagne no data); profile dropdown changes apply by themselves. 213 tests, 7 live.
- [x] 2026-10-16 (cloud session, after the merge of dfa9c05): empty press caught in the page (under 0.3 s never reaches Voice Live) and spoken as "I didn't catch that, try again." / "Anlayamadım, tekrar dener misin?" through the normal audited path; the voice socket closes quietly when the browser already left (profile switch), no more ASGI exception noise; live tests exempt from the 30 s guard so `python -m pytest tests -m live` works without flags. 219 tests, 7 live. Oguz's third live run: 7/7 live passed, p50 answer 3.7 s, speech audit 13/13 exact.
- [x] 2026-10-16 (cloud session): T10b code: app/eval/{export_runs,run_eval,report}.py, tests/eval (12 offline, 1 live), docs/eval-results.md rendered as "not run yet"; runs/ gitignored. 231 tests, 8 live.
- [x] 2026-10-16 (local session): T10b fixes and live Foundry evaluation (t10b-fixes branch). Fixed actor check false positives (possessive/locative opponent mentions), allowed minute citations without explicit key, honest headline derivation in report.py, live export and 4 Foundry evaluation runs completed; docs/eval-results.md populated with real numbers and honest headline. 241 tests pass.

## Next step
Merge `t10b-fixes` into `main`, then `docs/prompts/T13-deploy.md`, then Phase P (polish), T10 (tracing + recap + hosted, timeboxed), T14 to T16. Live agent work uses `FOUNDRY_PROJECT_ENDPOINT` from .env (local, gitignored) and `az login --tenant ...`; azd reuses the az login.

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
