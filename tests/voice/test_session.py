"""VoiceLiveSpeaker against fake connections: two connections, event routing, the verified session update, error
isolation, and no waiting forever on a silent socket."""

import asyncio
import base64
import json
from types import SimpleNamespace

import pytest

import app.voice.session as session
from app.voice.session import MIN_UTTERANCE_BYTES, SAMPLE_RATE, NothingHeard, SpeechError, TranscriptionError, VoiceLiveSpeaker, listening_session_update, speaking_session_update


@pytest.fixture(autouse=True)
def quick_waits(monkeypatch):
    monkeypatch.setattr(session, "COMMIT_WAIT_S", 0.05)
    monkeypatch.setattr(session, "SESSION_UPDATE_TIMEOUT_S", 0.5)
    monkeypatch.setattr(session, "SPEAK_IDLE_TIMEOUT_S", 0.3)
    monkeypatch.setattr(session, "TRANSCRIBE_TIMEOUT_S", 0.5)


def ev(kind: str, **fields):
    return SimpleNamespace(type=kind, **fields)


class FakeConnection:
    """Records what was sent; replies with scripted events per sent event type. An Exception placed on `incoming`
    is raised by recv(), which is how a test breaks the socket under the running receive pump."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.on_send: dict[str, callable] = {}
        self.on_send["session.update"] = lambda p: [ev("session.updated")]

    async def send(self, event) -> None:
        payload = event.as_dict() if hasattr(event, "as_dict") else dict(event)
        self.sent.append(payload)
        for reply in self.on_send.get(payload["type"], lambda p: [])(payload):
            self.incoming.put_nowait(reply)

    async def recv(self):
        item = await self.incoming.get()
        if isinstance(item, Exception):
            raise item
        return item

    def sent_types(self) -> list[str]:
        return [p["type"] for p in self.sent]


def speaking_replies(p):
    text = p["response"]["pre_generated_assistant_message"]["content"][0]["text"]
    return [ev("response.audio.delta", delta=b"\x01\x02" * 100), ev("response.audio_transcript.delta", delta=text), ev("response.done", response=SimpleNamespace(status="completed"))]


def listening_replies(p):
    return [ev("input_audio_buffer.committed", item_id="i1"), ev("conversation.item.input_audio_transcription.completed", item_id="i1", content_index=0, transcript=" how is my player doing ")]


class Fakes:
    """Hands out the speaking connection first, then the listening one."""

    def __init__(self) -> None:
        self.speaking = FakeConnection()
        self.speaking.on_send["response.create"] = speaking_replies
        self.listening = FakeConnection()
        self.listening.on_send["input_audio_buffer.commit"] = listening_replies
        self._queue = [self.speaking, self.listening]

    async def factory(self):
        return self._queue.pop(0)


async def opened(fakes: Fakes) -> VoiceLiveSpeaker:
    return await VoiceLiveSpeaker("https://example/", connection_factory=fakes.factory).open()


async def no_audio(_: bytes) -> None:
    return None


def test_listening_session_update_is_the_verified_payload_plus_locale_and_phrase_list() -> None:
    payload = listening_session_update("en")
    transcription = payload["session"]["input_audio_transcription"]
    assert payload["type"] == "session.update"
    assert payload["session"]["input_audio_format"] == "pcm16"
    assert payload["session"]["turn_detection"] == {"type": "azure_semantic_vad", "create_response": False}
    assert transcription["model"] == "azure-speech" and transcription["language"] == "en-US"
    phrases = transcription["phrase_list"]
    assert {"score", "goal", "possession", "why", "Kestrel Bay", "Ironvale", "Jory Calloway", "Remy Tallis", "Luca Brightwater"} <= set(phrases)
    assert len(phrases) == len(set(phrases)) and all(isinstance(p, str) and p for p in phrases)
    tr = listening_session_update("tr")["session"]["input_audio_transcription"]
    assert tr["language"] == "tr-TR" and {"skor", "gol", "şut", "pas", "oyuncum", "neden", "nasıl", "kaç", "Jory Calloway"} <= set(tr["phrase_list"])
    plain = listening_session_update("en", bias=False)
    assert plain == {"type": "session.update", "session": {"input_audio_format": "pcm16", "turn_detection": {"type": "azure_semantic_vad", "create_response": False},
                                                            "input_audio_transcription": {"model": "azure-speech", "language": "en-US"}}}, "the fallback is exactly the verified payload"
    assert listening_session_update("tr", vad_type="azure_semantic_vad_multilingual")["session"]["turn_detection"]["type"] == "azure_semantic_vad_multilingual"
    json.dumps(payload)
    speaking = speaking_session_update("tr-TR-EmelNeural")
    assert speaking["type"] == "session.update" and "turn_detection" not in speaking["session"]
    assert speaking["session"]["voice"] == {"name": "tr-TR-EmelNeural", "type": "azure-standard"}


async def test_rejected_phrase_list_falls_back_to_the_plain_payload() -> None:
    fakes = Fakes()
    updates = []

    def session_reply(p):
        updates.append(p)
        if "phrase_list" in p["session"].get("input_audio_transcription", {}):
            return [ev("error", error={"message": "Unknown parameter: 'session.input_audio_transcription.phrase_list'", "type": "invalid_request_error", "param": "session.input_audio_transcription.phrase_list"})]
        return [ev("session.updated")]

    fakes.listening.on_send["session.update"] = session_reply
    speaker = await opened(fakes)
    assert await speaker.transcribe(b"\x00\x10" * MIN_UTTERANCE_BYTES, "en") == "how is my player doing"
    assert len(updates) == 2 and "phrase_list" in updates[0]["session"]["input_audio_transcription"] and "phrase_list" not in updates[1]["session"]["input_audio_transcription"]
    assert updates[1] == listening_session_update("en", bias=False)
    await speaker.transcribe(b"\x00\x10" * MIN_UTTERANCE_BYTES, "tr")
    assert "phrase_list" not in updates[-1]["session"]["input_audio_transcription"], "once rejected, the phrase list stays off"
    await speaker.close()


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


async def test_transcribe_uses_a_second_connection_with_the_verified_update_first() -> None:
    fakes = Fakes()
    speaker = await opened(fakes)
    pcm = b"\x00\x10" * 24000
    assert await speaker.transcribe(pcm, "en") == "how is my player doing"
    kinds = fakes.listening.sent_types()
    assert kinds[0] == "session.update" and kinds[-1] == "input_audio_buffer.commit" and "input_audio_buffer.append" in kinds
    assert fakes.listening.sent[0] == listening_session_update("en"), "the first update on the listening connection is the verified payload with locale and phrase list"
    appended = b"".join(base64.b64decode(p["audio"]) for p in fakes.listening.sent if p["type"] == "input_audio_buffer.append")
    assert appended.startswith(pcm) and len(appended) == len(pcm) + int(SAMPLE_RATE * 2 * 0.6)
    assert fakes.speaking.sent == [], "listening never touches the speaking connection"
    await speaker.transcribe(pcm, "en")
    assert fakes.listening.sent_types().count("session.update") == 1, "configured once per language"
    await speaker.transcribe(pcm, "tr")
    updates = [p for p in fakes.listening.sent if p["type"] == "session.update"]
    assert len(updates) == 2 and updates[1]["session"]["input_audio_transcription"]["language"] == "tr-TR"
    assert updates[1]["session"]["turn_detection"]["type"] == "azure_semantic_vad", "the VAD type never changes after the first update"
    await speaker.close()


async def test_vad_commit_is_used_when_it_arrives_first(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_LISTEN_VAD_TR", "azure_semantic_vad_multilingual")
    fakes = Fakes()
    fakes.listening.on_send["input_audio_buffer.append"] = lambda p: [ev("input_audio_buffer.speech_stopped"), ev("input_audio_buffer.committed", item_id="i2"), ev("conversation.item.input_audio_transcription.completed", item_id="i2", content_index=0, transcript="skor ne")]
    speaker = await opened(fakes)
    assert await speaker.transcribe(b"\x00\x01" * MIN_UTTERANCE_BYTES, "tr") == "skor ne"
    assert fakes.listening.sent[0]["session"]["turn_detection"]["type"] == "azure_semantic_vad_multilingual", "the env override for Turkish is honoured"
    assert "input_audio_buffer.commit" not in fakes.listening.sent_types(), "no manual commit when the VAD already committed"
    await speaker.close()


async def test_transcription_errors_are_isolated_from_speaking() -> None:
    fakes = Fakes()
    fakes.listening.on_send["input_audio_buffer.commit"] = lambda p: [ev("error", error={"message": "bad audio", "type": "invalid_request_error", "code": "x"})]
    speaker = await opened(fakes)
    with pytest.raises(TranscriptionError, match="bad audio"):
        await speaker.transcribe(b"\x00\x01" * MIN_UTTERANCE_BYTES, "en")
    assert await speaker.speak("Still speaking.", "en", no_audio) == "Still speaking."

    fakes2 = Fakes()
    fakes2.listening.on_send["session.update"] = lambda p: [ev("error", error={"message": "Cannot disable turn detection during session", "code": "turn_detection_type_change_not_allowed"})]
    speaker2 = await opened(fakes2)
    with pytest.raises(TranscriptionError, match="turn_detection_type_change_not_allowed"):
        await speaker2.transcribe(b"\x00\x01" * MIN_UTTERANCE_BYTES, "en")
    assert await speaker2.speak("Voice unaffected.", "en", no_audio) == "Voice unaffected.", "a rejected listening update never breaks speak()"

    fakes3 = Fakes()
    fakes3.listening.on_send["input_audio_buffer.commit"] = lambda p: [ev("conversation.item.input_audio_transcription.failed", item_id="i", content_index=0, error={"message": "no speech"})]
    speaker3 = await opened(fakes3)
    with pytest.raises(TranscriptionError, match="no speech"):
        await speaker3.transcribe(b"\x00\x01" * MIN_UTTERANCE_BYTES, "en")
    for s in (speaker, speaker2, speaker3):
        await s.close()


async def test_speaking_errors_raise_speech_error_and_do_not_leak_into_transcription() -> None:
    fakes = Fakes()
    fakes.speaking.on_send["session.update"] = lambda p: [ev("error", error={"message": "invalid voice", "code": "invalid_session_update_message"})]
    speaker = await opened(fakes)
    with pytest.raises(SpeechError, match="invalid voice"):
        await speaker.speak("x", "en", no_audio)
    assert await speaker.transcribe(b"\x00\x01" * MIN_UTTERANCE_BYTES, "en") == "how is my player doing"
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
    fakes.speaking.on_send["response.create"] = lambda p: [ConnectionError("socket closed")]  # recv raises under the pump
    with pytest.raises(SpeechError, match="socket closed"):
        await speaker.speak("x", "en", no_audio)
    fakes.listening.on_send["input_audio_buffer.commit"] = lambda p: [ConnectionError("socket closed")]
    with pytest.raises(TranscriptionError, match="socket closed"):
        await speaker.transcribe(b"\x00\x01" * MIN_UTTERANCE_BYTES, "en")
    await speaker.close()


async def test_silent_socket_times_out_instead_of_waiting_forever() -> None:
    fakes = Fakes()
    speaker = await opened(fakes)
    fakes.speaking.on_send["response.create"] = lambda p: [ev("response.audio.delta", delta=b"\x01" * 4)]  # then nothing, ever
    with pytest.raises(SpeechError, match="sent nothing"):
        await speaker.speak("x", "en", no_audio)
    fakes.listening.on_send["input_audio_buffer.commit"] = lambda p: [ev("input_audio_buffer.committed", item_id="i")]  # committed, no transcript
    with pytest.raises(TranscriptionError, match="in time"):
        await speaker.transcribe(b"\x00\x01" * MIN_UTTERANCE_BYTES, "en")
    fakes.speaking.on_send["response.create"] = speaking_replies
    assert await speaker.speak("Back.", "en", no_audio) == "Back.", "a timed-out line does not poison the next one"
    await speaker.close()


async def test_empty_utterances_fail_at_once_not_by_timeout() -> None:
    fakes = Fakes()
    speaker = await opened(fakes)
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(NothingHeard, match="shorter than"):
        await speaker.transcribe(b"\x00\x01" * 100, "en")
    assert fakes.listening.sent == [], "nothing is sent for a too-short utterance"
    fakes.listening.on_send["input_audio_buffer.commit"] = lambda p: [ev("error", error={"message": "Error committing input audio buffer: buffer too small", "type": "invalid_request_error", "code": "input_audio_buffer_commit_empty"})]
    with pytest.raises(NothingHeard, match="input_audio_buffer_commit_empty"):
        await speaker.transcribe(b"\x00\x01" * MIN_UTTERANCE_BYTES, "en")
    assert loop.time() - started < 0.4, "the commit-empty error ends the utterance immediately"
    assert isinstance(NothingHeard("x"), TranscriptionError)
    assert await speaker.speak("Still fine.", "en", no_audio) == "Still fine."
    await speaker.close()
