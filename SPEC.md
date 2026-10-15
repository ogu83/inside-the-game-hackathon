# Spec: Matchday Companion (voice-first Commentator's Brain)

Status: APPROVED by Oguz on 2026-10-15 (voice-first version). Changes to interfaces, boundaries or scope still need a spec update first.
Pivot 2026-10-15: the fan experience is now voice-first. A live spoken co-commentator, in the fan's language, that the fan can interrupt to ask "why?" and that answers only from verified ledger evidence. The verified four-agent pipeline stays as the backbone. Reason: the text-based "verified multi-agent crew" concept is crowded on the hackathon platform; live conversational voice is rare and is Oguz's strongest proven domain. Innovation Studio project: "Matchday Companion" (minimal public page until ~2026-10-25).
Source idea: [IDEA.md](IDEA.md). Rules: https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md
Deadline: 2026-10-27 11:59 PM PT (= 2026-10-28 09:59 Istanbul). Internal target: submitted by 2026-10-26.

## Assumptions (correct these now or they stand)

1. **Azure access gets fixed on day 1.** `az account show` reports "Azure subscription 1" as `Disabled` (checked 2026-10-14). Nothing in the Foundry or deploy track works until a subscription is active (re-enable with a payment method, or a new pay-as-you-go / free-credit subscription). Local work (simulator, ledger, UI) does not wait on it.
2. **Python 3.11** for everything backend (`py -3.11`), matching the other labs.
3. **Microsoft Agent Framework (Python, 1.0 GA)** is the orchestration layer: a graph workflow with a conditional edge for the Fact-Checker reject loop (max 1 retry) back to the Commentator. The workflow is **deployed as a Foundry Hosted Agent** (GA 2026-07-09) via `azd`, which gives managed runtime plus Foundry portal tracing with no telemetry plumbing. Models are called through the Responses API with keyless `DefaultAzureCredential`. Fallback if hosted deployment fights back: the same workflow self-hosted in the Container App, calling Foundry model deployments directly (still Foundry, but tracing must be wired by hand). Old "connected agents" and the Assistants API (threads/runs) are superseded and not used.
3a. **Frontier-model quota is not automatic.** GPT-5.5/5.6-class deployments need an explicit quota request unless the subscription is Tier 5/6. Request quota on day 1; design so Analyst, Fact-Checker and Producer run on a small model that has default quota, and only the Commentator needs a frontier model.
4. **Fictional league only.** No real clubs, players, crests, or StatsBomb data in code, fixtures, UI or video.
5. **Frontend is Vue 3 via CDN, no build step** (same pattern as ai-decision-room), streamed over Server-Sent Events.
6. **English + Turkish** are the two narrative languages.
7. **Local dev port 8010** (8000 is held by voicebox, 8002 by ai-decision-room).

## Objective

Build an AI pipeline that ingests a live stream of synthetic football events and produces commentator-grade intelligence: what happened, why it matters, verified against the data, then said two ways from one truth: a timed broadcast overlay cue and a personalized fan narrative.

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
| `ledger` | Deterministic match state: possession, pass quality, pressing, momentum windows, player thresholds; queryable evidence | `simulator` (event schema) |
| `agents` | Analyst, Commentator, Fact-Checker, Producer on Agent Framework + Foundry models; handoff contracts | `ledger` |
| `api` | FastAPI: start/stop match, SSE streams for cues and narratives, profile endpoint | `agents`, `ledger` |
| `voice` | Foundry Voice Live session per fan: speaks Producer narratives, server-side VAD + barge-in, routes spoken questions to an evidence-grounded answer path (Commentator + Fact-Checker over the ledger) | `agents`, `ledger` |
| `ui` | Two-panel web page: broadcast panel with overlay cues, fan panel with profile switch and push-to-talk / open-mic voice companion | `api`, `voice` |
| `deploy` | Container image, Azure Container Apps, Foundry tracing wired | `api`, `ui` |

Build order: `simulator` -> `ledger` -> `agents` -> `api` -> `voice` -> `ui` -> `deploy`. Each module is small enough to stay inside this one spec; split into `SPEC-<module>.md` only if one grows past a page.

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
    evidence: dict[str, float]    # ledger numbers the claim may cite

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
| Foundry SDK | `azure-ai-projects>=2.5.0` (use `project.agents`, not the old `project.beta.agents`), `openai>=3.0.0`, `azure-identity`; Python 3.11 |
| CLI | `az` 2.87 (installed) + `azd` with the `azure.ai.agents` extension, or the Foundry DevPack (`winget install Microsoft.FoundryDevPack`); both `az login` and `azd auth login` |
| Models | Deployed in the Foundry project (selecting in the catalog is not enough; each needs a named deployment). Commentator on a frontier model; Analyst, Fact-Checker, Producer on a small fast model. 429s handled with exponential backoff + jitter honoring `Retry-After` |
| Observability | Foundry tracing (OpenTelemetry GenAI conventions, GA) into an Application Insights resource linked to the project |
| Evaluation | Foundry built-in evaluators over recorded match runs: Groundedness (claims vs ledger evidence), Task Adherence, Intent Resolution. Cloud evaluations are long-running operations: submit, then poll |
| API | FastAPI + uvicorn, SSE via `sse-starlette` |
| Voice | Foundry Voice Live (GA July 2026): real-time duplex audio, server-side VAD, echo cancellation, noise suppression; browser audio over WebSocket through the API |
| State | SQLite (local) for ledger snapshots and run logs |
| Frontend | Vue 3 CDN, single `frontend/index.html`, no npm |
| Tests | pytest, pytest-asyncio |
| Container | Single Dockerfile, `docker compose` for local |
| Hosting | Agent workflow: Foundry Hosted Agent. API + UI: one small Azure Container App that invokes the hosted agent |

Exact package names and versions get pinned during the day-1 Foundry spike (task T2) and recorded here.

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
3. From candidate moment to overlay cue: median under 5 s, measured by Foundry tracing at 1x speed.
4. Switching the fan profile changes the next narrative's language, focus player/club and depth (demonstrable on video).
5. Full-time recap generated in English and Turkish.
6. `docker compose up --build` from a clean clone runs the full demo with only `.env` filled in.
7. Public GitHub repo, README with architecture diagram, under-2-minute YouTube demo, submitted on Innovation Studio by 2026-10-26.
9. Voice: the co-commentator speaks verified moments in English and Turkish; a spoken interruption stops playback in under 500 ms; a spoken "why?" question gets an evidence-grounded spoken answer in under ~3 s median; a question with no ledger evidence gets "I don't have data on that" instead of an invented answer.
8. A Foundry cloud evaluation over 3 recorded matches reports Groundedness for verified insights, with the Fact-Checker on vs off; the improvement is shown in the README and the demo (this is the Foundry-category proof point).

## Open Questions

- Azure subscription re-enable vs new subscription (blocking for T2 onward on the agents track).
- Which concrete models are available in Foundry for this subscription/region, and their cost.
- Hosted Agent is the default (managed runtime, tracing out of the box, strongest Foundry story; costs hosting per active session on top of tokens). T2 confirms it deploys from Windows with `azd` inside the time box; otherwise the in-container fallback applies.
- Voice Live: region availability, quota and cost for this subscription; whether it can drive the Commentator model directly or we pass text in/out. Verify in the T2 spike with a 30-second hello-world session.
- Stretch only: expose ledger queries as an MCP tool through a Foundry Toolbox (GA July 2026) so agents fetch evidence via MCP; hits the "MCP integration" judging bullet. Not in MVP.
- Package versions above come from a notebook summary of public Microsoft sources (2026-10-15); verify against learn.microsoft.com during T2 before pinning.
- Innovation Studio submission fields (invite expected by ~2026-10-16).
