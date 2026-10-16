import json
import logging
import re

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.api.main import app
from app.api.streams import template_workflow
from app.api.voice_ws import narrative_for

CHUNK = b"\x00\x01" * 240


class FakeSpeaker:
    """Streams two silent chunks and reports a transcript; `mangle` simulates a voice that changes a number."""

    def __init__(self, mangle: bool = False) -> None:
        self.mangle = mangle
        self.spoken: list[tuple[str, str]] = []
        self.closed = False

    async def speak(self, text: str, lang: str, on_audio) -> str:
        self.spoken.append((text, lang))
        await on_audio(CHUNK)
        await on_audio(CHUNK)
        return re.sub(r"\d+", "99", text, count=1) if self.mangle else text

    async def cancel(self) -> None:
        self.cancelled = getattr(self, "cancelled", 0) + 1

    async def transcribe(self, pcm16: bytes, lang: str) -> str:
        import asyncio

        from app.voice.session import MIN_UTTERANCE_BYTES, NothingHeard

        self.transcribed = getattr(self, "transcribed", []) + [len(pcm16)]
        await asyncio.sleep(getattr(self, "transcribe_delay", 0.0))
        if len(pcm16) < MIN_UTTERANCE_BYTES or getattr(self, "hears_nothing", False):
            raise NothingHeard("input_audio_buffer_commit_empty")
        return "how is my player doing?" if lang == "en" else "oyuncum nasıl oynuyor?"

    async def close(self) -> None:
        self.closed = True


def run_voice(speaker: FakeSpeaker | None, lang: str = "en", profile: str | None = None, after_match: bool = False) -> tuple[list[dict], int, dict]:
    """Start a short precomputed match, listen on /api/voice until it closes."""
    messages, audio_bytes = [], 0
    with TestClient(app) as client:
        async def factory():
            return speaker

        app.state.speaker_factory = factory if speaker else None
        app.state.workflow_factory = template_workflow
        started = client.post("/api/match/start", json={"seed": 7, "speed": 1500, "delay_s": 120, "minutes": 8})
        assert started.status_code == 200
        if after_match:
            with client.stream("GET", "/api/stream/cues") as stream:
                for line in stream.iter_lines():
                    if line.startswith("event: match_end"):
                        break
        query = f"profile={profile}" if profile else f"lang={lang}"
        with client.websocket_connect(f"/api/voice?{query}") as ws:
            while True:
                try:
                    message = ws.receive()
                except WebSocketDisconnect:
                    break
                if message["type"] == "websocket.close":
                    break
                if message.get("bytes") is not None:
                    audio_bytes += len(message["bytes"])
                elif message.get("text") is not None:
                    messages.append(json.loads(message["text"]))
                    if messages[-1]["type"] in ("match_end", "unavailable"):
                        break
        metrics = app.state.run.report()
    return messages, audio_bytes, metrics


def test_verified_lines_are_spoken_verbatim_and_audited() -> None:
    speaker = FakeSpeaker()
    messages, audio_bytes, metrics = run_voice(speaker)
    spoken = [m for m in messages if m["type"] == "spoken"]
    assert spoken, messages
    assert all(m["check"]["ok"] and m["check"]["gate"] == "speech" for m in spoken)
    assert audio_bytes == len(spoken) * 2 * len(CHUNK)
    assert {lang for _, lang in speaker.spoken} == {"en"}
    speaking = [m["text"] for m in messages if m["type"] == "speaking"]
    assert speaking == [text for text, _ in speaker.spoken]
    assert metrics["speech_checks"] == len(spoken) and metrics.get("speech_mismatches", 0) == 0
    assert speaker.closed
    assert messages[-1]["type"] == "match_end", "the socket stays open after the match for questions"


def test_a_voice_that_changes_a_number_is_caught_by_the_speech_gate() -> None:
    messages, _, metrics = run_voice(FakeSpeaker(mangle=True))
    spoken = [m for m in messages if m["type"] == "spoken"]
    assert spoken and not any(m["check"]["ok"] for m in spoken)
    assert any("transcript differs from approved text" in r for m in spoken for r in m["check"]["mismatches"])
    assert metrics["speech_mismatches"] == len(spoken)


def test_turkish_listener_hears_the_turkish_narrative() -> None:
    speaker = FakeSpeaker()
    run_voice(speaker, lang="tr")
    assert speaker.spoken and {lang for _, lang in speaker.spoken} == {"tr"}


def test_voice_off_is_reported_not_silent() -> None:
    messages, audio_bytes, _ = run_voice(None)
    assert messages == [{"type": "unavailable", "reason": "voice is off (no Foundry endpoint or VOICE_MODE=off)"}]
    assert audio_bytes == 0


def test_no_match_running_is_reported() -> None:
    with TestClient(app) as client:
        app.state.run = None
        with client.websocket_connect("/api/voice") as ws:
            assert ws.receive_json() == {"type": "unavailable", "reason": "no match running"}


@pytest.mark.parametrize(("lang", "expected"), [("en", "English line"), ("tr", "Turkce satir"), ("de", None)])
def test_narrative_for_picks_the_listener_language(lang: str, expected: str | None) -> None:
    cue = {"narratives": [
        {"profile_key": "-|-|casual|en", "text": "English line", "moment_id": "m"},
        {"profile_key": "-|-|casual|tr", "text": "Turkce satir", "moment_id": "m"},
    ]}
    found = narrative_for(cue, lang)
    assert (found["text"] if found else None) == expected


def test_profile_switch_speaks_the_re_rendered_latest_line_first_in_the_new_language() -> None:
    speaker = FakeSpeaker()
    messages, audio_bytes, metrics = run_voice(speaker, profile="iva|iva-06|analyst|tr", after_match=True)
    speaking = [m for m in messages if m["type"] == "speaking"]
    assert speaking and speaking[0]["replay"] is True and speaking[0]["lang"] == "tr"
    assert speaker.spoken[0][1] == "tr" and ("pası" in speaker.spoken[0][0] or "baskı" in speaker.spoken[0][0])
    spoken = [m for m in messages if m["type"] == "spoken"]
    assert spoken[0]["check"]["ok"] and spoken[0]["check"]["profile_key"] == "iva|iva-06|analyst|tr" and spoken[0]["check"]["gate"] == "speech"
    assert audio_bytes >= 2 * len(CHUNK) and metrics["speech_checks"] >= 1


def test_voice_follows_the_profile_during_the_match() -> None:
    speaker = FakeSpeaker()
    messages, _, _ = run_voice(speaker, profile="kby|-|analyst|en")
    spoken = [m for m in messages if m["type"] == "spoken"]
    assert spoken and all(m["check"]["profile_key"] == "kby|-|analyst|en" for m in spoken)
    assert {lang for _, lang in speaker.spoken} == {"en"}


def test_bad_profile_key_is_reported() -> None:
    with TestClient(app) as client:
        async def factory():
            return FakeSpeaker()

        app.state.speaker_factory = factory
        app.state.workflow_factory = template_workflow
        client.post("/api/match/start", json={"seed": 7, "speed": 600, "delay_s": 120, "minutes": 4})
        with client.websocket_connect("/api/voice?profile=nonsense") as ws:
            assert ws.receive_json()["type"] == "unavailable"


def ask_over_voice(profile: str, actions, speaker: FakeSpeaker | None = None) -> tuple[list[dict], FakeSpeaker, dict, list[dict]]:
    """Finished match, voice connected for `profile`; `actions(ws)` sends the fan's frames; returns messages, speaker, metrics, audits."""
    speaker = speaker or FakeSpeaker()
    messages: list[dict] = []
    with TestClient(app) as client:
        async def factory():
            return speaker

        app.state.speaker_factory = factory
        app.state.workflow_factory = template_workflow
        client.post("/api/match/start", json={"seed": 30, "speed": 1500, "delay_s": 10, "minutes": 8})
        with client.stream("GET", "/api/stream/cues") as stream:
            for line in stream.iter_lines():
                if line.startswith("event: match_end"):
                    break
        with client.websocket_connect(f"/api/voice?profile={profile}") as ws:
            # the replay line is spoken first and the socket stays open after match_end; then act
            while True:
                m = ws.receive()
                if m.get("text") and json.loads(m["text"])["type"] == "match_end":
                    break
            actions(ws)
            answers = 0
            while answers < 1:
                m = ws.receive()
                if m.get("text"):
                    msg = json.loads(m["text"])
                    messages.append(msg)
                    if msg["type"] == "spoken" and msg["audit"]["question_id"]:
                        answers += 1
        metrics = app.state.run.report()
        audits = client.get("/api/match/audits").json()["audits"]
    return messages, speaker, metrics, audits


def test_typed_question_is_answered_from_the_ledger_and_spoken_verbatim() -> None:
    messages, speaker, metrics, audits = ask_over_voice("iva|iva-06|casual|en", lambda ws: ws.send_text(json.dumps({"type": "ask", "transcript": "how is my player doing?"})))
    kinds = [m["type"] for m in messages]
    assert kinds[:3] == ["question", "answer", "speaking"] and kinds[-1] == "spoken"
    answer = messages[1]["answer"]
    assert "Remy Tallis" in answer["text"] and answer["verdict"]["status"] == "verified" and "player_stats" in answer["tool_calls"]
    assert speaker.spoken[-1] == (answer["text"], "en") and speaker.cancelled >= 1, "barge-in stops the current line before the answer"
    audit = messages[-1]["audit"]
    assert audit["ok"] and audit["question_id"] == answer["question_id"] and audit["approved_text"] == answer["text"]
    assert metrics["questions_answered"] == 1 and metrics["answers_spoken"] == 1
    assert any(a["question_id"] == answer["question_id"] for a in audits) and any(a["moment_id"] for a in audits)


def test_push_to_talk_transcribes_then_answers_in_the_profile_language() -> None:
    def talk(ws):
        ws.send_text(json.dumps({"type": "talk_start"}))
        ws.send_bytes(b"\x00\x01" * 12000)
        ws.send_bytes(b"\x00\x01" * 12000)
        ws.send_text(json.dumps({"type": "talk_end"}))

    messages, speaker, metrics, _ = ask_over_voice("kby|kby-07|analyst|tr", talk)
    assert speaker.transcribed == [48000]
    timing = next(m for m in messages if m["type"] == "answer")["timing"]
    assert timing["transcription_ms"] is not None and 0 <= timing["transcription_ms"] <= timing["answer_ms"], "push-to-talk marks pressed, transcribed and answered"
    speaking = next(m for m in messages if m["type"] == "speaking" and m.get("question_id"))
    assert speaking["timing"]["speech_ms"] >= timing["answer_ms"] and metrics["qa_speech_p50_ms"] == speaking["timing"]["speech_ms"]
    question = next(m for m in messages if m["type"] == "question")["question"]
    assert question["transcript"] == "oyuncum nasıl oynuyor?" and question["profile_key"] == "kby|kby-07|analyst|tr"
    answer = next(m for m in messages if m["type"] == "answer")["answer"]
    assert "Luca Brightwater" in answer["text"] and "pas" in answer["text"]
    assert speaker.spoken[-1][1] == "tr"


def test_too_short_push_to_talk_is_reported_not_answered() -> None:
    speaker = FakeSpeaker()
    with TestClient(app) as client:
        async def factory():
            return speaker

        app.state.speaker_factory = factory
        app.state.workflow_factory = template_workflow
        client.post("/api/match/start", json={"seed": 7, "speed": 1500, "delay_s": 120, "minutes": 4})
        with client.websocket_connect("/api/voice?profile=-|-|casual|en") as ws:
            ws.send_text(json.dumps({"type": "talk_start"}))
            ws.send_bytes(b"\x00" * 100)
            ws.send_text(json.dumps({"type": "talk_end"}))
            while True:
                m = ws.receive()
                if m.get("text"):
                    msg = json.loads(m["text"])
                    if msg["type"] == "question":
                        assert msg["question"] is None and msg["reason"] == "I didn't catch that, try again."
                        break
        assert app.state.run.metrics["nothing_heard"] == 1


def nothing_heard_flow(profile: str, frames, speaker: FakeSpeaker | None = None) -> tuple[list[dict], FakeSpeaker, dict]:
    speaker = speaker or FakeSpeaker()
    with TestClient(app) as client:
        async def factory():
            return speaker

        app.state.speaker_factory = factory
        app.state.workflow_factory = template_workflow
        client.post("/api/match/start", json={"seed": 7, "speed": 1500, "delay_s": 120, "minutes": 4})
        messages = []
        with client.websocket_connect(f"/api/voice?profile={profile}") as ws:
            frames(ws)
            while True:
                m = ws.receive()
                if not m.get("text"):
                    continue
                msg = json.loads(m["text"])
                messages.append(msg)
                if msg["type"] == "spoken" and (msg["audit"]["question_id"] or "").startswith("nh-"):
                    break
        return messages, speaker, app.state.run.report()


def test_a_press_cancelled_in_the_page_is_answered_with_a_spoken_line_without_voice_live() -> None:
    def frames(ws):
        ws.send_text(json.dumps({"type": "talk_start"}))
        ws.send_bytes(b"\x00\x01" * 2000)
        ws.send_text(json.dumps({"type": "talk_cancel"}))

    messages, speaker, metrics = nothing_heard_flow("iva|iva-07|casual|tr", frames)
    reason = next(m for m in messages if m["type"] == "question")["reason"]
    assert reason == "Anlayamadım, tekrar dener misin?"
    spoken_line = next(m for m in messages if m["type"] == "speaking" and m.get("question_id", "").startswith("nh-"))
    assert spoken_line["text"] == reason and spoken_line["lang"] == "tr"
    assert speaker.spoken[-1] == (reason, "tr") and not getattr(speaker, "transcribed", []), "spoken verbatim, nothing sent to Voice Live"
    audit = messages[-1]["audit"]
    assert audit["ok"] and audit["approved_text"] == reason and audit["profile_key"] == "iva|iva-07|casual|tr"
    assert metrics["nothing_heard"] == 1 and metrics.get("answers_spoken", 0) == 0 and metrics["speech_checks"] >= 1


def test_commit_empty_from_voice_live_is_spoken_the_same_way() -> None:
    def frames(ws):
        ws.send_text(json.dumps({"type": "talk_start"}))
        ws.send_bytes(b"\x00\x01" * 24000)
        ws.send_text(json.dumps({"type": "talk_end"}))

    deaf = FakeSpeaker()
    deaf.hears_nothing = True
    messages, speaker, metrics = nothing_heard_flow("-|-|casual|en", frames, speaker=deaf)
    assert speaker.transcribed == [48000], "Voice Live was asked and said the buffer was empty"
    assert speaker.spoken[-1] == ("I didn't catch that, try again.", "en") and metrics["nothing_heard"] == 1


def test_commit_empty_from_voice_live_is_reported_at_once() -> None:
    speaker = FakeSpeaker()
    speaker.hears_nothing = True
    with TestClient(app) as client:
        async def factory():
            return speaker

        app.state.speaker_factory = factory
        app.state.workflow_factory = template_workflow
        client.post("/api/match/start", json={"seed": 7, "speed": 1500, "delay_s": 120, "minutes": 4})
        with client.websocket_connect("/api/voice?profile=-|-|casual|tr") as ws:
            ws.send_text(json.dumps({"type": "talk_start"}))
            ws.send_bytes(b"\x00\x01" * 24000)
            ws.send_text(json.dumps({"type": "talk_end"}))
            while True:
                m = ws.receive()
                if m.get("text") and json.loads(m["text"]).get("type") == "question":
                    msg = json.loads(m["text"])
                    assert msg["question"] is None and msg["reason"] == "Anlayamadım, tekrar dener misin?"
                    break
        assert speaker.transcribed == [48000] and app.state.run.metrics["nothing_heard"] == 1


def test_repeated_press_and_release_frames_make_exactly_one_question() -> None:
    def jittery_talk(ws):
        for _ in range(3):
            ws.send_text(json.dumps({"type": "talk_start"}))  # pointer, mouse and touch all firing
        ws.send_bytes(b"\x00\x01" * 12000)
        ws.send_bytes(b"\x00\x01" * 12000)
        for _ in range(3):
            ws.send_text(json.dumps({"type": "talk_end"}))

    messages, speaker, metrics, _ = ask_over_voice("iva|iva-06|casual|en", jittery_talk)
    questions = [m for m in messages if m["type"] == "question" and m.get("question")]
    assert len(questions) == 1 and speaker.transcribed == [48000], "one transcription with all the audio, one question"
    assert metrics["questions_answered"] == 1 and metrics["answers_spoken"] == 1


def test_talk_start_cancels_the_speaker_at_once() -> None:
    """Barge-in on the server side: the press cancels the current line before any transcription happens."""
    speaker = FakeSpeaker()
    with TestClient(app) as client:
        async def factory():
            return speaker

        app.state.speaker_factory = factory
        app.state.workflow_factory = template_workflow
        client.post("/api/match/start", json={"seed": 7, "speed": 1500, "delay_s": 120, "minutes": 4})
        with client.websocket_connect("/api/voice?profile=-|-|casual|en") as ws:
            before = getattr(speaker, "cancelled", 0)
            ws.send_text(json.dumps({"type": "talk_start"}))
            ws.send_text(json.dumps({"type": "talk_end"}))  # too short: no transcription, but the cancel already happened
            while True:
                m = ws.receive()
                if m.get("text") and json.loads(m["text"]).get("type") == "question":
                    break
            assert speaker.cancelled == before + 1
            assert getattr(speaker, "transcribed", []) in ([], [0]), "nothing was transcribed, yet the line was cancelled"


def test_a_new_press_supersedes_a_slow_transcription() -> None:
    def two_quick_presses(ws):
        for _ in range(2):
            ws.send_text(json.dumps({"type": "talk_start"}))
            ws.send_bytes(b"\x00\x01" * 12000)
            ws.send_bytes(b"\x00\x01" * 12000)
            ws.send_text(json.dumps({"type": "talk_end"}))

    speaker_holder = {}

    def make_speaker():
        speaker = FakeSpeaker()
        speaker.transcribe_delay = 0.25
        speaker_holder["s"] = speaker
        return speaker

    speaker = make_speaker()
    messages, _, metrics, _ = ask_over_voice("iva|iva-06|casual|en", two_quick_presses, speaker=speaker)
    questions = [m for m in messages if m["type"] == "question" and m.get("question")]
    assert len(questions) == 1, "the first utterance was superseded before its slow transcription finished"
    assert metrics["transcriptions_superseded"] == 1 and metrics["questions_answered"] == 1
    assert len(speaker.transcribed) == 2, "both transcriptions started; the first was cancelled"


def test_a_line_cut_off_in_the_browser_is_marked_interrupted() -> None:
    """The server finished sending the line long before the fan pressed; the page names the line it cut off."""
    speaker = FakeSpeaker()
    with TestClient(app) as client:
        async def factory():
            return speaker

        app.state.speaker_factory = factory
        app.state.workflow_factory = template_workflow
        client.post("/api/match/start", json={"seed": 30, "speed": 1500, "delay_s": 10, "minutes": 8})
        with client.stream("GET", "/api/stream/cues") as stream:
            for line in stream.iter_lines():
                if line.startswith("event: match_end"):
                    break
        with client.websocket_connect("/api/voice?profile=iva|iva-07|casual|en") as ws:
            spoken = None
            while spoken is None:
                m = ws.receive()
                if m.get("text") and json.loads(m["text"])["type"] == "spoken":
                    spoken = json.loads(m["text"])["audit"]
            assert spoken["interrupted"] is False and spoken["moment_id"]
            ws.send_text(json.dumps({"type": "talk_start", "interrupting": spoken["moment_id"]}))
            updated = None
            while updated is None:
                m = ws.receive()
                if m.get("text") and json.loads(m["text"])["type"] == "audit_updated":
                    updated = json.loads(m["text"])["audit"]
            assert updated["moment_id"] == spoken["moment_id"] and updated["interrupted"] is True and updated["ok"] is True
            ws.send_text(json.dumps({"type": "talk_end"}))
        audits = client.get("/api/match/audits").json()["audits"]
        assert [a for a in audits if a["moment_id"] == spoken["moment_id"]][-1]["interrupted"] is True
        assert app.state.run.metrics["lines_interrupted"] == 1
        assert app.state.run.mark_interrupted("nonexistent") is None


def test_a_client_that_leaves_mid_line_closes_quietly(caplog) -> None:
    """A profile switch closes the old socket from the browser; the server must not log an error or close twice."""
    speaker = FakeSpeaker()
    speaker.transcribe_delay = 0.3
    with TestClient(app) as client:
        async def factory():
            return speaker

        app.state.speaker_factory = factory
        app.state.workflow_factory = template_workflow
        client.post("/api/match/start", json={"seed": 30, "speed": 150, "delay_s": 20, "minutes": 60})
        with caplog.at_level(logging.WARNING, logger="app.api.voice_ws"):
            with client.websocket_connect("/api/voice?profile=iva|iva-07|casual|en") as ws:
                ws.send_text(json.dumps({"type": "talk_start"}))
                ws.send_bytes(b"\x00\x01" * 24000)
                ws.send_text(json.dumps({"type": "talk_end"}))
                # leave while the transcription task, the answer and the speech are still in flight
            import time

            time.sleep(0.6)
        client.post("/api/match/stop")
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], [r.getMessage() for r in caplog.records]
    assert not any("voice task failed" in r.getMessage() for r in caplog.records)
    assert speaker.closed


def test_client_gone_detection_and_quiet_close() -> None:
    from types import SimpleNamespace

    from app.api.voice_ws import _client_gone, _close_quietly

    gone = SimpleNamespace(client_state=WebSocketState.DISCONNECTED, application_state=WebSocketState.CONNECTED)
    here = SimpleNamespace(client_state=WebSocketState.CONNECTED, application_state=WebSocketState.CONNECTED)
    assert _client_gone(gone, RuntimeError("x")) is True
    assert _client_gone(here, type("ClientDisconnected", (OSError,), {})()) is True
    assert _client_gone(here, RuntimeError("real bug")) is False

    closed = []

    async def close():
        closed.append(True)
        raise RuntimeError("already closed")

    import asyncio

    asyncio.run(_close_quietly(SimpleNamespace(client_state=WebSocketState.CONNECTED, application_state=WebSocketState.CONNECTED, close=close)))
    asyncio.run(_close_quietly(SimpleNamespace(client_state=WebSocketState.DISCONNECTED, application_state=WebSocketState.CONNECTED, close=close)))
    assert closed == [True], "close is attempted once while connected, swallowed when it races, skipped when the client is gone"
