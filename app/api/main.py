"""FastAPI app: start a match, stream delayed events and verified cues over SSE."""

import asyncio
import json
import os
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
from app.ledger.mcp_server import LedgerTools, build_mcp_server
from app.voice.qa import QaPipeline, RuleQaAgent, new_question
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


class _AppView:
    """LedgerView over whatever match the app is showing right now."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def events(self):
        run = self.app.state.run
        return run.displayed_events() if run else []

    def shown_moments(self):
        run = self.app.state.run
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
    app.state.run = None
    if not getattr(app.state, "qa", None):
        app.state.qa = qa_pipeline_from_env(app)
    app.state.workflow_factory = getattr(app.state, "workflow_factory", None) or workflow_factory_from_env()
    if not hasattr(app.state, "producer") or app.state.producer is None:
        app.state.producer = producer_from_env()
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
        if app.state.run is not None:
            await app.state.run.stop()
        stop.set()
        await mcp_task


app = FastAPI(title="Matchday Companion", lifespan=lifespan)
app.include_router(voice_router)
app.mount("/static", StaticFiles(directory=FRONTEND.parent), name="static")


async def mcp_mount(scope, receive, send) -> None:
    """Forwards to the MCP ASGI app built in the current lifespan."""
    await app.state.mcp_asgi(scope, receive, send)


app.mount("/mcp", mcp_mount, name="mcp")


def default_delay() -> float:
    return float(os.environ.get("BROADCAST_DELAY_S", "20"))


def agent_mode() -> str:
    return os.environ.get("AGENT_MODE", "template").lower()


def visitor_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "agent_mode": os.environ.get("AGENT_MODE", "template"), "voice": app.state.speaker_factory is not None, "running": app.state.run is not None and not app.state.run.finished.is_set()}


@app.post("/api/match/start")
async def start_match(request: StartRequest, http: Request) -> dict:
    if app.state.run is not None:
        await app.state.run.stop()
    mode, fallback_reason = agent_mode(), None
    workflow_factory, producer = app.state.workflow_factory, app.state.producer
    if mode == "foundry" and not app.state.limiter.allow(visitor_id(http)):
        mode, fallback_reason = "template", f"live-run limit reached ({app.state.limiter.per_day} per visitor per day); continuing with offline agents"
        workflow_factory, producer = template_workflow, template_producer()
    run = MatchRun(
        seed=request.seed, speed=request.speed, delay_s=request.delay_s if request.delay_s is not None else default_delay(),
        minutes=request.minutes, precompute=request.precompute, home=request.home, away=request.away,
        workflow_factory=workflow_factory, producer=producer, agent_mode=mode, fallback_reason=fallback_reason,
    )
    app.state.run = run
    await run.start()
    now = asyncio.get_running_loop().time()
    assert run.clock is not None
    return {
        "match_id": run.match_id, "mode": run.mode, "agent_mode": run.agent_mode, "fallback_reason": run.fallback_reason,
        "live_runs_remaining": app.state.limiter.remaining(visitor_id(http)) if agent_mode() == "foundry" else None,
        "events": len(run.events), "clock": run.clock.as_dict(now), "precomputed_moments": len(run.processed),
        "profiles": [p.key() for p in run.profiles],
    }


@app.get("/api/profiles")
async def profiles() -> dict:
    return {
        "clubs": [{"id": c.id, "name": c.name, "short": c.short, "players": [{"id": p.id, "name": p.name, "number": p.number, "position": p.position} for p in c.players]} for c in CLUBS.values()],
        "depths": ["casual", "analyst"],
        "languages": ["en", "tr"],
        "active": [p.key() for p in app.state.run.profiles] if app.state.run else [],
    }


def parse_profile_key(key: str) -> FanProfile:
    try:
        return FanProfile.from_key(key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/fan/profile")
async def set_profile(profile: FanProfile) -> dict:
    run = app.state.run
    if run is None:
        raise HTTPException(status_code=404, detail="no match running")
    run.add_profile(profile)
    latest = await run.render_latest(profile)
    return {"profile_key": profile.key(), "latest": latest.model_dump() if latest else None}


class AskRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=500)
    profile_key: str = "-|-|casual|en"


@app.post("/api/qa")
async def ask(request: AskRequest) -> dict:
    """Text-first Q&A: the same path the voice uses, without the speech. Answers only from the ledger tools."""
    run = app.state.run
    if run is None:
        raise HTTPException(status_code=404, detail="no match running")
    profile = parse_profile_key(request.profile_key)
    seq = len(run.displayed_events())
    question = new_question(profile.key(), request.transcript, seq)
    timing = QaTiming(pressed_at=time.time())
    answer = await app.state.qa.answer(question, profile)
    timing.answered_at = time.time()
    answer.timing = timing
    run.record_timing(timing)
    run.metrics["questions_answered"] += 1
    run.metrics["questions_without_data"] += int(answer.text in ("I don't have data on that.", "Bu konuda elimde veri yok."))
    return {"question": question.model_dump(), "answer": answer.model_dump()}


@app.get("/api/match/audits")
async def audits() -> dict:
    run = app.state.run
    return {"audits": [a.model_dump() for a in run.audits] if run else [], "exact": sum(a.ok for a in run.audits) if run else 0}


@app.get("/api/match/moments")
async def moments() -> dict:
    run = app.state.run
    if run is None:
        return {"moments": []}
    return {"moments": run.timelines(), "metrics": run.report()}


@app.post("/api/match/stop")
async def stop_match() -> dict:
    run = app.state.run
    if run is None:
        raise HTTPException(status_code=404, detail="no match running")
    await run.stop()
    return {"match_id": run.match_id, "metrics": run.report()}


@app.get("/api/match/state")
async def match_state() -> dict:
    run = app.state.run
    if run is None:
        return {"running": False}
    now = asyncio.get_running_loop().time()
    return {"running": not run.finished.is_set(), "match_id": run.match_id, "mode": run.mode, "clock": run.clock.as_dict(now) if run.clock else None, "metrics": run.report()}


def _stream(channel: str) -> EventSourceResponse:
    run = app.state.run
    if run is None:
        raise HTTPException(status_code=404, detail="no match running; POST /api/match/start first")
    return EventSourceResponse(run.broadcast.subscribe(channel))


@app.get("/api/stream/cues")
async def stream_cues() -> EventSourceResponse:
    return _stream("cues")


@app.get("/api/stream/events")
async def stream_events() -> EventSourceResponse:
    return _stream("events")


@app.get("/api/stream/verdicts")
async def stream_verdicts() -> EventSourceResponse:
    return _stream("verdicts")


@app.get("/api/stream/fan")
async def stream_fan(profile: str) -> EventSourceResponse:
    """Narratives for one profile key as their moments are displayed; registers the profile and replays the latest moment first."""
    run = app.state.run
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
        async for item in run.broadcast.drain(channel, queue):
            yield item

    return EventSourceResponse(stream())


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)
