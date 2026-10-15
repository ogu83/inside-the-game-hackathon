"""FastAPI app: start a match, stream delayed events and verified cues over SSE."""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.api.streams import MatchRun, producer_from_env, workflow_factory_from_env
from app.api.voice_ws import router as voice_router
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.run = None
    app.state.workflow_factory = getattr(app.state, "workflow_factory", None) or workflow_factory_from_env()
    if not hasattr(app.state, "producer") or app.state.producer is None:
        app.state.producer = producer_from_env()
    if not hasattr(app.state, "speaker_factory"):
        app.state.speaker_factory = speaker_factory_from_env()
    yield
    if app.state.run is not None:
        await app.state.run.stop()


app = FastAPI(title="Matchday Companion", lifespan=lifespan)
app.include_router(voice_router)


def default_delay() -> float:
    return float(os.environ.get("BROADCAST_DELAY_S", "20"))


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "agent_mode": os.environ.get("AGENT_MODE", "template"), "voice": app.state.speaker_factory is not None, "running": app.state.run is not None and not app.state.run.finished.is_set()}


@app.post("/api/match/start")
async def start_match(request: StartRequest) -> dict:
    if app.state.run is not None:
        await app.state.run.stop()
    run = MatchRun(
        seed=request.seed, speed=request.speed, delay_s=request.delay_s if request.delay_s is not None else default_delay(),
        minutes=request.minutes, precompute=request.precompute, home=request.home, away=request.away,
        workflow_factory=app.state.workflow_factory, producer=app.state.producer,
    )
    app.state.run = run
    await run.start()
    now = asyncio.get_running_loop().time()
    assert run.clock is not None
    return {"match_id": run.match_id, "mode": run.mode, "events": len(run.events), "clock": run.clock.as_dict(now), "precomputed_moments": len(run.processed)}


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


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)
