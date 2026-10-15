import json
import re

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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

    async def close(self) -> None:
        self.closed = True


def run_voice(speaker: FakeSpeaker | None, lang: str = "en") -> tuple[list[dict], int, dict]:
    """Start a short precomputed match, listen on /api/voice until it closes."""
    messages, audio_bytes = [], 0
    with TestClient(app) as client:
        async def factory():
            return speaker

        app.state.speaker_factory = factory if speaker else None
        app.state.workflow_factory = template_workflow
        started = client.post("/api/match/start", json={"seed": 7, "speed": 600, "delay_s": 120, "minutes": 10})
        assert started.status_code == 200
        with client.websocket_connect(f"/api/voice?lang={lang}") as ws:
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
