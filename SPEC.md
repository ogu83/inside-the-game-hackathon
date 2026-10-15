# Spec: Matchday Companion (voice-first Commentator's Brain)

Status: APPROVED by Oguz on 2026-10-15 (voice-first version). Changes to interfaces, boundaries or scope still need a spec update first.
Pivot 2026-10-15: the fan experience is now voice-first. A live spoken co-commentator, in the fan's language, that the fan can interrupt to ask "why?" and that answers only from verified ledger evidence. The verified four-agent pipeline stays as the backbone. Reason: the text-based "verified multi-agent crew" concept is crowded on the hackathon platform; live conversational voice is rare and is Oguz's strongest proven domain. Innovation Studio project: "Matchday Companion" (minimal public page until ~2026-10-25).
Revision 2026-10-15 (post-T2 review, approved by Oguz): build a walking skeleton end to end first, then deepen; run playback behind a broadcast delay; two-layer Fact-Checker (deterministic number check in code, then LLM for wording); Analyst becomes the director (batch per window, decides when to stay quiet); ledger queries exposed over MCP for the voice Q&A path; planted-error test added to the evaluation; scope tiered Must / Should / Cut in tasks/plan.md, driven by the demo script.
Source idea: [IDEA.md](IDEA.md). Rules: https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md
Deadline: 2026-10-27 11:59 PM PT (= 2026-10-28 09:59 Istanbul). Internal target: submitted by 2026-10-26.

## Assumptions (correct these now or they stand)

1. **Azure access.** Resolved 2026-10-15: subscription re-enabled, Foundry project live (see T2 findings).
2. **Python 3.11** for everything backend (`py -3.11`), matching the other labs.
3. **Microsoft Agent Framework (Python, 1.0 GA)** is the orchestration layer: a graph workflow with a conditional edge for the Fact-Checker reject loop (max 1 retry) back to the Commentator. The workflow is **deployed as a Foundry Hosted Agent** (GA 2026-07-09) via `azd`, which gives managed runtime plus Foundry portal tracing with no telemetry plumbing. Models are called through the Responses API with keyless `DefaultAzureCredential`. Fallback if hosted deployment fights back: the same workflow self-hosted in the Container App, calling Foundry model deployments directly (still Foundry, but tracing must be wired by hand). Old "connected agents" and the Assistants API (threads/runs) are superseded and not used.
3a. **Frontier-model quota is not automatic.** GPT-5.5/5.6-class deployments need an explicit quota request unless the subscription is Tier 5/6. Request quota on day 1; design so Analyst, Fact-Checker and Producer run on a small model that has default quota, and only the Commentator needs a frontier model.
4. **Fictional league only.** No real clubs, players, crests, or StatsBomb data in code, fixtures, UI or video.
5. **Frontend is Vue 3 via CDN, no build step** (same pattern as ai-decision-room), streamed over Server-Sent Events.
6. **English + Turkish** are the two narrative languages.
7. **Local dev port 8010** (8000 is held by voicebox, 8002 by ai-decision-room).

## Objective

Pitch: **a live co-commentator you can interrupt, and that can't lie: every number it says is checked against the match data before it is spoken.**

Build an AI pipeline that ingests a live stream of synthetic football events and produces commentator-grade intelligence: what happened, why it matters, verified against the data, then said two ways from one truth: a timed broadcast overlay cue and a personalized fan narrative that a voice co-commentator speaks in the fan's language and answers questions about.

Users (both shown in the 2-minute demo):
- **Broadcast producer:** wants machine-readable overlay cues timed to play, and trusts them because every claim is verified.
- **Fan:** wants the same match told for them: favourite club, favourite player, casual vs analyst depth, language.

Primary goal: place in **Best Use of Microsoft Foundry** (judges may reassign to Best Multi-Agent System). Secondary goal: real hands-on Foundry and Agent Framework experience.

### User stories

- As a producer, I see overlay cues appear in sync with the simulated match clock, each with text, metric, duration and priority.
- As a producer, I never see a cue whose claim the Fact-Checker rejected, and I can open a trace showing why a claim passed.
- As a fan, I switch my profile (club, player, depth, language) and the next narrative visibly changes in focus, depth and language.
- As a fan, I hear the co-commentator speak verified moments live in my language, and I can interrupt it ("why was that pass important?", "how is my player doing?"); it stops talking within a beat and answers from ledger evidence, or says it does not know.
- As a fan, I get a full-time recap tailored to my profile.
- As a judge, I can run the whole thing with one command, or open a public URL.

## Capability Map

| Module id | Responsibility | Depends on |
| --- | --- | --- |
| `simulator` | Fictional league, match phase model, emits events on a clock; exports a dataset file | none |
| `ledger` | Deterministic match state: possession, pass quality, pressing, momentum windows, player thresholds; queryable evidence; read-only queries also served as an MCP server | `simulator` (event schema) |
| `agents` | Analyst (director), Commentator, Fact-Checker (code layer + LLM layer), Producer on Agent Framework + Foundry models; handoff contracts | `ledger` |
| `api` | FastAPI: start/stop match, SSE streams for cues and narratives, profile endpoint | `agents`, `ledger` |
| `voice` | Foundry Voice Live session per fan: speaks Producer narratives, server-side VAD + barge-in, routes spoken questions to an evidence-grounded answer path (Q&A agent that queries the ledger over MCP, checked by the Fact-Checker); speaks only approved text, verbatim (design rule 6) | `agents`, `ledger` |
| `ui` | Two-panel web page: broadcast panel with a 2D SVG pitch (ball and player dots from event x/y) and overlay cues, fan panel with profile switch and push-to-talk / open-mic voice companion | `api`, `voice` |
| `deploy` | `docker compose` judge path (Must); hosted agent; Azure Container App public URL (Should) | `api`, `ui` |

Build order: walking skeleton first (a thin slice of `simulator` -> `ledger` -> `agents` -> `api` -> `ui` -> `voice` working end to end), then deepen each module. See tasks/plan.md. Each module is small enough to stay inside this one spec; split into `SPEC-<module>.md` only if one grows past a page.

## Pipeline design rules

1. **Broadcast delay.** The simulator emits events ahead of playback; the UI and voice show the match `BROADCAST_DELAY_S` (default 10 s of match time) behind the event stream, like a real broadcast delay. Agents work on events as they arrive, so a cue is ready before its moment is displayed. `OverlayCue.show_at_seq` ties the cue to the display clock. A cue that is not ready when its moment plays is dropped, never shown late (counted in metrics).
2. **Two-layer Fact-Checker.** Layer 1 is deterministic code: every `evidence_refs` key must exist in the moment's evidence, and every number in `claim` and `why_it_matters` must match a cited evidence value (after rounding and unit normalisation). Any failure is an immediate `rejected` with machine-readable reasons, no LLM call. Layer 2 is an LLM that judges only the qualitative wording ("dominated", "one-way") against the evidence and may return `rewritten`. Numbers are verified by code, wording by a model.
   **The code check runs at every gate where a number can change, not only after the Commentator:** (a) the Commentator's `Insight`; (b) every Producer output, i.e. each `OverlayCue` headline/metric and each `FanNarrative` per profile and language, because per-profile rewrites and translation can change or drop numbers; (c) every text sent to the voice, including Q&A answers. The number parser handles English and Turkish formats: `68%`, `%68`, `yüzde 68`, `68.5`, `68,5`. The Producer and Q&A prompts require numbers as digits; a number written as a word fails the check. A failed Producer rendering is regenerated once, then dropped for that profile only (other profiles still get the cue). Every gate result is recorded as a `NumberCheck`.
3. **Analyst as director.** The Analyst runs once per window (default 60 s of match time) over the batch of candidate moments, ranks them, and decides what is worth saying now and when to stay quiet so commentary does not pile up. It never computes numbers.
4. **Ledger over MCP.** The ledger exposes read-only queries (team stats, player stats, recent moments) as an MCP server (`mcp` Python package, streamable HTTP). The voice Q&A agent calls these tools to answer open questions ("how is my player doing?"); its answer then passes the Fact-Checker like any other claim. The main moment pipeline gets evidence inline in `CandidateMoment` and does not need MCP.
5. **One truth, many renderings.** The Producer renders each verified insight once per active profile; per-profile calls run in parallel.
6. **The voice only speaks approved text.** Narrations and Q&A answers are sent to Voice Live as `response.create` with `pre_generated_assistant_message`, which synthesizes audio for the exact text with no model rewording (verified 2026-10-15 in en and tr, including `%68`). The realtime model is used only to listen: server VAD, transcription of the fan's question, barge-in. It never authors spoken words. Q&A is therefore text first: question transcript -> Q&A agent (ledger over MCP) -> Fact-Checker gate (c) -> verbatim speech. As an audit, the transcript of every spoken response is compared with the approved text and run through the number check; any mismatch is counted as an error (target 0). Pitch line for the demo: "even the voice is audited".

## Interfaces (contracts between modules)

```python
# simulator -> ledger
class MatchEvent(BaseModel):
    match_id: str
    seq: int                      # strictly increasing per match
    minute: int
    second: int
    type: Literal["pass", "shot", "tackle", "interception", "pressure",
                  "possession_change", "substitution", "foul", "goal",
                  "kickoff", "half_time", "full_time"]
    team_id: str
    player_id: str | None
    x: float; y: float            # pitch coords 0-100, attacking left to right
    end_x: float | None; end_y: float | None
    outcome: Literal["success", "fail"] | None
    meta: dict[str, float | str]  # e.g. speed_kmh, pass_length_m, xg

# ledger -> agents
class CandidateMoment(BaseModel):
    moment_id: str
    window: tuple[int, int]       # seq range the moment covers
    kind: str                     # e.g. "pressing_trap", "momentum_shift", "pass_streak"
    team_id: str                  # team the moment is about (added in S2)
    minute: int                   # match minute when the moment ended (added in S2)
    evidence: dict[str, float]    # ledger numbers the claim may cite; includes window_minutes and minute so time references are citable

# Commentator -> Fact-Checker -> Producer
class Insight(BaseModel):
    moment_id: str
    claim: str
    why_it_matters: str
    evidence_refs: list[str]      # keys into CandidateMoment.evidence / ledger
    confidence: float

class Verdict(BaseModel):
    moment_id: str
    status: Literal["verified", "rewritten", "rejected"]
    insight: Insight | None
    reasons: list[str]
    layer: Literal["code", "llm"]  # which Fact-Checker layer decided
    attempt: int                  # 1, or 2 after the single retry

class NumberCheck(BaseModel):     # one per gate pass, logged and counted in the run report
    gate: Literal["insight", "producer", "speech"]
    moment_id: str
    profile_key: str | None       # producer and speech gates
    text: str                     # the text that was checked
    ok: bool
    mismatches: list[str]         # e.g. "68 not in cited evidence", "number written as word: altmış sekiz"

# Producer outputs
class OverlayCue(BaseModel):
    moment_id: str
    show_at_seq: int
    duration_s: int
    priority: Literal["low", "normal", "high"]
    headline: str                 # <= 60 chars
    metric_label: str | None
    metric_value: str | None

class FanProfile(BaseModel):
    club_id: str | None
    player_id: str | None
    depth: Literal["casual", "analyst"]
    language: Literal["en", "tr"]

class FanNarrative(BaseModel):
    moment_id: str
    profile_key: str
    text: str
```

## Tech Stack

| Layer | Choice |
| --- | --- |
| Language | Python 3.11 |
| Agents | Microsoft Agent Framework (Python 1.0+), graph workflow with conditional reject edge; deployed as a Foundry Hosted Agent |
| Foundry SDK | `agent-framework-foundry` (`FoundryChatClient`), `azure-ai-projects` (use `project.agents`, not the old `project.beta.agents`), `openai`, `azure-identity`; Python 3.11 locally, 3.13 in the hosted runtime. Versions pinned below |
| CLI | `az` 2.87 (installed) + `azd` with the `azure.ai.agents` extension, installed via `winget install Microsoft.Azd --source winget`; `az login --tenant <tenant>` only, with `azd config set auth.useAzCliAuth true` |
| Models | Deployed in the Foundry project (selecting in the catalog is not enough; each needs a named deployment). Commentator on a frontier model; Analyst, Fact-Checker, Producer on a small fast model. 429s handled with exponential backoff + jitter honoring `Retry-After` |
| Observability | Foundry tracing (OpenTelemetry GenAI conventions, GA) into an Application Insights resource linked to the project |
| Evaluation | Foundry built-in evaluators over recorded match runs: Groundedness (claims vs ledger evidence), Task Adherence, Intent Resolution. Cloud evaluations are long-running operations: submit, then poll |
| API | FastAPI + uvicorn, SSE via `sse-starlette` |
| MCP | `mcp` Python package (already a dependency of the hosting package): read-only ledger tools over streamable HTTP, consumed by the voice Q&A agent through Agent Framework's MCP tool support |
| Voice | Foundry Voice Live (GA July 2026): real-time duplex audio, server-side VAD, echo cancellation, noise suppression; browser audio over WebSocket through the API |
| State | SQLite (local) for ledger snapshots and run logs |
| Frontend | Vue 3 CDN, single `frontend/index.html`, no npm; inline SVG pitch |
| Tests | pytest, pytest-asyncio |
| Container | Single Dockerfile, `docker compose` for local |
| Hosting | Agent workflow: Foundry Hosted Agent (same workflow module also runs in-process for local runs and the video). Judge path: `docker compose` (Must). Public URL: one small Azure Container App (Should; the rules accept a test build) |

### Pinned in the T2 spike (2026-10-15)

| Package | Version | Note |
| --- | --- | --- |
| `agent-framework-core` | 1.21.0 | workflows: `WorkflowBuilder`, `Executor`, `@handler`, conditional `add_edge` |
| `agent-framework-foundry` | 1.14.1 | `FoundryChatClient` (Responses API); reads `FOUNDRY_PROJECT_ENDPOINT` |
| `agent-framework-foundry-hosting` | 1.0.0b261008 | `ResponsesHostServer` for the hosted agent (beta) |
| `azure-ai-projects` | 2.7.0 | 2.8.0 conflicts with agent-framework-foundry 1.14.1 |
| `azure-identity` | 1.26.0 | keyless `DefaultAzureCredential` |
| `openai` | 3.31.0 | |
| `azure-monitor-opentelemetry` | 1.8.11 | local runs export spans to App Insights |
| `azure-ai-voicelive` | 1.3.0 | Voice Live client, API version 2026-07-15 |
| `azd` | 1.35.1 | + extension `azure.ai.agents` 1.0.0-beta.19 |

### T2 decisions and findings (2026-10-15)

- **Region:** eastus2. One resource group with a Foundry resource (AIServices, S0, project management enabled) and one project; "Foundry User" role on the resource; Application Insights (workspace-based) linked as a project connection. Subscription budget alert: $50/month (50%, 80%, forecast 100%).
- **Models and quota:** in eastus2 `gpt-5.4-mini` has quota only as DataZone Standard (200K TPM; deployed at 100K TPM). `gpt-5.5` and all `gpt-5.6-*` have 0 quota (Global and DataZone), so the frontier Commentator waits on a quota request. Until then `FRONTIER_MODEL_DEPLOYMENT` points at `gpt-5.4-mini`; the code reads the deployment name from env, so switching is a config change.
- **Hosted vs in-container: Hosted Agent confirmed.** `azd deploy` (code deploy, `python_3_13` runtime, remote build from `uv.lock`) works from Windows in about 1 to 2 minutes and the agent is invoked remotely over the Responses protocol. Cold first call: about 9 s to response headers, 29 s end to end for a 4-call workflow. Lessons:
  - Host the workflow natively: `ResponsesHostServer(workflow=factory, parse_response=...)`. Hosting a `WorkflowAgent` through `agent=` is deprecated and fails on hosted sessions.
  - Messages between executors must be JSON-safe (dicts, str, numbers) or explicitly allow-listed: the hosted checkpoint store refuses to deserialize custom classes and fails the run. T10 passes payloads as `model_dump()` dicts and re-validates them into the Pydantic models above at each executor.
  - Commit an up-to-date `uv.lock`; the remote build installs exactly what it pins.
  - `azd` can reuse the `az` login: `azd config set auth.useAzCliAuth true`.
- **Tracing:** the hosted agent exports spans to the linked App Insights automatically (`workflow.run`, `executor.process <id>`, `invoke_agent <name>`, `chat <model>` with token usage). Local runs export the same spans with `configure_azure_monitor()` + `enable_instrumentation()`, using the connection string from `project.telemetry`.
- **Voice Live:** works in eastus2 against the Foundry resource endpoint with keyless auth and the managed `gpt-realtime` model (no deployment needed). Headless test: `response.cancel` after 1 s of audio stopped the server in about 0.4 s; a follow-up reply took about 1.6 s. `output_audio_buffer.clear` is avatar-only, so on barge-in the browser drops its own playback buffer. The SDK can also attach Voice Live directly to a Foundry agent (`agent_name`, `project_name`), which is an option for T12b; the default stays text in/out from our verified pipeline. **Verbatim speech:** `response.create` with `pre_generated_assistant_message` speaks the exact text we send (tested with an English line and a Turkish line containing `%68`: transcript identical to the sent text, about 7 s of audio each). This is the basis of design rule 6.
- **Latency watch:** one `gpt-5.4-mini` call takes about 1.5 to 2.5 s, so a moment that needs Analyst, Commentator, Fact-Checker and Producer in sequence lands around 6 to 9 s. Resolved by design rather than tuning: broadcast delay (rule 1), Analyst once per window (rule 3), code-layer rejects with no LLM call (rule 2), parallel Producer (rule 5).

## Commands

```
# setup
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# tests (also run by the test_gate hook after every git commit)
python -m pytest tests/ -q

# simulator only, prints a match as text at 20x speed
python -m app.simulator.run --seed 7 --speed 20

# full app, local
python -m uvicorn app.api.main:app --port 8010 --reload
# then open http://localhost:8010

# container
docker compose up --build -d
curl http://localhost:8010/api/health
```

## Project Structure

```
app/
  simulator/     league data, phase model, event emitter, dataset export
  ledger/        match state, stat calculators, candidate moment detection
  agents/        one module per agent, prompts, workflow wiring
  api/           FastAPI app, SSE endpoints
frontend/        index.html, style.css
data/            generated datasets (fictional league), git-tracked samples only
tests/           mirrors app/ (tests/simulator, tests/ledger, ...)
docs/            architecture diagram, demo script, submission text
tasks/           plan.md, todo.md
.hooks/          PowerShell hooks
```

## Code Style

```python
def pass_difficulty(event: MatchEvent, pressure_nearby: int) -> float:
    """0..1, higher is harder."""
    length = event.meta.get("pass_length_m", 0.0)
    forward = max(0.0, (event.end_x or event.x) - event.x)
    score = 0.4 * min(length / 40, 1) + 0.3 * min(forward / 30, 1) + 0.3 * min(pressure_nearby / 3, 1)
    return round(score, 3)
```

- Pydantic models for every cross-module payload; no loose dicts across boundaries.
- Numbers come from deterministic code in `ledger`; agents never compute stats, they only cite ledger keys.
- Type hints everywhere, `ruff` defaults, no comments that restate the code.
- Prompts live in `app/agents/prompts.py` as constants.

## Testing Strategy

- **Unit (pytest):** simulator determinism (same seed, same events), event schema validity, every ledger calculator, candidate-moment detection on hand-built event sequences.
- **Contract:** agent outputs parse into the Pydantic models above; Fact-Checker rejects an insight citing a missing or contradicted ledger key (fixture with a deliberately false claim).
- **Fact-Checker layer 1 is plain unit tests** (no model): number extraction, rounding and unit rules, missing keys, mismatched values, claims with no numbers.
- **Planted errors:** a test helper corrupts N Commentator insights per match (wrong number, missing key, swapped team) and N Producer renderings, including Turkish translations (changed number, dropped number, number as a word); the run report counts how many reached a cue, a narrative or the voice (target 0).
- **Number parser:** unit tests for en and tr formats (`68%`, `%68`, `yüzde 68`, `68.5`, `68,5`), digits-only rule, and the speech-transcript comparison.
- **Agent tests with real models are opt-in** (`pytest -m live`), excluded from the commit gate so commits do not burn tokens.
- **End to end:** one seeded 90-minute match at high speed produces at least N verified cues, zero cues from rejected insights, and a recap in both languages.
- Coverage target: ledger and simulator high; agents tested by contract, not by wording.

## Boundaries

- **Always:** keep the league fictional; update `task_state.md` after each task; run `python -m pytest tests/ -q` before commits; keep secrets in `.env` (gitignored); cite ledger keys for every number an agent says.
- **Ask first:** adding a dependency outside the tech stack above; switching model or provider; any Azure resource that costs money beyond the Foundry project and one Container App; changing the interfaces above.
- **Never:** real club/player names, crests or third-party trademarks anywhere (rules section 4.4); StatsBomb or other non-commercially licensed data as input; committing `.env` or keys; building features on the IDEA.md "Not Doing" list without a spec change.

## Success Criteria

1. A seeded 90-minute match (run at 30x speed) produces at least 15 overlay cues, each traceable to a verified insight.
2. Zero overlay cues or narratives originate from a `rejected` verdict (asserted in the end-to-end test).
3. At 1x speed with a 10 s broadcast delay, at least 90% of cues are ready before their moment is displayed (none shown late); moment-to-cue latency is reported from Foundry tracing.
4. Switching the fan profile changes the next narrative's language, focus player/club and depth (demonstrable on video).
5. Full-time recap generated in English and Turkish.
6. `docker compose up --build` from a clean clone runs the full demo with only `.env` filled in.
7. Public GitHub repo, README with architecture diagram, under-2-minute YouTube demo, submitted on Innovation Studio by 2026-10-26.
8. A Foundry cloud evaluation over 3 recorded matches reports Groundedness for verified insights, with the Fact-Checker on vs off, plus a planted-error count ("caught X of N planted errors, 0 reached air"); both numbers appear in the README and the demo (this is the Foundry-category proof point).
9. Voice: the co-commentator speaks verified moments in English and Turkish; a spoken interruption stops playback in under 500 ms; a spoken "why?" question gets an evidence-grounded spoken answer in under ~3 s median (target; measured, since Q&A is text first then verbatim speech); a question with no ledger evidence gets "I don't have data on that" instead of an invented answer; every spoken line is approved text read verbatim, and the speech transcript audit shows 0 mismatches.
10. The voice Q&A agent answers at least one open question in the demo by calling a ledger MCP tool, visible as a tool-call span in the trace.

## Open Questions

- Frontier-model quota for `gpt-5.5` (or `gpt-5.6-*`) in eastus2: request filed? (see T2 findings).
- Actual cost per seeded match (tokens + hosted sessions + Voice Live minutes): read Cost analysis after the first full T10 run.
- Stretch only: register the ledger MCP server in a Foundry Toolbox (GA July 2026) instead of a direct connection. MCP itself is now in MVP (design rule 4).
- Innovation Studio submission fields (invite expected by ~2026-10-16).
