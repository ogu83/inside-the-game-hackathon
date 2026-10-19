# Prompt: T13b deploy and verify the public URL (finish T13)

You are working in the repository at `the repository root` (Windows, PowerShell, Python 3.11 venv in `.venv`). You have an Azure login and a filled `.env`.

## Where T13 stands (reviewed 2026-10-16)

The T13 code is merged into `main` (per-visitor sessions, Dockerfile, compose offline mode, GHCR workflow, `infra/deploy.ps1`, `docs/deploy.md`, ADR 0001); 246 tests pass. But the deployment itself was **not** done:

- `az containerapp show -n ca-matchday -g rg-matchday` returns **ResourceNotFound**; only the environment `cae-matchday` exists. The URL `https://ca-matchday.orangetree-bcef6d10.eastus2.azurecontainerapps.io` returns 404. The previous report listed it as provisioned and verified; it was not.
- The GHCR image did not exist yet (the workflow only runs on `main`).
- The `docker compose` clean-clone check was not run (the Docker engine needs an elevated start).
- None of the six public-URL checks from T13 task 6 were run.

**Reporting rule for this task:** only report something as done when you ran it and can show the evidence (command output, HTTP status, a screenshot description with what was on screen). Say "not done" or "blocked" otherwise.

## Tasks (in this order; commit script or doc changes one per commit)

1. **Image on GHCR.** Pushing `main` triggers `.github/workflows/image.yml`. Confirm the run succeeded (GitHub Actions page for `ogu83/inside-the-game-hackathon`, or `gh run list` if `gh` is installed) and that `ghcr.io/ogu83/matchday-companion:latest` exists. The package must be **public**. If it is private, stop and give Oguz the exact steps (GitHub profile, Packages, matchday-companion, Package settings, Change visibility, Public), then wait. Verify anonymous pull access without credentials, for example:
   `curl -s "https://ghcr.io/token?scope=repository:ogu83/matchday-companion:pull"` then a HEAD request for `https://ghcr.io/v2/ogu83/matchday-companion/manifests/latest` with that token and `Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json`; it must return 200.
2. **Fix `infra/deploy.ps1` before running it.**
   - Roles: assign **"Foundry User"** on the Foundry resource (the role this project uses everywhere and that worked for the Responses API and Voice Live in T2). Remove "Azure AI Developer" (too broad). Keep "Cognitive Services OpenAI User" only if a test shows it is needed. Do not swallow role assignment errors (`2>$null | Out-Null`); print them and fail.
   - Set `PUBLIC_LIVE_RUNS_PER_DAY=2` explicitly in the env vars.
   - Replace the unconditional "Deployment Successful" with a real check: poll `https://<fqdn>/api/health` for up to 5 minutes and exit non-zero if it never returns 200; print the last container logs (`az containerapp logs show -n <app> -g <rg> --tail 50`) on failure.
   - Add tests only if you change Python code (none expected).
3. **Deploy.** Run `pwsh infra/deploy.ps1`. Wait for role propagation (up to about 5 minutes) before judging Foundry or Voice Live errors. Show the final `az containerapp show` summary (image, replicas, fqdn, running status) and the role assignments for the app's principal.
4. **Verify the public URL end to end over HTTPS**, with evidence for each:
   1. `/api/health` returns 200 with `agent_mode: foundry` and `voice: true`.
   2. In a browser: a match starts with live Foundry agents and cues appear on the delayed clock.
   3. The voice speaks a cue (Voice Live with the managed identity; if 401 or 403, read the logs, add the narrowest missing role, redeploy, and record which role).
   4. Push-to-talk works over HTTPS: hold, ask "How is my player doing?", release; one question card, answer spoken verbatim.
   5. A second visitor (another browser profile or incognito) gets an isolated match.
   6. After two live runs the same visitor falls back to offline agents with a visible notice.
   7. Traces from the public app appear in Application Insights (query `dependencies | where cloud_RoleName contains "matchday" or name contains "invoke_agent" | take 20` in the last hour, or the Foundry portal Tracing tab).
   If you cannot operate a browser or microphone yourself, run checks 1 and 7 and the API-level parts (start a match via `POST /api/match/start`, read `/api/stream/cues`), then list the browser checks for Oguz to do and say so plainly.
5. **docker compose clean clone.** Ask Oguz to start Docker Desktop (it needs an elevated start on this machine). Then: clone `main` into a temporary folder, `docker compose up --build -d`, `curl http://localhost:8010/api/health`, start a match through the API, confirm cues arrive, `docker compose down`, delete the folder. If Docker still cannot start, report "blocked" with the error.
6. **Record results** in `docs/deploy.md` (URL, image tag, roles, first-cue time, each check with its result) and update `task_state.md` and `tasks/todo.md` (T13).

## Rules

- Branch: `t13b-deploy` from `main`; push it; do not push to `main`; no pull request.
- Before every commit: `.venv\Scripts\python.exe -m pytest tests -q` must pass.
- No em dashes, no Co-Authored-By trailers, fictional league only.
- Keep Azure spend to the Foundry project plus this one Container App (no registry). Leave the app running (it must stay up until 2026-11-10).

## Done when

- The public URL serves the app and every check in task 4 has a recorded result with evidence (done, or explicitly handed to Oguz for the browser and microphone parts).
- The compose clean-clone run worked, or is reported as blocked with the error.
- Report back: the URL, the image tag, the role assignments, the results table for task 4, the compose result, and anything that failed.
