# ADR 0004: Broadcast Delay for Agent Processing and Verification

## Status
Accepted

## Context
A live sports companion requires deep contextual analysis: identifying tactical patterns, consulting the statistical ledger, formulating commentary insights, translating into multiple languages and personas, and passing strict two-layer Fact-Checker gates with potential retry loops.

Executing this multi-agent workflow (Director, Commentator, Fact-Checker, Producer) requires between 4 and 14 seconds of round-trip model inference and verification latency. If the broadcast stream were displayed synchronously without delay, commentary cues would consistently arrive after the play had moved on, creating a disjointed viewer experience.

## Decision
1. **20-Second Artificial Broadcast Delay:**
   - The application introduces a deliberate delay (`delay_s`, default 20 seconds, configurable via `BROADCAST_DELAY_S`) between event ingestion and viewer display (`app/api/clock.py`, `app/api/streams.py`).
   - The ingest loop operates ahead of time, processing raw match events into the ledger as they occur.
   - The display loop streams events and cues to the frontend on the delayed playback clock (`playback_t = current_wall_time - delay_s`).

2. **On-Time Gate or Drop Policy:**
   - In live mode (1x speed), moments are processed the instant they close in the ingest loop.
   - The 20-second buffer provides sufficient wall-clock time for the multi-agent graph:
     - Analyst/Director decides angle and priority (0.5 to 1.5 s).
     - Commentator drafts the core insight (1.5 to 3.5 s).
     - Fact-Checker verifies numbers and attribution; if rejected, allows one retry (1.0 to 4.0 s).
     - Producer renders tailored fan narratives across active profiles (1.0 to 3.0 s).
   - If a cue is ready before its closing event reaches display time, it airs precisely in sync with the action.
   - If processing exceeds the delay window, the cue is strictly dropped (`cues_dropped_late`) and recorded in metrics. Late cues are never displayed out of sequence.

3. **Temporal Isolation for Q&A:**
   - Tools exposed via MCP (`app/ledger/mcp_server.py`) operate over a `LedgerView` filtered strictly by `playback_t`.
   - The Q&A agent cannot observe events or statistics residing in the 20-second future ingest buffer, eliminating spoilers.

4. **Precompute Mode for Accelerated Demos:**
   - When running at accelerated speeds (e.g., 100x or 2000x for testing or judging sweeps), all moments are processed upfront, and the broadcast clock governs playback pacing without dropped cues.

## Consequences
- **Positive:**
  - High factual quality: models have sufficient time to check facts, catch mistakes, and rewrite without degrading playback synchronicity.
  - Predictable presentation: cues appear simultaneously with or immediately following the relevant highlight.
  - Spoiling prevention: fans cannot query the score or recent moments before they appear on screen.
- **Negative / Trade-offs:**
  - True live delay of 20 seconds relative to the match engine.
  - Requires maintaining two concurrent time horizons (ingest time and playback time) across clock adapters and ledger views.
