"""Performance measurement harness for Matchday Companion (P5 baseline and validation)."""

import sys
sys.path.insert(0, ".")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import asyncio
import os
import time
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
os.environ["AZURE_CORE_ENABLE_BROKER_ON_WINDOWS"] = "false"

from app.observability import init_observability, flush_tracing
from app.simulator.engine import simulate
from app.ledger.state import detect_all, Ledger
from app.ledger.labels import moment_labels
from app.ledger.mcp_server import LedgerTools, build_mcp_server
from app.agents.models import FanProfile, Question, PacingState
from app.agents.analyst import PacingTracker, FoundryDirector
from app.agents.commentator import FoundryCommentator
from app.agents.fact_checker import FactChecker, FoundryWordingJudge
from app.agents.producer import FoundryRenderer, Producer
from app.agents.prompts import ANALYST_INSTRUCTIONS, COMMENTATOR_INSTRUCTIONS, FACT_CHECKER_INSTRUCTIONS, PRODUCER_INSTRUCTIONS, QA_INSTRUCTIONS
from app.agents.workflow import build_workflow, run_moment
from app.voice.qa import QaPipeline, new_question
from app.voice.session import open_voice_live_speaker, VoiceLiveSpeaker

class SimpleRunView:
    def __init__(self, events, displayed_t):
        self._events = [e for e in events if e.t <= displayed_t]
    def events(self):
        return self._events
    def shown_moments(self):
        return []

async def measure_qa(mcp_url: str):
    from app.agents.run_match import live_agent, live_qa_agent
    qa_agent = live_qa_agent(mcp_url)
    checker_agent = live_agent("SMALL_MODEL_DEPLOYMENT", "fact_checker", FACT_CHECKER_INSTRUCTIONS)
    fc = FactChecker(FoundryWordingJudge(checker_agent))

    events = simulate(30)
    tools = LedgerTools(SimpleRunView(events, displayed_t=120))

    pipeline = QaPipeline(qa_agent, fc, tools)

    speaker = None
    try:
        speaker = await open_voice_live_speaker()
    except Exception as exc:
        print("Voice Live speaker unavailable:", exc)

    test_cases = [
        ("How is my player doing?", FanProfile(club_id="kby", player_id="kby-07", depth="casual", language="en")),
        ("How is my player doing?", FanProfile(club_id="kby", player_id="kby-07", depth="analyst", language="en")),
        ("What's the score?", FanProfile(club_id="kby", player_id="kby-07", depth="casual", language="en")),
        ("What's the score?", FanProfile(club_id="kby", player_id="kby-07", depth="analyst", language="en")),
        ("skor ne", FanProfile(club_id="kby", player_id="kby-07", depth="casual", language="tr")),
        ("skor ne", FanProfile(club_id="kby", player_id="kby-07", depth="analyst", language="tr")),
    ]

    results = []
    print("\n--- MEASURING Q&A STAGES ---")
    for text, profile in test_cases:
        q = new_question(profile.key(), text, asked_at_seq=40)
        t_start = time.perf_counter()
        ans = await pipeline.answer(q, profile)
        t_answered = time.perf_counter()
        ans_ms = (t_answered - t_start) * 1000

        audio_first_ms = None
        if speaker:
            try:
                first_chunk_t = None
                async def on_audio(chunk):
                    nonlocal first_chunk_t
                    if first_chunk_t is None:
                        first_chunk_t = time.perf_counter()
                t_speak_start = time.perf_counter()
                await speaker.speak(ans.text, profile.language, on_audio)
                if first_chunk_t:
                    audio_first_ms = (first_chunk_t - t_speak_start) * 1000
            except Exception as e:
                print("Speech error:", e)

        timing_data = {
            "query": text,
            "depth": profile.depth,
            "language": profile.language,
            "answer_text": ans.text,
            "verdict": ans.verdict.status if ans.verdict else "none",
            "tools_called": ans.tool_calls,
            "draft_ms": ans.timing.draft_ms if ans.timing else None,
            "factcheck_ms": ans.timing.factcheck_ms if ans.timing else None,
            "total_answer_ms": round(ans_ms, 1),
            "first_audio_ms": round(audio_first_ms, 1) if audio_first_ms else None,
        }
        results.append(timing_data)
        print(f"[{profile.depth}/{profile.language}] '{text}' -> {ans_ms:.0f}ms (draft={ans.timing.draft_ms if ans.timing else 0:.0f}ms, check={ans.timing.factcheck_ms if ans.timing else 0:.0f}ms, first_audio={audio_first_ms}): {ans.text[:60]}")

    if speaker:
        await speaker.close()
    return results

async def measure_moments():
    from app.agents.run_match import live_workflow, live_producer
    events = simulate(30)
    moments = detect_all(events)[:3]
    pacing = PacingTracker()

    profiles = [
        FanProfile(language="en", depth="casual", club_id="kby"),
        FanProfile(language="en", depth="analyst", club_id="kby", player_id="kby-07"),
        FanProfile(language="tr", depth="casual", club_id="kby"),
        FanProfile(language="tr", depth="analyst", club_id="kby", player_id="kby-07"),
    ]

    print("\n--- MEASURING MOMENT STAGES ---")
    results = []
    for moment in moments:
        close_event = events[moment.window[1] - 1]
        t = close_event.t
        labels = moment_labels(moment, ("kby", "iva"))

        t_moment_start = time.perf_counter()
        wf = live_workflow()

        t0 = time.perf_counter()
        analyst_decision = await wf.executors["analyst"].director.decide(moment, labels, pacing.state_for(moment, t))
        analyst_ms = (time.perf_counter() - t0) * 1000

        res = await run_moment(wf, moment, labels=labels, pacing=pacing.state_for(moment, t))
        pacing.record(res.decision, t)
        wf_ms = (time.perf_counter() - t_moment_start) * 1000

        producer = live_producer()
        t_prod_start = time.perf_counter()
        output = None
        if res.verdict and res.verdict.insight:
            output = await producer.render(res.verdict.insight, moment, labels, profiles)
        prod_ms = (time.perf_counter() - t_prod_start) * 1000
        total_stage_ms = (time.perf_counter() - t_moment_start) * 1000

        late = total_stage_ms > 20000.0 # 20s broadcast delay

        stage_data = {
            "moment_id": moment.moment_id,
            "kind": moment.kind,
            "minute": moment.minute,
            "analyst_ms": round(analyst_ms, 1),
            "workflow_ms": round(wf_ms, 1),
            "producer_ms": round(prod_ms, 1),
            "total_ms": round(total_stage_ms, 1),
            "late_at_20s": late,
            "dropped_profiles": output.dropped_profiles if output else [],
            "narratives_count": len(output.narratives) if output else 0,
        }
        results.append(stage_data)
        print(f"Moment {moment.moment_id} (min {moment.minute}): wf={wf_ms:.0f}ms (analyst={analyst_ms:.0f}ms), prod={prod_ms:.0f}ms, TOTAL={total_stage_ms:.0f}ms, LATE={late}, dropped={stage_data['dropped_profiles']}")

    return results

async def main():
    init_observability()
    server = build_mcp_server(LedgerTools(SimpleRunView(simulate(30), 120)))
    app = server.streamable_http_app()

    import uvicorn
    config = uvicorn.Config(app, host="127.0.0.1", port=8019, log_level="warning")
    srv = uvicorn.Server(config)
    task = asyncio.create_task(srv.serve())
    await asyncio.sleep(0.5)

    try:
        async with server.session_manager.run():
            qa_results = await measure_qa("http://127.0.0.1:8019/mcp")
            moment_results = await measure_moments()
            out = {"qa": qa_results, "moments": moment_results}
            Path("runs").mkdir(exist_ok=True)
            with open("runs/perf_after.json", "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2)
            print("\nResults saved to runs/perf_after.json")
    finally:
        srv.should_exit = True
        await task
        flush_tracing()

if __name__ == "__main__":
    asyncio.run(main())
