"""Measure moments baseline performance on seed 30."""

import sys
sys.path.insert(0, ".")
import os
import time
import json
import asyncio
from dotenv import load_dotenv

load_dotenv()
os.environ["AZURE_CORE_ENABLE_BROKER_ON_WINDOWS"] = "false"

from app.observability import init_observability, flush_tracing
from app.simulator.engine import simulate
from app.ledger.state import detect_all
from app.ledger.labels import moment_labels
from app.agents.models import FanProfile
from app.agents.analyst import PacingTracker
from app.agents.run_match import live_workflow, live_producer, run_moment

async def run_moment_benchmark():
    init_observability()
    events = simulate(30)
    moments = detect_all(events)[:4] # First 4 moments
    pacing = PacingTracker()

    profiles = [
        FanProfile(language="en", depth="casual", club_id="kby"),
        FanProfile(language="en", depth="analyst", club_id="kby", player_id="kby-07"),
        FanProfile(language="tr", depth="casual", club_id="kby"),
        FanProfile(language="tr", depth="analyst", club_id="kby", player_id="kby-07"),
    ]

    print("Measuring first 4 moments of seed 30...")
    results = []
    for i, moment in enumerate(moments):
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
        total_ms = (time.perf_counter() - t_moment_start) * 1000

        late = total_ms > 20000.0 # 20s delay

        data = {
            "moment_index": i,
            "moment_id": moment.moment_id,
            "minute": moment.minute,
            "kind": moment.kind,
            "analyst_ms": round(analyst_ms, 1),
            "workflow_ms": round(wf_ms, 1),
            "producer_ms": round(prod_ms, 1),
            "total_ms": round(total_ms, 1),
            "late": late,
            "verdict_status": res.verdict.status if res.verdict else "skipped",
            "verdict_layer": res.verdict.layer if res.verdict else None,
            "dropped_profiles": output.dropped_profiles if output else [],
            "narratives_count": len(output.narratives) if output else 0,
            "narratives": [{"profile": n.profile_key, "text": n.text} for n in output.narratives] if output else [],
            "cue": output.cue.headline if output and output.cue else None,
        }
        results.append(data)
        print(f"Moment {i} ({moment.moment_id}, min {moment.minute}): total={total_ms:.0f}ms (wf={wf_ms:.0f}ms, prod={prod_ms:.0f}ms), late={late}, dropped={data['dropped_profiles']}")

    flush_tracing()
    with open("runs/moments_baseline.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\nSaved to runs/moments_baseline.json")

if __name__ == "__main__":
    asyncio.run(run_moment_benchmark())
