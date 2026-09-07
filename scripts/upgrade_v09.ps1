$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.9 - Realtime Voice Upgrade ===" -ForegroundColor Cyan
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

Ensure-EnvValue "OPENAI_REALTIME_MODEL" "gpt-realtime-2.1"
Ensure-EnvValue "OPENAI_REALTIME_VOICE" "marin"
Ensure-EnvValue "OPENAI_REALTIME_TIMEOUT_SECONDS" "30"
Ensure-EnvValue "VOICE_AUDIO_MAX_BYTES" "5000000"
Ensure-EnvValue "VOICE_SESSION_MAX_MINUTES" "60"

Write-Host "`n[1/4] Rebuilding API with Realtime Voice dependencies..." -ForegroundColor Yellow
docker compose build api
if ($LASTEXITCODE -ne 0) { throw "docker compose build api failed" }

Write-Host "`n[2/4] Starting API and applying 0007_voice_realtime..." -ForegroundColor Yellow
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
if (-not $healthy) { docker compose logs --tail=140 api; throw "API did not become healthy" }

Write-Host "`n[4/4] Status, Voice config and logs..." -ForegroundColor Yellow
docker compose ps
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/channels/voice/config" | ConvertTo-Json -Depth 10
docker compose logs --tail=90 api

Write-Host "`n=== v0.9 UPGRADE APPLIED ===" -ForegroundColor Green
Write-Host "Next: PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v09.ps1"
