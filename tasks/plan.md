# Implementation Plan: The Commentator's Brain

Follows [SPEC.md](../SPEC.md). Status: DRAFT, awaiting review together with the spec.

## Architecture

```
[simulator] --MatchEvent stream--> [ledger] --CandidateMoment--> [Analyst agent]
                                      ^                               |
                                      | evidence lookups              v
                                      |                        [Commentator agent] <--+
                                      |                               |  Insight       | rejected (max 1 retry)
                                      +------------------------ [Fact-Checker agent] --+
                                                                      |  Verdict (verified/rewritten)
                                                                      v
                                                               [Producer agent]
                                                                 |            |
                                                            OverlayCue   FanNarrative x profiles
                                                                 |            |
                                                            [FastAPI SSE: /api/stream/cues, /api/stream/fan]
                                                                 |
                                                            [Vue 3 page: broadcast panel | fan panel]

Models: deployed in a Microsoft Foundry project. Orchestration: Agent Framework graph workflow
(conditional reject edge), deployed as a Foundry Hosted Agent; API + UI on one Container App.
Tracing: Foundry (OpenTelemetry) spans per agent step via linked Application Insights, visible in the portal.
Evaluation: Foundry Groundedness / Task Adherence over recorded runs, Fact-Checker on vs off (T10b).
```

Design rules:
- Ledger is deterministic code; agents read evidence, never compute numbers.
- Analyst is a filter, not a calculator: it ranks candidate moments and drops the dull ones, so expensive agents only see what matters. This also controls cost and latency.
- Fact-Checker gets one retry loop back to the Commentator, then rejects. Rejections are logged and shown in a debug drawer (good demo material).
- Producer renders one verified insight for every active fan profile (demo uses 2-3 fixed profiles).

## Phases and checkpoints

### Phase A: Foundations (Oct 14-16)
- T1 Repo scaffold, tests placeholder, .gitignore, venv. (no Azure)
- T2 **Azure + Foundry spike** (blocking for Phase C): re-enable subscription, create Foundry project, deploy two models, run a 2-agent Agent Framework workflow with tracing visible in the portal. Pin package versions in SPEC.md. Decide hosted agents vs in-container agents.
- T3 Simulator v1: fictional league (4 clubs, squads), phase model, seeded event emitter, text printer.
- T4 Simulator dataset export (JSONL) + 3 sample matches committed.

**Checkpoint A:** 5 minutes of simulated play reads like football as text; Foundry 2-agent hello world traced.

### Phase B: Ledger (Oct 16-18)
- T5 Ledger core: possession, pass quality/difficulty, shot speed, distance and speed thresholds.
- T6 Candidate-moment detectors: pressing trap, momentum shift, pass streak, player milestone, lull ("nothing is happening and why").

**Checkpoint B:** a seeded match yields 30-60 candidate moments with evidence dicts; all unit-tested.

### Phase C: Agents (Oct 17-21)
- T7 Analyst + Commentator agents with structured output (Insight).
- T8 Fact-Checker with reject/rewrite and one retry loop; false-claim fixture test.
- T9 Producer: OverlayCue + FanNarrative (en, tr) per profile.
- T10 Workflow wiring end to end + tracing on every step; recap at full time.

**Checkpoint C:** headless seeded match at 30x produces >= 15 cues, zero from rejected verdicts, recap in en/tr. Latency measured.

### Phase D: Product surface (Oct 21-23)
- T11 FastAPI: start match, SSE streams, profiles, health.
- T12 Frontend: broadcast panel with timed overlay cues on a stylized pitch/event ticker; fan panel with profile switch; debug drawer with verdicts.

**Checkpoint D:** full demo locally in the browser, `docker compose up --build` works from clean clone.

### Phase E: Ship (Oct 23-26)
- T13 Container Apps deploy, secrets as env, public URL.
- T14 README + architecture diagram + judge testing instructions.
- T15 Demo script, record under-2-minute video, upload to YouTube.
- T16 Submit on Innovation Studio by Oct 26.

## Parallelism

Simulator/ledger work (T3-T6) does not need Azure, so it runs while the T2 spike is blocked on subscription fixes. Frontend (T12) can start against recorded SSE fixtures once T11's schema exists.

## Risks

| Risk | Mitigation |
| --- | --- |
| Azure subscription stays disabled | Fix on day 1; fallback: new pay-as-you-go subscription. Local track continues meanwhile. |
| Foundry/Agent Framework learning curve eats the week | T2 is time-boxed to 1.5 days; fallback is Agent Framework calling Foundry-deployed models from our container (still Foundry, tracing still possible). |
| Simulator output reads as noise | Phase model (build-up, pressing, transition, set piece) instead of uniform randomness; check by reading 5 minutes of text output. |
| Latency too high for "live" | Analyst filters aggressively; small models for Analyst/Fact-Checker/Producer; show the latency in tracing honestly. |
| Token cost | Seeded short matches in dev, `-m live` tests opt-in, budget alert on the subscription. |
| Scope creep from Not Doing list | Spec change required before building anything on it. |
