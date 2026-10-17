"""Voice Live speaker and listener: speaks approved text verbatim, transcribes push-to-talk questions, audits what
was spoken (SPEC design rule 6).

Two connections, because Voice Live refuses to change the turn-detection type during a session:
- the **speaking** connection only ever sets the voice and output format (as in S5) and sends `response.create`
  with `pre_generated_assistant_message`, so the realtime model never authors spoken words;
- the **listening** connection is opened on the first push-to-talk question. Its first `session.update` is the one
  verified against the service on 2026-10-15: pcm16 input, `azure_semantic_vad` with `create_response=false` (the
  model never answers by itself; azure-speech transcription requires a semantic VAD) and `azure-speech`
  transcription in the fan's language, which keeps digits as digits. Audio goes to the input buffer, the buffer is
  committed, and `conversation.item.input_audio_transcription.completed` carries the words.
Each connection has its own receive pump, so an error on one never breaks the other, and neither speaking nor
transcribing waits forever on a silent socket.
"""

import asyncio
import base64
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol

log = logging.getLogger(__name__)

Lang = Literal["en", "tr"]
OnAudio = Callable[[bytes], Awaitable[None]]

SAMPLE_RATE = 24000  # pcm16 mono, in and out
VOICES: dict[str, str] = {"en": "en-US-AvaMultilingualNeural", "tr": "tr-TR-EmelNeural"}
LISTEN_VAD: dict[str, str] = {"en": "azure_semantic_vad", "tr": "azure_semantic_vad"}  # VOICE_LISTEN_VAD_TR=azure_semantic_vad_multilingual if Turkish needs it
SILENCE_TAIL_S = 0.6
COMMIT_WAIT_S = 1.5
SPEAK_IDLE_TIMEOUT_S = 15.0   # no event while speaking: the socket is silent, give up on the line
TRANSCRIBE_TIMEOUT_S = 20.0   # whole transcription, from the last appended chunk to the transcript
SESSION_UPDATE_TIMEOUT_S = 6.0
AUDIO_CHUNK_BYTES = SAMPLE_RATE * 2  # 1.0 s chunk of 24 kHz pcm16 audio (48,000 bytes)


class SpeechError(RuntimeError):
    """Voice Live refused or failed a spoken line."""


class TranscriptionError(RuntimeError):
    """Voice Live could not transcribe a push-to-talk utterance; the voice itself keeps working."""


class NothingHeard(TranscriptionError):
    """The utterance was empty or too short (Voice Live: input_audio_buffer_commit_empty). Fails at once, never by timeout."""


MIN_UTTERANCE_BYTES = SAMPLE_RATE * 2 // 5  # 0.2 s of pcm16 at 24 kHz


class Speaker(Protocol):
    async def speak(self, text: str, lang: Lang, on_audio: OnAudio) -> str:
        """Speak `text` verbatim, stream pcm16 chunks to `on_audio`, return the transcript of what was spoken."""
        ...

    async def cancel(self) -> None:
        """Barge-in: stop the current response; the browser drops its own playback buffer."""
        ...

    async def transcribe(self, pcm16: bytes, lang: Lang) -> str:
        """Transcribe one push-to-talk utterance (pcm16 mono 24 kHz). Raises TranscriptionError, never breaks speak()."""
        ...

    async def close(self) -> None: ...


def speaking_session_update(voice: str) -> dict[str, Any]:
    """The S5 update: voice and pcm16 output only; turn detection is never touched on this connection."""
    return {"type": "session.update", "session": {"modalities": ["text", "audio"], "voice": {"name": voice, "type": "azure-standard"}, "output_audio_format": "pcm16"}}


TRANSCRIBE_LOCALE: dict[str, str] = {"en": "en-US", "tr": "tr-TR"}
FOOTBALL_PHRASES: dict[str, list[str]] = {
    "en": ["score", "goal", "goals", "shot", "shots", "pass", "passes", "possession", "pressing", "press", "why", "how is my player",
           "player", "minute", "Kestrel Bay", "Ironvale", "Meridian League"],
    "tr": ["skor", "gol", "şut", "pas", "top", "topa sahip", "oyuncu", "oyuncum", "neden", "nasıl", "kaç", "baskı", "dakika",
           "Kestrel Bay", "Ironvale", "Meridian Ligi"],
}


def phrase_list(lang: Lang) -> list[str]:
    """Recognition bias: football vocabulary in the fan's language plus every club and player name of the league."""
    from app.simulator.league import CLUBS, PLAYERS

    names = [c.name for c in CLUBS.values()] + [c.short for c in CLUBS.values()] + [p.name for p in PLAYERS.values()]
    return list(dict.fromkeys(FOOTBALL_PHRASES[lang] + names))


def listening_session_update(lang: Lang, transcribe_model: str = "azure-speech", vad_type: str | None = None, bias: bool = True) -> dict[str, Any]:
    """The first update on the listening connection: the payload verified against the service (pcm16, a semantic VAD
    that never creates a response, azure-speech), with the full locale and a phrase list for football words and the
    league's names. `bias=False` is the fallback payload without the phrase list."""
    transcription: dict[str, Any] = {"model": transcribe_model, "language": TRANSCRIBE_LOCALE[lang]}
    if bias:
        transcription["phrase_list"] = phrase_list(lang)
    return {
        "type": "session.update",
        "session": {
            "input_audio_format": "pcm16",
            "turn_detection": {"type": vad_type or LISTEN_VAD[lang], "create_response": False},
            "input_audio_transcription": transcription,
        },
    }


class _ClosedEvent:
    type = "closed"

    def __init__(self, message: str) -> None:
        self.error = {"message": message}


def _error_of(event: Any) -> Any:
    return getattr(event, "error", None) or getattr(event, "type", "unknown")


class _Channel:
    """One Voice Live connection with a receive pump that routes events to the waiting operation."""

    def __init__(self, connection: Any, name: str) -> None:
        self.connection = connection
        self.name = name
        self.events: asyncio.Queue = asyncio.Queue()
        self.session_events: asyncio.Queue = asyncio.Queue()
        self.active = False
        self.last_error: dict[str, Any] | None = None
        self._pump: asyncio.Task | None = None

    def start(self) -> None:
        self._pump = asyncio.create_task(self._pump_events())

    async def _pump_events(self) -> None:
        try:
            while True:
                event = await self.connection.recv()
                kind = str(getattr(event, "type", ""))
                if kind == "session.updated":
                    self.session_events.put_nowait(event)
                elif kind == "error":
                    self.last_error = dict(getattr(event, "error", {}) or {})
                    log.warning("Voice Live %s error: %s", self.name, self.last_error)
                    self.session_events.put_nowait(event)
                    if self.active:
                        self.events.put_nowait(event)
                elif self.active:
                    self.events.put_nowait(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # the socket went away: wake every waiter
            log.warning("Voice Live %s receive loop ended: %s", self.name, exc)
            closed = _ClosedEvent(str(exc))
            self.events.put_nowait(closed)
            self.session_events.put_nowait(closed)

    async def update_session(self, event: Any, error_cls: type[RuntimeError]) -> None:
        while not self.session_events.empty():
            leftover = self.session_events.get_nowait()
            if str(getattr(leftover, "type", "")) == "closed":
                raise error_cls(f"Voice Live {self.name} connection is closed")
        await self.connection.send(event)
        while True:
            try:
                reply = await asyncio.wait_for(self.session_events.get(), timeout=SESSION_UPDATE_TIMEOUT_S)
            except TimeoutError as exc:
                raise error_cls(f"Voice Live {self.name} session update was not acknowledged") from exc
            kind = str(getattr(reply, "type", ""))
            if kind == "session.updated":
                return
            if kind in ("error", "closed"):
                raise error_cls(f"Voice Live rejected the {self.name} session update: {_error_of(reply)}")

    def drain(self) -> None:
        while not self.events.empty():
            self.events.get_nowait()

    async def close(self) -> None:
        if self._pump is not None:
            self._pump.cancel()
            try:
                await self._pump
            except (asyncio.CancelledError, Exception):
                pass


class VoiceLiveSpeaker:
    """One listener's voice: a speaking connection, plus a listening connection opened on the first question."""

    def __init__(self, endpoint: str, model: str = "gpt-realtime", transcribe_model: str = "azure-speech",
                 connection_factory: Callable[[], Awaitable[Any]] | None = None) -> None:
        self.endpoint = endpoint
        self.model = model
        self.transcribe_model = transcribe_model
        self._connection_factory = connection_factory  # injected in tests; otherwise Voice Live
        self._managers: list[Any] = []
        self._credential = None
        self._speaking: _Channel | None = None
        self._listening: _Channel | None = None
        self._voice: str | None = None
        self._listen_lang: Lang | None = None
        self._cancelled = False
        self._bias = True  # phrase-list bias on the listening session; switched off if the service rejects the field

    async def _connect(self, name: str) -> _Channel:
        if self._connection_factory is not None:
            connection = await self._connection_factory()
        else:
            from azure.ai.voicelive.aio import connect
            from azure.identity.aio import DefaultAzureCredential

            self._credential = self._credential or DefaultAzureCredential()
            manager = connect(endpoint=self.endpoint, credential=self._credential, model=self.model)
            connection = await manager.__aenter__()
            self._managers.append(manager)
        channel = _Channel(connection, name)
        channel.start()
        return channel

    async def open(self) -> "VoiceLiveSpeaker":
        self._speaking = await self._connect("speaking")
        return self

    # ----- speaking -----
    async def speak(self, text: str, lang: Lang, on_audio: OnAudio) -> str:
        assert self._speaking is not None, "open() first"
        channel = self._speaking
        voice = VOICES[lang]
        if voice != self._voice:
            await channel.update_session(speaking_session_update(voice), SpeechError)
            self._voice = voice
        self._cancelled = False
        channel.active = True
        channel.drain()
        try:
            await channel.connection.send({
                "type": "response.create",
                "response": {"pre_generated_assistant_message": {
                    "type": "message", "role": "assistant", "content": [{"type": "text", "text": text}],
                }},
            })
            transcript: list[str] = []
            while True:
                try:
                    event = await asyncio.wait_for(channel.events.get(), timeout=SPEAK_IDLE_TIMEOUT_S)
                except TimeoutError as exc:
                    raise SpeechError(f"Voice Live sent nothing for {SPEAK_IDLE_TIMEOUT_S:g} s while speaking") from exc
                kind = str(getattr(event, "type", ""))
                if kind == "response.audio.delta":
                    if not self._cancelled:
                        await on_audio(event.delta)  # the SDK has already base64-decoded it
                elif kind == "response.audio_transcript.delta":
                    transcript.append(event.delta)
                elif kind == "response.done":
                    return "".join(transcript)
                elif kind in ("error", "closed"):
                    raise SpeechError(f"Voice Live error while speaking: {_error_of(event)}")
        finally:
            channel.active = False

    async def cancel(self) -> None:
        """Barge-in (T2: the server stopped in about 0.4 s). Audio already in flight is dropped here and in the browser."""
        self._cancelled = True
        if self._speaking is not None and self._speaking.active:
            await self._speaking.connection.send({"type": "response.cancel"})

    # ----- listening -----
    def _listen_vad(self, lang: Lang) -> str:
        return os.environ.get(f"VOICE_LISTEN_VAD_{lang.upper()}", LISTEN_VAD[lang])

    async def _configure_listener(self, channel: _Channel, lang: Lang, vad_type: str) -> None:
        """Send the biased update; if the service rejects the phrase list, log the exact error and retry without it."""
        try:
            await channel.update_session(listening_session_update(lang, self.transcribe_model, vad_type, bias=self._bias), TranscriptionError)
        except TranscriptionError as exc:
            if not self._bias or "phrase" not in str(exc).casefold():
                raise
            log.warning("Voice Live rejected the transcription phrase list, continuing without it: %s", exc)
            self._bias = False
            await channel.update_session(listening_session_update(lang, self.transcribe_model, vad_type, bias=False), TranscriptionError)

    async def _listener(self, lang: Lang) -> _Channel:
        if self._listening is None:
            channel = await self._connect("listening")
            try:
                await self._configure_listener(channel, lang, self._listen_vad(lang))
            except TranscriptionError:
                await channel.close()
                raise
            self._listening, self._listen_lang = channel, lang
        elif lang != self._listen_lang:
            # Only the transcription language (and its phrase list) changes; the VAD type stays what the first update set.
            await self._configure_listener(self._listening, lang, self._listen_vad(self._listen_lang))
            self._listen_lang = lang
        return self._listening

    async def transcribe(self, pcm16: bytes, lang: Lang) -> str:
        if len(pcm16) < MIN_UTTERANCE_BYTES:
            raise NothingHeard("the utterance was shorter than 0.2 s")
        channel = await self._listener(lang)
        channel.active = True
        channel.drain()
        try:
            audio = pcm16 + b"\x00" * int(SAMPLE_RATE * 2 * SILENCE_TAIL_S)  # trailing silence lets the VAD close the turn
            for offset in range(0, len(audio), AUDIO_CHUNK_BYTES):
                await channel.connection.send({"type": "input_audio_buffer.append", "audio": base64.b64encode(audio[offset:offset + AUDIO_CHUNK_BYTES]).decode("ascii")})
            committed = False
            loop = asyncio.get_running_loop()
            deadline = loop.time() + TRANSCRIBE_TIMEOUT_S
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TranscriptionError("Voice Live did not return a transcript in time")
                try:
                    event = await asyncio.wait_for(channel.events.get(), timeout=min(remaining, remaining if committed else COMMIT_WAIT_S))
                except TimeoutError:
                    if committed:
                        continue
                    committed = True  # the VAD did not close the turn: commit the buffer ourselves
                    await channel.connection.send({"type": "input_audio_buffer.commit"})
                    continue
                kind = str(getattr(event, "type", ""))
                if kind == "input_audio_buffer.committed":
                    committed = True
                elif kind == "conversation.item.input_audio_transcription.completed":
                    return (getattr(event, "transcript", "") or "").strip()
                elif kind == "conversation.item.input_audio_transcription.failed":
                    raise TranscriptionError(f"Voice Live transcription failed: {_error_of(event)}")
                elif kind in ("error", "closed"):
                    error = _error_of(event)
                    if "commit_empty" in str(error) or "too small" in str(error).casefold():
                        raise NothingHeard(f"Voice Live heard nothing: {error}")  # terminal for this utterance, at once
                    raise TranscriptionError(f"Voice Live error while listening: {error}")
        finally:
            channel.active = False

    async def close(self) -> None:
        for channel in (self._speaking, self._listening):
            if channel is not None:
                await channel.close()
        for manager in self._managers:
            try:
                await manager.__aexit__(None, None, None)
            except Exception:  # closing a dead socket is not an error worth surfacing
                log.debug("Voice Live connection close failed", exc_info=True)
        if self._credential is not None:
            await self._credential.close()


async def open_voice_live_speaker() -> Speaker:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].split("/api/projects")[0] + "/"
    speaker = VoiceLiveSpeaker(endpoint, os.environ.get("VOICE_LIVE_MODEL", "gpt-realtime"), os.environ.get("VOICE_TRANSCRIBE_MODEL", "azure-speech"))
    return await speaker.open()


SpeakerFactory = Callable[[], Awaitable[Speaker]]


def speaker_factory_from_env() -> SpeakerFactory | None:
    """Voice is on when a Foundry endpoint is configured, unless VOICE_MODE=off."""
    if os.environ.get("VOICE_MODE", "voicelive").lower() == "off" or not os.environ.get("FOUNDRY_PROJECT_ENDPOINT"):
        return None
    return open_voice_live_speaker
