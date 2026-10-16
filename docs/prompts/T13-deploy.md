# Prompt: T13 deploy (docker compose offline mode, per-visitor sessions, public Azure Container App)

You are working in the repository at `C:\Users\oguz\source\repos\inside-the-game-hackathon` (Windows, PowerShell, Python 3.11 venv in `.venv`). You have an Azure login (`az login --tenant <tenant from CLAUDE.md>`), `azd`, and a filled `.env`, so live Foundry and Voice Live calls work on this machine.

## Why this matters

The hackathon rules require a working project that judges can use for free until judging ends on 2026-11-10. Judges have no identity in our Azure tenant, so keyless local runs are not a judge path. Both paths are Must (SPEC criteria 6 and 11, design rule 7):

1. `docker compose up --build` from a clean clone runs the full demo in offline mode (template agents, no Azure, no `.env`).
2. A public HTTPS URL on one Azure Container App, using a system-assigned managed identity for Foundry and Voice Live, with a per-visitor live-run limit and an offline fallback.

## Read first

`CLAUDE.md` (house rules), `SPEC.md` (design rules 1, 6, 7; hosting row; criteria 6 and 11), `tasks/todo.md` (T13), `task_state.md` (Azure resources), `.env.example`, `app/api/main.py`, `app/api/streams.py`, `app/api/voice_ws.py`, `app/api/limits.py`, `app/ledger/mcp_server.py`, `app/voice/session.py`, `frontend/index.html`.

## Current state you must know

- There is no Dockerfile, compose file or deploy script yet.
- **The app holds one global match** (`app.state.run`). Every endpoint (`/api/match/*`, `/api/stream/*`, `/api/fan/*`, `/api/qa`, `/api/match/audits`, `/api/voice`) and the ledger MCP server (`/mcp`) use it. On a public URL two judges would replace each other's match. This must be fixed first.
- Visitor identity for the live-run limit comes from `X-Forwarded-For` (`visitor_id` in `main.py`).
- The live Q&A agent reaches the ledger MCP server over HTTP (`QaPipeline(live_qa_agent(f"{base}/mcp"))`); the MCP transport's Host check is disabled.
- Existing Azure resources (eastus2, resource group `rg-matchday`): the Foundry resource and project, a Log Analytics workspace and an Application Insights resource. A $50/month subscription budget alert exists.
- Start the app locally with `python -m uvicorn app.api.main:app --port 8010 --env-file .env`. The app does not load `.env` by itself on purpose (tests import it).

## Tasks (one commit each, in this order)

1. **Per-visitor match sessions.** Replace the single `app.state.run` with a small registry keyed by a session cookie (for example `mc_session`, HttpOnly, SameSite=Lax, Secure when served over HTTPS). Each visitor gets their own `MatchRun`. Every endpoint, the SSE streams, the voice WebSocket and Q&A use the caller's run. The ledger MCP tools must read the asking visitor's run, for example through a run id in the MCP path (`/mcp/{run_id}`) or a required tool argument that the Q&A agent passes. Limits: `MAX_CONCURRENT_RUNS` (default 4; beyond it return a clear "the demo is busy, try again in a minute" message the page shows), idle runs stopped after `RUN_IDLE_TTL_S` (default 600), finished runs removed. Local single-visitor behaviour must stay the same. Tests: two clients get isolated runs (events, cues, Q&A answers, audits never cross), the cap, the idle cleanup, MCP isolation. Write `docs/adr/0001-per-visitor-sessions.md` (context, decision, consequences, about one page).
2. **Container image.** `Dockerfile` (python:3.11-slim, non-root user, `pip install -r requirements.txt`, uvicorn on port 8010, `HEALTHCHECK` on `/api/health`) and `.dockerignore` (exclude `.env`, `.venv`, `.git`, `runs/`, `spikes/out/`, `.azure/`, `docs/private/`, caches). Keep the image small.
3. **docker compose offline mode.** `docker-compose.yml` maps host port 8010 to the container, defaults to `AGENT_MODE=template` and `VOICE_MODE=off`, and uses `.env` only if it exists (compose `env_file` with `required: false`). Verify from a clean clone: `git clone` the branch into a temporary folder, `docker compose up --build -d`, `curl http://localhost:8010/api/health`, start a match through the API, confirm cues arrive, then `docker compose down`. If Docker is not available on this machine, say so and stop this step without faking it.
4. **Azure Container App.** Write an idempotent `infra/deploy.ps1` (az CLI) and `docs/deploy.md`. Steps:
   - Build the image in Azure with `az acr build` into an Azure Container Registry, **Basic SKU only**. Before creating the registry, print the estimated monthly cost and ask Oguz to confirm; do not create any other paid resource.
   - One Container Apps environment in eastus2 that uses the existing Log Analytics workspace.
   - One Container App: external ingress, target port 8010, WebSockets and SSE working, **min and max replicas 1** (state is in memory; never scale out), 0.5 vCPU and 1 GiB unless measurements say otherwise.
   - System-assigned managed identity with the "Foundry User" role on the Foundry resource. Check that Voice Live works with it; if it returns 401 or 403, add the narrowest extra role that fixes it and record which.
   - Environment: `FOUNDRY_PROJECT_ENDPOINT`, `SMALL_MODEL_DEPLOYMENT`, `FRONTIER_MODEL_DEPLOYMENT`, `AGENT_MODE=foundry`, `VOICE_MODE=voicelive`, `BROADCAST_DELAY_S=20`, `PUBLIC_LIVE_RUNS_PER_DAY=2`, `MAX_CONCURRENT_RUNS`, `RUN_IDLE_TTL_S`, and the Application Insights connection string so traces from the public app reach the Foundry portal. The Q&A agent should reach the MCP server on `http://127.0.0.1:8010` inside the container, not through the public hostname.
   - No secrets in the repo or in the script; values come from `.env` or `az` lookups at deploy time.
5. **Verify the public URL end to end** in a browser over HTTPS: the page loads; a match plays with live Foundry agents; the voice speaks; push-to-talk works (the microphone needs HTTPS); a Q&A answer is verified and spoken; a second visitor in another browser profile gets an isolated match; after `PUBLIC_LIVE_RUNS_PER_DAY` live runs the same visitor falls back to offline agents with a visible notice; traces from the public app show in the Foundry portal. Record the URL, the measured first-cue time and any problems in `docs/deploy.md` and `task_state.md`.

## Rules

- Branch: create `t13-deploy` from `main`; push it; do not push to `main`; do not open a pull request.
- Before every commit: `.venv\Scripts\python.exe -m pytest tests -q` must pass (about 230 tests, about 20 s, 30 s per-test guard). Add tests for every behaviour change; no test may depend on Azure unless it is marked `@pytest.mark.live`.
- No em dashes in code comments, docs or UI text. No Co-Authored-By trailers. Fictional league only. Keep Azure spend to the Foundry project plus one Container App and one Basic registry.
- Do not change `SPEC.md` interfaces or criteria directly; put proposed changes (for example the session cookie and the MCP path) in `docs/reviews/2026-10-17-t13-proposals.md`.
- Leave the Container App running when you finish (it must stay up until 2026-11-10).
- Update `task_state.md` and `tasks/todo.md` (T13) when done.

## Done when

- Five commits are pushed to `t13-deploy`, the suite passes, and the ADR exists.
- The clean-clone compose run works offline (or you reported that Docker is missing).
- The public URL works for the checks in task 5.
- Report back: the public URL, the resources created with SKUs and estimated monthly cost, the role assignments, the verification results for each check in task 5, and anything that did not work.
