"""Per-visitor match session registry and cookie management (SPEC criterion 11, ADR 0001)."""

import asyncio
import contextvars
import logging
import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, Response, WebSocket

from app.api.streams import MatchRun

log = logging.getLogger(__name__)

SESSION_COOKIE = "mc_session"
DEFAULT_MAX_CONCURRENT = 4
DEFAULT_IDLE_TTL_S = 600.0

current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_session_id", default=None)


@dataclass
class SessionEntry:
    session_id: str
    run: MatchRun
    last_active: float
    created_at: float


class MatchRegistry:
    """In-memory registry of active match runs, keyed by visitor session ID."""

    def __init__(self, max_concurrent: int | None = None, idle_ttl_s: float | None = None) -> None:
        self.max_concurrent = (
            int(os.environ.get("MAX_CONCURRENT_RUNS", str(DEFAULT_MAX_CONCURRENT)))
            if max_concurrent is None
            else max_concurrent
        )
        self.idle_ttl_s = (
            float(os.environ.get("RUN_IDLE_TTL_S", str(DEFAULT_IDLE_TTL_S)))
            if idle_ttl_s is None
            else idle_ttl_s
        )
        self._entries: dict[str, SessionEntry] = {}
        self._run_to_session: dict[str, str] = {}
        self._background_tasks: set[asyncio.Task] = set()

    def _schedule_stop(self, run: MatchRun) -> None:
        task = asyncio.create_task(self._safe_stop(run))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def active_count(self) -> int:
        self.cleanup()
        now = time.time()
        return sum(
            1
            for e in self._entries.values()
            if not e.run.finished.is_set() and (now - e.last_active) <= self.idle_ttl_s
        )

    def cleanup(self) -> list[str]:
        """Stop and remove idle runs."""
        now = time.time()
        to_remove = []
        for sid, entry in list(self._entries.items()):
            is_idle = (now - entry.last_active) > self.idle_ttl_s
            if is_idle:
                to_remove.append(sid)
        for sid in to_remove:
            entry = self._entries.pop(sid, None)
            if entry:
                self._run_to_session.pop(entry.run.match_id, None)
                self._schedule_stop(entry.run)
        return to_remove

    @staticmethod
    async def _safe_stop(run: MatchRun) -> None:
        try:
            await run.stop()
        except Exception:
            log.warning("error stopping run %s during session cleanup", run.match_id, exc_info=True)

    def get(self, session_id: str | None) -> MatchRun | None:
        if not session_id:
            return None
        self.cleanup()
        entry = self._entries.get(session_id)
        if entry is None:
            return None
        if (time.time() - entry.last_active) > self.idle_ttl_s:
            self._entries.pop(session_id, None)
            self._run_to_session.pop(entry.run.match_id, None)
            self._schedule_stop(entry.run)
            return None
        entry.last_active = time.time()
        return entry.run

    def get_by_run_id(self, run_id: str | None) -> MatchRun | None:
        if not run_id:
            return None
        sid = self._run_to_session.get(run_id)
        if sid:
            return self.get(sid)
        for entry in list(self._entries.values()):
            if entry.run.match_id == run_id:
                return self.get(entry.session_id)
        return None

    def latest_run(self) -> MatchRun | None:
        self.cleanup()
        if not self._entries:
            return None
        newest = max(self._entries.values(), key=lambda e: e.last_active)
        return newest.run

    async def start_run(self, session_id: str, run_factory: Callable[[], MatchRun]) -> MatchRun:
        self.cleanup()
        old = self._entries.pop(session_id, None)
        if old:
            self._run_to_session.pop(old.run.match_id, None)
            await self._safe_stop(old.run)
        elif self.active_count() >= self.max_concurrent:
            raise HTTPException(status_code=503, detail="The demo is busy, try again in a minute.")

        run = run_factory()
        now = time.time()
        entry = SessionEntry(session_id=session_id, run=run, last_active=now, created_at=now)
        self._entries[session_id] = entry
        self._run_to_session[run.match_id] = session_id
        await run.start()
        return run

    async def stop_run(self, session_id: str) -> MatchRun | None:
        entry = self._entries.pop(session_id, None)
        if entry:
            self._run_to_session.pop(entry.run.match_id, None)
            await entry.run.stop()
            return entry.run
        return None

    async def stop_all(self) -> None:
        entries = list(self._entries.values())
        self._entries.clear()
        self._run_to_session.clear()
        for e in entries:
            await self._safe_stop(e.run)
        if self._background_tasks:
            await asyncio.gather(*list(self._background_tasks), return_exceptions=True)


def get_session_id(request: Request) -> str:
    """Read session ID from request state, cookie, or query param, generating one if missing."""
    if hasattr(request.state, "session_id") and request.state.session_id:
        return request.state.session_id
    sid = current_session_id.get()
    if sid:
        request.state.session_id = sid
        return sid
    cookie_val = request.cookies.get(SESSION_COOKIE)
    if cookie_val:
        request.state.session_id = cookie_val
        request.state.session_is_new = False
        return cookie_val
    query_val = request.query_params.get("session")
    if query_val:
        request.state.session_id = query_val
        request.state.session_is_new = False
        return query_val
    sid = secrets.token_hex(16)
    request.state.session_id = sid
    request.state.session_is_new = True
    return sid


def get_ws_session_id(ws: WebSocket) -> str:
    """Read session ID for a WebSocket connection from cookie or query param."""
    return ws.cookies.get(SESSION_COOKIE) or ws.query_params.get("session") or secrets.token_hex(16)


def attach_session_cookie(response: Response, session_id: str, secure: bool = False) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


def qa_pipeline_for_run(run: MatchRun, app: Any) -> Any:
    """Build a QaPipeline bounded to this specific run's ledger tools and MCP endpoint."""
    override = getattr(app.state, "qa", None)
    if override and hasattr(override, "agent") and type(override.agent).__name__ != "RuleQaAgent":
        from app.voice.qa import QaPipeline
        return QaPipeline(override.agent, override.fact_checker, run.tools())
    if os.environ.get("AGENT_MODE", "template").lower() == "foundry":
        from app.agents.fact_checker import FactChecker, FoundryWordingJudge
        from app.agents.prompts import FACT_CHECKER_INSTRUCTIONS
        from app.agents.run_match import live_agent, live_qa_agent
        from app.voice.qa import QaPipeline

        base = os.environ.get("PUBLIC_BASE_URL", f"http://localhost:{os.environ.get('APP_PORT', '8010')}")
        return QaPipeline(
            live_qa_agent(f"{base}/mcp/{run.match_id}"),
            FactChecker(FoundryWordingJudge(live_agent("SMALL_MODEL_DEPLOYMENT", "fact_checker", FACT_CHECKER_INSTRUCTIONS))),
            run.tools(),
        )
    from app.agents.fact_checker import FactChecker
    from app.agents.fakes import AlwaysVerifies
    from app.voice.qa import QaPipeline, RuleQaAgent

    return QaPipeline(RuleQaAgent(), FactChecker(AlwaysVerifies()), run.tools())

