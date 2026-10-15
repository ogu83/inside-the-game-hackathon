# Inside the Game: The Commentator's Brain

Hackathon: Microsoft + Premier League "Inside the Game: Developer Hackathon"
Rules: https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md
Registered: 2026-10-14 (GitHub sign-in). Submission deadline: 2026-10-27, 11:59 PM PT. Judging to 2026-11-10.
Entrant: solo. Target category: Best Use of Microsoft Foundry (secondary fit: Best Multi-Agent System; judges may reassign).

## Problem Statement

How might we turn a live stream of football match events into intelligence a commentator would actually say (what happened, why it matters, and how to say it to *this* viewer), fast enough to sit on screen during play, and verifiable enough that a broadcaster would trust it?

## Recommended Direction

Model the pipeline on how a colour commentator thinks, and make each step of that thinking a separate Microsoft Foundry agent with a distinct role, shared state, and a handoff contract:

1. **Analyst agent (notice).** Consumes the event stream (passes, shots, tackles, pressure events, possession changes) and maintains the match state ledger: rolling possession, pass-quality ratings, pressing intensity, momentum windows, player speed/distance thresholds. Deterministic code does the arithmetic; the agent decides which deltas are *notable* and emits "candidate moments".
2. **Commentator agent (judge).** Takes a candidate moment plus the ledger and explains *why it matters*: control vs. chaos, a pressing trap that just closed, a rhythm change after a substitution. Produces a structured insight (claim, evidence pointers into the ledger, confidence, suggested timing).
3. **Fact-Checker agent (check yourself).** Verifies every claim in the insight against the ledger before anything reaches a screen. Rejects or rewrites unsupported claims. This is the explainability story made concrete, and it is where Foundry tracing and evaluation earn their place in the demo.
4. **Producer agent (say it for this audience).** Renders the verified insight into two outputs from one truth: (a) a timed, machine-readable overlay cue (JSON with on-screen text, metric, duration, priority) for the broadcast track; (b) a personalized narrative for the fan track, shaped by viewer profile (favourite club, favourite player, analyst vs. casual depth, language).

Why this wins on the rules: it hits all five pipeline stages the rules demand (ingest, interpret, explain, render, personalize), it is explicitly multi-agent with distinct roles and handoffs, and the Fact-Checker gives judges a reason the Foundry platform (connected agents, tracing, evals) mattered rather than being a wrapper around one prompt. The one-pipeline-two-outputs shape answers the rules' own warning that "a solution that only generates metrics has no audience, and a solution that only personalizes has nothing to personalize."

Why it fits Oguz: the orchestration pattern is the same one already proven in ai-decision-room (parallel specialist agents synthesized by a chairman) and n8n-ai-agent-lab (ReAct agents with persistent shared state); the new learning is the Foundry/Agent Framework surface, which is the explicit personal goal for this entry.

## Key Assumptions to Validate

- [ ] **Foundry supports this multi-agent shape in Python within the time budget.** Test on day 1-2: stand up two connected agents in Foundry Agent Service via Microsoft Agent Framework with a tool call between them. If it fights back, fall back to Agent Framework orchestrating Azure OpenAI deployments created in Foundry (still a legitimate Foundry story, weaker category fit).
- [ ] **A home-grown synthetic match simulator is credible enough for a 2-minute demo.** Build it first (day 1-3). It must produce an event stream that a football-literate viewer finds plausible: possession phases, pass chains with varying difficulty, shots with xG-like quality, pressing events, substitutions. Validate by watching 5 minutes of generated play as text; if it reads like noise, it needs a phase model, not more randomness.
- [ ] **Data licensing is clean.** StatsBomb open data is non-commercial-only and Microsoft takes a commercial licence to the submission, so it is NOT used as data. At most it informs the event schema. Confirm the simulator uses a fictional league (fictional clubs and players) so no third-party trademarks appear in the repo or the demo video, which the rules prohibit.
- [ ] **Azure budget covers the build.** Confirm subscription and credits on day 1; estimate GPT-4o-class token spend for ~40 matches of development runs plus one Container App.
- [ ] **Latency is "responsive enough for live play".** Target: a candidate moment reaches the overlay cue in under ~5 seconds of simulated match time. Measure with Foundry tracing; if too slow, cut the Fact-Checker to a cheaper model rather than removing it.

## MVP Scope

In:
- Synthetic match simulator (Python): fictional league, event schema inspired by public football event data, emits events on a timer to simulate live ingestion. Also exports a dataset file (satisfies the "data innovation" bullet).
- Four Foundry agents as above, orchestrated with Microsoft Agent Framework in Python; shared match-state ledger (SQLite locally, Azure-hosted Postgres or Cosmos DB in deployment if time allows).
- Two outputs from one pipeline: overlay cue JSON stream, and personalized narrative text (English plus one more language, e.g. Turkish, generated by the Producer agent).
- Minimal web UI (Vue 3 or plain HTML/JS): a fake "match feed" panel with overlay cues appearing on time, and a fan panel with a profile switch (club, player, depth, language) that visibly changes the narrative.
- Full-time recap generated at the end of the match.
- Deployment: FastAPI backend on Azure Container Apps; agents in Foundry; tracing visible in the Foundry portal for the demo.
- Public GitHub repo with README, architecture diagram, run instructions; under-2-minute demo video on YouTube.

Out of MVP (see Not Doing): video/auto-eventing, real player data, voice, more than two languages, multi-match dashboards.

## Not Doing (and Why)

- **Auto-eventing from video.** The rules list it as optional; computer vision in 13 days solo is a demo-killer. The simulator provides events directly.
- **Real club or player data, or StatsBomb open data as the feed.** Trademark rule for the video and the non-commercial data licence versus Microsoft's commercial submission licence. Fictional league removes both risks and scores on data innovation.
- **A full second-screen fan app with accounts.** The personalization needs to be visible in a profile switch, not in a product. UX criterion is 20%; a crisp two-panel demo beats a half-finished app.
- ~~Voice output.~~ **Reversed 2026-10-15:** after scanning the field, the text "verified crew" concept is crowded while live conversational voice is rare, so voice (Foundry Voice Live, not ElevenLabs) became the fan-facing differentiator. See SPEC.md pivot note.
- **Five-plus agents (Localization, Highlights, etc.).** Every extra agent is a handoff contract to debug. Localization folds into the Producer; highlights fold into the Commentator's "notable moment" threshold.
- **Microsoft Fabric.** Mentioned as a hero technology, but the match ledger does not need a lakehouse. Mention it in the README as the obvious next step for multi-match analytics; do not build it.
- **League-wide multi-match mode.** Dilutes explainability depth, which is the differentiator.

## Open Questions

- Which Foundry primitives are actually available today for multi-agent in Python: Agent Service "connected agents", Agent Framework workflows, or both? Decides the orchestration layer on day 1.
- Model choice per agent: can the Analyst and Fact-Checker run on a small model (cost, latency) while the Commentator uses a frontier model? Needs a quick quality comparison.
- Does the Innovation Studio Platform (the official submission portal) require anything beyond repo URL, video URL, and pitch text? Registration confirmation email arrived 2026-10-14; a separate Microsoft email with Innovation Studio profile-setup instructions is due within 48 hours (by ~2026-10-16). Set up the profile the day it lands and check the "Projects" page fields early, so the submission form is not a surprise on Oct 26.
- Judges "may test the project": is a public demo URL on Container Apps enough, or should a one-command local run (`docker compose up`) be the primary testing path? Plan for both, with the local path as the guaranteed one.
- Is there a Microsoft Reactor session on Foundry agents before 2026-10-20 worth attending for a fast start?

## Working Timeline (idea level, not an implementation plan)

- Days 1-3 (Oct 14-16): Azure/Foundry access check, Foundry two-agent spike, simulator v1.
- Days 4-8 (Oct 17-21): four agents and shared ledger running locally end to end; overlay cue and narrative outputs; profile switch.
- Days 9-11 (Oct 22-24): deploy to Container Apps and Foundry, tracing on, UI polish, recap.
- Days 12-13 (Oct 25-26): README, architecture diagram, demo video, submit with a one-day buffer before the Oct 27 deadline.
