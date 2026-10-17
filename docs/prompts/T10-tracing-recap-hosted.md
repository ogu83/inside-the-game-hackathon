# Prompt: T10 finish (tracing in the app, planted-claim demo switch, full-time recap, hosted agent)

You are working in the repository at `C:\Users\oguz\source\repos\inside-the-game-hackathon` (Windows, PowerShell, Python 3.11 venv in `.venv`). You have an Azure login (`az login --tenant 09c5e5e8-d9dd-4923-bbf2-9749f2e8082c`) and a filled `.env`. Read `CLAUDE.md` and `SPEC.md` first; their hard rules apply. `SPEC.md` is the source of truth: if a change here alters behaviour it describes, update `SPEC.md` in the same commit.

## Where things stand (reviewed 2026-10-17)

- The workflow is done: `app/agents/workflow.py` builds the Agent Framework graph (Analyst/director, Commentator, Fact-Checker with the reject edge back to the Commentator). The Producer (`app/agents/producer.py`) runs after the workflow, outside the graph, from `app/api/streams.py`. Q&A runs through `app/voice/qa.py` with ledger tools over MCP.
- **Tracing is off in the app.** Only `spikes/two_agents.py` calls `configure_azure_monitor()` and `enable_instrumentation()`. The Container App has `APPLICATIONINSIGHTS_CONNECTION_STRING` (resource `appi-matchday`, rg `rg-matchday`), but `appi-matchday` holds 0 requests, dependencies and traces. Demo scene 6 (`docs/demo-script.md`) needs a trace of one moment showing Analyst, Commentator, Fact-Checker and Producer spans, and SPEC success criterion 10 needs the Q&A ledger tool call visible as a span.
- **Planted errors are CLI only** (`python -m app.agents.run_match --seed 30 --plant 6`, `app/agents/planted_errors.py`). Demo scene 5 needs the page's timeline drawer to show the Fact-Checker rejecting "Ironvale have had six shots" with the reason "6 shots does not match the cited shots value (away_shots_last_10min = 0)". This is T12c in `tasks/todo.md`.
- **The full-time recap does not exist** (SPEC user story "a full-time recap tailored to my profile", success criterion 5: recap in English and Turkish).
- **Hosted agent:** the T2 spike in `spikes/hosted/` deployed with `azd` and worked (see SPEC "Hosted vs in-container" lessons: host the workflow natively with `ResponsesHostServer(workflow=factory, ...)`, JSON-safe messages between executors, Python 3.13 runtime, remote build from `uv.lock`). This task is a Should with a hard half-day timebox.

## Tasks (in this order; one commit per numbered item or sub-item; tests with each)

### 1. Tracing in the app (Must, video scene 6)

1. Add `app/observability.py` with one function, called once at app startup (FastAPI lifespan) and at the start of `run_match`: if `APPLICATIONINSIGHTS_CONNECTION_STRING` is set (or `TRACING=foundry` and the connection string comes from `project.telemetry.get_application_insights_connection_string()`), call `configure_azure_monitor(...)` and `agent_framework.observability.enable_instrumentation(enable_sensitive_data=...)`. With neither set, do nothing (tests, `docker compose` offline mode). Never fail startup because tracing could not start: log one warning and go on.
2. Sensitive data (prompt and completion text in spans): on only when `TRACE_SENSITIVE=1`. Set it locally for the video recording; leave it off on the public Container App, because fan questions are user input.
3. One parent span per moment: wrap the per-moment work in `app/api/streams.py` (workflow run plus the Producer render plus any voice line) in a span named `moment <moment_id>` with attributes `match.id`, `moment.id`, `moment.kind`, `moment.minute`, `cue.status` (aired, rejected, skipped), `factcheck.layer`, `factcheck.attempts`, and the moment-to-cue latency in ms. The framework's `workflow.run`, `executor.process <id>`, `invoke_agent <name>` and `chat <model>` spans must nest under it. Add a `producer.render` span with `profile.key` per profile. Use `opentelemetry.trace.get_tracer(__name__)`; no new dependency (it comes with `azure-monitor-opentelemetry`, already pinned).
4. Q&A: a span `qa.answer` with `qa.language`, `qa.tools` (the MCP tool names called), `qa.verdict`, and the timing segments already measured in `QaTiming`; the MCP tool calls appear as child spans (check whether the framework emits them; if not, add `mcp.tool <name>` spans around the calls).
5. Unit tests with an in-memory span exporter (`opentelemetry.sdk.trace.export.in_memory_span_exporter`): one moment through the template agents produces a `moment <id>` span with the child spans and attributes; a rejected moment has `cue.status = rejected`; startup without a connection string configures nothing.
6. **Live proof (required, with evidence):** run a live match locally with tracing on (`AGENT_MODE=foundry`, a few minutes at 1x or `run_match --seed 30 --limit 12 --live`), ask one question, then query App Insights. Use the Application Insights resource the Foundry project is linked to, so the **Foundry portal Tracing tab** shows the traces (scene 6 is recorded there). Find out which resource that is (`project.telemetry`, or the portal's Tracing settings). If it is not `appi-matchday`, either point the app at the linked one or link `appi-matchday` to the project, whichever needs no new resource, and record the choice in `docs/deploy.md`. Show the output of a query such as `dependencies | where timestamp > ago(1h) | summarize count() by name | top 20 by count_` and the operation id of one complete moment trace (with Analyst, Commentator, Fact-Checker and Producer spans) and of one Q&A trace with a tool span. Describe what the Foundry portal Tracing tab shows for that moment.
7. From the traces, report moment-to-cue latency (p50, p90) and the share of cues ready before display in live mode at 1x (SPEC success criterion 9); add the numbers to `docs/eval-results.md` under a short "Latency from traces" section.

### 2. Planted-claim demo switch (T12c, Must for video scene 5)

1. `StartRequest` in `app/api/main.py` gains `plant: int = Field(default=0, ge=0, le=3)`. It is honoured only when the environment has `DEMO_PLANT=1`; otherwise a request with `plant > 0` gets HTTP 403 with a clear message. The public Container App does not set `DEMO_PLANT`.
2. With `plant > 0`, wrap the Commentator writer with `PlantingCommentator` as `run_match.run_planted` does, choosing moments that have a cited shots key so the demo claim is the scene 5 one ("Ironvale have had six shots", rejected by layer code with the reason above). Reuse `PlantPlan` and `PlantingCommentator`; do not duplicate their logic.
3. The page: a small "Plant a false claim" toggle in the match settings, shown only when `/api/health` reports `demo_plant: true` (add that field). Keep to the P3 style guide (`docs/design/style-guide.md`); no other UI changes.
4. Tests: 403 without the env flag; with it, a planted moment ends rejected, never reaches the cue stream, the fan stream or the voice, and appears in `/api/match/moments` with the rejection reason.
5. Browser check: start seed 30 with the toggle on, open the timeline drawer, filter Rejected, and confirm the scene 5 layout (failed attempt struck through, reason in monospace, "Never aired"). Save a screenshot to `docs/design/screenshots/scene5-rejected.png`.

### 3. Full-time recap in English and Turkish (Must)

1. `app/agents/recap.py`: at full time, build the recap evidence from the ledger in deterministic code (final score, possession share, shots, the top moments by the existing moment scores, the fan's player line when a player is chosen). The agent writes only the wording and cites ledger keys, like every other agent. Template version for offline mode, Foundry version with instructions next to the other prompts in `app/agents/prompts.py` (digits only, en and tr, casual vs analyst depth).
2. The recap goes through the same Producer gate (`check_rendering`) with one regeneration on failure, then it is dropped for that profile with a visible "Recap unavailable" note (never an unchecked recap).
3. Delivery: one SSE event `recap` on the fan stream per active profile at full time, spoken by the voice when voice is on (through the same verbatim path and speech audit as cues), and a `GET /api/match/recap?profile=<profile_key>` for the page to fetch on reconnect. The page shows it as a "Full time" card on top of the narrative feed, styled per the style guide.
4. Tests: template recap in en and tr for casual and analyst; the gate rejects a recap with a wrong number; the SSE event arrives once at full time. One live test (`-m live`) for the Foundry recap in both languages.
5. Run `python -m app.agents.run_match --seed 7 --speed 30` and report its summary (cues, rejects, planted errors caught, ready-before-display share) plus the recap text in both languages.

### 4. Timeline drawer shows only moments already on air (Must, found in the P3 review 2026-10-17)

In precomputed mode (speed above 1x) the drawer lists every processed moment at once, so at 01:34 on the clock it already shows moments from minute 82. `/api/match/moments` must return only moments whose display time is at or before the playback clock (there is already `shown_moments()` and `displayed_events()` in `app/api/streams.py`; reuse that logic), and the page must add moments as they air. Test: at a given playback time no later moment is returned; at full time all are.

### 5. Hosted agent (Should, hard timebox: half a day)

1. Create `hosted/` (an `azd` project modelled on `spikes/hosted/`) that hosts the real commentary workflow from `app/agents/workflow.py` with `ResponsesHostServer(workflow=factory, ...)`. Input: one candidate moment as JSON; output: the `MomentResult` as JSON. Reuse the app modules; do not fork them.
2. Deploy to the existing Foundry project with `azd deploy`; invoke it remotely with one moment and show the response and its trace in the Foundry portal.
3. Spend: hosted sessions only while testing; no new Azure resources beyond what `azd` creates for the hosted agent inside the existing project. Note the hourly cost if the portal shows one, and stop or delete the deployment after the proof if it bills while idle (record what you did).
4. If it is not working within the timebox, stop, record the blocker and the last error in `docs/deploy.md` under "Hosted agent", and leave the T2 spike as the portal evidence. That is an acceptable outcome; do not keep pushing.

## Rules

- Branch `t10-finish` from `main` (P3 is merged). Push it; do not push to `main`; no pull request.
- Before every commit: `.venv\Scripts\python.exe -m pytest tests -q` must pass. Run `-m live` once at the end and report the totals.
- No em dashes, no Co-Authored-By trailers, fictional league only, no secrets in the repo (connection strings stay in `.env` and the Container App config).
- Do not redeploy the Container App yourself; list the env var changes it needs (for example `TRACE_SENSITIVE` stays unset, `DEMO_PLANT` stays unset) and Oguz redeploys after the merge.
- Update `SPEC.md` (tracing setup, the `plant` field and `DEMO_PLANT`, the recap interface), `task_state.md` and `tasks/todo.md` (T10 and T12c result lines) in the relevant commits.

## Reporting rule

Only report something as done when you ran it and can show the evidence (test output, query output, operation ids, what was on screen). Say "not done", "blocked" or "timeboxed out" otherwise.

## Done when

- Tracing: a live moment trace with all four agents and a Q&A trace with a tool span are in the App Insights resource the Foundry portal reads, with operation ids and query output in the report; latency numbers recorded.
- T12c: the toggle works locally, is refused on a server without `DEMO_PLANT=1`, and the scene 5 screenshot is saved.
- Recap: en and tr, both depths, gated, delivered at full time, spoken when voice is on; `run_match` summary reported.
- Drawer: no future moments in precomputed mode, with a test.
- Hosted: deployed and invoked with evidence, or timeboxed out with the blocker recorded.
- Report back: the branch, the commit list (one line each), the evidence for each task above, test totals (offline and live), and the Container App env var changes needed.
