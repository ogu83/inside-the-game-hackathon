<#
.SYNOPSIS
    Idempotent deployment script for Matchday Companion on Azure Container Apps.
.DESCRIPTION
    Creates or updates the Container Apps environment (cae-matchday) and the
    Container App (ca-matchday) with system-assigned managed identity and
    Foundry role assignments in eastus2.
.PARAMETER ResourceGroup
    Resource group name (default: rg-matchday).
.PARAMETER Location
    Azure region (default: eastus2).
.PARAMETER EnvironmentName
    Container Apps environment name (default: cae-matchday).
.PARAMETER AppName
    Container App name (default: ca-matchday).
.PARAMETER Image
    Container image to deploy (default: ghcr.io/ogu83/matchday-companion:latest).
.PARAMETER AgentMode
    Agent execution mode: 'foundry' or 'template' (default: foundry).
.PARAMETER VoiceMode
    Voice execution mode: 'live' or 'off' (default: off).
.PARAMETER Teardown
    If specified, deletes the Container App and Container Apps environment.
#>

[CmdletBinding()]
param(
    [string]$ResourceGroup = "rg-matchday",
    [string]$Location = "eastus2",
    [string]$EnvironmentName = "cae-matchday",
    [string]$AppName = "ca-matchday",
    [string]$Image = "ghcr.io/ogu83/matchday-companion:latest",
    [ValidateSet("foundry", "template")]
    [string]$AgentMode = "foundry",
    [ValidateSet("live", "off")]
    [string]$VoiceMode = "live",
    [string]$FoundryEndpoint = "https://matchday-foundry-ok.services.ai.azure.com/api/projects/matchday",
    [string]$CognitiveAccountName = "matchday-foundry-ok",
    [string]$FrontierModel = "gpt-5.4-mini",
    [string]$SmallModel = "gpt-5.4-mini",
    [string]$LogAnalyticsName = "law-matchday",
    [string]$AppInsightsName = "appi-matchday",
    [string]$RegistryServer = "ghcr.io",
    [string]$RegistryUsername = "",
    [string]$RegistryPassword = "",
    [switch]$Teardown
)

$ErrorActionPreference = "Stop"

if ($Teardown) {
    Write-Host "Teardown requested for $AppName in $ResourceGroup..." -ForegroundColor Yellow
    $appExists = az containerapp show -g $ResourceGroup -n $AppName --query name -o tsv 2>$null
    if ($appExists) {
        Write-Host "Deleting Container App: $AppName" -ForegroundColor Yellow
        az containerapp delete -g $ResourceGroup -n $AppName --yes
    }
    $envExists = az containerapp env show -g $ResourceGroup -n $EnvironmentName --query name -o tsv 2>$null
    if ($envExists) {
        Write-Host "Deleting Container Apps Environment: $EnvironmentName" -ForegroundColor Yellow
        az containerapp env delete -g $ResourceGroup -n $EnvironmentName --yes
    }
    Write-Host "Teardown complete." -ForegroundColor Green
    return
}

Write-Host "=== Deploying Matchday Companion to Azure Container Apps ===" -ForegroundColor Cyan
Write-Host "Resource Group: $ResourceGroup ($Location)"
Write-Host "Container App:  $AppName"
Write-Host "Image:          $Image"
Write-Host "Agent Mode:     $AgentMode"
Write-Host "Voice Mode:     $VoiceMode"

# 1. Ensure Resource Group exists
$rgExists = az group exists -n $ResourceGroup
if ($rgExists -ne "true") {
    Write-Host "Creating Resource Group: $ResourceGroup in $Location..."
    az group create -n $ResourceGroup -l $Location | Out-Null
} else {
    Write-Host "Resource Group $ResourceGroup exists." -ForegroundColor Gray
}

# 2. Ensure Log Analytics Workspace exists
$lawId = az monitor log-analytics workspace show -g $ResourceGroup -n $LogAnalyticsName --query id -o tsv 2>$null
if (-not $lawId) {
    Write-Host "Creating Log Analytics Workspace: $LogAnalyticsName..."
    az monitor log-analytics workspace create -g $ResourceGroup -n $LogAnalyticsName -l $Location --retention-time 30 | Out-Null
    $lawId = az monitor log-analytics workspace show -g $ResourceGroup -n $LogAnalyticsName --query id -o tsv
}
$lawKey = az monitor log-analytics workspace get-shared-keys -g $ResourceGroup -n $LogAnalyticsName --query primarySharedKey -o tsv

# 3. Ensure Application Insights connection string
$appInsightsConn = az monitor app-insights component show -g $ResourceGroup -a $AppInsightsName --query connectionString -o tsv 2>$null
if (-not $appInsightsConn) {
    Write-Host "Creating Application Insights: $AppInsightsName..."
    az monitor app-insights component create -g $ResourceGroup -a $AppInsightsName -l $Location --workspace $lawId | Out-Null
    $appInsightsConn = az monitor app-insights component show -g $ResourceGroup -a $AppInsightsName --query connectionString -o tsv
}

# 4. Ensure Container Apps Environment exists
$envId = az containerapp env show -g $ResourceGroup -n $EnvironmentName --query id -o tsv 2>$null
if (-not $envId) {
    Write-Host "Creating Container Apps Environment: $EnvironmentName..."
    az containerapp env create `
        -g $ResourceGroup `
        -n $EnvironmentName `
        -l $Location `
        --logs-workspace-id (az monitor log-analytics workspace show -g $ResourceGroup -n $LogAnalyticsName --query customerId -o tsv) `
        --logs-workspace-key $lawKey | Out-Null
    $envId = az containerapp env show -g $ResourceGroup -n $EnvironmentName --query id -o tsv
} else {
    Write-Host "Container Apps Environment $EnvironmentName exists." -ForegroundColor Gray
}

# 5. Deploy or Update Container App
$appProvState = az containerapp show -g $ResourceGroup -n $AppName --query properties.provisioningState -o tsv 2>$null
if ($appProvState -eq "Failed") {
    Write-Host "Existing Container App is in Failed state. Cleaning up before recreation..." -ForegroundColor Yellow
    az containerapp delete -g $ResourceGroup -n $AppName --yes | Out-Null
    $appExists = $null
} else {
    $appExists = az containerapp show -g $ResourceGroup -n $AppName --query name -o tsv 2>$null
}

$envVars = @(
    "AGENT_MODE=$AgentMode",
    "VOICE_MODE=$VoiceMode",
    "FOUNDRY_PROJECT_ENDPOINT=$FoundryEndpoint",
    "FRONTIER_MODEL_DEPLOYMENT=$FrontierModel",
    "SMALL_MODEL_DEPLOYMENT=$SmallModel",
    "APPLICATIONINSIGHTS_CONNECTION_STRING=$appInsightsConn",
    "BROADCAST_DELAY_S=20",
    "PUBLIC_LIVE_RUNS_PER_DAY=2",
    "PUBLIC_LIVE_RUNS_TOTAL_PER_DAY=40",
    "MAX_CONCURRENT_RUNS=4",
    "RUN_IDLE_TTL_S=600",
    "PORT=8010"
)

if (-not $appExists) {
    Write-Host "Creating Container App: $AppName..."
    $createArgs = @(
        "containerapp", "create",
        "-g", $ResourceGroup,
        "-n", $AppName,
        "--environment", $EnvironmentName,
        "--image", $Image,
        "--target-port", "8010",
        "--ingress", "external",
        "--transport", "auto",
        "--min-replicas", "1",
        "--max-replicas", "1",
        "--cpu", "0.5",
        "--memory", "1.0Gi",
        "--system-assigned",
        "--env-vars"
    ) + $envVars

    if ($RegistryUsername -and $RegistryPassword) {
        $createArgs += @(
            "--registry-server", $RegistryServer,
            "--registry-username", $RegistryUsername,
            "--registry-password", $RegistryPassword
        )
    }

    & az @createArgs | Out-Null
} else {
    Write-Host "Updating Container App: $AppName with image $Image..."
    $updateArgs = @(
        "containerapp", "update",
        "-g", $ResourceGroup,
        "-n", $AppName,
        "--image", $Image,
        "--set-env-vars"
    ) + $envVars

    if ($RegistryUsername -and $RegistryPassword) {
        $updateArgs += @(
            "--registry-server", $RegistryServer,
            "--registry-username", $RegistryUsername,
            "--registry-password", $RegistryPassword
        )
    }

    & az @updateArgs | Out-Null
}

# 6. Ensure System-Assigned Identity & Role Assignments
Write-Host "Configuring Managed Identity role assignments..." -ForegroundColor Cyan
az containerapp identity assign -g $ResourceGroup -n $AppName --system-assigned | Out-Null
$principalId = az containerapp identity show -g $ResourceGroup -n $AppName --query principalId -o tsv

if ($principalId) {
    Write-Host "Container App Principal ID: $principalId"
    $cogAccountId = az cognitiveservices account show -g $ResourceGroup -n $CognitiveAccountName --query id -o tsv
    if (-not $cogAccountId) {
        throw "Cognitive account $CognitiveAccountName not found in resource group $ResourceGroup."
    }

    Write-Host "Assigning 'Foundry User' role to managed identity..."
    az role assignment create `
        --assignee-object-id $principalId `
        --role "Foundry User" `
        --scope $cogAccountId `
        --assignee-principal-type ServicePrincipal
    if ($LASTEXITCODE -ne 0) {
        throw "Role assignment 'Foundry User' failed for principal $principalId."
    }
}

# 7. Verification & Output
$fqdn = az containerapp show -g $ResourceGroup -n $AppName --query properties.configuration.ingress.fqdn -o tsv
if (-not $fqdn) {
    throw "Container App $AppName has no ingress FQDN."
}

Write-Host "Waiting for container app health check at https://$fqdn/api/health (timeout 5 min)..." -ForegroundColor Cyan
$healthUrl = "https://$fqdn/api/health"
$timeout = (Get-Date).AddMinutes(5)
$healthy = $false

while ((Get-Date) -lt $timeout) {
    try {
        $resp = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 10 -ErrorAction Stop
        if ($resp.status -eq "ok") {
            $healthy = $true
            Write-Host "Health check passed: $($resp | ConvertTo-Json -Compress)" -ForegroundColor Green
            break
        }
    } catch {
        Write-Host "Waiting for service to become healthy ($($_.Exception.Message))..." -ForegroundColor Gray
    }
    Start-Sleep -Seconds 10
}

if (-not $healthy) {
    Write-Host "Health check failed after 5 minutes. Fetching recent container logs:" -ForegroundColor Red
    az containerapp logs show -n $AppName -g $ResourceGroup --tail 50
    throw "Deployment verification failed: $healthUrl did not return 200 OK within 5 minutes."
}

Write-Host ""
Write-Host "=== Deployment Successful ===" -ForegroundColor Green
Write-Host "App URL:    https://$fqdn" -ForegroundColor Yellow
Write-Host "Health:     https://$fqdn/api/health" -ForegroundColor Yellow
