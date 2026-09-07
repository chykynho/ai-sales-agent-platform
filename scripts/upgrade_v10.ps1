$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.10 - Twilio Media Streams Bridge Upgrade ===" -ForegroundColor Cyan
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

Ensure-EnvValue "VOICE_BRIDGE_LAB_ENABLED" "true"
Ensure-EnvValue "VOICE_BRIDGE_LAB_TOKEN" "local-v10-bridge-token-change-me"
Ensure-EnvValue "VOICE_BARGE_IN_ENABLED" "true"
Ensure-EnvValue "VOICE_BRIDGE_PLAYBACK_SPEED" "4.0"

Write-Host "`n[1/4] Rebuilding API with Twilio Media Streams bridge..." -ForegroundColor Yellow
docker compose build api
if ($LASTEXITCODE -ne 0) { throw "docker compose build api failed" }

Write-Host "`n[2/4] Starting v0.10 API (no new database migration)..." -ForegroundColor Yellow
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
if (-not $healthy) { docker compose logs --tail=160 api; throw "API did not become healthy" }

Write-Host "`n[4/4] Status, bridge config and protocol tests..." -ForegroundColor Yellow
docker compose ps
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/channels/voice/config" | ConvertTo-Json -Depth 12
docker compose exec -T api pytest -q tests/test_voice_contract.py
if ($LASTEXITCODE -ne 0) { throw "Voice protocol contract tests failed" }
docker compose logs --tail=80 api

Write-Host "`n=== v0.10 UPGRADE APPLIED ===" -ForegroundColor Green
Write-Host "Next: PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v10.ps1"
