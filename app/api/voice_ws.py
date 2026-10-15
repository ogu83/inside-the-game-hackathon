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
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.fact_check_rules import check_speech, cited_evidence
from app.agents.models import Answer, FanProfile, SpeechAudit
from app.api.streams import MatchRun
from app.voice.qa import new_question
from app.voice.session import Lang, Speaker, SpeechError, TranscriptionError

router = APIRouter()
log = logging.getLogger(__name__)
DONE = object()


def narrative_for(cue: dict[str, Any], lang: str) -> dict[str, Any] | None:
    """Kept for the cue payload shape: the narrative in `lang` among a cue's narratives."""
    return next((n for n in cue["narratives"] if n["profile_key"].rsplit("|", 1)[-1] == lang), None)


async def _feed(run: MatchRun, fan: FanProfile, waiting: asyncio.Queue, ws: WebSocket, state: dict) -> None:
    channel = f"fan:{fan.key()}"
    queue = run.broadcast.open(channel)  # register before rendering, so nothing published meanwhile is lost
    latest = await run.render_latest(fan)
    if latest is not None:
        waiting.put_nowait({**run.narrative_payload(latest, replay=True)})
    async for item in run.broadcast.drain(channel, queue):
        if item["event"] != "narrative":
            continue
        narrative = json.loads(item["data"])
        while not waiting.empty():
            stale = waiting.get_nowait()
            if isinstance(stale, Answer):
                waiting.put_nowait(stale)  # an answer is never stale
                break
            run.metrics["speech_skipped_stale"] += 1
            await ws.send_json({"type": "skipped", "moment_id": stale["moment_id"], "reason": "newer line waiting"})
        waiting.put_nowait(narrative)
    # The match is over: say so once the last line is out, but stay connected so the fan can still ask questions.
    while not waiting.empty() or state["busy"]:
        await asyncio.sleep(0.02)
    await ws.send_json({"type": "match_end"})


async def _speak_loop(run: MatchRun, speaker: Speaker, fan: FanProfile, waiting: asyncio.Queue, ws: WebSocket, state: dict) -> None:
    lang = fan.language
    while (item := await waiting.get()) is not DONE:
        state["busy"] = True
        if isinstance(item, Answer):
            text, cited, moment_id, question_id = item.text, item.evidence, None, item.question_id
            await ws.send_json({"type": "speaking", "question_id": question_id, "text": text, "lang": lang})
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


async def _ask(run: MatchRun, ws: WebSocket, fan: FanProfile, transcript: str, waiting: asyncio.Queue, speaker: Speaker, state: dict) -> None:
    """Barge-in: stop the current line, drop stale lines, answer text first, then speak the answer verbatim."""
    state["interrupted"] = True
    await speaker.cancel()
    while not waiting.empty():
        stale = waiting.get_nowait()
        if isinstance(stale, Answer):
            waiting.put_nowait(stale)
            break
        run.metrics["speech_skipped_stale"] += 1
    question = new_question(fan.key(), transcript, len(run.displayed_events()))
    await ws.send_json({"type": "question", "question": question.model_dump()})
    answer = await ws.app.state.qa.answer(question, fan)
    run.metrics["questions_answered"] += 1
    await ws.send_json({"type": "answer", "answer": answer.model_dump()})
    waiting.put_nowait(answer)


async def _listen(run: MatchRun, ws: WebSocket, fan: FanProfile, waiting: asyncio.Queue, speaker: Speaker, state: dict) -> None:
    """Text frames: ask / talk_start / talk_end. Binary frames between talk_start and talk_end are pcm16 mic audio."""
    pcm = bytearray()
    talking = False
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
                await _ask(run, ws, fan, data["transcript"], waiting, speaker, state)
            elif kind == "talk_start":
                talking, pcm = True, bytearray()
                state["interrupted"] = True
                await speaker.cancel()
            elif kind == "talk_end" and talking:
                talking = False
                if len(pcm) < 4800:  # under 0.1 s of audio
                    await ws.send_json({"type": "question", "question": None, "reason": "no speech captured"})
                    continue
                try:
                    transcript = await speaker.transcribe(bytes(pcm), fan.language)
                except (TranscriptionError, RuntimeError) as exc:  # reported to the page; the voice keeps working
                    log.warning("transcription failed: %s", exc)
                    run.metrics["transcription_errors"] += 1
                    await ws.send_json({"type": "question", "question": None, "reason": f"could not transcribe: {exc}"})
                    continue
                if transcript.strip():
                    await _ask(run, ws, fan, transcript, waiting, speaker, state)
                else:
                    await ws.send_json({"type": "question", "question": None, "reason": "nothing understood"})
    except WebSocketDisconnect:
        return


@router.websocket("/api/voice")
async def voice(ws: WebSocket, lang: Lang = "en", profile: str | None = None) -> None:
    await ws.accept()
    run: MatchRun | None = ws.app.state.run
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
            except Exception:
                log.exception("voice task failed")
        await speaker.close()
        try:
            await ws.close()
        except RuntimeError:
            pass
