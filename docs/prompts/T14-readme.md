# Prompt: T14 README, architecture diagram and judge instructions (Matchday Companion)

You are working in the repository at `the repository root` (Windows, PowerShell, Python 3.11 venv in `.venv`). Read `CLAUDE.md`, `SPEC.md`, `requirements.md` and `docs/demo-script.md` first; their hard rules apply.

## Goal

The README is what judges read after the 2-minute video, and the repo becomes public for judging. Write it so a judge understands in 30 seconds what this is, why it matters, how it uses Microsoft Foundry, and how to try it in 2 minutes. Judging (20% each): technical implementation, agentic design and innovation, real-world impact, user experience and presentation, category fit (Best Use of Microsoft Foundry).

## Inputs (read before writing; use only facts you can point to in the repo)

- `README.md` today: pitch line, quick start, the synthetic dataset section and its schema table, data licence. Keep the dataset and licence sections (tighten wording if needed).
- `SPEC.md` (design rules, interfaces, pipeline), `docs/adr/0001` to `0006`, `docs/eval-results.md` (headline and tables, latency from traces), `docs/deploy.md` (public URL, roles, limits), `docs/performance.md` if P5 has added it, `docs/design/screenshots/` (desktop and phone screenshots, `scene5-rejected.png`), `docs/assets/hero.jpg`.
- Public URL: https://ca-matchday.orangetree-bcef6d10.eastus2.azurecontainerapps.io

## README structure (in this order)

1. **Title, hero image, one-line pitch.** `docs/assets/hero.jpg` scaled in Markdown (`<img src="docs/assets/hero.jpg" width="100%">`), then: "A live co-commentator you can interrupt, and that can't lie." Under it a row of links: Try it (public URL), 2-minute video (placeholder `VIDEO_URL`, Oguz fills it in T15), Architecture, Evaluation.
2. **Why it matters (impact, 4 to 6 sentences).** Broadcasters cannot put an AI voice on air if it might invent a statistic; this is the trust layer that makes live AI commentary usable: every number comes from deterministic code, every sentence is checked before it is shown, every spoken word is audited. Name who uses it (broadcast producer for overlay cues, fan for a personal co-commentator in their language) without inventing market numbers.
3. **What you see (screenshots).** Desktop live cue and the open agent timeline side by side or stacked, the phone view, and `scene5-rejected.png` with a one-line caption each. Use the files in `docs/design/screenshots/`.
4. **Try it in 2 minutes (judge instructions).**
   - Public URL: press Start match (1x is live Foundry agents, 4x is precomputed), turn Voice on, hold "Hold to talk" and ask "How is my player doing?", open the timeline to see the four agents per moment. Mention the limits plainly: 2 live matches per visitor per day and a daily total, then offline agents with a visible notice; 20 s broadcast delay by design.
   - Local, no Azure: `docker compose up --build`, open http://localhost:8010 (offline agents, no voice).
   - Local with Foundry: the env vars from `.env.example` (create it if missing, names only, no values), `az login`, `AGENT_MODE=foundry VOICE_MODE=live`. Note that on some Windows machines the Azure CLI sign-in broker fails and `AZURE_CORE_ENABLE_BROKER_ON_WINDOWS=false` fixes it.
5. **Architecture.** A Mermaid diagram (GitHub renders it) from the synthetic event stream to the screen and the voice: simulator, ledger (deterministic metrics, MCP server), director, the four Foundry agents (Analyst, Commentator, Fact-Checker with code layer and LLM wording layer and the reject loop, Producer per fan profile), broadcast delay clock, SSE to the page, Voice Live (verbatim speech, speech audit, push-to-talk listening), Q&A agent over MCP, tracing to Application Insights and the Foundry portal, Container App with managed identity. Then a **pipeline stages table**: stage, what it does, model or code, file. Keep it to what the code does.
6. **How it uses Microsoft Foundry** (category fit, one bullet each, with the file): Foundry models through the Responses API with keyless `DefaultAzureCredential`; Microsoft Agent Framework graph workflow with a conditional reject edge; Foundry Voice Live for verbatim speech, barge-in and transcription; ledger tools over MCP; Foundry tracing in Application Insights (link a trace screenshot if one exists, otherwise a placeholder `docs/assets/trace.png` for Oguz to capture in T15); Foundry cloud evaluation (Groundedness, Relevance, Coherence); the hosted agent project in `hosted/` with its status stated honestly (built and unit-tested; live deployment blocked by the local sign-in, see `docs/deploy.md`) unless it has been deployed by then.
7. **Evaluation.** The headline sentence from `docs/eval-results.md` verbatim, the small results table, the planted-error result (0 of N reached air), the latency numbers from traces, and a link to the full file. Do not round differently from the source.
8. **Design decisions (short FAQ).** Each answer 2 to 4 sentences with a link to its ADR:
   - Why an LLM Fact-Checker if code checks the numbers? (code catches every number and actor error; the wording judge catches what keeps every number right but says something false, such as a swapped team; see the planted-error kinds in SPEC)
   - Why a 20 s broadcast delay? (ADR 0004)
   - Why speak pre-generated text instead of letting the voice model talk? (ADR 0003)
   - Why MCP for fan questions? (ADR 0005)
   - Why per-visitor sessions and run limits? (ADR 0001, the limits in `docs/deploy.md`)
9. **Notes on the data.** The pass-share possession note (possession is the share of passes, how it is computed, where) and the generated-names note (all clubs and players are invented; names are generated; any resemblance to real people is accidental). Keep the existing synthetic dataset section and schema table here.
10. **Repository map.** A short table of top-level folders and what is in them.
11. **Built with.** Microsoft Foundry, Microsoft Agent Framework, Foundry Voice Live, MCP, FastAPI, Vue 3, Azure Container Apps, GitHub Actions, and AI coding assistants as used (state plainly: Claude Code and another coding agent were used for implementation and review; GitHub Copilot only if it was actually used, otherwise leave it out). Image credits link to `docs/assets/CREDITS.md`.
12. **Licence.** Code licence (add `LICENSE` with MIT if none exists, copyright Oguz Koroglu 2026) and the existing data licence section.

## Additions from the judgement-day simulation (docs/review/judgement-day/REPORT.md, fixes 2 to 5 and 8)

- First screen of the README carries the proof numbers (planted errors on air with and without the Fact-Checker, cue on-time rate, Q&A median) with their source files; remove every "work in progress" phrase.
- Besides the architecture diagram, add two Mermaid sequence diagrams: one moment from event to cue and spoken line (including a rejection branch), and one fan question through MCP to the spoken answer.
- In "How it uses Microsoft Foundry", use a table: user-facing feature, Foundry capability, proof artifact (trace id, eval run, speech audit, MCP span), file.
- Add a "Where it fits in a broadcast" paragraph: position in the production chain, who approves cues, what it augments, and that a real feed plugs in through the same event schema the simulator emits (no claims of real integrations).
- Add a "Judge path" box: the 90-second flow on the public URL, what offline fallback looks like, and one command each to replay seed 30 offline (`python -m app.agents.run_match --seed 30 --speed 30`) and to rebuild the evaluation report from saved runs (check `app/eval/report.py` for the exact command).
- Add a short "When things go wrong" section: late cue dropped, Foundry or MCP unavailable, live-run limit reached, voice unavailable, each with what the viewer sees.

## Rules for the text

- English, plain and concrete, no marketing filler, no em dashes, no emoji. Short paragraphs, tables where they help.
- Every number in the README must come from a file in the repo (eval-results, deploy, performance); cite the file. No invented metrics, users or market sizes.
- Fictional league only: no real clubs, players, broadcasters, sponsors or trademarks; "Premier League" appears only as the hackathon's name.
- No keys, tenant IDs, subscription IDs, client names or private paths. The Foundry resource name and the public URL are fine.
- Links must be relative for repo files and must resolve (check each one).

## Also

- `docs/architecture.md`: the same Mermaid diagram with a longer walk-through of one moment end to end (event in, cue on screen, line spoken), for judges who want depth. Link it from the README.
- `.env.example` with every variable the app reads (grep `os.environ` in `app/`), names and one-line comments only, no values except safe defaults.
- Update `task_state.md` and `tasks/todo.md` (T14 result line).

## Verify

- `.venv\Scripts\python.exe -m pytest tests -q` passes (add a small test that every relative link in README.md and docs/architecture.md points to an existing file, and that README.md contains no em dash).
- Render check: open the README on GitHub on your branch and confirm the Mermaid diagram and images render; describe what you saw.

## Rules

- Branch `t14-readme` from `main`; push it; do not push to `main`; no pull request.
- One commit per logical part (README, architecture doc, .env.example, link test). No Co-Authored-By trailers.

## Reporting rule

Only report something as done when you ran it and can show the evidence. Say "not done" otherwise.

## Done when

- README.md follows the structure above, every number is sourced, every link resolves, the diagram renders on GitHub.
- Report back: the branch, the commit list, the placeholders left for Oguz (video URL, trace screenshot), and anything you could not source.
