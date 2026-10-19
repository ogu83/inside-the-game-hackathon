# ADR 0001: Per-Visitor Match Sessions

## Status
Accepted

## Context
In early development milestones, the application held a single global match run stored in `app.state.run`. Every HTTP endpoint (`/api/match/*`, `/api/stream/*`, `/api/fan/*`, `/api/qa`, `/api/match/audits`), the Server-Sent Events (SSE) channels, the FastMCP server (`/mcp`), and the voice WebSocket (`/api/voice`) routed to this single instance.

When deployed to a publicly accessible Azure Container App, multiple simultaneous visitors or judges would collide: starting a new match would stop or replace another visitor's match in progress, Q&A queries would cross-talk between different games, and audits would mix timelines.

To support multi-tenant evaluation and demo visitors without requiring heavy infrastructure (such as distributed databases or Redis clusters), each visitor must run their own isolated match session in-memory while enforcing concurrency limits and automated idle cleanup.

## Decision
1. **Session Identification via HttpOnly Cookie:**
   - A lightweight ASGI middleware (`SessionMiddleware`) assigns and inspects an `mc_session` cookie (`HttpOnly`, `SameSite=Lax`, `Secure` when served over HTTPS).
   - If the cookie is absent, a secure random token is generated and attached to response headers.
   - For WebSocket connections, the cookie is read from request headers, with fallback to an optional query parameter `session_id`.

2. **In-Memory MatchRegistry:**
   - An in-memory registry (`MatchRegistry`) maintains active match instances keyed by session ID.
   - Concurrency is capped via `MAX_CONCURRENT_RUNS` (default 4). When the cap is reached, `POST /api/match/start` responds with HTTP 503 (`"The demo is busy, try again in a minute."`).
   - Idle sessions are cleaned up automatically after `RUN_IDLE_TTL_S` (default 600 seconds of inactivity).
   - When a visitor starts a new match on an existing session, their previous run is stopped and replaced immediately.

3. **Context-Aware MCP and API Routing:**
   - The FastMCP server mounts at `/mcp`. Visitors address MCP tools either with `/mcp/{run_id}` or through the `mc_session` cookie.
   - ContextVar `current_session_id` propagates the caller session to the MCP tools ledger view.
   - Voice WebSocket and Q&A pipelines dynamically bind to the visitor match run and ledger tools.

4. **Backward Compatibility:**
   - When running unit tests or offline scripts without session cookies, endpoints fall back gracefully to `app.state.run` or the latest active run, preserving compatibility across all test suites.

## Consequences
- **Positive:**
  - Complete isolation between visitors: match events, timeline drawer, Q&A answers, speech audio, and audits never cross.
  - Predictable memory and CPU footprint on Azure Container Apps (0.5 vCPU / 1 GiB) via concurrency limit (4 runs max) and idle reaper.
  - Zero external state dependencies (no Redis or external DB required).
- **Negative / Trade-offs:**
  - Single-replica limitation: in-memory sessions require a single container replica (`minReplicas=1, maxReplicas=1`) or session affinity if scaled. For the hackathon demo, a single replica provides ample capacity within the 4 concurrent run ceiling.
  - Container restarts discard active matches, requiring visitors to restart their match.
