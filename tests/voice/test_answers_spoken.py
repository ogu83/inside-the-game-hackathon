"""Item 4: with the voice on, every answer is spoken verbatim and recorded as a SpeechAudit, mid-match too."""

import json
import time

from starlette.testclient import TestClient

from app.api.main import app
from app.api.streams import template_workflow
from tests.voice.test_voice_ws import FakeSpeaker


def test_every_answer_is_spoken_and_audited_during_the_match() -> None:
    speaker = FakeSpeaker()
    with TestClient(app) as client:
        async def factory():
            return speaker

        app.state.speaker_factory = factory
        app.state.workflow_factory = template_workflow
        # 60 match minutes at 150x with a 20 s delay: about 24 s of wall time, plenty to ask during it
        client.post("/api/match/start", json={"seed": 30, "speed": 150, "delay_s": 20, "minutes": 60})
        time.sleep(0.8)  # the first cue (minute 1 plus the delay) has aired
        with client.websocket_connect("/api/voice?profile=kby|kby-07|casual|en") as ws:
            answered, audits_seen = [], []
            ws.send_text(json.dumps({"type": "ask", "transcript": "how is my player doing?"}))
            ws.send_text(json.dumps({"type": "ask", "transcript": "what is the score?"}))
            deadline = time.time() + 15
            while len(audits_seen) < 2 and time.time() < deadline:
                m = ws.receive()
                if not m.get("text"):
                    continue
                msg = json.loads(m["text"])
                if msg["type"] == "answer":
                    answered.append(msg["answer"])
                if msg["type"] == "spoken" and msg["audit"]["question_id"]:
                    audits_seen.append(msg["audit"])
        assert len(answered) == 2 and len(audits_seen) == 2
        assert {a["question_id"] for a in answered} == {a["question_id"] for a in audits_seen}
        spoken_texts = [text for text, _ in speaker.spoken]
        for answer, audit in zip(answered, audits_seen, strict=True):
            assert answer["text"] in spoken_texts, "the approved answer text is what the voice spoke"
            assert audit["ok"] and audit["approved_text"] in spoken_texts and audit["profile_key"] == "kby|kby-07|casual|en"
        assert "Luca Brightwater" in answered[0]["text"] and answered[1]["text"].startswith("It is Kestrel Bay")
        stored = client.get("/api/match/audits").json()
        assert [a for a in stored["audits"] if a["question_id"]] and stored["exact"] >= 2
        metrics = client.get("/api/match/state").json()["metrics"]
        assert metrics["answers_spoken"] == metrics["questions_answered"] == 2
        client.post("/api/match/stop")
