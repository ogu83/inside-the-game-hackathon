"""WebSocket /api/voice: speaks each displayed cue's narrative in the listener's language.

Binary frames are pcm16 mono audio at 24 kHz; text frames are JSON status messages:
{"type": "speaking", ...}, {"type": "spoken", "check": NumberCheck}, {"type": "skipped", ...},
{"type": "unavailable", "reason": ...}. Lines are spoken one at a time; if cues arrive faster
than speech, only the newest waiting line is kept (a stale line is worse than a skipped one).
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.fact_check_rules import check_speech, cited_evidence
from app.api.streams import MatchRun
from app.voice.session import Lang, Speaker

router = APIRouter()
log = logging.getLogger(__name__)
DONE = object()


def narrative_for(cue: dict[str, Any], lang: str) -> dict[str, Any] | None:
    return next((n for n in cue["narratives"] if n["profile_key"].rsplit("|", 1)[-1] == lang), None)


async def _feed(run: MatchRun, lang: str, waiting: asyncio.Queue, ws: WebSocket) -> None:
    async for item in run.broadcast.subscribe("cues"):
        if item["event"] != "cue":
            continue
        narrative = narrative_for(json.loads(item["data"]), lang)
        if narrative is None:
            continue
        while not waiting.empty():
            stale = waiting.get_nowait()
            run.metrics["speech_skipped_stale"] += 1
            await ws.send_json({"type": "skipped", "moment_id": stale["moment_id"], "reason": "newer line waiting"})
        waiting.put_nowait(narrative)
    waiting.put_nowait(DONE)


async def _speak_loop(run: MatchRun, speaker: Speaker, lang: Lang, waiting: asyncio.Queue, ws: WebSocket) -> None:
    while (narrative := await waiting.get()) is not DONE:
        processed = run.processed[narrative["moment_id"]]
        insight = processed.result.verdict.insight
        cited, _ = cited_evidence(insight, processed.moment)
        await ws.send_json({"type": "speaking", "moment_id": narrative["moment_id"], "text": narrative["text"]})
        transcript = await speaker.speak(narrative["text"], lang, ws.send_bytes)
        check = check_speech(narrative["text"], transcript, cited, moment_id=narrative["moment_id"],
                             profile_key=narrative["profile_key"], lang=lang)
        run.metrics["speech_checks"] += 1
        run.metrics["speech_mismatches"] += int(not check.ok)
        await ws.send_json({"type": "spoken", "check": check.model_dump()})


async def _until_disconnect(ws: WebSocket) -> None:
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass


@router.websocket("/api/voice")
async def voice(ws: WebSocket, lang: Lang = "en") -> None:
    await ws.accept()
    run: MatchRun | None = ws.app.state.run
    factory = ws.app.state.speaker_factory
    if run is None or factory is None:
        reason = "no match running" if run is None else "voice is off (no Foundry endpoint or VOICE_MODE=off)"
        await ws.send_json({"type": "unavailable", "reason": reason})
        await ws.close()
        return
    speaker = await factory()
    waiting: asyncio.Queue = asyncio.Queue()
    tasks = [
        asyncio.create_task(_feed(run, lang, waiting, ws)),
        asyncio.create_task(_speak_loop(run, speaker, lang, waiting, ws)),
        asyncio.create_task(_until_disconnect(ws)),
    ]
    try:
        await asyncio.wait(tasks[1:], return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, WebSocketDisconnect):
                pass
            except Exception:
                log.exception("voice task failed")
        await speaker.close()
        try:
            await ws.close()
        except RuntimeError:
            pass
