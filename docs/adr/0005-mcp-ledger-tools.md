# ADR 0005: Ledger Tools over Model Context Protocol for Fan Q&A

## Status
Accepted

## Context
Interactive fan Q&A is a core capability of Matchday Companion (SPEC design rules 4 and 6). Fans can press Push-to-Talk or submit text questions about the match in progress (for example, "What is the score?", "How is my player doing?", "Why was that moment important?").

Allowing an LLM to answer fan questions purely from unstructured prompts or system instructions invites statistical hallucination, outdated scores, and speculation about events that have not occurred. The Q&A system requires strict grounding in the deterministic match ledger.

## Decision
1. **Tool Definition via Model Context Protocol (MCP):**
   - The match ledger exposes four deterministic tools implemented via FastMCP (`app/ledger/mcp_server.py`) and mounted over streamable HTTP at `/mcp`:
     - `score`: returns home and away goals, match minute, and current leader.
     - `team_stats(team_id, last_minutes)`: returns possession percentages, shots, pass counts, and pressing index.
     - `player_stats(player_id)`: returns individual player metrics including passes completed, touches, and shots.
     - `recent_moments(n)`: returns the last N candidate moments that have been displayed on air, including their tactical evidence.

2. **Session-Isolated LedgerView:**
   - Tools do not query global state directly. Instead, they interact with an adapter (`LedgerView`) resolved dynamically from the visitor's `mc_session` cookie or URL path (`/mcp/{session_id}`).
   - The ledger view restricts data visibility to events with timestamp `t <= playback_t`, ensuring answers cannot reveal upcoming events currently buffered in the 20-second broadcast delay.

3. **Two-Stage Q&A Pipeline:**
   - **Tool Execution:** The Q&A agent (`app/voice/qa.py`) executes MCP tool calls to collect relevant match facts into an evidence dictionary.
   - **Fact-Checker Verification:** Draft answers are passed through the Fact-Checker (`FactChecker.check`). Every number mentioned in the answer must match a value returned by the tool calls.
   - If verification fails, the agent receives feedback and retries up to twice. If it still fails, the response falls back to: "I don't have data on that" (English) or "Bu konuda elimde veri yok" (Turkish).

4. **Telemetry and Tracing:**
   - Each MCP tool invocation generates discrete OpenTelemetry child spans under `qa.answer`, capturing tool inputs, outputs, and execution duration for visibility in Application Insights and the Foundry portal.

## Consequences
- **Positive:**
  - Absolute factual grounding: the Q&A agent cannot invent match metrics or cite numbers not present in tool responses.
  - Interoperability: standard MCP protocol enables seamless integration with both in-process agents and external hosts.
  - Observability: detailed tracing of tool calls aids debugging and latency attribution.
- **Negative / Trade-offs:**
  - Answering latency includes MCP tool serialization and execution (typically 10 to 50 ms for in-process ASGI calls).
  - Queries falling outside the four defined tool domains (e.g., historical league standings or weather) receive polite "no data" responses by design.
