"""WebSocket /api/voice: speaks the listener's profile narrative for each displayed cue, verbatim.

Query: `profile=<club|player|depth|language>` (preferred) or `lang=en|tr` (a default profile in that language).
On connect the latest shown moment is re-rendered for the profile and spoken first, so a profile switch is
heard at once (demo scene 3). Binary frames are pcm16 mono audio at 24 kHz; text frames are JSON status
messages: {"type": "speaking", ...}, {"type": "spoken", "check": NumberCheck}, {"type": "skipped", ...},
{"type": "unavailable", "reason": ...}. Lines are spoken one at a time; if cues arrive faster than speech,
only the newest waiting line is kept (a stale line is worse than a skipped one).
"""

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.agents.fact_check_rules import check_speech, cited_evidence
from app.agents.models import Answer, FanProfile, QaTiming, SpeechAudit
from app.api.sessions import get_ws_session_id, qa_pipeline_for_run
from app.api.streams import MatchRun
from app.voice.qa import new_question
from app.voice.session import Lang, NothingHeard, Speaker, SpeechError, TranscriptionError

router = APIRouter()
log = logging.getLogger(__name__)
DONE = object()
NOTHING_HEARD = {"en": "I didn't catch that, try again.", "tr": "Anlayamadım, tekrar dener misin?"}


def narrative_for(cue: dict[str, Any], lang: str) -> dict[str, Any] | None:
    """Kept for the cue payload shape: the narrative in `lang` among a cue's narratives."""
    return next((n for n in cue["narratives"] if n["profile_key"].rsplit("|", 1)[-1] == lang), None)


async def _feed(run: MatchRun, fan: FanProfile, waiting: asyncio.Queue, ws: WebSocket, state: dict) -> None:
    channel = f"fan:{fan.key()}"
    queue = run.broadcast.open(channel)  # register before rendering, so nothing published meanwhile is lost
    try:
        latest = await run.render_latest(fan)
        if latest is not None:
            waiting.put_nowait({**run.narrative_payload(latest, replay=True)})
        async for item in run.broadcast.drain(channel, queue):
            if item["event"] == "recap":
                data = json.loads(item["data"])
                waiting.put_nowait({**data, "recap": True})
                continue
            if item["event"] != "narrative":
                continue
            narrative = json.loads(item["data"])
            while not waiting.empty():
                stale = waiting.get_nowait()
                if isinstance(stale, Answer) or (isinstance(stale, dict) and stale.get("recap")):
                    waiting.put_nowait(stale)  # an answer or recap is never stale
                    break
                run.metrics["speech_skipped_stale"] += 1
                await ws.send_json({"type": "skipped", "moment_id": stale["moment_id"], "reason": "newer line waiting"})
            waiting.put_nowait(narrative)
        # The match is over: say so once the last line is out, but stay connected so the fan can still ask questions.
        while not waiting.empty() or state["busy"]:
            await asyncio.sleep(0.02)
        await ws.send_json({"type": "match_end"})
    finally:
        run.broadcast.release(channel, queue)  # also when the socket closes before drain starts


async def _speak_loop(run: MatchRun, speaker: Speaker, fan: FanProfile, waiting: asyncio.Queue, ws: WebSocket, state: dict) -> None:
    lang = fan.language
    while (item := await waiting.get()) is not DONE:
        state["busy"] = True
        if isinstance(item, Answer):
            text, cited, moment_id, question_id = item.text, item.evidence, None, item.question_id
            if item.timing is not None:
                item.timing.speech_started_at = time.time()
                run.record_timing(item.timing)
            await ws.send_json({"type": "speaking", "question_id": question_id, "text": text, "lang": lang, "timing": item.timing.summary() if item.timing else None})
        elif isinstance(item, dict) and item.get("recap"):
            text, cited, moment_id, question_id = item["text"], item.get("evidence", {}), "recap", None
            await ws.send_json({"type": "speaking", "moment_id": "recap", "text": text, "replay": False, "lang": lang})
        else:
            processed = run.processed[item["moment_id"]]
            cited, _ = cited_evidence(processed.result.verdict.insight, processed.moment)
            text, moment_id, question_id = item["text"], item["moment_id"], None
            await ws.send_json({"type": "speaking", "moment_id": moment_id, "text": text, "replay": item.get("replay", False), "lang": lang})
        state["interrupted"] = False
        try:
            transcript = await speaker.speak(text, lang, ws.send_bytes)
        except (SpeechError, RuntimeError) as exc:  # the line is lost, the socket and the match are not
            log.warning("speech failed for %s: %s", moment_id or question_id, exc)
            run.metrics["speech_errors"] += 1
            await ws.send_json({"type": "speech_error", "moment_id": moment_id, "question_id": question_id, "reason": str(exc)})
            state["busy"] = False
            continue
        check = check_speech(text, transcript, cited, moment_id=moment_id or f"qa-{question_id}", profile_key=fan.key(), lang=lang)
        interrupted = state["interrupted"]
        ok = check.ok or (interrupted and not [m for m in check.mismatches if "transcript differs" not in m])
        audit = SpeechAudit(moment_id=moment_id, question_id=question_id, profile_key=fan.key(), approved_text=text, transcript=transcript,
                            ok=ok, mismatches=[] if ok else check.mismatches, interrupted=interrupted)
        run.record_audit(audit)
        await ws.send_json({"type": "spoken", "check": check.model_dump(), "audit": audit.model_dump()})
        state["busy"] = False


async def _barge_in(run: MatchRun, ws: WebSocket, speaker: Speaker, state: dict, interrupting: str | None) -> None:
    """Stop the current line. `interrupting` names the line still playing in the browser (the server may have finished
    sending it long ago); its audit is marked interrupted so a cut-off transcript is never counted as a mismatch."""
    state["interrupted"] = True
    await speaker.cancel()
    if interrupting:
        audit = run.mark_interrupted(interrupting)
        if audit is not None:
            await ws.send_json({"type": "audit_updated", "audit": audit.model_dump()})


async def _ask(run: MatchRun, ws: WebSocket, fan: FanProfile, transcript: str, waiting: asyncio.Queue, speaker: Speaker, state: dict,
               interrupting: str | None = None, timing: QaTiming | None = None) -> None:
    """Barge-in: stop the current line, drop stale lines, answer text first, then speak the answer verbatim."""
    timing = timing or QaTiming(pressed_at=time.time())
    await _barge_in(run, ws, speaker, state, interrupting)
    while not waiting.empty():
        stale = waiting.get_nowait()
        if isinstance(stale, Answer) or (isinstance(stale, dict) and stale.get("recap")):
            waiting.put_nowait(stale)
            break
        run.metrics["speech_skipped_stale"] += 1
    question = new_question(fan.key(), transcript, len(run.displayed_events()))
    await ws.send_json({"type": "question", "question": question.model_dump()})
    qa = qa_pipeline_for_run(run, ws.app)
    answer = await qa.answer(question, fan, timing=timing)
    timing.answered_at = time.time()
    answer.timing = timing
    run.record_timing(timing)
    run.metrics["questions_answered"] += 1
    await ws.send_json({"type": "answer", "answer": answer.model_dump(), "timing": timing.summary()})
    waiting.put_nowait(answer)


async def _nothing_heard(run: MatchRun, ws: WebSocket, fan: FanProfile, waiting: asyncio.Queue) -> None:
    """An empty press (caught in the page, or Voice Live's commit_empty): the reply is shown and spoken verbatim through
    the normal speech path, so it is audited like every other line."""
    run.metrics["nothing_heard"] += 1
    text = NOTHING_HEARD[fan.language]
    await ws.send_json({"type": "question", "question": None, "reason": text})
    while not waiting.empty():
        stale = waiting.get_nowait()
        if isinstance(stale, Answer) or (isinstance(stale, dict) and stale.get("recap")):
            waiting.put_nowait(stale)
            break
        run.metrics["speech_skipped_stale"] += 1
    waiting.put_nowait(Answer(question_id=f"nh-{int(time.time() * 1000)}", text=text, evidence_refs=[], tool_calls=[]))


async def _transcribe_then_ask(run: MatchRun, ws: WebSocket, fan: FanProfile, pcm: bytes, waiting: asyncio.Queue, speaker: Speaker, state: dict, pressed_at: float) -> None:
    """One utterance, in its own task: a slow or failed transcription never blocks the next press."""
    timing = QaTiming(pressed_at=pressed_at)
    try:
        transcript = await speaker.transcribe(pcm, fan.language)
        timing.transcribed_at = time.time()
    except asyncio.CancelledError:
        raise
    except NothingHeard:  # empty or too short: fails at once, with a spoken, human reason
        await _nothing_heard(run, ws, fan, waiting)
        return
    except (TranscriptionError, RuntimeError) as exc:  # reported to the page; the voice keeps working
        log.warning("transcription failed: %s", exc)
        run.metrics["transcription_errors"] += 1
        await ws.send_json({"type": "question", "question": None, "reason": f"could not transcribe: {exc}"})
        return
    if transcript.strip():
        await _ask(run, ws, fan, transcript, waiting, speaker, state, timing=timing)
    else:
        await _nothing_heard(run, ws, fan, waiting)


async def _listen(run: MatchRun, ws: WebSocket, fan: FanProfile, waiting: asyncio.Queue, speaker: Speaker, state: dict) -> None:
    """Text frames: ask / talk_start / talk_end. Binary frames between talk_start and talk_end are pcm16 mic audio.
    A new talk_start supersedes a transcription still in flight from the previous press."""
    pcm = bytearray()
    talking = False
    pending: asyncio.Task | None = None
    pressed_at = 0.0
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                if talking:
                    pcm.extend(message["bytes"])
                continue
            try:
                data = json.loads(message.get("text") or "{}")
            except json.JSONDecodeError:
                continue
            kind = data.get("type")
            if kind == "ask" and data.get("transcript", "").strip():
                await _ask(run, ws, fan, data["transcript"], waiting, speaker, state, data.get("interrupting"))
            elif kind == "talk_start":
                if talking:
                    continue  # a repeated press while already listening: one press, one question
                if pending is not None and not pending.done():
                    pending.cancel()  # the fan moved on: the earlier utterance is dropped
                    run.metrics["transcriptions_superseded"] += 1
                talking, pcm, pressed_at = True, bytearray(), time.time()
                await _barge_in(run, ws, speaker, state, data.get("interrupting"))
            elif kind == "talk_end" and talking:
                talking = False
                pending = asyncio.create_task(_transcribe_then_ask(run, ws, fan, bytes(pcm), waiting, speaker, state, pressed_at))
                pending.add_done_callback(_log_task_exception)
            elif kind == "talk_cancel" and talking:
                talking = False  # the page caught a too-short press: nothing goes to Voice Live, the reply is spoken
                await _nothing_heard(run, ws, fan, waiting)
    except WebSocketDisconnect:
        return
    finally:
        if pending is not None and not pending.done():
            pending.cancel()


def _log_task_exception(t: asyncio.Task) -> None:
    if not t.cancelled():
        exc = t.exception()
        if exc is not None:
            log.warning("unhandled exception in voice background task: %s", exc, exc_info=True)


@router.websocket("/api/voice")
async def voice(ws: WebSocket, lang: Lang = "en", profile: str | None = None) -> None:
    await ws.accept()
    session_id = get_ws_session_id(ws)
    registry = getattr(ws.app.state, "registry", None)
    run: MatchRun | None = registry.get(session_id) if registry else None
    if run is None:
        run = getattr(ws.app.state, "run", None)
    factory = ws.app.state.speaker_factory
    if run is None or factory is None:
        reason = "no match running" if run is None else "voice is off (no Foundry endpoint or VOICE_MODE=off)"
        await ws.send_json({"type": "unavailable", "reason": reason})
        await ws.close()
        return
    try:
        fan = FanProfile.from_key(profile) if profile else FanProfile(language=lang)
    except ValueError as exc:
        await ws.send_json({"type": "unavailable", "reason": str(exc)})
        await ws.close()
        return
    run.add_profile(fan)
    speaker = await factory()
    waiting: asyncio.Queue = asyncio.Queue()
    state = {"interrupted": False, "busy": False}
    tasks = [
        asyncio.create_task(_feed(run, fan, waiting, ws, state)),
        asyncio.create_task(_speak_loop(run, speaker, fan, waiting, ws, state)),
        asyncio.create_task(_listen(run, ws, fan, waiting, speaker, state)),
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
            except Exception as exc:
                if _client_gone(ws, exc):
                    log.debug("voice task ended with the client gone: %s", exc)  # a profile switch closes the old socket
                else:
                    log.exception("voice task failed")
        await speaker.close()
        await _close_quietly(ws)


def _client_gone(ws: WebSocket, exc: BaseException) -> bool:
    """True when the failure is only the browser having left (uvicorn ClientDisconnected, a 1006 close, a send after close)."""
    if ws.client_state == WebSocketState.DISCONNECTED or ws.application_state == WebSocketState.DISCONNECTED:
        return True
    name = type(exc).__name__
    return name in ("ClientDisconnected", "ConnectionClosed", "ConnectionClosedOK", "ConnectionClosedError", "WebSocketDisconnect")


async def _close_quietly(ws: WebSocket) -> None:
    """Close only if both sides are still connected; a client that already left raises on close, which is not an error."""
    if ws.client_state != WebSocketState.CONNECTED or ws.application_state != WebSocketState.CONNECTED:
        return
    try:
        await ws.close()
    except Exception as exc:  # the client raced us to the close
        log.debug("voice socket close skipped: %s", exc)
