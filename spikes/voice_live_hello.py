"""T2 spike: Foundry Voice Live round trip (speak, interrupt, reply), headless.

1. Ask the model to speak a long line; stream its audio.
2. After ~1 s of audio, interrupt it (response.cancel, the call the browser client makes on
   barge-in) and time how long until the server stops.
3. Send a follow-up question and receive the full spoken reply.

Typed text stands in for the microphone here; real mic + server VAD barge-in is T12b.
Audio is saved to spikes/out/*.wav so you can listen to both clips.

    python spikes/voice_live_hello.py [--model gpt-realtime] [--voice en-US-AvaMultilingualNeural]
"""

import argparse
import asyncio
import os
import time
import wave
from pathlib import Path

from azure.ai.voicelive.aio import connect
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

SAMPLE_RATE = 24000
INTERRUPT_AFTER_BYTES = SAMPLE_RATE * 2  # ~1 s of pcm16 mono
OUT_DIR = Path(__file__).parent / "out"

LONG_LINE = (
    "Narrate, in about eight sentences, a calm spell of possession for the home side in a "
    "fictional league match: patient passing at the back, a probing ball into midfield, a switch of play."
)
FOLLOW_UP = "Sorry to cut in. Why does that spell of possession matter, in one sentence?"


def save_wav(name: str, pcm: bytes) -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / name
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return path


async def say(connection, text: str) -> None:
    await connection.send(
        {
            "type": "conversation.item.create",
            "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]},
        }
    )
    await connection.send({"type": "response.create"})


async def collect(connection, interrupt_after: int | None) -> tuple[bytes, str, float | None, str]:
    """Stream one response. Returns audio, transcript, cancel-to-stop ms (if interrupted), final status."""
    audio, transcript = bytearray(), []
    cancelled_at: float | None = None
    while True:
        event = await connection.recv()
        kind = event.type
        if kind == "response.audio.delta":
            if cancelled_at is None:
                audio.extend(event.delta)  # SDK already base64-decodes to bytes
            if interrupt_after and cancelled_at is None and len(audio) >= interrupt_after:
                cancelled_at = time.perf_counter()
                # output_audio_buffer.clear is avatar-only; without avatar the client drops its own playback buffer.
                await connection.send({"type": "response.cancel"})
        elif kind == "response.audio_transcript.delta":
            transcript.append(event.delta)
        elif kind == "response.done":
            stop_ms = (time.perf_counter() - cancelled_at) * 1000 if cancelled_at else None
            return bytes(audio), "".join(transcript), stop_ms, event.response.status
        elif kind == "error":
            raise RuntimeError(f"Voice Live error: {event.error}")


async def main(model: str, voice: str) -> None:
    load_dotenv()
    account = os.environ["FOUNDRY_PROJECT_ENDPOINT"].split("/api/projects")[0] + "/"
    async with DefaultAzureCredential() as credential:
        started = time.perf_counter()
        async with connect(endpoint=account, credential=credential, model=model) as connection:
            await connection.send(
                {
                    "type": "session.update",
                    "session": {
                        "modalities": ["text", "audio"],
                        "instructions": "You are a friendly football co-commentator. Keep it conversational.",
                        "voice": {"name": voice, "type": "azure-standard"},
                        "output_audio_format": "pcm16",
                        "turn_detection": {"type": "azure_semantic_vad"},
                    },
                }
            )
            print(f"connected to {account} model={model} voice={voice}")

            t0 = time.perf_counter()
            await say(connection, LONG_LINE)
            audio1, text1, stop_ms, status1 = await collect(connection, INTERRUPT_AFTER_BYTES)
            print(f"[1] spoke {len(audio1) / (SAMPLE_RATE * 2):.1f}s before interrupt, status={status1}")
            print(f"[1] interrupt -> server stopped in {stop_ms:.0f} ms")
            print(f"[1] transcript so far: {text1[:160]}...")

            t1 = time.perf_counter()
            await say(connection, FOLLOW_UP)
            audio2, text2, _, status2 = await collect(connection, None)
            print(f"[2] reply status={status2}, {len(audio2) / (SAMPLE_RATE * 2):.1f}s audio, "
                  f"round trip {(time.perf_counter() - t1):.1f}s")
            print(f"[2] reply: {text2}")

    print(f"wav: {save_wav('voice_1_interrupted.wav', audio1)}, {save_wav('voice_2_reply.wav', audio2)}")
    print(f"total {(time.perf_counter() - started):.1f}s (first request at +{(t0 - started):.1f}s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-realtime")
    parser.add_argument("--voice", default="en-US-AvaMultilingualNeural")
    args = parser.parse_args()
    asyncio.run(main(args.model, args.voice))
