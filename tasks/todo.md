# Active Tasks: Matchday Companion (The Commentator's Brain)

Order: T1 -> T2 -> D1 -> S1 -> S2 -> S3 -> S4 -> S5 (walking skeleton, by Oct 19) -> T3..T12b (deepen, by Oct 23; T10b starts as soon as T10 runs) -> T13 -> T14 -> T15 -> T16
SPEC.md approved 2026-10-15; revised 2026-10-15 after the T2 review and again after the review in docs/reviews/2026-10-15-fable-review.md (director per moment, 20 s delay, public URL as Must with offline fallback, scope cuts; see SPEC.md status lines and tasks/plan.md scope table).

## Pre-build blockers
- [x] Azure subscription re-enabled 2026-10-15; $50/month budget alert set
- [x] Innovation Studio profile + registration done 2026-10-15 (submission form fields still to be noted in requirements.md)
- [x] SPEC.md assumptions approved 2026-10-15 (fictional league, en+tr, port 8010, Vue CDN)
- [ ] Frontier model quota request for gpt-5.5 in eastus2 (Oguz)

## Phase A: Foundations (done)
- [x] T1: Repo scaffold (done 2026-10-15)
  - Acceptance: `app/` packages exist, `requirements.txt`, `.env.example`, `tests/test_placeholder.py`; `python -m pytest tests/ -q` passes; `git init` + private GitHub repo `ogu83/inside-the-game-hackathon` (public before submission)
  - Verify: `python -m pytest tests/ -q`
  - Files: requirements.txt, .env.example, app/__init__.py, tests/test_placeholder.py
  - Result: packages app/{simulator,ledger,agents,api}; .venv on Python 3.11; 5 tests pass; private repo created, branch `main`; docs/document.{md,pdf} (B2B Connect terms) gitignored

- [x] T2: Azure + Foundry spike (done 2026-10-15, two manual follow-ups below)
  - Setup: install `azd` + `azure.ai.agents` extension (or Foundry DevPack via winget); `az login` and `azd auth login`; create Foundry resource + project; grant yourself the **Foundry User** role; link an Application Insights resource to the project; deploy one small model and one frontier model (file the frontier quota request first thing, it may take time)
  - Acceptance: a 2-agent Agent Framework graph workflow with one conditional edge runs locally against the deployments (keyless `DefaultAzureCredential`, Responses API); the same workflow deploys as a Foundry Hosted Agent and is invoked remotely; trace visible in the Foundry portal; package versions pinned in SPEC.md; hosted-vs-in-container decision confirmed in SPEC.md
  - Also: 30-second Foundry Voice Live hello world (speak a line, interrupt it, get a reply); record region/quota/cost findings in SPEC.md
  - Verify: `python spikes/two_agents.py` (local) and hosted invocation both print both agent outputs; screenshot of trace; `python spikes/voice_live_hello.py` round trip works
  - Files: spikes/two_agents.py, requirements.txt, .env.example, SPEC.md
  - Result: eastus2 Foundry resource + project, Foundry User role, App Insights linked, $50/month budget alert; `gpt-5.4-mini` deployed (DataZone Standard). `spikes/two_agents.py` runs locally (reject edge proven with `--inject-false`); `spikes/hosted/` deploys with `azd deploy` and answers `azd ai agent invoke t2-spike 'inject-false'`; spans from both in App Insights; `spikes/voice_live_hello.py` interrupt stops in ~0.4 s, reply in ~1.6 s. Findings and pins in SPEC.md "T2 decisions and findings".
  - Manual follow-ups (Oguz): (1) file a quota request for `gpt-5.5` in eastus2, then deploy it and set `FRONTIER_MODEL_DEPLOYMENT`; (2) open the project's Tracing tab in the Foundry portal and take the trace screenshot for the README.


## Phase S: Walking skeleton (Oct 15-19)

Thin vertical slices, each tested and committed. Goal: a seeded match plays in the browser with verified cues shown on time and spoken. Later phases deepen the same files.

- [x] D1: Demo script draft (done 2026-10-15: docs/demo-script.md, 7 scenes, ~1:58)
  - Acceptance: docs/demo-script.md, scene by scene, timed to under 2 minutes, every scene mapped to a Must item in tasks/plan.md; no trademarks, no copyrighted music
  - Verify: read aloud with a stopwatch
  - Files: docs/demo-script.md, tasks/plan.md (scope table if the script changes it)

- [x] S1: Thin simulator (done 2026-10-15: 17-31 shots, xG 1.4-2.9, ~84% pass completion across seeds)
  - Acceptance: 2 fictional clubs (11 + 3 subs each, fictional names), build-up and transition phases, seeded emitter; same seed -> identical events; every event validates as `MatchEvent`; text printer
  - Verify: `python -m pytest tests/simulator -q`; `python -m app.simulator.run --seed 7 --speed 20` reads like football for 5 minutes
  - Files: app/simulator/{models.py,league.py,engine.py,run.py}, tests/simulator/test_simulator.py

- [x] S2: Thin ledger + first detector (done 2026-10-15: 17-26 pass_streak moments per seeded match)
  - Acceptance: possession % and pass streak calculators; `pass_streak` detector emits `CandidateMoment` with an evidence dict; unit tests on hand-built sequences
  - Verify: `python -m pytest tests/ledger -q`; moment count printed for seed 7
  - Files: app/ledger/{state.py,metrics.py,moments.py}, tests/ledger/test_metrics.py, tests/ledger/test_moments.py

- [x] S3: Thin agents: Commentator + two-layer Fact-Checker (done 2026-10-15 in a cloud session; live check `-m live` still to run locally)
  - Acceptance: Fact-Checker layer 1 (code) rejects missing keys and mismatched numbers with no LLM call, fully unit-tested; layer 1 is a reusable number check (gates: insight, producer, speech) with an en/tr number parser (`68%`, `%68`, `yüzde 68`, `68.5`, `68,5`) and a digits-only rule, each result recorded as `NumberCheck`; layer 2 (LLM) judges wording; workflow with one retry on real S2 moments, in-process; messages between executors are dicts re-validated into SPEC models
  - Verify: `python -m pytest tests/agents -q` (layer 1 + contract, no model); `python -m pytest tests/agents -q -m live` on 3 moments
  - Files: app/agents/{models.py,prompts.py,fact_check_rules.py,commentator.py,fact_checker.py,workflow.py}, tests/agents/
  - Result: en/tr parser + gates in fact_check_rules.py (insight, producer, speech), `NumberCheck` per gate pass; `FactChecker` runs layer 1 then a `WordingJudge` (rewrites re-enter layer 1); Agent Framework workflow with dict messages re-validated per executor and one retry; offline agents in fakes.py (`TemplateCommentator`, `TemplateProducer`, `AlwaysVerifies`) for judges and recording fallback; `python -m app.agents.run_match --seed 7 [--jsonl f] [--live]` run log for T10b; pytest.ini deselects `live` by default. 52 new tests.

- [x] S4: Thin API + page with broadcast delay (done 2026-10-15 in a cloud session; Vue page not rendered there because the CDN is blocked, check it locally)
  - Acceptance: `POST /api/match/start`, `GET /api/stream/cues` (SSE), `GET /api/health`; playback clock runs `BROADCAST_DELAY_S` behind events; a cue not ready at its moment is dropped and counted; bare page shows an event ticker and cues; `speed` and `delay_s` are request parameters; speeds above 1x use precomputed verdicts (review section 1, pending spec approval)
  - Verify: `python -m pytest tests/api -q`; open http://localhost:8010 and watch a seeded match
  - Files: app/api/{main.py,streams.py,clock.py}, frontend/index.html, tests/api/test_api.py
  - Result: `BroadcastClock` (delay in match seconds, speed-aware); `MatchRun` with precompute mode (default above 1x) and live mode (ingest loop runs `delay_s` ahead of the display loop, a cue not ready at its closing event is dropped and counted as `cues_dropped_late`); SSE channels `/api/stream/{cues,events,verdicts}` via sse-starlette; `AGENT_MODE=template|foundry`; `GET /api/match/state` metrics; Vue 3 CDN page with ticker, cues, delay badge and playback clock. 9 tests; 89 pass in about 5 s.

- [x] S5: Thin voice (done 2026-10-15: real Voice Live round trip in en and tr through the app, speech audit exact; browser shows speaking line and audit 1/1)
  - Acceptance: browser plays Voice Live speech for each verified line in en, sent as `pre_generated_assistant_message` (verbatim, the realtime model never authors spoken words); speech gate: transcript of each spoken response compared with the approved text and number-checked, mismatches counted; no barge-in yet
  - Verify: manual: start a match, hear verified lines
  - Files: app/voice/session.py, app/api/voice_ws.py, frontend/index.html

Checkpoint S: one command, seeded match plays, verified cues appear on time and are spoken. Submittable in an emergency.

## Phase B: Deepen (Oct 19-23)

- [x] T3: Simulator v1 (scope cut 2026-10-15: 2 clubs, no set pieces; done 2026-10-15 in a cloud session)
  - Acceptance: the 2 existing clubs; phase model with build-up, pressing (per-club pressing trait so pressing_trap has something to find), transition; substitutions; goals with xG-like quality; deterministic per seed; fouls emit a restart pass; `half_seconds` naming and redundant phase line from the review fixed
  - Verify: `python -m pytest tests/simulator -q`; 5 minutes of text output reads plausibly
  - Files: app/simulator/*, tests/simulator/test_simulator.py
  - Result: `Club.pressing` trait (Ironvale 1.3, Kestrel Bay 0.85) multiplies the press chance; 2 like-for-like substitutions per club between minutes 58 and 82 (`substitution` events with player_on/player_off); fouls set a `free_kick` restart taken by the fouled team; `half_seconds` naming, redundant phase line, `zip(strict=True)`, clamped end coordinates; `DEMO_SEED = 30` (3 moments in the first 5 minutes, one ending in a shot); run.py prints subs and free kicks. 8 new tests, 113 pass.

- [x] T4: Dataset export (done 2026-10-15 in a cloud session)
  - Acceptance: `--export data/match_<seed>.jsonl`; 3 sample matches committed; README section describing the schema
  - Verify: export then re-load and validate every line
  - Files: app/simulator/export.py, data/, tests/simulator/test_export.py
  - Result: `app/simulator/export.py` (`export_match`, `load_match`, CLI), `--export` on run.py, samples `data/match_{7,30,42}.jsonl` (a test fails if they go stale against the engine), README.md started with the schema section and the frame convention. 116 tests.

- [ ] T5: Ledger metrics
  - Acceptance: pass accuracy, pass difficulty, shot speed, player distance/speed thresholds added to S2's calculators; each unit-tested on hand-built sequences
  - Verify: `python -m pytest tests/ledger -q`
  - Files: app/ledger/{state.py,metrics.py}, tests/ledger/test_metrics.py

- [ ] T6: Detectors (scope cut 2026-10-15: two detectors)
  - Acceptance: pressing_trap added to pass_streak (no momentum_shift, no player_milestone; player numbers come from T5 ledger queries and the MCP tools); possession keys omitted when `window_minutes < 3`; seeded match yields 25-45 moments with evidence dicts, sorted by closing seq and non-overlapping; `Detector` Protocol shared by both
  - Verify: `python -m pytest tests/ledger -q`; count printed for seed 7
  - Files: app/ledger/moments.py, tests/ledger/test_moments.py

- [ ] T7: Analyst as director (per moment) + Commentator
  - Acceptance: the Analyst is called per candidate moment with pacing state computed by code (seconds since last spoken cue, cues in the last 2 minutes, rank among recent moments) and returns a `DirectorDecision` (say/skip, angle, reason), never computing numbers; skipped moments are logged for the verdict drawer; Commentator (S3) takes the angle and returns a valid `Insight` citing only existing evidence keys; pacing tests with scripted decisions
  - Verify: `python -m pytest tests/agents -q`; `-m live` on 5 fixture moments
  - Files: app/agents/{prompts.py,analyst.py,commentator.py}, tests/agents/test_analyst.py, tests/agents/test_commentator.py

- [ ] T8: Fact-Checker full + planted errors
  - Acceptance: verified/rewritten/rejected with `layer` and `attempt` set; planted-error harness corrupts N insights per match (wrong number, missing key, swapped team) and N Producer renderings incl. Turkish translations (changed number, dropped number, number as a word); run report shows planted errors caught per gate and 0 reaching a cue, a narrative or the voice
  - Verify: `python -m pytest tests/agents -q`; `-m live` planted-error run on one seeded match
  - Files: app/agents/{fact_checker.py,fact_check_rules.py,planted_errors.py}, tests/agents/test_fact_checker.py

- [ ] T9: Producer
  - Acceptance: `OverlayCue` (headline <= 60 chars) + `FanNarrative` per profile in en and tr, per-profile calls in parallel; casual vs analyst depth visibly different; prompt requires numbers as digits; every rendering passes the producer gate (number check), a failure is regenerated once then dropped for that profile only
  - Verify: `-m live` test over 2 profiles x 2 languages
  - Files: app/agents/producer.py, tests/agents/test_producer.py

- [ ] T10: Workflow + tracing + recap + hosted (hosted timeboxed to half a day, 2026-10-15)
  - Acceptance: one workflow module wires all four agents and runs in-process with spans per step in App Insights; full-time recap in en/tr; Checkpoint B criteria met. Hosted Agent deployment is a Should with a half-day timebox: if it fights back, show the T2 hosted agent in the portal and move on
  - Verify: `python -m app.agents.run_match --seed 7 --speed 30` summary (cues, rejects, planted errors caught, ready-before-display %); hosted invoke works
  - Files: app/agents/{workflow.py,recap.py,run_match.py}, hosted/ (azd project), tests/agents/test_workflow.py

- [ ] T10b: Foundry evaluation (start as soon as T10 runs; can start earlier from the S3 run log `python -m app.agents.run_match --jsonl`, see docs/reviews/2026-10-15-fable-review.md section 3)
  - Acceptance: 3 recorded seeded matches exported as an evaluation dataset; Foundry cloud evaluation (Groundedness, Task Adherence) with Fact-Checker on vs off; planted-error count; results table in docs/eval-results.md with one headline sentence for README and video
  - Verify: evaluation job submitted and polled to completion; scores visible in the Foundry portal
  - Files: app/eval/export_runs.py, app/eval/run_eval.py, docs/eval-results.md

- [ ] T11: API full
  - Acceptance: adds `GET /api/stream/fan?profile=...`, `GET /api/profiles`, verdict stream for the debug drawer
  - Verify: `python -m pytest tests/api -q`; `curl -N localhost:8010/api/stream/cues`
  - Files: app/api/main.py, app/api/streams.py, tests/api/test_api.py

- [ ] T12: Frontend
  - Acceptance: SVG pitch with ball and player dots from event x/y on the delayed clock; overlay cues; fan panel with profile switch; verdict debug drawer showing rejects and the Analyst's skipped moments; no console errors; works at 1440x900 and phone width
  - Verify: manual run in browser, golden path + profile switch
  - Files: frontend/index.html, frontend/style.css

- [ ] T12b: Voice: barge-in + Q&A over MCP (text first, 2026-10-15: MCP server and text Q&A can be built in a cloud session with fake models; only the audio plumbing is local)
  - Acceptance: ledger read-only MCP server (team stats, player stats, recent moments); `Question`/`Answer`/`SpeechAudit` models per SPEC; push-to-talk only (open mic is Cut); voice Q&A is text first: question transcript -> Q&A agent calling MCP tools -> speech gate (number check + Fact-Checker) -> verbatim speech via `pre_generated_assistant_message`; speech transcript audit shows 0 mismatches; Q&A latency logged against the ~3 s target; barge-in stops playback < 500 ms; unknowns get "I don't have data on that"; en and tr; MCP tool-call span visible in trace
  - Verify: manual browser test with mic: golden path, interruption, unanswerable question; `python -m pytest tests/voice -q` for the MCP tools
  - Files: app/ledger/mcp_server.py, app/voice/{session.py,qa.py}, app/api/voice_ws.py, frontend/index.html, tests/voice/

## Phase E: Ship (Oct 23-26)

- [ ] T13: Deploy (both paths Must since 2026-10-15)
  - Must: `docker compose up --build` from a clean clone runs the full demo in offline mode (`AGENT_MODE=template`, no Azure, no `.env`); with `.env` and an Azure login it runs live agents
  - Must: API + UI on one Azure Container App with a public HTTPS URL (needed for mic in remote browsers), system-assigned managed identity with Foundry User on the project, `PUBLIC_LIVE_RUNS_PER_DAY` limit per visitor with offline fallback after the limit and on Foundry errors, scale-to-zero off and kept running until 2026-11-10; README judge section states the URL, the limit and the fallback
  - Files: Dockerfile, docker-compose.yml, docs/deploy.md

- [ ] T14: README + architecture diagram + judge instructions (pitch line, impact paragraph, eval headline, trace screenshot, "why an LLM Fact-Checker if code checks the numbers", pipeline stages table, pass-share possession note, generated-names note)
- [ ] T15: Record the video from docs/demo-script.md on a local in-process run at 3x to 4x speed, hosted agent warmed up first; app audio and voiceover recorded separately and mixed; English captions on every Turkish line; upload to YouTube (no trademarks, no copyrighted music)

- [ ] T16: Make repo public, submit on Innovation Studio by 2026-10-26
  - Pre-publish pass, in this order:
    1. Remove text that came from entrants-only hackathon pages: "the field is crowded" / competition framing in SPEC.md and IDEA.md; competition-scan line and Innovation Studio project ID in task_state.md
    2. Leak scan of the working tree: keys, vault paths, client names, billing details. Also remove (not secret, but no reason to publish): the Azure tenant ID in CLAUDE.md and task_state.md, and the Foundry resource name/endpoint in spikes/hosted/azure.yaml (replace with `${FOUNDRY_PROJECT_ENDPOINT}` or a placeholder)
    3. Start the public repo with fresh history (squash into one commit). Commit c28e1c0 has billing details in task_state.md, so pushing the current history publicly would expose them
  - Verify: `git log` on the public repo shows the single squashed commit; the grep leak scan returns nothing
