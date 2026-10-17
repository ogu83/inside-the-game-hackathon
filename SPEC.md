# Spec: Matchday Companion (voice-first Commentator's Brain)

Status: APPROVED by Oguz on 2026-10-15 (voice-first version). Changes to interfaces, boundaries or scope still need a spec update first.
Pivot 2026-10-15: the fan experience is now voice-first. A live spoken co-commentator, in the fan's language, that the fan can interrupt to ask "why?" and that answers only from verified ledger evidence. The verified four-agent pipeline stays as the backbone. Reason: the text-based "verified multi-agent crew" concept is crowded on the hackathon platform; live conversational voice is rare and is Oguz's strongest proven domain. Innovation Studio project: "Matchday Companion" (minimal public page until ~2026-10-25).
Revision 2026-10-15 (post-T2 review, approved by Oguz): build a walking skeleton end to end first, then deepen; run playback behind a broadcast delay; two-layer Fact-Checker (deterministic number check in code, then LLM for wording); Analyst becomes the director (batch per window, decides when to stay quiet); ledger queries exposed over MCP for the voice Q&A path; planted-error test added to the evaluation; scope tiered Must / Should / Cut in tasks/plan.md, driven by the demo script.
Revision 2026-10-15 (review in docs/reviews/2026-10-15-fable-review.md, all four decisions approved by Oguz): director decision per moment with pacing state (`DirectorDecision`), `BROADCAST_DELAY_S` default 20 s, precomputed mode above 1x and live mode at 1x; public Azure Container App URL becomes Must with a per-visitor run limit and an offline fallback, `docker compose` runs offline mode without Azure; interfaces gain `DirectorDecision`, `Question`, `Answer`, `SpeechAudit`, the `profile_key` definition and `top_player_*` evidence; rounding and digits-only rules documented; scope cut to 2 clubs, 2 detectors, hosted agent timeboxed, Q&A text-first.
Revision 2026-10-15 (Phase B notes, docs/reviews/2026-10-15-phase-b-notes.md, approved by Oguz): Producer coverage rule for dropped numbers; the planted swapped team is a layer 2 catch and the 0-reached-air target applies to the live run; `PacingState` named in rule 3; player distance is a proxy, no speed thresholds.
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
| `ledger` | Deterministic match state: possession (pass-attempt share), pass quality, pressing, player involvement and a distance proxy (metres between a player's consecutive event positions; event data has no tracking, so no speed thresholds); queryable evidence; read-only queries also served as an MCP server | `simulator` (event schema) |
| `agents` | Analyst (director, one `DirectorDecision` per moment), Commentator, Fact-Checker (code layer + LLM layer), Producer on Agent Framework + Foundry models; handoff contracts; offline template agents when no model is configured | `ledger` |
| `api` | FastAPI: start/stop match, SSE streams for cues and narratives, profile endpoint | `agents`, `ledger` |
| `voice` | Foundry Voice Live session per fan: speaks Producer narratives, server-side VAD + barge-in, routes spoken questions to an evidence-grounded answer path (Q&A agent that queries the ledger over MCP, checked by the Fact-Checker); speaks only approved text, verbatim (design rule 6) | `agents`, `ledger` |
| `ui` | Two-panel web page: broadcast panel with a 2D SVG pitch (ball and player dots from event x/y) and overlay cues, fan panel with profile switch and push-to-talk / open-mic voice companion | `api`, `voice` |
| `deploy` | `docker compose` offline mode without Azure (Must); public Azure Container App URL with managed identity, per-visitor run limit and offline fallback (Must); hosted agent (Should, timeboxed) | `api`, `ui` |

Build order: walking skeleton first (a thin slice of `simulator` -> `ledger` -> `agents` -> `api` -> `ui` -> `voice` working end to end), then deepen each module. See tasks/plan.md. Each module is small enough to stay inside this one spec; split into `SPEC-<module>.md` only if one grows past a page.

## Pipeline design rules

1. **Broadcast delay.** The simulator emits events ahead of playback; the UI and voice show the match `BROADCAST_DELAY_S` (default 20 s of match time) behind the event stream, like a real broadcast delay. Agents work on events as they arrive, so a cue is ready before its moment is displayed. `OverlayCue.show_at_seq` ties the cue to the display clock. A cue that is not ready when its moment plays is dropped, never shown late (counted in metrics as `cues_dropped_late`). Two playback modes: **live** at 1x (agents race the delayed clock; the video and the public URL) and **precomputed** above 1x (every moment is processed before playback starts, then replayed on the delayed clock; tests, evaluation runs and the 30x end-to-end criterion). The delay is in match seconds, so the wall-clock delay is `delay_s / speed`.
2. **Two-layer Fact-Checker.** Layer 1 is deterministic code: every `evidence_refs` key must exist in the moment's evidence, and every number in `claim` and `why_it_matters` must match a cited evidence value (after rounding and unit normalisation). Any failure is an immediate `rejected` with machine-readable reasons, no LLM call. Layer 2 is an LLM that judges only the qualitative wording ("dominated", "one-way") against the evidence and may return `rewritten`. Numbers are verified by code, wording by a model.
   **Rounding rule:** a number in text matches a cited evidence value when that value, rounded half-up to the text's number of decimals, equals it (68 matches 67.6; 52.5 matches "53" and "52.5" but not "52"). Keys ending in `_s` also match in minutes when the text says minutes. Qualified approximations ("over 50 metres" against 52.5) fail by design; prompts ask for exact ledger numbers. **Digits-only rule:** number words in English and Turkish fail the check, except "one" and "bir" (articles and pronouns) and ordinal words ("second half", "ikinci yarı"). Parser formats: `68%`, `%68`, `yüzde 68`, `68.5` and `1,250` (en), `68,5` and `1.250` (tr), ordinals `23rd` and `23.`, Turkish suffixes `14'ü`, `%68'lik`; a number glued to a letter or a `letter-` prefix is an identifier, not a number.
   **The code check runs at every gate where a number can change, not only after the Commentator:** (a) the Commentator's `Insight`; (b) every Producer output, i.e. each `OverlayCue` headline/metric and each `FanNarrative` per profile and language, because per-profile rewrites and translation can change or drop numbers; (c) every text sent to the voice, including Q&A answers. The number parser handles English and Turkish formats: `68%`, `%68`, `yüzde 68`, `68.5`, `68,5`. The Producer and Q&A prompts require numbers as digits; a number written as a word fails the check. A failed Producer rendering is regenerated once, then dropped for that profile only (other profiles still get the cue). Every gate result is recorded as a `NumberCheck`. **Coverage rule at gate (b):** a rendering is also compared with its verified source text: with coverage `all` (analyst depth and the overlay metric) every number in the source claim must survive, with coverage `any` (casual depth) at least one must survive when the source has numbers; a failure is recorded as `dropped number: 14` in the `NumberCheck`.
3. **Analyst as director.** The Analyst is called once per candidate moment as it closes and returns a `DirectorDecision`: say or skip, the angle to take, and a reason. It receives a `PacingState` computed by code (seconds since the last spoken cue, cues and moments in the last 2 minutes, the moment's rank among recent moments and its interest score; an internal contract between code and the Analyst, not a cross-module payload) so it can stay quiet when commentary would pile up, without waiting for a batch window. It never computes numbers. Skipped moments are logged and shown in the verdict drawer.
4. **Ledger over MCP.** The ledger exposes read-only queries (team stats, player stats, recent moments) as an MCP server (`mcp` Python package, streamable HTTP). The voice Q&A agent calls these tools to answer open questions ("how is my player doing?"); its answer then passes the Fact-Checker like any other claim. The main moment pipeline gets evidence inline in `CandidateMoment` and does not need MCP.
5. **One truth, many renderings.** The Producer renders each verified insight once per active profile; per-profile calls run in parallel.
6. **The voice only speaks approved text.** Narrations and Q&A answers are sent to Voice Live as `response.create` with `pre_generated_assistant_message`, which synthesizes audio for the exact text with no model rewording (verified 2026-10-15 in en and tr, including `%68`). The realtime model is used only to listen: server VAD, transcription of the fan's question, barge-in. It never authors spoken words. Q&A is therefore text first: question transcript -> Q&A agent (ledger over MCP) -> Fact-Checker gate (c) -> verbatim speech. As an audit, the transcript of every spoken response is compared with the approved text and run through the number check; any mismatch is counted as an error (target 0). Pitch line for the demo: "even the voice is audited".
7. **Offline mode and the judges' budget.** With no model configured (`AGENT_MODE=template`), the same pipeline runs with deterministic template agents that fill fixed sentences from the ledger evidence; every gate still runs. This is what `docker compose` runs from a clean clone and the recording fallback if Foundry returns errors. The public Container App runs live agents under a per-visitor run limit (default `PUBLIC_LIVE_RUNS_PER_DAY=2` live matches per visitor per day, by client IP or cookie); after the limit, and on any Foundry error, the app continues in offline mode and says so in the UI. Reason: judges' clicks spend Foundry tokens against a 50 USD/month budget.

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
    evidence: dict[str, float]    # ledger numbers the claim may cite; includes window_minutes and minute so time references are citable,
                                  # and top_player_passes for the most involved player (pass_streak)
    top_player_id: str | None     # most involved player; names are resolved in the agents layer (app/ledger/labels.py), never stored here

# Analyst (director) -> pipeline, one per candidate moment
class DirectorDecision(BaseModel):
    moment_id: str
    say: bool                     # False = stay quiet; the moment is logged and shown in the verdict drawer
    angle: str | None             # e.g. "control", "pressure", "player"; guides the Commentator
    reason: str

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

    def key(self) -> str:         # profile_key everywhere else
        return f"{self.club_id or '-'}|{self.player_id or '-'}|{self.depth}|{self.language}"

class FanNarrative(BaseModel):
    moment_id: str
    profile_key: str
    text: str

# Voice Q&A (text first, then verbatim speech)
class Question(BaseModel):
    question_id: str
    profile_key: str
    transcript: str               # what the fan said, transcribed by Voice Live
    asked_at_seq: int             # display-clock position when the question arrived

class Answer(BaseModel):
    question_id: str
    text: str                     # "I don't have data on that" when no evidence supports an answer
    evidence_refs: list[str]      # ledger keys returned by the MCP tools
    tool_calls: list[str]         # MCP tool names called, for the trace
    verdict: Verdict | None       # the Fact-Checker gate the answer passed

class SpeechAudit(BaseModel):     # one per spoken response (narration or answer)
    moment_id: str | None
    question_id: str | None
    profile_key: str
    approved_text: str
    transcript: str               # Voice Live's transcript of what was spoken
    ok: bool                      # transcript equals approved text (case, spacing, end punctuation ignored) and passes the number check
    mismatches: list[str]
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
| Hosting | Judge paths (both Must): `docker compose` in offline mode from a clean clone, and one small Azure Container App with a public HTTPS URL running live agents under a system-assigned managed identity that holds Foundry User on the project, kept running through judging (until 2026-11-10) with the per-visitor run limit and offline fallback of design rule 7. Agent workflow: the same module runs in-process (local, video, Container App) and as a Foundry Hosted Agent (Should, timeboxed to half a day) |

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
- **Tracing:** the hosted agent exports spans to the linked App Insights automatically (`workflow.run`, `executor.process <id>`, `invoke_agent <name>`, `chat <model>` with token usage). In-app runs configure OpenTelemetry via `app/observability.py` on startup if `APPLICATIONINSIGHTS_CONNECTION_STRING` is set (or `TRACING=foundry` via `project.telemetry`). Spans wrap each moment (`moment <moment_id>`), individual profile renderings (`producer.render`), Q&A answers (`qa.answer`), and MCP tool calls (`mcp.tool <name>`). Sensitive payload text is emitted into spans only when `TRACE_SENSITIVE=1` (disabled on public Container App).
- **Voice Live:** works in eastus2 against the Foundry resource endpoint with keyless auth and the managed `gpt-realtime` model (no deployment needed). Headless test: `response.cancel` after 1 s of audio stopped the server in about 0.4 s; a follow-up reply took about 1.6 s. `output_audio_buffer.clear` is avatar-only, so on barge-in the browser drops its own playback buffer. The SDK can also attach Voice Live directly to a Foundry agent (`agent_name`, `project_name`), which is an option for T12b; the default stays text in/out from our verified pipeline. **Verbatim speech:** `response.create` with `pre_generated_assistant_message` speaks the exact text we send (tested with an English line and a Turkish line containing `%68`: transcript identical to the sent text, about 7 s of audio each). This is the basis of design rule 6.
- **Latency watch:** one `gpt-5.4-mini` call takes about 1.5 to 2.5 s, so a moment that needs Analyst, Commentator, Fact-Checker and Producer in sequence lands around 6 to 9 s. Resolved by design rather than tuning: broadcast delay (rule 1), Analyst once per window (rule 3), code-layer rejects with no LLM call (rule 2), parallel Producer (rule 5).

## Commands

```
# setup (Windows)
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# setup (Linux, cloud sessions and the container)
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# tests (also run by the test_gate hook after every git commit)
python -m pytest tests/ -q

# simulator only, prints a match as text at 20x speed
python -m app.simulator.run --seed 7 --speed 20

# every S2 moment through the Commentator -> Fact-Checker workflow (offline agents; --live uses Foundry)
python -m app.agents.run_match --seed 7 --jsonl runs/7.jsonl [--live]

# full app, local (AGENT_MODE=template without Azure, AGENT_MODE=foundry with .env)
python -m uvicorn app.api.main:app --port 8010 --reload --env-file .env   # .env turns on Voice Live (and AGENT_MODE=foundry for live agents)
# then open http://localhost:8010 and start a match (speed 1 = live mode, above 1 = precomputed)

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
- **Director:** `DirectorDecision` parses by contract; pacing is tested with scripted decisions on hand-built moment sequences (no two cues inside the quiet period, a high-rank moment is never skipped for pacing alone).
- **Planted errors:** a test helper corrupts N Commentator insights per match (wrong number, missing key, swapped team) and N Producer renderings, including Turkish translations (changed number, dropped number, number as a word); the run report counts per kind what each layer caught and how many reached a cue, a narrative or the voice. A swapped team keeps every number right, so layer 1 passes it by design and only the layer 2 wording judge can reject it: the 0-reached-air target applies to the live run (`pytest -m live`, `run_match --plant --live`); the offline run proves that the code layer alone catches every number error.
- **Planted-claim demo switch (T12c):** `StartRequest` includes `plant: int = Field(default=0, ge=0, le=3)`. Honoured only when `DEMO_PLANT=1` is set in the environment (HTTP 403 otherwise). When enabled, `POST /api/match/start` with `plant=1` wraps Commentator with `PlantingCommentator(recover=False)` targeting moments citing shots, causing the Fact-Checker to reject the claim ("Ironvale have had 6 shots.", reason: `6 shots does not match the cited shots value (away_shots_last_10min = 0)`). `/api/health` exposes `demo_plant: bool`.
- **Full-time recap:** Deterministic evidence built from ledger events (final score, possession pct, shots, top moment minute) and fan profile player stats. Wording generated by TemplateRecapWriter (offline) or FoundryRecapWriter (live) in en and tr for casual and analyst depths. Gated by Producer number checks with 1 retry on error. Delivered via SSE event `recap` on `/api/stream/fan`, spoken verbatim over the voice websocket, and queryable at `GET /api/match/recap?profile=<key>`. Rendered as a full-time card on top of the fan narrative feed.
- **Number parser:** unit tests for en and tr formats (`68%`, `%68`, `yüzde 68`, `68.5`, `68,5`), digits-only rule, and the speech-transcript comparison.
- **Agent tests with real models are opt-in** (`pytest -m live`), excluded from the commit gate so commits do not burn tokens.
- **End to end:** one seeded 90-minute match at high speed produces at least N verified cues, zero cues from rejected insights, and a recap in both languages.
- Coverage target: ledger and simulator high; agents tested by contract, not by wording.

## Boundaries

- **Always:** keep the league fictional; update `task_state.md` after each task; run `python -m pytest tests/ -q` before commits; keep secrets in `.env` (gitignored); cite ledger keys for every number an agent says.
- **Ask first:** adding a dependency outside the tech stack above; switching model or provider; any Azure resource that costs money beyond the Foundry project and one Container App; changing the interfaces above; raising the per-visitor live-run limit.
- **Never:** real club/player names, crests or third-party trademarks anywhere (rules section 4.4); StatsBomb or other non-commercially licensed data as input; committing `.env` or keys; building features on the IDEA.md "Not Doing" list without a spec change.

## Success Criteria

1. A seeded 90-minute match (run at 30x speed in precomputed mode) produces at least 15 overlay cues, each traceable to a verified insight.
2. Zero overlay cues or narratives originate from a `rejected` verdict (asserted in the end-to-end test).
3. At 1x speed in live mode with a 20 s broadcast delay, at least 90% of cues are ready before their moment is displayed (none shown late); moment-to-cue latency is reported from Foundry tracing.
4. Switching the fan profile changes the next narrative's language, focus player/club and depth (demonstrable on video).
5. Full-time recap generated in English and Turkish.
6. `docker compose up --build` from a clean clone runs the full demo in offline mode with no Azure and no `.env`; with `.env` filled in and an Azure login it runs the live agents.
7. Public GitHub repo, README with architecture diagram, under-2-minute YouTube demo, submitted on Innovation Studio by 2026-10-26.
8. A Foundry cloud evaluation over 3 recorded matches reports Groundedness for verified insights, with the Fact-Checker on vs off, plus a planted-error count ("caught X of N planted errors, 0 reached air"); both numbers appear in the README and the demo (this is the Foundry-category proof point).
9. Voice: the co-commentator speaks verified moments in English and Turkish; a spoken interruption stops playback in under 500 ms; a spoken "why?" question gets an evidence-grounded spoken answer in under ~3 s median (target; measured, since Q&A is text first then verbatim speech); a question with no ledger evidence gets "I don't have data on that" instead of an invented answer; every spoken line is approved text read verbatim, and the speech transcript audit shows 0 mismatches.
10. The voice Q&A agent answers at least one open question in the demo by calling a ledger MCP tool, visible as a tool-call span in the trace.
11. A public HTTPS URL on Azure Container Apps runs the live demo for judges from submission until 2026-11-10 with no credentials (managed identity), enforces the per-visitor live-run limit, and falls back to offline mode on Foundry errors; both facts are stated in the README judge section.

## Open Questions

- Frontier-model quota for `gpt-5.5` (or `gpt-5.6-*`) in eastus2: request filed? (see T2 findings).
- Actual cost per seeded match (tokens + hosted sessions + Voice Live minutes): read Cost analysis after the first full T10 run.
- Stretch only: register the ledger MCP server in a Foundry Toolbox (GA July 2026) instead of a direct connection. MCP itself is now in MVP (design rule 4).
- Innovation Studio submission fields (invite expected by ~2026-10-16).
