# Architecture: Matchday Companion

Matchday Companion is an AI co-commentary and broadcast overlay system designed around a foundational requirement: **it cannot lie on air**.

This document details the complete end-to-end architecture, the multi-agent pipeline, the two-layer verification gating, and the execution flow from raw match events to verified broadcast graphics and synthesized voice.

---

## 1. System Architecture

The following diagram illustrates the flow of data through Matchday Companion, from synthetic event generation through the ledger, agent workflow, broadcast delay clock, web delivery, and Microsoft Foundry services.

```mermaid
flowchart TD
    subgraph DataLayer["1. Data & Ledger Layer"]
        Sim["Match Simulator (app/simulator)<br/>Seeded 90-min deterministic match"] --> |MatchEvent stream| Ingest["Ledger Ingest (app/ledger/state.py)<br/>Event windowing & state"]
        Ingest --> Detectors["Moment Detectors (app/ledger/moments.py)<br/>pass_streak, pressing_trap, etc."]
        Detectors --> |CandidateMoment + Evidence dict| Director
        Ingest --> MCP["Ledger FastMCP Server (app/ledger/mcp_server.py)<br/>Read-only tools bounded by display clock"]
    end

    subgraph AgentPipeline["2. Multi-Agent Commentary Pipeline (app/agents)"]
        Director["FoundryDirector (Analyst)<br/>Pacing state & angle decision"]
        Director --> |say: editorial angle| Commentator["FoundryCommentator<br/>Drafts claim from cited evidence"]
        Director --> |skip| DropMoment["Skip moment<br/>(Recorded in timeline)"]

        Commentator --> |Draft claim| FactChecker{"Two-Layer Fact-Checker"}
        
        subgraph FactCheckerGates["Fact-Checking Gates"]
            L1["Layer 1: Deterministic Code Gate<br/>Number parser & actor check (no LLM)"]
            L2["Layer 2: Foundry Wording Judge<br/>Catches subtle hallucinations & framing"]
        end

        FactChecker --> L1
        L1 --> |Pass| L2
        L1 --> |Fail| RejectBranch{"Retry < 2?"}
        L2 --> |Verified| Producer["FoundryRenderer (Producer)<br/>Parallel rendering per fan profile"]
        L2 --> |Rewrite / Reject| RejectBranch

        RejectBranch --> |Yes: feedback loop| Commentator
        RejectBranch --> |No: reject| RejectMoment["Moment Rejected<br/>(Never reaches air)"]
        
        Producer --> ProducerGate["Producer Number Gate<br/>Checks all numbers in cues & narratives"]
    end

    subgraph BroadcastTiming["3. Broadcast Delay & Delivery (app/api)"]
        ProducerGate --> |Verified cue + narratives| PlaybackBuffer["Playback Buffer<br/>20.0s broadcast delay window"]
        Clock["Broadcast Clock (app/api/clock.py)<br/>Synchronized match time"] --> PlaybackBuffer
        PlaybackBuffer --> |On-time: t <= 20.0s| SSE["SSE Stream (/api/stream/*)<br/>Cues, narratives, verdicts"]
        PlaybackBuffer --> |Late: t > 20.0s| DroppedLate["Dropped Late<br/>(Counted, never airs)"]
    end

    subgraph ClientUI["4. Broadcast Frontend (frontend)"]
        SSE --> WebUI["Web Interface (Vue 3)<br/>SVG pitch, lower-third cue banner, fan panel"]
        WebUI --> |Push-to-Talk audio / ask| VoiceWS["WebSocket (/api/voice)<br/>Session-isolated client connection"]
    end

    subgraph VoiceAndQA["5. Voice Live & Q&A (app/voice)"]
        VoiceWS --> |User Question| QAPipeline["Q&A Pipeline (app/voice/qa.py)<br/>Foundry Q&A Agent"]
        QAPipeline <--> |Tool calls| MCP
        QAPipeline --> QAGate["Speech Gate<br/>Code number check on answer"]
        
        QAGate --> |Approved text only| VoiceLiveSpeak["Foundry Voice Live (Speaker)<br/>pre_generated_assistant_message"]
        SSE --> |Approved narrative| VoiceLiveSpeak
        VoiceLiveSpeak --> |Verbatim PCM audio| WebUI
        
        WebUI --> |Microphone PCM audio| VoiceLiveListen["Foundry Voice Live (Listener)<br/>azure-speech transcription + phrase bias"]
        VoiceLiveListen --> |Question transcript| VoiceWS
        
        VoiceLiveSpeak --> SpeechAudit["Speech Audit Verification<br/>Verifies spoken transcript verbatim"]
    end

    subgraph AzureInfra["6. Microsoft Foundry & Azure Infrastructure"]
        Models["Foundry Chat Deployments<br/>gpt-5.4-mini (Responses API)"]
        VoiceService["Foundry Voice Live<br/>eastus2 WebSockets"]
        AppInsights["Azure Application Insights<br/>OpenTelemetry distributed traces"]
        ContainerApp["Azure Container Apps<br/>System-Assigned Managed Identity"]

        Director -.-> Models
        Commentator -.-> Models
        L2 -.-> Models
        Producer -.-> Models
        QAPipeline -.-> Models
        VoiceLiveSpeak -.-> VoiceService
        VoiceLiveListen -.-> VoiceService
        AgentPipeline -.-> AppInsights
        QAPipeline -.-> AppInsights
    end
```

---

## 2. Pipeline Stages

The commentary pipeline enforces strict separation of concerns across deterministic code and model evaluation:

| Stage | Name | Implementation | Function | Inputs | Outputs | Gating / Guarantees |
|---|---|---|---|---|---|---|
| **1** | Simulator | Deterministic code (`app/simulator/engine.py`) | Generates realistic, seeded football events | Seed (int), match clock | `MatchEvent` stream | Fully reproducible: identical seed generates identical match events. |
| **2** | Ledger & Detectors | Deterministic code (`app/ledger/state.py`, `app/ledger/moments.py`) | Aggregates possession, shots, pass streaks, pressing traps | `MatchEvent` list | `CandidateMoment` + `evidence` dict | Pure calculation; no probabilistic logic. All numbers originate here. |
| **3** | FastMCP Server | FastMCP protocol (`app/ledger/mcp_server.py`) | Exposes read-only ledger tools (`score`, `team_stats`, `player_stats`, `recent_moments`) | Tool invocation request | Structured JSON records | Bound to playback display clock; cannot leak future match events. |
| **4** | Director (Analyst) | Foundry agent (`app/agents/analyst.py`) | Evaluates pacing state and decides whether to commentate or skip; selects tactical angle | `CandidateMoment`, `PacingState`, labels | `DirectorDecision` (`decision`: say/skip, `angle`, `reasons`) | Max tokens: 100. Skips low-interest moments or congested phases. |
| **5** | Commentator | Foundry agent (`app/agents/commentator.py`) | Drafts a factual commentary claim citing specific ledger metrics | `CandidateMoment`, labels, feedback | `Insight` (`claim`, `evidence_refs`, `why_it_matters`) | Max tokens: 250. Restricted to metrics present in the evidence dict. |
| **6** | Fact-Checker Layer 1 | Deterministic code (`app/agents/fact_check_rules.py`) | Parses every number in the claim and verifies exact match against cited evidence; verifies actor attribution | `Insight.claim`, `evidence` dict, labels | `NumberCheck` (`ok`, `mismatches`) | Zero LLM calls. If a number is wrong, missing, or an actor swapped, rejects immediately with feedback. |
| **7** | Fact-Checker Layer 2 | Foundry agent (`app/agents/fact_checker.py`) | Analyzes tone, framing, and catches subtle hallucinations that keep numbers right but state false facts | `Insight`, labels, `evidence` dict | `Verdict` (`status`: verified/rejected/rewrite, `layer`: llm, `reasons`) | Max tokens: 250. One retry loop allowed for rewrites; second rejection is terminal. |
| **8** | Producer | Foundry agent (`app/agents/producer.py`) | Renders verified insight into broadcast overlay cues and personalized narratives per fan profile | Verified `Insight`, `FanProfile` list | `ProducerOutput` (`cue`, `narratives`, `checks`) | Max tokens: 120 (cue), 180 (narrative). Rendered in English and Turkish across casual and analyst depths. |
| **9** | Producer Number Gate | Deterministic code (`app/agents/fact_check_rules.py`) | Re-verifies that every rendered cue and narrative contains only approved numbers | Rendered text, `evidence` dict, language | `NumberCheck` per profile | Zero tolerance for invented numbers during translation or style adaptation. |
| **10** | Broadcast Clock | Deterministic code (`app/api/clock.py`, `app/api/streams.py`) | Buffers events and cues behind a 20.0 s broadcast delay window | Processing timestamp, match clock | Emitted SSE event or dropped cue | If total pipeline latency > 20.0 s, cue is dropped late (`cues_dropped_late`) and never aired. |
| **11** | Voice Live Speaker | Foundry Voice Live WebSocket (`app/voice/session.py`) | Speaks verified narrative lines verbatim using pre-generated text | Approved text, voice configuration | Verbatim PCM audio stream | Uses `pre_generated_assistant_message`. The realtime model never authors spoken words. |
| **12** | Speech Audit | Deterministic code (`app/voice/session.py`) | Compares Voice Live speech transcript against approved input text | Audio transcript, approved text | `SpeechAudit` (`check`: true/false, `text`, `transcript`) | Discrepancies are recorded as audit failures and shown. |
| **13** | Voice Live Listener | Foundry Voice Live WebSocket (`app/voice/session.py`) | Captures push-to-talk audio and transcribes user speech with football phrase list bias | Raw PCM audio stream, language | Recognized question transcript | Session-isolated listening connection with turn-detection disabled. |
| **14** | Q&A Pipeline | Foundry agent + FastMCP (`app/voice/qa.py`) | Answers fan match questions by querying ledger MCP tools | Question transcript, `FanProfile` | `Answer` (`text`, `tool_calls`, `verdict`) | Max tokens: 150. Gated by code number check before text is returned or spoken. |

---

## 3. Execution Sequences

### Sequence 1: Moment Ingest, Verification, and Broadcast Cue Delivery

This sequence follows a single match event from simulation through the commentary pipeline, showing both the happy path and the rejection branch:

```mermaid
sequenceDiagram
    autonumber
    participant S as Simulator / Ledger
    participant D as Analyst Director
    participant C as Commentator
    participant FC1 as Fact-Checker L1 (Code)
    participant FC2 as Fact-Checker L2 (LLM)
    participant P as Producer
    participant PG as Producer Gate (Code)
    participant B as Broadcast Clock
    participant UI as Web Frontend / SSE
    participant V as Voice Live (Speaker)

    S->>D: CandidateMoment (e.g. pass_streak, evidence dict)
    D->>D: Evaluate PacingState & match rhythm
    alt Director decides SKIP
        D-->>S: Skip moment (recorded in drawer timeline)
    else Director decides SAY
        D->>C: Editorial angle + evidence dict
        C->>FC1: Draft insight (claim quoting metrics)
        
        Note over FC1: Layer 1: Code Number & Actor Check
        alt Number mismatch or swapped team detected
            FC1-->>C: Reject with specific mismatch feedback (Retry 1)
            C->>FC1: Corrected draft insight
            FC1->>FC2: Layer 1 OK -> Pass to Layer 2
        else Numbers match evidence
            FC1->>FC2: Layer 1 OK -> Pass to Layer 2
        end

        Note over FC2: Layer 2: LLM Wording Judge
        alt Hallucination or invalid framing
            FC2-->>UI: REJECTED (Emitted to debug drawer, blocked from air)
        else Verified
            FC2->>P: Approved Insight
            par Parallel rendering
                P->>P: Render broadcast cue
                P->>P: Render fan narratives (en/tr, casual/analyst)
            end
            P->>PG: Generated cue and narrative texts
            
            Note over PG: Producer Gate: Code Number Re-Check
            PG->>B: Verified cue + narratives (all numbers valid)
            
            alt Total latency <= 20.0s broadcast delay
                B->>UI: SSE event: cue (Display overlay banner)
                B->>UI: SSE event: fan narrative (Update fan card)
                B->>V: pre_generated_assistant_message (Approved text)
                V->>UI: Stream PCM audio chunks
                V->>V: Speech Audit: transcript == approved text
            else Total latency > 20.0s
                B-->>B: Drop cue late (cues_dropped_late + 1, never airs)
            end
        end
    end
```

---

### Sequence 2: Push-to-Talk Fan Question over FastMCP

This sequence traces a fan interrupting the broadcast to ask a live match question:

```mermaid
sequenceDiagram
    autonumber
    participant Fan as Fan / Microphone
    participant UI as Web Frontend
    participant VL as Voice Live (Listener)
    participant WS as WebSocket (/api/voice)
    participant QA as Foundry Q&A Agent
    participant MCP as Ledger FastMCP Server
    participant Gate as Speech Gate (Code)
    participant VS as Voice Live (Speaker)

    Fan->>UI: Press & hold "Hold to talk"
    UI->>WS: Frame: talk_start (Cancels any ongoing playback)
    WS->>VS: Cancel active speech stream immediately (<0.4s)
    
    loop Stream microphone audio
        Fan->>UI: Speak question (e.g. "skor ne" / "How is my player doing?")
        UI->>WS: Binary PCM chunks (16kHz mono)
        WS->>VL: Forward PCM audio
    end

    Fan->>UI: Release "Hold to talk"
    UI->>WS: Frame: talk_end
    VL->>VL: azure-speech recognition with football phrase list
    VL-->>WS: Final recognized transcript
    
    WS->>QA: Answer question(transcript, FanProfile)
    
    Note over QA,MCP: Focused MCP Tool Calling
    QA->>MCP: Call tool (e.g. score, player_stats)
    MCP-->>QA: Structured JSON evidence
    QA->>QA: Draft concise answer quoting ledger evidence
    
    QA->>Gate: Answer text + cited tool results
    Note over Gate: Code number check: verify every number in answer
    Gate-->>QA: Gate passed (verified)
    
    QA->>WS: Answer record (text, tools, timing)
    WS->>UI: Frame: answer (Display answer card with timing bar)
    
    WS->>VS: pre_generated_assistant_message(answer.text)
    VS->>UI: Binary PCM audio chunks (Spoken answer)
    VS->>VS: Verify spoken transcript against approved answer text
    VS->>WS: SpeechAudit record (exact match confirmed)
    WS->>UI: Frame: spoken (Audit badge: 100% verified)
```

---

## 4. Key Architectural Patterns

### 1. Two-Layer Fact-Checking (Code before Model)
Broadcasters cannot rely on an LLM alone to police another LLM. Matchday Companion uses deterministic code as the first and strictest filter:
- **Layer 1 (Code)**: Extracts all numbers in English and Turkish notations (`68%`, `%68`, `yüzde 68`, `14.0 passes`). It matches each extracted number against the ledger evidence dictionary and enforces actor attribution (a team cannot be attributed an opponent metric). This layer runs in sub-millisecond time with zero API cost.
- **Layer 2 (Model)**: Runs only after Layer 1 passes. It evaluates subtle semantic issues, tone, and scenarios where numbers are accurate but the qualitative claim is misleading (e.g. claiming a team was dominant when they were pinned in their half).
- See [ADR 0002: Numbers by Code](adr/0002-numbers-by-code.md).

### 2. Verbatim Speech Pipeline
Voice AI models in conversational mode hallucinate, round numbers, or rephrase statistics. Matchday Companion decouples generation from speech:
- The text generation pipeline produces and gates the exact sentence first.
- The approved string is sent to Foundry Voice Live using `pre_generated_assistant_message`.
- The Voice Live model acts purely as an audio synthesizer for the approved text; it is strictly prohibited from authoring words.
- An automated speech audit compares the emitted audio transcript against the source text to ensure 100% fidelity.
- See [ADR 0003: Verbatim Voice](adr/0003-verbatim-voice.md).

### 3. Broadcast Delay Window
Live broadcasts already run some seconds behind real time. Matchday Companion uses a 20 second delay:
- The simulation and agent workflow run in real-time ahead of the viewer playback clock.
- A 20.0-second delay window (`BROADCAST_DELAY_S=20`) gives the multi-agent pipeline sufficient time to analyze, draft, verify, and render multi-lingual graphics before the moment appears on the viewer screen.
- If a moment encounters network latency and exceeds the 20.0-second window, it is dropped late rather than popping up out-of-sync with the action.
- See [ADR 0004: Broadcast Delay](adr/0004-broadcast-delay.md).

### 4. Bounded Ledger over FastMCP
The FastMCP server exposes deterministic match statistics to the Q&A agent:
- Tools include `score`, `team_stats`, `player_stats`, `recent_moments`, and `squads`.
- All queries are bounded by the viewer's current playback clock, preventing the agent from leaking spoilers or stats from future match moments.
- See [ADR 0005: MCP Ledger Tools](adr/0005-mcp-ledger-tools.md).

### 5. Multi-Visitor Session Isolation and Spend Protection
Public web deployment requires deterministic isolation between independent visitors:
- Each browser session receives an isolated `mc_session` cookie routing to its own match state, event buffer, and FastMCP context.
- Rate limits protect live Azure spend: maximum 2 live matches per visitor IP per day, and a global daily cap of 40 live runs (`PUBLIC_LIVE_RUNS_TOTAL_PER_DAY=40`).
- When caps are reached, the application seamlessly falls back to offline template agents with an explicit user notice.
- See [ADR 0001: Per-Visitor Sessions](adr/0001-per-visitor-sessions.md) and [docs/deploy.md](deploy.md).
