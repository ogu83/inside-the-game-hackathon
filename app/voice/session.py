"""Voice Live speaker: speaks approved text verbatim and audits what was spoken (SPEC design rule 6).

Narration is sent as `response.create` with `pre_generated_assistant_message`, so the realtime model
never authors spoken words; it only synthesizes the exact approved text. The transcript of each
spoken response goes through the speech gate (`check_speech`).
"""

import os
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol

Lang = Literal["en", "tr"]
OnAudio = Callable[[bytes], Awaitable[None]]

SAMPLE_RATE = 24000  # pcm16 mono, what Voice Live returns for output_audio_format "pcm16"
VOICES: dict[str, str] = {"en": "en-US-AvaMultilingualNeural", "tr": "tr-TR-EmelNeural"}


class Speaker(Protocol):
    async def speak(self, text: str, lang: Lang, on_audio: OnAudio) -> str:
        """Speak `text` verbatim, stream pcm16 chunks to `on_audio`, return the transcript of what was spoken."""
        ...

    async def cancel(self) -> None:
        """Barge-in: stop the current response; the browser drops its own playback buffer."""
        ...

    async def transcribe(self, pcm16: bytes, lang: Lang) -> str:
        """Transcribe one push-to-talk utterance (pcm16 mono 24 kHz). The realtime model only listens here."""
        ...

    async def close(self) -> None: ...


class VoiceLiveSpeaker:
    """One Voice Live connection, reused for every line of one listener."""

    def __init__(self, endpoint: str, model: str = "gpt-realtime") -> None:
        self.endpoint = endpoint
        self.model = model
        self._credential = None
        self._manager = None
        self._connection = None
        self._voice: str | None = None
        self._cancelled = False

    async def open(self) -> "VoiceLiveSpeaker":
        from azure.ai.voicelive.aio import connect
        from azure.identity.aio import DefaultAzureCredential

        self._credential = DefaultAzureCredential()
        self._manager = connect(endpoint=self.endpoint, credential=self._credential, model=self.model)
        self._connection = await self._manager.__aenter__()
        return self

    async def _use_voice(self, lang: Lang) -> None:
        voice = VOICES[lang]
        if voice == self._voice:
            return
        await self._connection.send({
            "type": "session.update",
            "session": {"modalities": ["text", "audio"], "voice": {"name": voice, "type": "azure-standard"}, "output_audio_format": "pcm16"},
        })
        self._voice = voice

    async def speak(self, text: str, lang: Lang, on_audio: OnAudio) -> str:
        await self._use_voice(lang)
        self._cancelled = False
        await self._connection.send({
            "type": "response.create",
            "response": {"pre_generated_assistant_message": {
                "type": "message", "role": "assistant", "content": [{"type": "text", "text": text}],
            }},
        })
        transcript: list[str] = []
        while True:
            event = await self._connection.recv()
            if event.type == "response.audio.delta":
                if not self._cancelled:
                    await on_audio(event.delta)  # the SDK has already base64-decoded it
            elif event.type == "response.audio_transcript.delta":
                transcript.append(event.delta)
            elif event.type == "response.done":
                return "".join(transcript)
            elif event.type == "error":
                raise RuntimeError(f"Voice Live error: {event.error}")

    async def cancel(self) -> None:
        """Barge-in (T2: the server stopped in about 0.4 s). Audio already in flight is dropped here and in the browser."""
        self._cancelled = True
        if self._connection is not None:
            await self._connection.send({"type": "response.cancel"})

    async def transcribe(self, pcm16: bytes, lang: Lang) -> str:
        """Push-to-talk transcription through Voice Live (live test only; verify locally before relying on it):
        append the utterance to the input buffer, commit it, and wait for the transcription of the created item."""
        import base64

        await self._connection.send({
            "type": "session.update",
            "session": {"turn_detection": None, "input_audio_transcription": {"model": "whisper-1", "language": lang}},
        })
        for offset in range(0, len(pcm16), 48000):
            await self._connection.send({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm16[offset:offset + 48000]).decode("ascii")})
        await self._connection.send({"type": "input_audio_buffer.commit"})
        while True:
            event = await self._connection.recv()
            if event.type == "conversation.item.input_audio_transcription.completed":
                return (event.transcript or "").strip()
            if event.type == "conversation.item.input_audio_transcription.failed":
                raise RuntimeError(f"Voice Live transcription failed: {getattr(event, 'error', '')}")
            if event.type == "error":
                raise RuntimeError(f"Voice Live error: {event.error}")

    async def close(self) -> None:
        if self._manager is not None:
            await self._manager.__aexit__(None, None, None)
        if self._credential is not None:
            await self._credential.close()


async def open_voice_live_speaker() -> Speaker:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].split("/api/projects")[0] + "/"
    return await VoiceLiveSpeaker(endpoint, os.environ.get("VOICE_LIVE_MODEL", "gpt-realtime")).open()


SpeakerFactory = Callable[[], Awaitable[Speaker]]


def speaker_factory_from_env() -> SpeakerFactory | None:
    """Voice is on when a Foundry endpoint is configured, unless VOICE_MODE=off."""
    if os.environ.get("VOICE_MODE", "voicelive").lower() == "off" or not os.environ.get("FOUNDRY_PROJECT_ENDPOINT"):
        return None
    return open_voice_live_speaker
