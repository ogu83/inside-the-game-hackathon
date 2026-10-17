"""Read-only ledger queries as an MCP server (SPEC design rule 4), streamable HTTP via the `mcp` package (1.x,
the range Agent Framework pins).

`LedgerTools` are plain functions over a `LedgerView`, so the offline Q&A agent calls them directly and the
MCP server wraps the same functions for the live Q&A agent. The view is bounded by the display clock: a
question is answered with what the fan has seen, never with events still in the broadcast delay.
"""

from typing import Any, Protocol

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from opentelemetry import trace

from app.ledger.metrics import in_window, player_stats, team_stats
from app.simulator.league import CLUBS, PLAYERS
from app.simulator.models import MatchEvent

NO_MATCH = {"error": "no match is being shown right now"}


class LedgerView(Protocol):
    def events(self) -> list[MatchEvent]:
        """Events displayed so far (behind the broadcast delay)."""
        ...

    def shown_moments(self) -> list[dict[str, Any]]:
        """Moments whose cue has aired, newest last: moment_id, minute, kind, team_id, claim, why_it_matters, evidence."""
        ...


tracer = trace.get_tracer(__name__)


class LedgerTools:
    def __init__(self, view: LedgerView) -> None:
        self.view = view

    def _events(self, last_minutes: float | None) -> list[MatchEvent]:
        events = self.view.events()
        if not events or last_minutes is None:
            return events
        return in_window(events, events[-1].t, int(last_minutes * 60))

    def score(self) -> dict[str, Any]:
        """Current score and match minute as displayed."""
        with tracer.start_as_current_span("mcp.tool score"):
            events = self.view.events()
            if not events:
                return dict(NO_MATCH)
            goals = {cid: float(sum(e.type == "goal" and e.team_id == cid for e in events)) for cid in CLUBS}
            return {"minute": float(events[-1].minute), **{f"{cid}_goals": g for cid, g in goals.items()},
                    "teams": {cid: CLUBS[cid].short for cid in CLUBS}}

    def team_stats(self, team_id: str, last_minutes: float | None = None) -> dict[str, Any]:
        """Possession share (pass attempts), pass accuracy, passes, shots, xG, goals, pressures and regains for a club
        (`kby` Kestrel Bay, `iva` Ironvale), over the whole match or the last N displayed minutes."""
        with tracer.start_as_current_span("mcp.tool team_stats"):
            if team_id not in CLUBS:
                return {"error": f"unknown team {team_id}; use one of {sorted(CLUBS)}"}
            events = self._events(last_minutes)
            if not events:
                return dict(NO_MATCH)
            return {"team": CLUBS[team_id].short, "window_minutes": float(last_minutes) if last_minutes else round(events[-1].t / 60, 1), **team_stats(events, team_id)}

    def player_stats(self, player_id: str, last_minutes: float | None = None) -> dict[str, Any]:
        """Passes, pass accuracy, forward progress, shots, goals, pressures, tackles, interceptions and a distance proxy
        for a player id such as `kby-07`, over the whole match or the last N displayed minutes."""
        with tracer.start_as_current_span("mcp.tool player_stats"):
            if player_id not in PLAYERS:
                return {"error": f"unknown player {player_id}"}
            events = self._events(last_minutes)
            if not events:
                return dict(NO_MATCH)
            player = PLAYERS[player_id]
            return {"player": player.name, "position": player.position, "team": CLUBS[player_id.split("-")[0]].short,
                    "window_minutes": float(last_minutes) if last_minutes else round(events[-1].t / 60, 1), **player_stats(events, player_id)}

    def recent_moments(self, limit: int = 3) -> dict[str, Any]:
        """The most recent verified moments that aired, newest first, each with its claim, why it matters and the
        ledger evidence behind it."""
        with tracer.start_as_current_span("mcp.tool recent_moments"):
            moments = self.view.shown_moments()
            return {"moments": list(reversed(moments))[: max(1, min(limit, 10))], "count": len(moments)}

    def squads(self) -> dict[str, Any]:
        """Club ids and names with their players (id, name, shirt number, position)."""
        with tracer.start_as_current_span("mcp.tool squads"):
            return {cid: {"name": c.name, "players": [{"id": p.id, "name": p.name, "number": p.number, "position": p.position} for p in c.players]} for cid, c in CLUBS.items()}


TOOL_NAMES = ("score", "team_stats", "player_stats", "recent_moments", "squads")


def build_mcp_server(tools: LedgerTools, name: str = "matchday-ledger", path: str = "/") -> FastMCP:
    """Stateless streamable HTTP server. Host checking is off: the live Q&A agent reaches it through the public
    hostname, and the data is read-only."""
    server = FastMCP(
        name,
        instructions="Read-only match ledger of the fictional Meridian League, bounded by what the broadcast has shown. Every number you quote must come from these tools.",
        stateless_http=True, json_response=True, streamable_http_path=path,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    for tool_name in TOOL_NAMES:
        server.add_tool(getattr(tools, tool_name), name=tool_name)
    return server
