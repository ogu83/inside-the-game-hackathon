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
- Enables system-assigned managed identity on the container app and assigns:
  - `Cognitive Services OpenAI User`
  - `Azure AI Developer`
  on the `matchday-foundry-ok` cognitive services account.

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
- **Assigned Roles on `matchday-foundry-ok`**:
  - `Cognitive Services OpenAI User`
  - `Azure AI Developer`
- **Authentication**: Zero credentials stored in container configuration. `DefaultAzureCredential` obtains Entra tokens automatically in container runtime.

### Image and CI/CD
- **Container Registry**: GitHub Container Registry (`ghcr.io/ogu83/matchday-companion:latest`)
- **Automated Workflow**: `.github/workflows/image.yml` builds and pushes multi-stage container images on merge to `main`.
- **Deployment Execution**: Run `pwsh infra/deploy.ps1` to provision or roll forward the live Container App.

