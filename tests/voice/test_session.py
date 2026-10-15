"""VoiceLiveSpeaker against fake connections: two connections, event routing, typed session updates, error isolation."""

import asyncio
import base64
import json
from types import SimpleNamespace

import pytest

import app.voice.session as session
from app.voice.session import SAMPLE_RATE, SpeechError, TranscriptionError, VoiceLiveSpeaker, listening_session_update, speaking_session_update


@pytest.fixture(autouse=True)
def quick_waits(monkeypatch):
    monkeypatch.setattr(session, "COMMIT_WAIT_S", 0.05)
    monkeypatch.setattr(session, "CREATED_WAIT_S", 0.1)
    monkeypatch.setattr(session, "SESSION_UPDATE_TIMEOUT_S", 1.0)


def ev(kind: str, **fields):
    return SimpleNamespace(type=kind, **fields)


class FakeConnection:
    """Records what was sent; replies with scripted events per sent event type."""

    def __init__(self, created_vad: str | None = "azure_semantic_vad") -> None:
        self.sent: list[dict] = []
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.on_send: dict[str, callable] = {}
        if created_vad:
            self.incoming.put_nowait(ev("session.created", session={"turn_detection": {"type": created_vad}, "voice": "x"}))
        self.on_send["session.update"] = lambda p: [ev("session.updated")]

    async def send(self, event) -> None:
        payload = event.as_dict() if hasattr(event, "as_dict") else dict(event)
        self.sent.append(payload)
        for reply in self.on_send.get(payload["type"], lambda p: [])(payload):
            self.incoming.put_nowait(reply)

    async def recv(self):
        return await self.incoming.get()

    def sent_types(self) -> list[str]:
        return [p["type"] for p in self.sent]


def speaking_replies(p):
    text = p["response"]["pre_generated_assistant_message"]["content"][0]["text"]
    return [ev("response.audio.delta", delta=b"\x01\x02" * 100), ev("response.audio_transcript.delta", delta=text), ev("response.done", response=SimpleNamespace(status="completed"))]


def listening_replies(p):
    return [ev("input_audio_buffer.committed", item_id="i1"), ev("conversation.item.input_audio_transcription.completed", item_id="i1", content_index=0, transcript=" how is my player doing ")]


class Fakes:
    """Hands out the speaking connection first, then the listening one."""

    def __init__(self, created_vad="azure_semantic_vad") -> None:
        self.speaking = FakeConnection(created_vad)
        self.speaking.on_send["response.create"] = speaking_replies
        self.listening = FakeConnection(created_vad)
        self.listening.on_send["input_audio_buffer.commit"] = listening_replies
        self._queue = [self.speaking, self.listening]

    async def factory(self):
        return self._queue.pop(0)


async def opened(fakes: Fakes) -> VoiceLiveSpeaker:
    return await VoiceLiveSpeaker("https://example/", connection_factory=fakes.factory).open()


async def no_audio(_: bytes) -> None:
    return None


def test_session_updates_are_valid_and_never_change_the_vad_type() -> None:
    speaking = speaking_session_update("tr-TR-EmelNeural")
    assert speaking["type"] == "session.update" and "turn_detection" not in speaking["session"]
    assert speaking["session"]["voice"] == {"name": "tr-TR-EmelNeural", "type": "azure-standard"}
    listening = listening_session_update("tr", "azure-speech", "azure_semantic_vad").as_dict()
    session = listening["session"]
    assert listening["type"] == "session.update" and "voice" not in session and "modalities" not in session
    assert session["turn_detection"] == {"type": "azure_semantic_vad", "create_response": False, "interrupt_response": False, "silence_duration_ms": 400}
    assert session["input_audio_transcription"] == {"model": "azure-speech", "language": "tr-TR"}
    assert session["input_audio_format"] == "pcm16" and session["input_audio_sampling_rate"] == SAMPLE_RATE
    assert listening_session_update("en", "whisper-1", "server_vad").as_dict()["session"]["turn_detection"]["type"] == "server_vad"
    assert listening_session_update("en", "whisper-1", "azure_semantic_vad_en").as_dict()["session"]["turn_detection"]["type"] == "azure_semantic_vad_en"
    json.dumps(listening)


async def test_speak_streams_audio_and_sets_the_voice_once_per_language() -> None:
    fakes = Fakes()
    speaker = await opened(fakes)
    chunks = []

    async def collect(b):
        chunks.append(b)

    assert await speaker.speak("Kestrel Bay have 14 passes.", "en", collect) == "Kestrel Bay have 14 passes."
    assert chunks == [b"\x01\x02" * 100]
    await speaker.speak("Ikinci satır.", "tr", collect)
    await speaker.speak("Third.", "en", collect)
    await speaker.speak("Fourth.", "en", collect)
    assert fakes.speaking.sent_types().count("session.update") == 3 and fakes.speaking.sent_types().count("response.create") == 4
    assert fakes.listening.sent == [], "speaking never opens or touches the listening connection"
    await speaker.close()


async def test_transcribe_uses_a_second_connection_with_the_created_vad_type() -> None:
    fakes = Fakes(created_vad="azure_semantic_vad")
    speaker = await opened(fakes)
    pcm = b"\x00\x10" * 24000
    assert await speaker.transcribe(pcm, "en") == "how is my player doing"
    kinds = fakes.listening.sent_types()
    assert kinds[0] == "session.update" and kinds[-1] == "input_audio_buffer.commit" and "input_audio_buffer.append" in kinds
    update = fakes.listening.sent[0]["session"]
    assert update["turn_detection"]["type"] == "azure_semantic_vad" and update["turn_detection"]["create_response"] is False
    assert update["input_audio_transcription"] == {"model": "azure-speech", "language": "en-US"}
    appended = b"".join(base64.b64decode(p["audio"]) for p in fakes.listening.sent if p["type"] == "input_audio_buffer.append")
    assert appended.startswith(pcm) and len(appended) == len(pcm) + int(SAMPLE_RATE * 2 * 0.6)
    assert fakes.speaking.sent == [], "listening never touches the speaking connection"
    await speaker.transcribe(pcm, "en")
    assert fakes.listening.sent_types().count("session.update") == 1, "the listening session is configured once per language"
    await speaker.transcribe(pcm, "tr")
    assert fakes.listening.sent[-1 - 1 - len(pcm) // 48000 - 1]["type"] == "session.update" or fakes.listening.sent_types().count("session.update") == 2
    await speaker.close()


async def test_default_vad_type_when_the_server_announces_none() -> None:
    fakes = Fakes(created_vad=None)
    fakes.listening.on_send["input_audio_buffer.append"] = lambda p: [ev("input_audio_buffer.committed", item_id="i2"), ev("conversation.item.input_audio_transcription.completed", item_id="i2", content_index=0, transcript="skor ne")]
    speaker = await opened(fakes)
    assert await speaker.transcribe(b"\x00\x01" * 100, "tr") == "skor ne"
    assert fakes.listening.sent[0]["session"]["turn_detection"]["type"] == "server_vad"
    assert "input_audio_buffer.commit" not in fakes.listening.sent_types(), "no manual commit when the VAD already committed"
    await speaker.close()


async def test_transcription_errors_are_isolated_from_speaking() -> None:
    fakes = Fakes()
    fakes.listening.on_send["input_audio_buffer.commit"] = lambda p: [ev("error", error={"message": "bad audio", "type": "invalid_request_error", "code": "x"})]
    speaker = await opened(fakes)
    with pytest.raises(TranscriptionError, match="bad audio"):
        await speaker.transcribe(b"\x00\x01" * 1000, "en")
    assert await speaker.speak("Still speaking.", "en", no_audio) == "Still speaking."

    fakes2 = Fakes()
    fakes2.listening.on_send["session.update"] = lambda p: [ev("error", error={"message": "Cannot disable turn detection during session", "code": "turn_detection_type_change_not_allowed"})]
    speaker2 = await opened(fakes2)
    with pytest.raises(TranscriptionError, match="turn_detection_type_change_not_allowed"):
        await speaker2.transcribe(b"\x00\x01" * 1000, "en")
    assert await speaker2.speak("Voice unaffected.", "en", no_audio) == "Voice unaffected.", "a rejected listening update never breaks speak()"

    fakes3 = Fakes()
    fakes3.listening.on_send["input_audio_buffer.commit"] = lambda p: [ev("conversation.item.input_audio_transcription.failed", item_id="i", content_index=0, error={"message": "no speech"})]
    speaker3 = await opened(fakes3)
    with pytest.raises(TranscriptionError, match="no speech"):
        await speaker3.transcribe(b"\x00\x01" * 1000, "en")
    for s in (speaker, speaker2, speaker3):
        await s.close()


async def test_speaking_errors_raise_speech_error_and_do_not_leak_into_transcription() -> None:
    fakes = Fakes()
    fakes.speaking.on_send["session.update"] = lambda p: [ev("error", error={"message": "invalid voice", "code": "invalid_session_update_message"})]
    speaker = await opened(fakes)
    with pytest.raises(SpeechError, match="invalid voice"):
        await speaker.speak("x", "en", no_audio)
    assert await speaker.transcribe(b"\x00\x01" * 1000, "en") == "how is my player doing"
    await speaker.close()


async def test_cancel_only_while_speaking_and_drops_remaining_audio() -> None:
    fakes = Fakes()
    speaker = await opened(fakes)
    await speaker.cancel()
    assert "response.cancel" not in fakes.speaking.sent_types(), "nothing to cancel yet"
    gate = asyncio.Event()
    fakes.speaking.on_send["response.create"] = lambda p: [ev("response.audio.delta", delta=b"\x01" * 10)]

    async def finish_later():
        await gate.wait()
        fakes.speaking.incoming.put_nowait(ev("response.audio.delta", delta=b"\x02" * 10))
        fakes.speaking.incoming.put_nowait(ev("response.done", response=SimpleNamespace(status="cancelled")))

    chunks = []

    async def collect(b):
        chunks.append(b)
        await speaker.cancel()
        gate.set()

    asyncio.get_running_loop().create_task(finish_later())
    await speaker.speak("long line", "en", collect)
    assert chunks == [b"\x01" * 10] and "response.cancel" in fakes.speaking.sent_types()
    await speaker.close()


async def test_socket_loss_surfaces_as_an_error_not_a_hang() -> None:
    fakes = Fakes()
    speaker = await opened(fakes)
    await asyncio.sleep(0.01)

    async def broken_recv():
        await asyncio.sleep(0)
        raise ConnectionError("socket closed")

    fakes.speaking.recv = broken_recv
    await asyncio.sleep(0.01)
    with pytest.raises(SpeechError, match="socket closed"):
        await speaker.speak("x", "en", no_audio)
    await speaker.close()
