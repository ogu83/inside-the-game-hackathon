"""The page is Vue over a CDN, so the browser part is checked manually; here we check what can be checked without one."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from app.api.main import app

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
SCRIPT = re.findall(r"<script>(.*?)</script>", HTML, re.S)[0]


def test_page_has_the_t12_panels_and_keeps_the_voice_controls() -> None:
    for needle in ("<svg class=\"pitch\"", "cuebanner", "Agent timeline", "follow", "toggleVoice", "Speech audit", "/api/stream/fan", "/api/match/moments", "/api/voice?profile=",
                   "Hold to talk", "talk_start", "talk_end", "/api/qa", "getUserMedia", "webkitSpeechRecognition", "dropPlayback",
                   "ensureVoiceSocket", "reconnecting the voice", "text only (voice off)", "ws.onclose",
                   "@pointerdown.prevent=\"pressTalk\"", "@pointercancel=\"releaseTalk\"", "class PushToTalk", "isFinal", "class PlaybackGate", "bargeIn"):
        assert needle in HTML, needle
    assert "@mousedown" not in HTML and "@touchstart" not in HTML, "pointer events only, so a touch is not also a mouse press"
    assert "\u2014" not in HTML
    assert "player-label" in HTML, "player label rendered as HTML pill over SVG"
    assert "font-size: 13px" in (ROOT / "frontend" / "style.css").read_text(encoding="utf-8"), "player label is 13px Barlow pill"
    assert "crest-kby-256.png" in HTML and "crest-iva-256.png" in HTML, "cue banner renders 256px club crests"
    assert "v-chip verified" in HTML, "cue banner has lower-third verdict chip"
    assert "league-mark-256.png" in HTML, "header renders league mark"
    assert "scoreboard-pill" in HTML, "header renders scoreboard pill"
    assert "aria-label=\"Stop match\"" in HTML, "stop button has aria-label"
    assert "waveform" in HTML, "voice bar has waveform glyph"
    assert "Paused for you" in HTML, "voice bar has paused-for-you chip"
    assert "ptt-btn" in HTML, "push-to-talk button has ptt-btn class"
    assert "ask-submit" in HTML, "voice-off input has ask-submit button"
    css = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
    assert 'href="/static/style.css"' in HTML and "@media (max-width: 900px)" in css
    phone = css.split("@media (max-width: 480px)")[1]
    for rule in (".profile { grid-template-columns: 1fr; }", ".row { grid-template-columns: 1fr;", ".player-label { display: none; }", "header h1 { font-size: 16px; width: 100%;"):
        assert rule in phone, rule
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in HTML


async def test_static_css_and_index_are_served() -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            assert (await client.get("/static/style.css")).headers["content-type"].startswith("text/css")
            assert "Matchday Companion" in (await client.get("/")).text


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_page_script_parses_and_pure_helpers_behave(tmp_path: Path) -> None:
    helpers = SCRIPT.split("createApp({")[0]
    (tmp_path / "helpers.js").write_text("const Vue = { createApp(){}, reactive: x => x, computed: f => f, toRefs: x => x, watch(){} };\n" + helpers, encoding="utf-8")
    (tmp_path / "full.js").write_text("const Vue = { createApp(){ return { mount(){} }; }, reactive: x => x, computed: f => f, toRefs: x => x, watch(){} };\n" + SCRIPT, encoding="utf-8")
    subprocess.run(["node", "--check", str(tmp_path / "full.js")], check=True)
    probe = (
        "const h = require(process.argv[1]);"
        "console.log(JSON.stringify([h.toPitch({team_id:'kby',x:10,y:50},'kby'), h.toPitch({team_id:'iva',x:10,y:20},'kby'),"
        " h.profileKeyOf({club_id:null,player_id:null,depth:'casual',language:'en'}), h.profileKeyOf({club_id:'iva',player_id:'iva-06',depth:'analyst',language:'tr'}), h.clockText(-5), h.clockText(125),"
        " h.labelPos({x:1,y:30},'Luca Brightwater'), h.labelPos({x:104,y:66},'Ollie Marsh'), h.labelPos({x:50,y:30},'Dax'),"
        " h.askRoute(true, true), h.askRoute(true, false), h.askRoute(false, false), h.askRoute(false, true)]))"
    )
    out = subprocess.run(["node", "-e", probe, str(tmp_path / "helpers.js")], check=True, capture_output=True, text=True).stdout
    home, away, key1, key2, c0, c125, left_edge, bottom_right, middle, *routes = json.loads(out)
    assert routes == ["socket", "reconnect", "text", "text"], "voice on never falls back to text; voice off is text only"
    ptt_probe = (
        "const h = require(process.argv[1]); const p = new h.PushToTalk();"
        "const out = [p.press(), p.press(), p.press({repeat: true}), p.release(), p.release(), p.press({repeat: true}), p.press(), p.result(), p.result(), p.release(), p.press(), p.result(), p.pressId];"
        "console.log(JSON.stringify(out))"
    )
    out = subprocess.run(["node", "-e", ptt_probe, str(tmp_path / "helpers.js")], check=True, capture_output=True, text=True).stdout
    assert json.loads(out) == [True, False, False, True, False, False, True, True, False, True, True, True, 3], "idle->held once, held->idle once, one result per press, key repeat ignored"
    gate_probe = (
        "const h = require(process.argv[1]); const g = new h.PlaybackGate(); const buf = new ArrayBuffer(8);"
        "const out = [g.accept(buf), g.interrupt(), g.accept(buf), g.accept(buf), g.nextLine(), g.accept(buf), g.accept(null), g.interrupt(), g.nextLine(), g.accept(buf)];"
        "console.log(JSON.stringify(out))"
    )
    out = subprocess.run(["node", "-e", gate_probe, str(tmp_path / "helpers.js")], check=True, capture_output=True, text=True).stdout
    assert json.loads(out) == [True, True, False, False, 1, True, False, True, 2, True], "interrupt mutes until the next line starts"
    talk_probe = "const h = require(process.argv[1]); console.log(JSON.stringify([h.MIN_TALK_BYTES, h.talkOutcome(0), h.talkOutcome(h.MIN_TALK_BYTES - 1), h.talkOutcome(h.MIN_TALK_BYTES), h.talkOutcome(96000)]))"
    out = subprocess.run(["node", "-e", talk_probe, str(tmp_path / "helpers.js")], check=True, capture_output=True, text=True).stdout
    assert json.loads(out) == [14400, "talk_cancel", "talk_cancel", "talk_end", "talk_end"], "under 0.3 s of audio the press is cancelled in the page"
    assert "type: talkOutcome(talkBytes)" in HTML and "talkBytes += pcm.buffer.byteLength" in HTML
    assert "interrupting = state.voice ? bargeIn() : null; startTalk();" in HTML, "the press mutes playback before anything async"
    script = SCRIPT
    assert script.count("getUserMedia(") == 1 and script.index("getUserMedia(") < script.index("const toggleVoice"), "the mic is opened once, by warmMic, before the first press"
    assert "warmMic();  // in parallel with the socket" in script and "releaseMic(); return closeVoice();" in script
    assert "if (!state.talking || !socketOpen()) return;" in script, "frames flow only while the button is held"
    assert "if (!gate.accept(buffer)) return;" in HTML
    assert "type: 'talk_start', interrupting" in HTML and "type: 'ask', transcript, interrupting: cut" in HTML, "the cut-off line's id travels with the press"
    assert "const stillPlaying = () =>" in HTML and "audit_updated" in HTML
    assert "answered in {{ (q.answer.timing.answer_ms / 1000).toFixed(1) }} s" in HTML and "'qa_answer_p50_ms'" in HTML
    assert "watch(pendingKey," in HTML and "if (profilePending.value) follow();" in HTML, "a dropdown change applies by itself"
    assert "change pending: {{ pendingKey }}" in HTML
    assert left_edge["x"] >= 9 and left_edge["y"] == 34, "a long name near the left edge is pushed inside the pitch"
    assert bottom_right["x"] <= 97.7 and bottom_right["y"] == 63.6, "near the goal line and the bottom edge the label moves inside and above the ball"
    assert middle == {"x": 50, "y": 34}
    assert home == {"x": 10.5, "y": 34.0, "home": True}
    assert away == {"x": pytest.approx(94.5), "y": pytest.approx(54.4), "home": False}, "the away team is mirrored into the home frame"
    assert key1 == "-|-|casual|en" and key2 == "iva|iva-06|analyst|tr"
    assert c0 == "00:00" and c125 == "02:05"
