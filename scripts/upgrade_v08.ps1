$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.8 - WhatsApp Channel Upgrade ===" -ForegroundColor Cyan

Set-Location (Split-Path $PSScriptRoot -Parent)

function Ensure-EnvValue([string]$Name, [string]$Value) {
    $path = Join-Path (Get-Location) ".env"
    if (-not (Test-Path $path)) { throw ".env not found at $path" }
    $lines = Get-Content $path
    if (-not ($lines | Select-String -Pattern ("^" + [regex]::Escape($Name) + "="))) {
        Add-Content -Path $path -Value ("$Name=$Value") -Encoding UTF8
        Write-Host "Added local development setting: $Name"
    }
}

Ensure-EnvValue "WHATSAPP_VERIFY_TOKEN" "local-v08-verify-token"
Ensure-EnvValue "WHATSAPP_APP_SECRET" "local-v08-app-secret-change-me"
Ensure-EnvValue "WHATSAPP_GRAPH_API_VERSION" "v26.0"
Ensure-EnvValue "WHATSAPP_WEBHOOK_MAX_BODY_BYTES" "1048576"
Ensure-EnvValue "WHATSAPP_HTTP_TIMEOUT_SECONDS" "20"

Write-Host "`n[1/4] Rebuilding API with WhatsApp channel code..." -ForegroundColor Yellow
docker compose build api
if ($LASTEXITCODE -ne 0) { throw "docker compose build api failed" }

Write-Host "`n[2/4] Starting API and applying 0006_whatsapp_channel..." -ForegroundColor Yellow
docker compose up -d --force-recreate api
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

Write-Host "`n[3/4] Waiting for health..." -ForegroundColor Yellow
$healthy = $false
for ($i=0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $h = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -TimeoutSec 3
        if ($h.status -eq "ok") { $healthy = $true; break }
    } catch {}
}
if (-not $healthy) {
    docker compose logs --tail=120 api
    throw "API did not become healthy"
}

Write-Host "`n[4/4] Status, channel config and logs..." -ForegroundColor Yellow
docker compose ps
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/channels/config" | ConvertTo-Json -Depth 8
docker compose logs --tail=80 api

Write-Host "`n=== v0.8 UPGRADE APPLIED ===" -ForegroundColor Green
Write-Host "Next: PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v08.ps1"
