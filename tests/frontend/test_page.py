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
    for needle in ("<svg class=\"pitch\"", "cuebanner", "Agent timeline", "follow", "toggleVoice", "speech audit", "/api/stream/fan", "/api/match/moments", "/api/voice?profile=",
                   "hold to talk", "talk_start", "talk_end", "/api/qa", "getUserMedia", "webkitSpeechRecognition", "dropPlayback",
                   "ensureVoiceSocket", "reconnecting the voice", "text only (voice off)", "ws.onclose"):
        assert needle in HTML, needle
    assert "\u2014" not in HTML
    assert "font-size: 2.2px" in (ROOT / "frontend" / "style.css").read_text(encoding="utf-8"), "player label stays small"
    css = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
    assert 'href="/static/style.css"' in HTML and "@media (max-width: 900px)" in css
    phone = css.split("@media (max-width: 480px)")[1]
    for rule in (".profile { grid-template-columns: 1fr; }", ".row { grid-template-columns: 1fr;", ".pitch .label { display: none; }", "header h1 { font-size: 16px; width: 100%;"):
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
    assert left_edge["x"] >= 9 and left_edge["y"] == 34, "a long name near the left edge is pushed inside the pitch"
    assert bottom_right["x"] <= 97.7 and bottom_right["y"] == 63.6, "near the goal line and the bottom edge the label moves inside and above the ball"
    assert middle == {"x": 50, "y": 34}
    assert home == {"x": 10.5, "y": 34.0, "home": True}
    assert away == {"x": pytest.approx(94.5), "y": pytest.approx(54.4), "home": False}, "the away team is mirrored into the home frame"
    assert key1 == "-|-|casual|en" and key2 == "iva|iva-06|analyst|tr"
    assert c0 == "00:00" and c125 == "02:05"
