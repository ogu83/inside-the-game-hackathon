# Prompt: T13c deploy the commentary workflow as a Foundry Hosted Agent (timeboxed)

You are working in the repository at `the repository root` (Windows, PowerShell, Python 3.11 venv in `.venv`). You have an Azure login and a filled `.env`. Read `CLAUDE.md` (Azure section) and the SPEC "Hosted vs in-container" lessons first.

**Hard timebox: half a day.** If it is not working by then, stop, record the blocker and the last error, and reword the README and `docs/deploy.md` so the hosted agent reads as an option that is packaged and tested, not as a failure. That is an acceptable outcome.

## Where it stands (reviewed 2026-10-18)

- `hosted/` is an `azd` project (`hosted/azure.yaml`, service `commentary`, `host: azure.ai.agent`, Python 3.13, remote build from `uv.lock`, Responses protocol 2.0.0) wrapping `app/agents/workflow.py` with `ResponsesHostServer`. `tests/test_hosted.py` passes.
- The T10 deploy was blocked by the Azure CLI sign-in broker. That is fixed: `az config set core.enable_broker_on_windows=false` is set and `az account get-access-token` works without any extra variable.
- **Packaging bug found in review, fix it first:** the build context is only `hosted/src/commentary` (see its `Dockerfile`: `COPY . .`), so the repo's `app/` package is not in the container. `main.py` also adds `Path(__file__).resolve().parents[2]` to `sys.path`, which is `hosted/`, not the repo root. Locally the tests pass because they run from the repo root; in Foundry the agent would fail at import time. `pyproject.toml` also lacks dependencies that the imported `app` modules need (check what `app/agents/*` and `app/ledger/*` import, for example `mcp`, `opentelemetry`, `azure-monitor-opentelemetry` if pulled in).
- `azd` may not be on the bash PATH; check `azd version` in PowerShell. If missing, install it (`winget install microsoft.azd`) and the agents extension (`azd extension install azure.ai.agents`). Reuse the az login: `azd config set auth.useAzCliAuth true`.

## Tasks

1. **Make the build context self-contained.** Add a small script `hosted/sync_app.py` (or an `azd` `predeploy` hook in `hosted/azure.yaml` that runs it) that copies only the needed packages (`app/__init__.py`, `app/agents/`, `app/ledger/`, and anything they import) into `hosted/src/commentary/app/`, skipping `__pycache__`. Git-ignore the copy. Fix the `sys.path` line so the container finds the vendored `app/` next to `main.py`. Add the missing runtime dependencies to `hosted/src/commentary/pyproject.toml` and refresh `uv.lock` (`uv lock` in that folder).
2. **Prove it outside the repo.** Copy `hosted/src/commentary` (after the sync) to a temp folder outside the repo, run `uv sync --frozen` there, and start `main.py` (or at least import it) to show it no longer depends on the repo root. Add a test that runs the sync into a temp dir and asserts `main.py` imports from there with the repo root not on `sys.path`.
3. **Deploy.** `cd hosted; azd deploy` against the existing Foundry project. No new Azure resources beyond what `azd` creates for the hosted agent inside the project.
4. **Invoke it remotely** over the Responses protocol with one candidate moment from seed 30 (as `test_hosted.py` builds it), show the response (verdict, aired text), and find its trace in the Foundry portal Tracing tab (operation id plus what the spans show).
5. **Cost.** Check in the portal whether the hosted agent bills while idle. If it does, scale it to zero or stop it after the proof and write down how to start it again before the video (T15 needs a warm agent for scene 6 if we show it).
6. **Record** in `docs/deploy.md` (replace the "Deployment Blocker" section with the result), update the README "How it uses Microsoft Foundry" table row and the hosted-agent status line with the real outcome, and update `task_state.md` and `tasks/todo.md` (T13c result line).

## Rules

- Branch `t13c-hosted` from `main`; push it; do not push to `main`; no pull request.
- Before every commit: `.venv\Scripts\python.exe -m pytest tests -q` must pass. No em dashes, no Co-Authored-By trailers, no keys or tenant IDs added to the repo.
- Do not touch the Container App or the app code outside `hosted/` (except the README and docs lines named above).

## Reporting rule

Only report something as done when you ran it and can show the evidence (command output, the remote response, the trace id). Say "timeboxed out" with the last error otherwise.

## Done when

- The hosted agent answers a remote request and its trace is visible, with evidence; or the timebox ran out and the blocker is recorded and the README wording is honest.
- Report back: the branch, the commit list, the deploy output summary, the remote response, the trace id, the idle-cost finding and what you did about it.
