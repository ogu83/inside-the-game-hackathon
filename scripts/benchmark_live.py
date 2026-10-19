import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import asyncio
import json
import time
import websockets
import httpx

BASE_URL = "http://127.0.0.1:8010"
WS_URL = "ws://127.0.0.1:8010"

async def test_qa_client():
    client = httpx.AsyncClient(base_url=BASE_URL, timeout=60.0)

    # 1. Start match seed 30 with 0s delay so ledger events are immediately visible
    print("Starting match seed 30 at speed 10x with delay_s=0...")
    t0 = time.perf_counter()
    res = await client.post("/api/match/start", json={
        "seed": 30,
        "speed": 10.0,
        "delay_s": 0.0,
        "minutes": 10,
        "precompute": False
    })
    print(f"Match start responded in {time.perf_counter()-t0:.2f}s: {res.json()}")
    await asyncio.sleep(2.0)

    # 2. Test Q&A with Casual and Analyst profiles
    questions = [
        ("How is my player doing?", "kby|kby-07|casual|en"),
        ("How is my player doing?", "kby|kby-07|analyst|en"),
        ("What's the score?", "kby|kby-07|casual|en"),
        ("What's the score?", "kby|kby-07|analyst|en"),
        ("skor ne", "kby|kby-07|casual|tr"),
        ("skor ne", "kby|kby-07|analyst|tr"),
    ]

    print("\n--- ASKING 6 QUESTIONS OVER /api/qa ---")
    qa_results = []
    for q_text, profile_key in questions:
        t_start = time.perf_counter()
        r = await client.post("/api/qa", json={
            "transcript": q_text,
            "profile_key": profile_key
        })
        t_end = time.perf_counter()
        data = r.json()
        ans = data.get("answer", {})
        timing = ans.get("timing") or {}
        elapsed_s = t_end - t_start
        print(f"[{profile_key}] '{q_text}' -> {elapsed_s:.2f}s | verdict={ans.get('verdict', {}).get('status')} | tools={ans.get('tool_calls')} | text={ans.get('text')}")
        qa_results.append({
            "query": q_text,
            "profile_key": profile_key,
            "latency_s": round(elapsed_s, 2),
            "verdict": ans.get("verdict", {}).get("status"),
            "tools": ans.get("tool_calls"),
            "timing": timing,
            "text": ans.get("text")
        })

    # 3. Test Voice Live WebSocket for Casual vs Analyst
    print("\n--- TESTING VOICE WEBSOCKET FOR CASUAL VS ANALYST ---")
    for profile_key in ["kby|kby-07|casual|en", "kby|kby-07|analyst|en"]:
        ws_endpoint = f"{WS_URL}/api/voice?profile={profile_key}"
        try:
            async with websockets.connect(ws_endpoint) as ws:
                print(f"Connected to {ws_endpoint}")
                # Ask a question over WebSocket
                await ws.send(json.dumps({"type": "ask", "transcript": "What is the score?"}))
                got_speaking = False
                got_audio = False
                audio_bytes = 0
                t_ask = time.perf_counter()
                deadline = t_ask + 30.0
                while time.perf_counter() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        if isinstance(msg, bytes):
                            got_audio = True
                            audio_bytes += len(msg)
                        else:
                            payload = json.loads(msg)
                            print(f"  [{profile_key}] WS msg: {payload.get('type')} {payload.get('text', '')[:40]}")
                            if payload.get("type") == "spoken":
                                break
                    except asyncio.TimeoutError:
                        break
                print(f"  [{profile_key}] Result: got_audio={got_audio} ({audio_bytes} bytes), total={time.perf_counter()-t_ask:.2f}s")
        except Exception as e:
            print(f"WS error for {profile_key}: {e}")

    # 4. Check Match State and Moments
    st = (await client.get("/api/match/state")).json()
    metrics = st.get("metrics", {})
    print("\n--- CURRENT METRICS ---")
    print(json.dumps(metrics, indent=2))

    await client.post("/api/match/stop")
    await client.aclose()
    return qa_results, metrics

if __name__ == "__main__":
    asyncio.run(test_qa_client())
