# Implementation Plan: Matchday Companion (The Commentator's Brain)

Follows [SPEC.md](../SPEC.md). Status: APPROVED 2026-10-15 (revised after T2 review: walking skeleton first, demo-script-driven scope).

Pitch: **a live co-commentator you can interrupt, and that can't lie: every number it says is checked against the match data before it is spoken.**

## Architecture

```
[simulator] --MatchEvent stream--> [ledger] --CandidateMoment batch / window--> [Analyst: director]
   |                                 |  ^                                              |  ranked, paced
   |                                 |  | MCP tools (read-only)                        v
   |                                 |  +------------------- [Voice Q&A agent]   [Commentator] <------+
   |                                 |                             ^                 |  Insight       | rejected
   |                                 v                             |                 v                | (1 retry)
   |                       evidence values ----------------> [Fact-Checker: L1 code numbers, L2 LLM wording]
   |                                                               |  Verdict (verified / rewritten)
   |                                                               v
   |                                                         [Producer] x profiles (parallel)
   |                                                           |               |
   |                                                      OverlayCue      FanNarrative
   v                                                           |               |
[playback clock = event clock - BROADCAST_DELAY_S] --> [FastAPI SSE] --> [Vue page: SVG pitch + cues | fan panel]
                                                                               |
                                                                  [Voice Live: speaks narratives, barge-in,
                                                                   "why?" -> Voice Q&A agent]

Models: Foundry deployments (gpt-5.4-mini now, frontier Commentator after quota). Orchestration:
Agent Framework graph workflow, same module runs in-process (local, video) and as a Foundry Hosted Agent.
Tracing: App Insights linked to the project. Evaluation: Groundedness on/off + planted-error count (T10b).
```

Design rules: see SPEC.md "Pipeline design rules" (broadcast delay, two-layer Fact-Checker, Analyst as director, ledger over MCP, parallel Producer).

## Demo-driven scope

The 2-minute video is what judges experience. Every task is ranked by whether it is on screen. The demo script (docs/demo-script.md, task D1) is the source for this table; update both together.

| Must (on screen) | Should | Cut / README only |
| --- | --- | --- |
| SVG pitch with moving ball and overlay cues timed to the delayed clock | Full-time recap (en/tr) | SQLite ledger snapshots (in-memory is enough) |
| Fan profile switch: language en to tr, club/player focus | Casual vs analyst depth | 18-player squads (11 + 3 subs per club) |
| Voice co-commentator speaking verified lines | Azure Container App public URL (docker compose is the guaranteed judge path) | Lull detector |
| Barge-in + spoken "why?" answered from ledger via MCP | Momentum shift detector | Foundry Toolbox registration for MCP |
| Fact-Checker rejecting a planted claim (debug drawer) | Analyst "stay quiet" pacing visible in drawer | Microsoft Fabric (README "next step" only) |
| Eval headline: Groundedness on vs off + planted errors caught | Hosted agent invocation shown in portal | More than 4 clubs |
| Foundry portal trace of one moment | | |

## Phases and checkpoints

### Phase A: Foundations (done 2026-10-15)
- T1 Repo scaffold. T2 Azure + Foundry spike (local + hosted workflow, tracing, Voice Live).

### Phase S: Walking skeleton (Oct 15-19)
Goal: one command shows a moving match whose verified cues are displayed and spoken. Each slice is thin, tested and committed; nothing is polished.
- D1 Demo script draft (scene by scene, 2 minutes), drives the scope table above.
- S1 Thin simulator: 2 clubs, build-up + transition phases, seeded, events validate as `MatchEvent`.
- S2 Thin ledger: possession % and pass streak, one detector (`pass_streak`) emitting `CandidateMoment`.
- S3 Thin agents: Commentator + two-layer Fact-Checker (layer 1 code, layer 2 LLM) on real moments, in-process, reusing the T2 workflow shape.
- S4 Thin API + page: SSE cue stream, broadcast delay clock, bare page with an event ticker and cues.
- S5 Thin voice: browser plays Voice Live speech for verified lines (text in, audio out), no barge-in yet.

**Checkpoint S:** `python -m uvicorn app.api.main:app --port 8010` then open the page: a seeded match plays, verified cues appear on time and are spoken. Submittable in an emergency.

### Phase B: Deepen (Oct 19-23)
- T3 Simulator v1 full (4 clubs, phase model incl. pressing + set pieces, substitutions). T4 dataset export.
- T5 Ledger metrics. T6 Detectors (pressing_trap, momentum_shift, pass_streak, player_milestone).
- T7 Analyst as director + Commentator. T8 Fact-Checker full (retry loop, planted-error harness). T9 Producer per profile (parallel).
- T10 Workflow + tracing + recap; same workflow deployed as hosted agent. T10b Evaluation (early: as soon as T10 runs).
- T11 API full. T12 Frontend: SVG pitch, fan panel, verdict drawer. T12b Voice: barge-in, "why?" via ledger MCP server.

**Checkpoint B:** Must column of the scope table works locally; eval numbers exist.

### Phase E: Ship (Oct 23-26)
- T13 docker compose from clean clone (Must); Container App (Should). T14 README + diagram. T15 Record video from a local in-process run with the hosted agent warmed up. T16 Pre-publish pass and submit by Oct 26.

## Parallelism

Simulator/ledger work has no Azure dependency. Frontend (T12) can start against recorded SSE fixtures once S4's stream shape exists. The eval (T10b) runs as a background long-running job while UI work continues.

## Risks

| Risk | Mitigation |
| --- | --- |
| Scope too large for one person in 11 days | Must/Should/Cut table; walking skeleton means a submittable demo exists from Oct 19 |
| Latency too high for "live" | Broadcast delay; Analyst once per window; code-layer rejects skip the LLM; parallel Producer |
| Frontier model quota never arrives | Everything runs on gpt-5.4-mini; deployment names come from env |
| Hosted agent cold start (~29 s) during recording | Record from the in-process run; warm the hosted agent before showing it |
| Simulator output reads as noise | Phase model, not uniform randomness; read 5 minutes of text output at S1 and T3 |
| Voice in the browser (mic permissions, echo) | Push-to-talk first, open mic second; Voice Live server-side echo cancellation |
| Token / Azure cost | $50/month budget alert; seeded short matches in dev; `-m live` tests opt-in |
| Scope creep from Not Doing list | Spec change required before building anything on it |
