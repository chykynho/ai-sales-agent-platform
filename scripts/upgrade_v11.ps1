$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.11 - Production Telephony Hardening Upgrade ===" -ForegroundColor Cyan
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

Ensure-EnvValue "VOICE_PRODUCTION_ENABLED" "true"
Ensure-EnvValue "TWILIO_REQUIRE_SIGNATURE" "true"
Ensure-EnvValue "TWILIO_PUBLIC_BASE_URL" "https://voice.example.test"
Ensure-EnvValue "TWILIO_WSS_BASE_URL" "wss://voice.example.test"
Ensure-EnvValue "TWILIO_AUTH_TOKEN_SMOKE" "local-v011-twilio-auth-token"
Ensure-EnvValue "OPENAI_TRANSCRIBE_MODEL" "gpt-transcribe"
Ensure-EnvValue "VOICE_VAD_RMS_THRESHOLD" "450"
Ensure-EnvValue "VOICE_VAD_SILENCE_MS" "700"
Ensure-EnvValue "VOICE_VAD_MIN_SPEECH_MS" "240"
Ensure-EnvValue "VOICE_VAD_MAX_UTTERANCE_MS" "15000"
Ensure-EnvValue "VOICE_PRODUCTION_FIRST_TURN_ONLY" "true"

Write-Host "`n[1/4] Rebuilding API with Twilio SDK + production voice hardening..." -ForegroundColor Yellow
docker compose build api
if ($LASTEXITCODE -ne 0) { throw "docker compose build api failed" }

Write-Host "`n[2/4] Starting v0.11 API (no new database migration)..." -ForegroundColor Yellow
docker compose up -d --force-recreate api
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

Write-Host "`n[3/4] Waiting for health..." -ForegroundColor Yellow
$healthy = $false
for ($i=0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    try {
        $h = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -TimeoutSec 3
        if ($h.status -eq "ok") { $healthy = $true; break }
    } catch {}
}
if (-not $healthy) { docker compose logs --tail=200 api; throw "API did not become healthy" }

Write-Host "`n[4/4] Status, Voice config and full regression suite..." -ForegroundColor Yellow
docker compose ps
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/channels/voice/config" | ConvertTo-Json -Depth 12
docker compose exec -T api pytest -q tests
if ($LASTEXITCODE -ne 0) { throw "Full regression suite failed" }
docker compose logs --tail=100 api

Write-Host "`n=== v0.11 UPGRADE APPLIED ===" -ForegroundColor Green
Write-Host "Next: PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v11.ps1"
