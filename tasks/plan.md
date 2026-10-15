# Implementation Plan: Matchday Companion (The Commentator's Brain)

Follows [SPEC.md](../SPEC.md). Status: APPROVED 2026-10-15 (revised after T2 review: walking skeleton first, demo-script-driven scope; revised again 2026-10-15 after the review in docs/reviews/2026-10-15-fable-review.md: director per moment, 20 s delay, public URL as Must with offline fallback, scope cuts).

Pitch: **a live co-commentator you can interrupt, and that can't lie: every number it says is checked against the match data before it is spoken.**

## Architecture

```
[simulator] --MatchEvent stream--> [ledger] --CandidateMoment + pacing state--> [Analyst: director, per moment]
   |                                 |  ^                                              |  DirectorDecision (say / skip)
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
[playback clock = event clock - BROADCAST_DELAY_S (20 s); live at 1x, precomputed above] --> [FastAPI SSE] --> [Vue page: SVG pitch + cues | fan panel]
                                                                               |
                                                                  [Voice Live: speaks narratives, barge-in,
                                                                   "why?" -> Voice Q&A agent]

Models: Foundry deployments (gpt-5.4-mini now, frontier Commentator after quota); AGENT_MODE=template runs the
same pipeline offline (docker compose, fallback). Orchestration: Agent Framework graph workflow, same module runs
in-process (local, video, Container App) and as a Foundry Hosted Agent (Should).
Tracing: App Insights linked to the project. Evaluation: Groundedness on/off + planted-error count (T10b).
```

Design rules: see SPEC.md "Pipeline design rules" (broadcast delay with live and precomputed modes, two-layer Fact-Checker, director per moment, ledger over MCP, parallel Producer, verbatim voice, offline mode and judges' budget).

## Demo-driven scope

The 2-minute video is what judges experience. Every task is ranked by whether it is on screen. The demo script (docs/demo-script.md, task D1) is the source for this table; update both together.

| Must (on screen) | Should | Cut / README only |
| --- | --- | --- |
| SVG pitch with moving ball and overlay cues timed to the delayed clock | Full-time recap (en/tr) | SQLite ledger snapshots (in-memory is enough) |
| Fan profile switch: language en to tr, club/player focus; re-renders the latest moment at once | Casual vs analyst depth | 18-player squads (11 + 3 subs per club) |
| Voice co-commentator speaking verified lines | Player dots on the pitch (ball dot is Must) | Lull detector, momentum shift detector |
| Barge-in (push-to-talk) + spoken "why?" answered from ledger via MCP | Hosted agent invocation shown in portal (timeboxed to half a day) | Foundry Toolbox registration for MCP |
| Fact-Checker rejecting a planted claim (debug drawer with the agent timeline per moment) | Analyst "stay quiet" pacing visible in drawer | Microsoft Fabric (README "next step" only) |
| Eval headline: Groundedness on vs off + planted errors caught (started from the S3 run log) | Open mic (push-to-talk is Must) | More than 2 clubs, set pieces |
| Foundry portal trace of one moment | | Third detector (pass_streak + pressing_trap are enough) |
| Public Azure Container App URL with managed identity, run limit, offline fallback; docker compose offline mode | | |
| One impact sentence in the video and README | | |

## Phases and checkpoints

### Phase A: Foundations (done 2026-10-15)
- T1 Repo scaffold. T2 Azure + Foundry spike (local + hosted workflow, tracing, Voice Live).

### Phase S: Walking skeleton (Oct 15-19)
Goal: one command shows a moving match whose verified cues are displayed and spoken. Each slice is thin, tested and committed; nothing is polished.
- D1 Demo script draft (scene by scene, 2 minutes), drives the scope table above.
- S1 Thin simulator: 2 clubs, build-up + transition phases, seeded, events validate as `MatchEvent`.
- S2 Thin ledger: possession % and pass streak, one detector (`pass_streak`) emitting `CandidateMoment`.
- S3 Thin agents: Commentator + two-layer Fact-Checker (layer 1 code, layer 2 LLM) on real moments, in-process, reusing the T2 workflow shape. Done 2026-10-15, plus offline template agents and the run log.
- S4 Thin API + page: SSE cue stream, broadcast delay clock (live and precomputed modes), bare page with an event ticker and cues. Done 2026-10-15.
- S5 Thin voice: browser plays Voice Live speech for verified lines (text in, audio out), no barge-in yet.

**Checkpoint S:** `python -m uvicorn app.api.main:app --port 8010` then open the page: a seeded match plays, verified cues appear on time and are spoken. Submittable in an emergency.

### Phase B: Deepen (Oct 19-23)
- T3 Simulator v1 (2 clubs, per-club pressing trait, substitutions, goals; no set pieces). T4 dataset export.
- T5 Ledger metrics (incl. player stats for the MCP tools). T6 Detectors: pressing_trap added to pass_streak (two detectors total).
- T7 Analyst as director per moment (`DirectorDecision`, pacing state from code) + Commentator. T8 Fact-Checker full (retry loop, planted-error harness). T9 Producer per profile (parallel; profile switch re-renders the latest moment).
- T10 Workflow + tracing + recap; hosted agent deployment timeboxed to half a day. T10b Evaluation starts from the S3 run log, in parallel with T7.
- T11 API full (incl. per-visitor live-run limit and offline fallback). T12 Frontend: SVG pitch (ball dot), fan panel, verdict drawer with agent timeline. T12b Voice: MCP server + text Q&A first (cloud session), then push-to-talk barge-in and speech locally.

**Checkpoint B:** Must column of the scope table works locally; eval numbers exist.

### Phase E: Ship (Oct 23-26)
- T13 docker compose offline mode from a clean clone (Must) and Container App public URL with managed identity, run limit and offline fallback, kept up through 2026-11-10 (Must). T14 README + diagram + impact paragraph + judge section. T15 Record video from a local in-process run at 3x to 4x with English captions, hosted agent warmed up. T16 Pre-publish pass and submit by Oct 26.

## Parallelism

Simulator/ledger work has no Azure dependency. Frontend (T12) can start against recorded SSE fixtures once S4's stream shape exists. The eval (T10b) runs as a background long-running job while UI work continues.

## Risks

| Risk | Mitigation |
| --- | --- |
| Scope too large for one person in 11 days | Must/Should/Cut table; walking skeleton means a submittable demo exists from Oct 19; 2 clubs, 2 detectors, hosted agent timeboxed |
| Latency too high for "live" | 20 s broadcast delay; director per moment (no batch wait); code-layer rejects skip the LLM; parallel Producer; precomputed mode above 1x |
| Judges cannot run keyless auth | Public Container App with managed identity is the judge path; docker compose runs offline mode without Azure |
| Judges' clicks spend Foundry tokens | Per-visitor live-run limit on the public app, offline fallback after the limit and on Foundry errors; $50/month budget alert |
| Frontier model quota never arrives | Everything runs on gpt-5.4-mini; deployment names come from env |
| Hosted agent cold start (~29 s) during recording | Record from the in-process run; warm the hosted agent before showing it |
| Simulator output reads as noise | Phase model, not uniform randomness; read 5 minutes of text output at S1 and T3 |
| Voice in the browser (mic permissions, echo) | Push-to-talk first, open mic second; Voice Live server-side echo cancellation |
| Token / Azure cost | $50/month budget alert; seeded short matches in dev; `-m live` tests opt-in |
| Scope creep from Not Doing list | Spec change required before building anything on it |
