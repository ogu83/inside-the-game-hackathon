# ADR 0003: Verbatim Voice Speech and Transcript Auditing

## Status
Accepted

## Context
Interactive audio commentary presents two core challenges: factual fidelity and responsiveness. When realtime voice models (such as Azure Voice Live) generate conversational speech autonomously, they frequently rephrase statistics, invent numbers, or drop critical nuances, bypassing Fact-Checker gates.

Furthermore, in a live match broadcast with push-to-talk Q&A, fans must be able to interrupt (barge in on) ongoing speech immediately when asking a question, without auditory collision or delayed silence.

## Decision
1. **Pre-Generated Verbatim Messages Only:**
   - The Voice Live connection (`app/voice/session.py`) operates exclusively in verbatim playback mode.
   - The server configures output audio format (`pcm16` at 24 kHz) and voice profiles, but issues `response.create` containing a `pre_generated_assistant_message` with the approved, fact-checked text.
   - The model never authors or paraphrases spoken words autonomously.

2. **Automated Post-Speech Auditing:**
   - As Voice Live streams audio frames, it emits `response.audio_transcript.delta` events reflecting what the synthesizer produced.
   - Upon completion, `check_speech` (`app/agents/fact_check_rules.py`) verifies that the returned transcript matches the approved text verbatim (normalising whitespace and punctuation) and re-verifies all numbers against ground truth.
   - The result is logged into `SpeechAudit` records exposed via `/api/match/audits` and transmitted to the client over WebSocket.

3. **Low-Latency Barge-In:**
   - When a fan presses Push-to-Talk (`talk_start` or `ask`), the server issues `response.cancel` over the Voice Live socket.
   - The browser client immediately stops local audio playback and flushes its audio buffer.
   - The interrupted utterance is marked with `interrupted: true` in the audit ledger so that incomplete transcripts are not penalized as accuracy mismatches.

4. **Dual Independent Connections:**
   - Because Voice Live prohibits altering the turn-detection mode during an active session, two separate connections are maintained: a dedicated speaking connection and an on-demand listening connection with semantic VAD (`azure_semantic_vad`) and speech transcription (`azure-speech`).

## Consequences
- **Positive:**
  - Absolute alignment between visual overlay cues, fan narratives, and spoken speech.
  - Verifiable speech audit trail ensuring zero unverified numbers reach the fan's ears.
  - Sub-second barge-in response (~0.4 s server-side cancellation plus instant browser buffer flush).
- **Negative / Trade-offs:**
  - Requires maintaining two concurrent Voice Live WebSocket connections per active audio session.
  - The voice lacks spontaneous conversational improvisation, as all spoken content must originate from approved agent artifacts.
