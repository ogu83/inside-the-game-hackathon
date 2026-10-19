# CLAUDE.md: The Commentator's Brain

## What this project is
Solo entry for the Microsoft + Premier League "Inside the Game: Developer Hackathon". Four Microsoft Foundry agents (Analyst, Commentator, Fact-Checker, Producer) turn a synthetic football event stream into verified broadcast overlay cues and personalized fan narratives. Target category: Best Use of Microsoft Foundry.

Deadline: 2026-10-27 23:59 PT. Internal target: submitted 2026-10-26.

## Key files
- `IDEA.md`: why this direction, Not Doing list
- `SPEC.md`: source of truth (objective, interfaces, boundaries, success criteria). Update it before changing behavior.
- `requirements.md`: hackathon rules, dates, submission checklist
- `tasks/plan.md`, `tasks/todo.md`: plan and task list
- `task_state.md`: session state. **Update after every task, before committing.** Run `pwsh .hooks/compaction_restore.ps1` at session start.

## Gate
SPEC.md is DRAFT until Oguz approves it. Do not write implementation code before approval. Work tasks in todo.md order, one at a time.

## Hard rules (from the official rules)
- Fictional league only: no real clubs, players, crests, sponsors or other third-party trademarks in code, data, UI, README or video.
- No StatsBomb or other non-commercially licensed data as input (Microsoft gets a commercial licence to the submission).
- Repo becomes public before submission: no keys, no client names, no paths into private notes, no Co-Authored-By trailers.
- Agents never compute numbers; they cite ledger keys. Deterministic code owns every statistic.
- No em dashes in docs or UI copy.

## Event confidentiality (agreed 2026-10-15)
Oguz signed the Microsoft Event Participation and Confidentiality Agreement and the B2B Connect guest terms (`docs/document.md`).
- No audio/video recording of Event sessions (Reactor talks, office hours, Teams calls): no Raven, no Fathom.
- Non-public information from the Event (Innovation Studio resources, starter kits, preview features, internal slides) is confidential: never copy it into the repo, README, demo video, YouTube content or LinkedIn posts. Build on public docs (learn.microsoft.com, public GitHub) so every artifact stays publishable.
- The guest Teams workspace is audited and visible to others there: no keys, client material or private notes.

## Run commands
```
py -3.11 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests/ -q              # commit gate (no live model calls)
python -m pytest tests/ -q -m live      # opt-in, calls Foundry models, costs tokens
python -m uvicorn app.api.main:app --port 8010 --reload
docker compose up --build -d
```
- Live locally: the app does not load `.env`. In PowerShell: `Get-Content .env | ? {$_ -match '^[A-Z_]+='} | % {$k,$v=$_ -split '=',2; Set-Item "env:$k" $v}; $env:AGENT_MODE='foundry'; $env:VOICE_MODE='live'`, then uvicorn
- `pytest -m live`: the Q&A-over-MCP test needs the app on :8010 with a match running and one cue aired; otherwise expect that single failure
- Helper scripts that need Pillow: `py -3.11 -I script.py` (the default `python` 3.13 has a broken PIL install)

## Frontend gotchas
- `#app` is the Vue mount element: bindings on it (`:class`) are never compiled; set them from a watcher
- Bump `style.css?v=` in index.html on every CSS change, or browsers and the public app serve stale CSS
- Verify UI in a real browser with a real match, never with injected state; `tests/frontend/test_page.py` pins copy and structure only

## Ports
- 8010: this app (dev and container host port)
- 8000: taken by voicebox; 8002: ai-decision-room

## Hooks
- `test_gate.ps1` (PostToolUse on Bash|PowerShell): runs pytest after any `git commit`; exit 2 stops the loop if tests fail. `tests/` must contain at least one passing test before the first commit.
- `compaction_save.ps1` (Notification PreCompact): timestamps `task_state.md`.
- Hook paths in `.claude/settings.json` use forward slashes.

## Azure
- Subscription "Azure subscription 1" (<subscription-id>) in tenant <tenant-id>. Log in with `az login --tenant <tenant-id>` (MFA is enforced; plain `az login` silently skips the tenant). Never use the "Microsoft" tenant (72f988bf...) that shows up from the hackathon's B2B guest access.
- `azd` is not installed; `az` 2.87 is. Install `azd` + `azure.ai.agents` extension (or `winget install Microsoft.FoundryDevPack`) in T2.
- Foundry facts as of 2026-10 (Azure AI Foundry was renamed Microsoft Foundry): use the Responses API, not the Assistants API; `project.agents`, not `project.beta.agents` (azure-ai-projects >= 2.3.0); cloud evaluations are long-running operations (submit, then poll); a catalog model is not callable until it has a named deployment; RBAC role is "Foundry User".
- Frontier models (GPT-5.5/5.6 class) need a quota request unless the subscription is Tier 5/6.
- Keep Azure spend to one Foundry project + one Container App; set a budget alert.
- The Azure CLI sign-in broker fails on this PC (0x800704cf, "Status_NoNetwork"): keep `az config set core.enable_broker_on_windows=false` (set 2026-10-17); log in with `az login --tenant <id> --use-device-code`
- Public app: https://ca-matchday.orangetree-bcef6d10.eastus2.azurecontainerapps.io. It picks up a new GHCR image only after a restart: `az containerapp revision restart -n ca-matchday -g rg-matchday --revision $(az containerapp revision list -n ca-matchday -g rg-matchday --query "[?properties.active].name | [0]" -o tsv)` (bash syntax for `!`)
