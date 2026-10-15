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
    for needle in ("<svg class=\"pitch\"", "cuebanner", "Agent timeline", "follow", "toggleVoice", "speech audit", "/api/stream/fan", "/api/match/moments", "/api/voice?profile="):
        assert needle in HTML, needle
    assert "\u2014" not in HTML
    assert 'href="/static/style.css"' in HTML and "@media (max-width: 900px)" in (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")


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
        " h.profileKeyOf({club_id:null,player_id:null,depth:'casual',language:'en'}), h.profileKeyOf({club_id:'iva',player_id:'iva-06',depth:'analyst',language:'tr'}), h.clockText(-5), h.clockText(125)]))"
    )
    out = subprocess.run(["node", "-e", probe, str(tmp_path / "helpers.js")], check=True, capture_output=True, text=True).stdout
    home, away, key1, key2, c0, c125 = json.loads(out)
    assert home == {"x": 10.5, "y": 34.0, "home": True}
    assert away == {"x": pytest.approx(94.5), "y": pytest.approx(54.4), "home": False}, "the away team is mirrored into the home frame"
    assert key1 == "-|-|casual|en" and key2 == "iva|iva-06|analyst|tr"
    assert c0 == "00:00" and c125 == "02:05"
