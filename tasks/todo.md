# Active Tasks: The Commentator's Brain

Dependency order: T1 -> (T2 || T3 -> T4 -> T5 -> T6) -> T7 -> T8 -> T9 -> T10 -> T10b -> T11 -> T12 -> T13 -> T14 -> T15 -> T16
Nothing here starts until SPEC.md and tasks/plan.md are approved.

## Pre-build blockers
- [ ] Re-enable Azure subscription (`az account show` -> state `Disabled` on 2026-10-14) or create a new one; set a budget alert
- [ ] Innovation Studio profile set up when the invite email arrives (~2026-10-16); note submission form fields in requirements.md
- [ ] Approve SPEC.md assumptions (fictional league, en+tr, port 8010, Vue CDN)

## Phase A: Foundations

- [x] T1: Repo scaffold (done 2026-10-15)
  - Acceptance: `app/` packages exist, `requirements.txt`, `.env.example`, `tests/test_placeholder.py`; `python -m pytest tests/ -q` passes; `git init` + private GitHub repo `ogu83/inside-the-game-hackathon` (public before submission)
  - Verify: `python -m pytest tests/ -q`
  - Files: requirements.txt, .env.example, app/__init__.py, tests/test_placeholder.py
  - Result: packages app/{simulator,ledger,agents,api}; .venv on Python 3.11; 5 tests pass; private repo created, branch `main`; docs/document.{md,pdf} (B2B Connect terms) gitignored

- [ ] T2: Azure + Foundry spike (time-box 1.5 days)
  - Setup: install `azd` + `azure.ai.agents` extension (or Foundry DevPack via winget); `az login` and `azd auth login`; create Foundry resource + project; grant yourself the **Foundry User** role; link an Application Insights resource to the project; deploy one small model and one frontier model (file the frontier quota request first thing, it may take time)
  - Acceptance: a 2-agent Agent Framework graph workflow with one conditional edge runs locally against the deployments (keyless `DefaultAzureCredential`, Responses API); the same workflow deploys as a Foundry Hosted Agent and is invoked remotely; trace visible in the Foundry portal; package versions pinned in SPEC.md; hosted-vs-in-container decision confirmed in SPEC.md
  - Also: 30-second Foundry Voice Live hello world (speak a line, interrupt it, get a reply); record region/quota/cost findings in SPEC.md
  - Verify: `python spikes/two_agents.py` (local) and hosted invocation both print both agent outputs; screenshot of trace; `python spikes/voice_live_hello.py` round trip works
  - Files: spikes/two_agents.py, requirements.txt, .env.example, SPEC.md

- [x] T3: Simulator v1 (done 2026-10-15)
  - Acceptance: fictional league (4 clubs, 18-player squads, fictional names); phase model; same seed -> identical event list; events validate as `MatchEvent`
  - Verify: `python -m pytest tests/simulator -q`; `python -m app.simulator.run --seed 7 --speed 20` reads plausibly
  - Files: app/simulator/{league.py,model.py,emitter.py,run.py}, tests/simulator/test_simulator.py
  - Result: Northshore League (VEL, SAL, COR, EMB), 4-4-2 starters + 7 subs; phases build_up/transition/pressing/set_piece with 8-15 min intensity windows; ~1600 events per match, ~3 goals and ~34 shots on average over 40 seeds; coords are from the acting team's view; first half ends at 45:00 exactly so the clock never runs backwards; `stream`/`astream` pace by match clock

- [x] T4: Dataset export (done 2026-10-15)
  - Acceptance: `--export data/match_<seed>.jsonl`; 3 sample matches committed; README section describing the schema
  - Verify: export then re-load and validate every line
  - Files: app/simulator/export.py, data/, tests/simulator/test_export.py
  - Result: `python -m app.simulator.run --seed N --export data/match_N.jsonl`; samples for seeds 7, 8, 9 (~0.5 MB each); schema in data/README.md; a test fails if a committed sample drifts from the simulator

## Phase B: Ledger

- [ ] T5: Ledger core metrics
  - Acceptance: possession %, pass accuracy, pass difficulty, shot speed, player distance/speed thresholds, all from events; each calculator unit-tested on hand-built sequences
  - Verify: `python -m pytest tests/ledger -q`
  - Files: app/ledger/{state.py,metrics.py}, tests/ledger/test_metrics.py

- [ ] T6: Candidate-moment detectors
  - Acceptance: pressing_trap, momentum_shift, pass_streak, player_milestone, lull; seeded match yields 30-60 moments with evidence dicts
  - Verify: `python -m pytest tests/ledger -q`; count printed for seed 7
  - Files: app/ledger/moments.py, tests/ledger/test_moments.py

## Phase C: Agents

- [ ] T7: Analyst + Commentator
  - Acceptance: Analyst ranks/drops moments; Commentator returns valid `Insight` citing only existing evidence keys
  - Verify: `python -m pytest tests/agents -q -m live` on 5 fixture moments
  - Files: app/agents/{prompts.py,analyst.py,commentator.py}, tests/agents/test_commentator.py

- [ ] T8: Fact-Checker
  - Acceptance: verified/rewritten/rejected verdicts; one retry loop; deliberately false claim fixture is rejected or rewritten, never passed through
  - Verify: `python -m pytest tests/agents -q` (contract) and `-m live`
  - Files: app/agents/fact_checker.py, tests/agents/test_fact_checker.py

- [ ] T9: Producer
  - Acceptance: `OverlayCue` (headline <= 60 chars) + `FanNarrative` per profile in en and tr; casual vs analyst depth visibly different
  - Verify: `-m live` test over 2 profiles x 2 languages
  - Files: app/agents/producer.py, tests/agents/test_producer.py

- [ ] T10: Workflow + tracing + recap
  - Acceptance: Agent Framework workflow wires all four agents; traces per step in Foundry; full-time recap in en/tr; Checkpoint C criteria met
  - Verify: `python -m app.agents.run_match --seed 7 --speed 30` summary; trace screenshot
  - Files: app/agents/workflow.py, app/agents/recap.py, app/agents/run_match.py, tests/agents/test_workflow.py

- [ ] T10b: Foundry evaluation (Groundedness proof point)
  - Acceptance: 3 recorded seeded matches exported as an evaluation dataset; Foundry cloud evaluation (Groundedness, Task Adherence) run with Fact-Checker on vs off; results table saved to docs/eval-results.md
  - Verify: evaluation job submitted and polled to completion (long-running operation); scores visible in the Foundry portal
  - Files: app/eval/export_runs.py, app/eval/run_eval.py, docs/eval-results.md

## Phase D: Product surface

- [ ] T11: FastAPI + SSE
  - Acceptance: `/api/health`, `POST /api/match/start`, `GET /api/stream/cues`, `GET /api/stream/fan?profile=...`, `GET /api/profiles`
  - Verify: `python -m pytest tests/api -q`; `curl -N localhost:8010/api/stream/cues`
  - Files: app/api/main.py, app/api/streams.py, tests/api/test_api.py

- [ ] T12: Frontend
  - Acceptance: broadcast panel (overlay cues timed to match clock), fan panel with profile switch, verdict debug drawer; no console errors; works at 1440x900 and phone width
  - Verify: manual run in browser, golden path + profile switch
  - Files: frontend/index.html, frontend/style.css

- [ ] T12b: Voice co-commentator
  - Acceptance: per-fan Voice Live session speaks verified Producer narratives (en, tr); barge-in stops playback < 500 ms; spoken "why?" routed to the evidence-grounded answer path; unknowns answered with "I don't have data on that"
  - Verify: manual browser test with mic, golden path + interruption + unanswerable question; latency logged in traces
  - Files: app/voice/session.py, app/voice/qa.py, app/api/voice_ws.py, frontend/index.html

## Phase E: Ship

- [ ] T13: Deploy: agent workflow as Foundry Hosted Agent + API/UI on Azure Container Apps
  - Acceptance: `docker compose up --build` from clean clone (local judge path); hosted agent deployed via `azd`; public Container Apps URL serving the demo and invoking the hosted agent
  - Files: Dockerfile, docker-compose.yml, docs/deploy.md

- [ ] T14: README + architecture diagram + judge instructions
- [ ] T15: Demo script + under-2-minute video on YouTube (no trademarks, no copyrighted music)
- [ ] T16: Make repo public, leak scan (keys, vault paths, client names), submit on Innovation Studio by 2026-10-26
