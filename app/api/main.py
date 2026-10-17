"""FastAPI app: start a match, stream delayed events and verified cues over SSE."""

import asyncio
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agents.fact_checker import FactChecker
from app.agents.fakes import AlwaysVerifies
from app.agents.models import FanProfile, QaTiming
from app.api.limits import RunLimiter, live_runs_per_day
from app.api.sessions import (
    MatchRegistry,
    SESSION_COOKIE,
    attach_session_cookie,
    current_session_id,
    get_session_id,
    qa_pipeline_for_run,
)
from app.ledger.mcp_server import LedgerTools, build_mcp_server
from app.observability import flush_tracing, init_observability
from app.voice.qa import QaPipeline, RuleQaAgent, new_question
from app.agents.recap import TemplateRecapWriter, recap_writer_from_env
from app.api.streams import MatchRun, producer_from_env, template_producer, template_workflow, workflow_factory_from_env
from app.api.voice_ws import router as voice_router
from app.simulator.league import CLUBS
from app.voice.session import speaker_factory_from_env

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


class StartRequest(BaseModel):
    seed: int = 7
    speed: float = Field(default=1.0, gt=0, le=2000)
    delay_s: float | None = Field(default=None, ge=0)
    minutes: int = Field(default=90, ge=2, le=120)
    precompute: bool | None = None
    home: str = "kby"
    away: str = "iva"
    plant: int = Field(default=0, ge=0, le=3)


class _AppView:
    """LedgerView over the requesting visitor's match run (or fallback)."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def _get_run(self) -> MatchRun | None:
        sid = current_session_id.get()
        if sid and hasattr(self.app.state, "registry"):
            run = self.app.state.registry.get(sid) or self.app.state.registry.get_by_run_id(sid)
            if run is not None:
                return run
        if getattr(self.app.state, "run", None) is not None:
            return self.app.state.run
        if hasattr(self.app.state, "registry"):
            return self.app.state.registry.latest_run()
        return None

    def events(self):
        run = self._get_run()
        return run.displayed_events() if run else []

    def shown_moments(self):
        run = self._get_run()
        return run.shown_moments() if run else []


def qa_pipeline_from_env(app: FastAPI) -> QaPipeline:
    tools = LedgerTools(_AppView(app))
    if os.environ.get("AGENT_MODE", "template").lower() == "foundry":
        from app.agents.fact_checker import FoundryWordingJudge
        from app.agents.prompts import FACT_CHECKER_INSTRUCTIONS
        from app.agents.run_match import live_agent, live_qa_agent

        base = os.environ.get("PUBLIC_BASE_URL", f"http://localhost:{os.environ.get('APP_PORT', '8010')}")
        return QaPipeline(live_qa_agent(f"{base}/mcp"), FactChecker(FoundryWordingJudge(live_agent("SMALL_MODEL_DEPLOYMENT", "fact_checker", FACT_CHECKER_INSTRUCTIONS))), tools)
    return QaPipeline(RuleQaAgent(), FactChecker(AlwaysVerifies()), tools)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_observability()
    app.state.registry = MatchRegistry()
    app.state.run = None
    if not getattr(app.state, "qa", None):
        app.state.qa = qa_pipeline_from_env(app)
    app.state.workflow_factory = getattr(app.state, "workflow_factory", None) or workflow_factory_from_env()
    if not hasattr(app.state, "producer") or app.state.producer is None:
        app.state.producer = producer_from_env()
    if not hasattr(app.state, "recap_writer") or app.state.recap_writer is None:
        app.state.recap_writer = recap_writer_from_env()
    if not hasattr(app.state, "limiter") or app.state.limiter is None:
        app.state.limiter = RunLimiter(live_runs_per_day())
    if not hasattr(app.state, "speaker_factory"):
        app.state.speaker_factory = speaker_factory_from_env()
    # The MCP transport is built per lifespan (a session manager runs once) and one task owns its cancel scope.
    server = build_mcp_server(LedgerTools(_AppView(app)))
    app.state.mcp_asgi = server.streamable_http_app()
    stop, started = asyncio.Event(), asyncio.Event()

    async def run_mcp_sessions() -> None:
        async with server.session_manager.run():
            started.set()
            await stop.wait()

    mcp_task = asyncio.create_task(run_mcp_sessions())
    waiter = asyncio.create_task(started.wait())
    await asyncio.wait({mcp_task, waiter}, return_when=asyncio.FIRST_COMPLETED)
    if mcp_task.done():
        waiter.cancel()
        mcp_task.result()  # raises the startup error instead of hanging
    try:
        yield
    finally:
        if hasattr(app.state, "registry"):
            await app.state.registry.stop_all()
        if app.state.run is not None:
            await app.state.run.stop()
        stop.set()
        await mcp_task
        flush_tracing()


app = FastAPI(title="Matchday Companion", lifespan=lifespan)


class SessionMiddleware:
    """Pure ASGI middleware for session cookie management without BaseHTTPMiddleware task-group latency."""

    def __init__(self, app_instance) -> None:
        self.app = app_instance

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        cookie_val = None
        for name, value in scope.get("headers", []):
            if name.lower() == b"cookie":
                cookie_str = value.decode("utf-8", errors="ignore")
                for item in cookie_str.split(";"):
                    if "=" in item:
                        k, v = item.strip().split("=", 1)
                        if k == SESSION_COOKIE:
                            cookie_val = v
                            break
        query_val = None
        query_str = scope.get("query_string", b"").decode("utf-8", errors="ignore")
        if query_str:
            for pair in query_str.split("&"):
                if pair.startswith("session="):
                    query_val = pair.split("=", 1)[1]
                    break
        is_new = False
        if cookie_val:
            sid = cookie_val
        elif query_val:
            sid = query_val
        else:
            sid = secrets.token_hex(16)
            is_new = True

        token = current_session_id.set(sid)
        state = scope.setdefault("state", {})
        state["session_id"] = sid

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start" and is_new:
                headers = list(message.get("headers", []))
                secure = scope.get("scheme") == "https"
                cookie_header = f"{SESSION_COOKIE}={sid}; Path=/; HttpOnly; SameSite=Lax"
                if secure:
                    cookie_header += "; Secure"
                headers.append((b"set-cookie", cookie_header.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            current_session_id.reset(token)


app.add_middleware(SessionMiddleware)


app.include_router(voice_router)
app.mount("/static", StaticFiles(directory=FRONTEND.parent), name="static")


def _extract_mcp_id(scope: dict) -> str | None:
    path = scope.get("path", "")
    if path.startswith("/mcp/"):
        parts = [p for p in path[5:].split("/") if p]
        if parts:
            return parts[0]
    elif not path.startswith("/mcp"):
        parts = [p for p in path.split("/") if p]
        if parts:
            return parts[0]
    headers = dict(scope.get("headers", []))
    cookie_str = headers.get(b"cookie", b"").decode("utf-8", errors="ignore")
    if SESSION_COOKIE in cookie_str:
        for item in cookie_str.split(";"):
            if "=" in item:
                k, v = item.strip().split("=", 1)
                if k == SESSION_COOKIE:
                    return v
    return None


async def mcp_mount(scope, receive, send) -> None:
    """Forwards to the MCP ASGI app built in the current lifespan, resolving the visitor's run."""
    mcp_id = _extract_mcp_id(scope)
    token = current_session_id.set(mcp_id)
    try:
        scope_copy = dict(scope)
        scope_copy["path"] = "/"
        scope_copy["raw_path"] = b"/"
        await app.state.mcp_asgi(scope_copy, receive, send)
    finally:
        current_session_id.reset(token)


app.mount("/mcp", mcp_mount, name="mcp")


def default_delay() -> float:
    return float(os.environ.get("BROADCAST_DELAY_S", "20"))


def agent_mode() -> str:
    return os.environ.get("AGENT_MODE", "template").lower()


def visitor_id(request: Request) -> str:
    # Reverse proxies and Azure Container Apps ingress append the real client IP to the
    # end of the X-Forwarded-For chain. The first entry is client-controlled and can be
    # forged by a caller to bypass rate limits. We use the last entry added by the ingress.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


def get_run(request: Request) -> MatchRun | None:
    session_id = get_session_id(request)
    if hasattr(app.state, "registry"):
        run = app.state.registry.get(session_id)
        if run is not None:
            return run
        if session_id:
            return None
    return getattr(app.state, "run", None)


@app.get("/api/health")
async def health() -> dict:
    registry = getattr(app.state, "registry", None)
    active = registry.active_count() if registry else 0
    running = active > 0
    return {
        "status": "ok",
        "agent_mode": os.environ.get("AGENT_MODE", "template"),
        "voice": app.state.speaker_factory is not None,
        "running": running,
        "active_runs": active,
        "demo_plant": os.environ.get("DEMO_PLANT", "").lower() in ("1", "true", "yes"),
    }


@app.post("/api/match/start")
async def start_match(request: StartRequest, http: Request) -> dict:
    if request.plant > 0 and os.environ.get("DEMO_PLANT", "").lower() not in ("1", "true", "yes"):
        raise HTTPException(
            status_code=403,
            detail="Planted-claim demo disabled on this instance (DEMO_PLANT != 1)",
        )
    session_id = get_session_id(http)
    mode, fallback_reason = agent_mode(), None
    workflow_factory, producer = app.state.workflow_factory, app.state.producer
    recap_writer = getattr(app.state, "recap_writer", None) or recap_writer_from_env()
    if mode == "foundry" and not app.state.limiter.allow(visitor_id(http)):
        mode, fallback_reason = "template", f"live-run limit reached ({app.state.limiter.per_day} per visitor per day); continuing with offline agents"
        workflow_factory, producer = template_workflow, template_producer()
        recap_writer = TemplateRecapWriter()
    elif mode != "foundry":
        recap_writer = TemplateRecapWriter()
    run = await app.state.registry.start_run(
        session_id,
        lambda: MatchRun(
            seed=request.seed, speed=request.speed, delay_s=request.delay_s if request.delay_s is not None else default_delay(),
            minutes=request.minutes, precompute=request.precompute, home=request.home, away=request.away,
            plant=request.plant,
            workflow_factory=workflow_factory, producer=producer, recap_writer=recap_writer,
            agent_mode=mode, fallback_reason=fallback_reason,
        ),
    )
    app.state.run = run
    now = asyncio.get_running_loop().time()
    assert run.clock is not None
    return {
        "match_id": run.match_id, "mode": run.mode, "agent_mode": run.agent_mode, "fallback_reason": run.fallback_reason,
        "live_runs_remaining": app.state.limiter.remaining(visitor_id(http)) if agent_mode() == "foundry" else None,
        "events": len(run.events), "clock": run.clock.as_dict(now), "precomputed_moments": len(run.processed),
        "profiles": [p.key() for p in run.profiles],
    }


@app.get("/api/profiles")
async def profiles(http: Request) -> dict:
    run = get_run(http)
    return {
        "clubs": [{"id": c.id, "name": c.name, "short": c.short, "players": [{"id": p.id, "name": p.name, "number": p.number, "position": p.position} for p in c.players]} for c in CLUBS.values()],
        "depths": ["casual", "analyst"],
        "languages": ["en", "tr"],
        "active": [p.key() for p in run.profiles] if run else [],
    }


def parse_profile_key(key: str) -> FanProfile:
    try:
        return FanProfile.from_key(key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/fan/profile")
async def set_profile(profile: FanProfile, http: Request) -> dict:
    run = get_run(http)
    if run is None:
        raise HTTPException(status_code=404, detail="no match running")
    run.add_profile(profile)
    latest = await run.render_latest(profile)
    return {"profile_key": profile.key(), "latest": latest.model_dump() if latest else None}


class AskRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=500)
    profile_key: str = "-|-|casual|en"


@app.post("/api/qa")
async def ask(request: AskRequest, http: Request) -> dict:
    """Text-first Q&A: the same path the voice uses, without the speech. Answers only from the ledger tools."""
    run = get_run(http)
    if run is None:
        raise HTTPException(status_code=404, detail="no match running")
    profile = parse_profile_key(request.profile_key)
    seq = len(run.displayed_events())
    question = new_question(profile.key(), request.transcript, seq)
    timing = QaTiming(pressed_at=time.time())
    qa = qa_pipeline_for_run(run, app)
    answer = await qa.answer(question, profile, timing=timing)
    timing.answered_at = time.time()
    answer.timing = timing
    run.record_timing(timing)
    run.metrics["questions_answered"] += 1
    run.metrics["questions_without_data"] += int(answer.text in ("I don't have data on that.", "Bu konuda elimde veri yok."))
    return {"question": question.model_dump(), "answer": answer.model_dump()}


@app.get("/api/match/audits")
async def audits(http: Request) -> dict:
    run = get_run(http)
    return {"audits": [a.model_dump() for a in run.audits] if run else [], "exact": sum(a.ok for a in run.audits) if run else 0}


@app.get("/api/match/moments")
async def moments(http: Request) -> dict:
    run = get_run(http)
    if run is None:
        return {"moments": []}
    return {"moments": run.timelines(), "metrics": run.report()}


@app.post("/api/match/stop")
async def stop_match(http: Request) -> dict:
    session_id = get_session_id(http)
    run = None
    if hasattr(app.state, "registry"):
        run = await app.state.registry.stop_run(session_id)
    if run is None and app.state.run is not None:
        run = app.state.run
        await run.stop()
        app.state.run = None
    if run is None:
        raise HTTPException(status_code=404, detail="no match running")
    return {"match_id": run.match_id, "metrics": run.report()}


@app.get("/api/match/state")
async def match_state(http: Request) -> dict:
    run = get_run(http)
    if run is None:
        return {"running": False}
    now = asyncio.get_running_loop().time()
    return {"running": not run.finished.is_set(), "match_id": run.match_id, "mode": run.mode, "clock": run.clock.as_dict(now) if run.clock else None, "metrics": run.report()}


def _stream(channel: str, http: Request) -> EventSourceResponse:
    run = get_run(http)
    if run is None:
        raise HTTPException(status_code=404, detail="no match running; POST /api/match/start first")
    return EventSourceResponse(run.broadcast.subscribe(channel))


@app.get("/api/stream/cues")
async def stream_cues(http: Request) -> EventSourceResponse:
    return _stream("cues", http)


@app.get("/api/stream/events")
async def stream_events(http: Request) -> EventSourceResponse:
    return _stream("events", http)


@app.get("/api/stream/verdicts")
async def stream_verdicts(http: Request) -> EventSourceResponse:
    return _stream("verdicts", http)


@app.get("/api/stream/fan")
async def stream_fan(profile: str, http: Request) -> EventSourceResponse:
    """Narratives for one profile key as their moments are displayed; registers the profile and replays the latest moment first."""
    run = get_run(http)
    if run is None:
        raise HTTPException(status_code=404, detail="no match running; POST /api/match/start first")
    fan = parse_profile_key(profile)
    run.add_profile(fan)
    channel = f"fan:{fan.key()}"

    async def stream():
        queue = run.broadcast.open(channel)
        latest = await run.render_latest(fan)
        if latest is not None:
            yield {"event": "narrative", "data": json.dumps(run.narrative_payload(latest, replay=True), ensure_ascii=False)}
        if run.finished.is_set() and fan.key() in run.recaps:
            yield {"event": "recap", "data": json.dumps(run.recaps[fan.key()].model_dump(), ensure_ascii=False)}
        async for item in run.broadcast.drain(channel, queue):
            yield item

    return EventSourceResponse(stream())


@app.get("/api/match/recap")
async def match_recap(profile: str, http: Request) -> dict:
    run = get_run(http)
    if run is None:
        raise HTTPException(status_code=404, detail="no match running; POST /api/match/start first")
    fan = parse_profile_key(profile)
    recap = await run.render_recap(fan)
    return recap.model_dump()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)
