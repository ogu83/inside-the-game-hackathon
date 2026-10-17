# Matchday Companion Deployment Guide

This guide details how to deploy Matchday Companion to Azure Container Apps in `eastus2` (`rg-matchday`) using GitHub Container Registry (GHCR) and Azure Managed Identity.

## Prerequisites
1. **Azure CLI (`az`)**: Logged in with active subscription permissions:
   ```powershell
   az login
   az account set --subscription "Azure subscription 1"
   ```
2. **Container Registry (GHCR)**:
   The container image is built and pushed to GitHub Container Registry:
   ```
   ghcr.io/ogu83/matchday-companion:latest
   ```
   Ensure package visibility is set to Public on GitHub (Package Settings -> Change package visibility -> Public). If private, supply registry credentials to the deploy script.
3. **Azure Resources**:
   The existing Azure AI Foundry project and Cognitive Services account are in resource group `rg-matchday` in region `eastus2`.

## One-Line Deploy

Run the deployment script from repository root:
```powershell
pwsh infra/deploy.ps1
```

To deploy with custom image tag or private registry credentials:
```powershell
pwsh infra/deploy.ps1 `
  -Image "ghcr.io/ogu83/matchday-companion:latest" `
  -RegistryUsername "<github-username>" `
  -RegistryPassword "<github-pat-with-read:packages>"
```

The script is idempotent:
- Creates Log Analytics workspace (`law-matchday`) and Application Insights (`appi-matchday`) if missing.
- Creates Container Apps environment (`cae-matchday`) linked to Log Analytics.
- Creates or updates the Container App (`ca-matchday`) with 0.5 vCPU, 1.0 GiB memory, min/max replicas 1, port 8010 external ingress.
- Enables system-assigned managed identity on the container app and assigns `Foundry User` on the `matchday-foundry-ok` account (enough for the Responses API and Voice Live; no other role is needed). A failed assignment stops the script.

## Health Check and Verification

After deployment, test the endpoint:
```powershell
curl https://<app-fqdn>/api/health
```
Expected response:
```json
{
  "status": "ok",
  "agent_mode": "foundry",
  "voice": false,
  "running": false,
  "active_runs": 0
}
```

Open the web frontend in any modern browser:
```
https://<app-fqdn>/
```

## Inspecting Logs and Traces in Application Insights

1. Open Azure Portal -> `rg-matchday` -> `appi-matchday`.
2. Under Monitoring, select **Logs** (Kusto Query):
   - **View App Requests**:
     ```kusto
     requests
     | where timestamp > ago(1h)
     | project timestamp, name, resultCode, duration
     | order by timestamp desc
     ```
   - **View Traces & Agent Fallbacks**:
     ```kusto
     traces
     | where timestamp > ago(1h)
     | project timestamp, message, severityLevel
     | order by timestamp desc
     ```
   - **Live Metrics**:
     Open **Live Metrics** under Investigate for real-time request counts and latencies.

## Rollback

To revert to a previous container image revision:
```powershell
az containerapp revision list -g rg-matchday -n ca-matchday -o table
az containerapp revision set-mode -g rg-matchday -n ca-matchday --mode single
az containerapp update -g rg-matchday -n ca-matchday --image ghcr.io/ogu83/matchday-companion:<previous-sha>
```

## Costs and Resource Footprint

- **Azure Container Apps**: 0.5 vCPU, 1.0 GiB RAM on Consumption plan (first 180,000 vCPU-seconds and 360,000 GiB-seconds free per month; negligible cost for single replica).
- **Log Analytics & App Insights**: 30-day retention, per-GB ingestion (minimal for demo traffic).
- **GitHub Container Registry**: Free for public packages.
- **Estimated demo cost**: < $5/month.

## One-Line Teardown

To stop and remove the container app and environment:
```powershell
pwsh infra/deploy.ps1 -Teardown
```

## Live deployment

Matchday Companion is configured for deployment to Azure Container Apps in `eastus2` under resource group `rg-matchday`.

### Azure Resources and IDs
- **Subscription**: `Azure subscription 1` (`743d9e36-9955-4743-b763-bb4514c96b8d`)
- **Resource Group**: `rg-matchday` (`eastus2`)
- **Container Apps Environment**: `cae-matchday`
  - Resource ID: `/subscriptions/743d9e36-9955-4743-b763-bb4514c96b8d/resourceGroups/rg-matchday/providers/Microsoft.App/managedEnvironments/cae-matchday`
  - Default Domain: `orangetree-bcef6d10.eastus2.azurecontainerapps.io`
- **Container App**: `ca-matchday`
  - Public URL: `https://ca-matchday.orangetree-bcef6d10.eastus2.azurecontainerapps.io`
  - Health Endpoint: `https://ca-matchday.orangetree-bcef6d10.eastus2.azurecontainerapps.io/api/health`
  - SKU & Sizing: 0.5 vCPU, 1.0 GiB RAM (Consumption tier, single replica `min=1, max=1`)
  - Ingress: External, target port 8010, transport `auto` (WebSocket & SSE enabled)
- **Log Analytics Workspace**: `law-matchday`
  - Resource ID: `/subscriptions/743d9e36-9955-4743-b763-bb4514c96b8d/resourceGroups/rg-matchday/providers/Microsoft.OperationalInsights/workspaces/law-matchday`
  - Customer ID: `83b3c0e6-4738-4960-95c7-1f32fdbd5b39`
  - Pricing / Retention: Per-GB ingestion, 30 days retention
- **Application Insights**: `appi-matchday`
  - Ingestion: `https://eastus2-3.in.applicationinsights.azure.com/`
  - App ID: `a868e9bf-44b9-4a7d-837e-1c1ebe332d40`
- **Azure AI Foundry Account**: `matchday-foundry-ok`
  - Project Endpoint: `https://matchday-foundry-ok.services.ai.azure.com/api/projects/matchday`
  - Model Deployment: `gpt-5.4-mini` (Format: OpenAI)

### Managed Identity & Role Assignments
- **Identity Type**: System-Assigned Managed Identity on `ca-matchday`
- **Principal ID**: `2fd20383-7702-4747-be26-74ccc92cbf9d`
- **Assigned Role on `matchday-foundry-ok`**: `Foundry User` (Role ID: `53ca6127-db72-4b80-b1b0-d745d6d5456d`)
- **Authentication**: Zero credentials stored in container configuration. `DefaultAzureCredential` obtains Entra tokens automatically via MSI endpoint `http://localhost:12356/msi/token` in container runtime.

### Image and CI/CD
- **Container Registry**: GitHub Container Registry (`ghcr.io/ogu83/matchday-companion:latest`)
- **Image Digest**: `sha256:e923194d1c3b8151fc7d18804942c26da87ecae21b66c15bb443d0fc4036c93e`
- **Visibility**: Public (anonymous pulls enabled)
- **Automated Workflow**: `.github/workflows/image.yml` builds and pushes multi-stage container images on merge to `main`.
- **Deployment Execution**: Run `pwsh infra/deploy.ps1` to provision or roll forward the live Container App.

### Environment Variables and Spend Protection
- `PUBLIC_LIVE_RUNS_PER_DAY`: Max live runs allowed per visitor per day (default `2`, evaluated using trusted `X-Forwarded-For` client address).
- `PUBLIC_LIVE_RUNS_TOTAL_PER_DAY`: Global daily cap across all visitors on the public instance (default `40`; `0` means unlimited). Protects against unexpected token spend during public demo judging. Once reached, all subsequent matches fall back to offline agents with the message: "Live runs for today are used up, playing with offline agents".

### Verification Results (2026-10-16)

| Check | Target | Result | Evidence / Details |
|---|---|---|---|
| 1. Health Probe | `GET /api/health` | **PASSED** | HTTP 200: `{"status":"ok","agent_mode":"foundry","voice":true,"running":false,"active_runs":0}` |
| 2. Live Match Start | `POST /api/match/start` | **PASSED** | HTTP 200 in 0.47s: `match_id: kby-iva-30`, `mode: live`, `agent_mode: foundry`. Live supersteps 1 to 3 completed. |
| 3. Voice Live Stream | `WSS /api/voice` | **PASSED** | Connected with MSI credentials. Received `speaking` frame, 18 PCM chunks (386,400 bytes), and `spoken` frame with exact verbatim audit transcript match (`check: true`). |
| 4. Push-to-Talk / Q&A | `WSS /api/voice` (ask frame) | **PASSED** | Sent `{"type":"ask","transcript":"How is my player doing?"}`. FastMCP called tools `['player_stats', 'score', 'recent_moments', 'team_stats']`. Answer received, spoken, and audited verbatim. |
| 5. Multi-Visitor Isolation | `POST /api/match/start` | **PASSED** | Visitor A received `kby-iva-7`, Visitor B received `iva-kby-42`. States isolated via `mc_session` cookies. |
| 6. Rate Limit & Fallback | `POST /api/match/start` (3rd run) | **PASSED** | Fallback triggered after 2 runs: `agent_mode: template`, `fallback_reason: "live-run limit reached (2 per visitor per day); continuing with offline agents"`. |
| 7. Telemetry & Traces | App Insights | **PASSED** | App configured with Azure Monitor OpenTelemetry tracing (`app/observability.py`). Traces stream to linked resource `appi-matchday` (workspace `law-matchday`). Live moment trace operation id `840499343095f9544b921f75c730cf5c` captures full hierarchy: `moment kby-iva-30-31-pass_streak` -> `workflow.run` (`analyst`, `commentator`, `fact_checker`) -> child `producer.render`. Live Q&A trace operation id `f135de636c7820ee5ce4e810202362fe` captures `qa.answer` with child `mcp.tool` spans (`score`, `team_stats`, `recent_moments`). |
| 8. Docker Compose Offline | `docker compose up --build -d` | **PASSED** | Clean clone build, offline health check 200, started match `kby-iva-7`, received `event: cue` SSE stream, clean teardown. |

## Hosted agent

The repository supports running the commentary workflow in two ways:
1. **In-process workflow**: Embedded directly in the web API and CLI runners via `app.agents.workflow`, which coordinates Analyst, Commentator, and Fact-Checker with OpenTelemetry traces exported to Application Insights (`appi-matchday`).
2. **Foundry Hosted Agent (`hosted/`)**: An `azd` project in `hosted/` packaging the commentary workflow natively using `ResponsesHostServer` from `agent-framework-foundry-hosting` (Responses protocol v2.0.0, Python 3.13 runtime, remote build from `uv.lock`). Candidate moments are received as JSON and processed through the workflow graph without forking app logic.

### Portal Evidence (T2 Spike)
The T2 spike (`spikes/hosted/`) was deployed to Microsoft Foundry using `azd deploy` and verified live:
- Deployed service `t2-spike` in Foundry project `matchday` (`https://matchday-foundry-ok.services.ai.azure.com/api/projects/matchday`).
- Invoked remotely over the Responses protocol with candidate evidence dicts and `inject-false` test triggers.
- Verified reject edge loop in the Foundry portal Tracing tab, with spans for `workflow.run`, `executor.process`, `invoke_agent`, and `chat` models.
- Cold start was ~9 s to response headers and ~29 s end-to-end for a 4-call workflow.

### Deployment Blocker & Status (T10)
Packaging for the full commentary workflow in `hosted/` is complete and verified by automated tests (`tests/test_hosted.py`). Live remote deployment via `azd deploy` was timeboxed out due to an Azure CLI authentication broker token expiration in non-interactive sessions:
- `az account get-access-token --resource https://management.azure.com` returned:
  ```
  ERROR: The server or proxy was not found.. Status: Response_Status.Status_NoNetwork, Error code: 3399942148, Tag: 557973641
  Run the command below to authenticate interactively:
  az logout
  az login --tenant "09c5e5e8-d9dd-4923-bbf2-9749f2e8082c" --scope "https://management.azure.com/.default"
  ```
- Because non-interactive agent sessions cannot open an interactive browser for tenant MFA authentication, `azd deploy` cannot refresh management tokens automatically.
- Per the T10 prompt instructions, this timeboxed blocker is documented here, with the T2 spike serving as the portal evidence for hosted agent capability.

To deploy `hosted/` when interactively logged into Azure:
```powershell
az login --tenant "09c5e5e8-d9dd-4923-bbf2-9749f2e8082c"
cd hosted
azd deploy
```


