"""Judgement day simulation for our own entry: four judge personas score Matchday Companion against the official
criteria on the Foundry frontier deployment. Only repo materials are used (see docs/review/judgement-day/PLAN.md).

    python scripts/judge_panel.py            # 4 judges x 2 runs, writes results.json and REPORT.md
"""

import asyncio
import json
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "review" / "judgement-day"
CRITERIA = ["technical_implementation", "agentic_design_innovation", "real_world_impact", "ux_presentation", "category_fit"]
LABELS = {
    "technical_implementation": "Technological implementation",
    "agentic_design_innovation": "Agentic design and innovation",
    "real_world_impact": "Real-world impact",
    "ux_presentation": "UX and presentation",
    "category_fit": "Category fit (Foundry)",
}


class Score(BaseModel):
    score: int = Field(ge=1, le=10)
    reason: str


class Fix(BaseModel):
    fix: str
    effort: Literal["S", "M", "L"]
    lifts: str = Field(description="which criterion this improves")


class Verdict(BaseModel):
    technical_implementation: Score
    agentic_design_innovation: Score
    real_world_impact: Score
    ux_presentation: Score
    category_fit: Score
    weaknesses: list[str] = Field(description="the three biggest weaknesses, most important first")
    fixes: list[Fix] = Field(description="three concrete fixes, highest impact per effort first")
    memorable: str = Field(description="what would make this entry stand out in the judges' memory")
    top3_likelihood: Literal["low", "medium", "high"]
    top3_reason: str


JUDGES = {
    "foundry_pm": "You are a Microsoft Foundry product lead judging the 'Best Use of Microsoft Foundry' category. You care about depth and correctness of Foundry use: agents and orchestration, evaluation, tracing, Voice Live, hosting, MCP, and whether Foundry is essential rather than decorative.",
    "broadcast_lead": "You are a football broadcast and media innovation lead at a top league. You care about real-world impact: would a broadcaster, league or club actually deploy this, does it solve a real production or fan problem, what blocks adoption.",
    "engineer": "You are a senior engineer and developer advocate. You care about technical implementation: architecture, code quality, testing, synthetic data quality, reproducibility for a judge, honest claims backed by evidence.",
    "ux_judge": "You are a product and UX judge who mostly sees the 2-minute demo video and a few screenshots. You care about how fast the idea lands, clarity of the story, polish of the UI, and the balance of frontend and backend.",
}

RUBRIC = """Hackathon: Microsoft + Premier League "Inside the Game: Developer Hackathon". Build an AI solution that turns synthetic, football-realistic data into explainable match intelligence, narratives, recaps or personalised experiences. Submissions: a demo video under 2 minutes, a public GitHub repo, a project page. Five criteria, 20% each:
1. Technological implementation (synthetic data quality, code quality, hero-technology use)
2. Agentic design and innovation (orchestration, MCP, multi-agent)
3. Real-world impact and applicability
4. User experience and presentation (demo video clarity, frontend/backend balance)
5. Adherence to category (this entry targets: Best Use of Microsoft Foundry)
Hero technologies: Microsoft Foundry, Microsoft Agent Framework, Foundry tracing and evaluation, Azure Container Apps, GitHub Copilot Agent Mode, Azure MCP.
Judge strictly, as in a competition with about 224 projects. A 7 means clearly good, 9 to 10 means best in the field."""

SCREENSHOTS = """UI screenshots (described, from docs/design/screenshots/, a real seed 30 match):
- Desktop 1440x900, one screen: dark navy 'floodlight broadcast' theme; header with league mark, scoreboard pill (Kestrel Bay 0:0 Ironvale, gold clock), chips 'Broadcast delay 20 s' and 'Foundry agents live', Stop and Voice buttons. Left: SVG pitch with mowing stripes, a ball with a club-coloured dotted trail and a player name pill; a broadcast lower-third cue 'Ironvale: 22-pass move' with crest block, green 'Verified' chip, 'numbers by code, wording by model, attempt 1' and a big '22 PASSES'. Three ticker cards under the pitch. Right: fan panel with club and player selects, Casual/Analyst and English/Turkce toggles, 'Hold to talk' button, an answer card. Footer: agent timeline summary (cues aired, skipped, rejected, number checks, answer p50) and 'Open timeline'.
- Agent timeline drawer: list of moments with verdict chips; selected moment shows steps Analyst (say it, cited ledger keys), Commentator attempts, Fact-Checker verdict and layer, Producer per profile, aired.
- Scene 5 screenshot: a planted false claim 'Ironvale have had 6 shots.' struck through, Fact-Checker 'rejected, layer code', reason '6 shots does not match the cited shots value (away_shots_last_10min = 0)', 'Never aired: no overlay, no voice, no fan narrative'.
- Phone 390 px: stacked header, pitch with the cue overlapping, profile controls, bottom tabs Live / Feed / Agents."""


def read(path: str, limit: int | None = None) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    return text if limit is None else text[:limit]


def section(text: str, start: str, end: str) -> str:
    i = text.find(start)
    j = text.find(end, i + 1) if i >= 0 else -1
    return text[i:j] if i >= 0 and j > i else ""


def dossier() -> str:
    spec = read("SPEC.md")
    adrs = "\n".join(f"- {p.stem}: {p.read_text(encoding='utf-8').splitlines()[0].lstrip('# ')}" for p in sorted((ROOT / "docs" / "adr").glob("*.md")))
    tests = len(re.findall(r"^def test_|^async def test_", "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "tests").rglob("test_*.py")), re.M))
    tree = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    top = sorted({t.split("/")[0] for t in tree})
    deploy = read("docs/deploy.md")
    perf = read("docs/performance.md")
    return "\n\n".join([
        "# PROJECT DOSSIER: Matchday Companion",
        "## README.md (current)\n" + read("README.md"),
        "## Demo video script (docs/demo-script.md)\n" + read("docs/demo-script.md"),
        "## Evaluation results (docs/eval-results.md)\n" + read("docs/eval-results.md"),
        "## Performance after fixes (docs/performance.md, summary)\n" + (section(perf, "## 2.", "\n## 3") or perf[-3000:]),
        "## SPEC objective\n" + section(spec, "## Objective", "## Capability Map"),
        "## SPEC pipeline design rules\n" + section(spec, "## Pipeline design rules", "## Interfaces"),
        "## Architecture decision records\n" + adrs,
        "## Deployment facts\nPublic URL on Azure Container Apps (managed identity, Foundry User role), per-visitor and daily live-run limits with offline fallback, docker compose offline mode, GHCR image built by GitHub Actions.\n" + section(deploy, "### Verification Results", "\n## ")[:2500],
        f"## Repository\nTop-level entries: {', '.join(top)}. Test functions: {tests} (offline suite runs without model calls; a live suite calls Foundry). Hosted agent project in hosted/ (built and unit-tested; live deployment blocked by a local sign-in issue).",
        SCREENSHOTS,
    ])


async def judge(name: str, persona: str, material: str, run: int) -> dict:
    from app.agents.auth import get_foundry_chat_client

    client = get_foundry_chat_client(os.environ["FOUNDRY_PROJECT_ENDPOINT"], os.environ["FRONTIER_MODEL_DEPLOYMENT"])
    agent = client.as_agent(name=f"judge_{name}", instructions=persona + "\n\n" + RUBRIC)
    response = await agent.run(material + "\n\nScore this entry now. Be specific and cite the dossier.", options={"response_format": Verdict})
    value = response.value
    verdict = Verdict.model_validate(value if isinstance(value, dict) else value.model_dump())
    return {"judge": name, "run": run, **verdict.model_dump()}


def report(results: list[dict]) -> str:
    lines = ["# Judgement day simulation: results", "", "Panel of four AI judge personas on the Foundry frontier deployment, two runs each, scoring our own materials against the five official criteria (20% each). See PLAN.md for method and limits.", ""]
    lines += ["| Judge | " + " | ".join(LABELS[c] for c in CRITERIA) + " | Weighted /10 | Top-3 likelihood |", "|" + " --- |" * (len(CRITERIA) + 3)]
    per_crit: dict[str, list[int]] = {c: [] for c in CRITERIA}
    for name in JUDGES:
        runs = [r for r in results if r["judge"] == name]
        means = {c: statistics.mean(r[c]["score"] for r in runs) for c in CRITERIA}
        for c in CRITERIA:
            per_crit[c] += [r[c]["score"] for r in runs]
        spread = [c for c in CRITERIA if max(r[c]["score"] for r in runs) - min(r[c]["score"] for r in runs) > 2]
        likely = "/".join(r["top3_likelihood"] for r in runs)
        lines.append(f"| {name} | " + " | ".join(f"{means[c]:.1f}" for c in CRITERIA) + f" | {statistics.mean(means.values()):.2f} | {likely}{' (unstable: ' + ', '.join(spread) + ')' if spread else ''} |")
    overall = {c: statistics.mean(v) for c, v in per_crit.items()}
    lines.append("| **Panel mean** | " + " | ".join(f"**{overall[c]:.1f}**" for c in CRITERIA) + f" | **{statistics.mean(overall.values()):.2f}** | |")
    lines += ["", "## Reasons per criterion (first run of each judge)", ""]
    for c in CRITERIA:
        lines.append(f"### {LABELS[c]} (panel mean {overall[c]:.1f})")
        for r in results:
            if r["run"] == 1:
                lines.append(f"- **{r['judge']}** ({r[c]['score']}): {r[c]['reason']}")
        lines.append("")
    lines += ["## Weaknesses (all judges, all runs)", ""] + [f"- {r['judge']}: {w}" for r in results for w in r["weaknesses"]]
    lines += ["", "## Proposed fixes (all judges, all runs)", "", "| Judge | Fix | Effort | Lifts |", "| --- | --- | --- | --- |"]
    lines += [f"| {r['judge']} | {f['fix']} | {f['effort']} | {f['lifts']} |" for r in results for f in r["fixes"]]
    lines += ["", "## What would make it memorable", ""] + [f"- {r['judge']} (run {r['run']}): {r['memorable']}" for r in results]
    lines += ["", "## Top-3 reasoning", ""] + [f"- {r['judge']} (run {r['run']}, {r['top3_likelihood']}): {r['top3_reason']}" for r in results]
    return "\n".join(lines) + "\n"


async def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    material = dossier()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dossier.md").write_text(material, encoding="utf-8")
    tasks = [judge(n, p, material, run) for n, p in JUDGES.items() for run in (1, 2)]
    results = await asyncio.gather(*tasks)
    no_dash = lambda text: text.replace(" — ", ", ").replace("—", ", ")  # repo rule: no em dashes in docs
    (OUT / "results.json").write_text(no_dash(json.dumps(results, indent=2, ensure_ascii=False)), encoding="utf-8")
    (OUT / "REPORT.md").write_text(no_dash(report(list(results))), encoding="utf-8")
    print(f"wrote {OUT / 'REPORT.md'} ({len(results)} verdicts, dossier {len(material)} chars)")


if __name__ == "__main__":
    asyncio.run(main())
