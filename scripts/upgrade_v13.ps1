$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.13 - Resilience/Performance Upgrade ===" -ForegroundColor Cyan
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

Ensure-EnvValue "RESILIENCE_ENABLED" "true"
Ensure-EnvValue "RESILIENCE_FAIL_OPEN" "true"
Ensure-EnvValue "RESILIENCE_RATE_LIMIT_ENABLED" "true"
Ensure-EnvValue "RESILIENCE_RATE_LIMIT_REQUESTS" "600"
Ensure-EnvValue "RESILIENCE_RATE_LIMIT_WINDOW_SECONDS" "60"
Ensure-EnvValue "RESILIENCE_RATE_LIMIT_EXEMPT_PATHS" "/metrics,/api/v1/health/live,/api/v1/health/ready,/docs,/openapi.json"
Ensure-EnvValue "RESILIENCE_BULKHEAD_ENABLED" "true"
Ensure-EnvValue "RESILIENCE_BULKHEAD_LLM_CONCURRENCY" "16"
Ensure-EnvValue "RESILIENCE_BULKHEAD_ACQUIRE_TIMEOUT_SECONDS" "0.25"
Ensure-EnvValue "RESILIENCE_CIRCUIT_BREAKER_ENABLED" "true"
Ensure-EnvValue "RESILIENCE_CIRCUIT_FAILURE_THRESHOLD" "5"
Ensure-EnvValue "RESILIENCE_CIRCUIT_FAILURE_WINDOW_SECONDS" "60"
Ensure-EnvValue "RESILIENCE_CIRCUIT_COOLDOWN_SECONDS" "30"
Ensure-EnvValue "RESILIENCE_CIRCUIT_PROBE_LOCK_SECONDS" "10"
Ensure-EnvValue "RESILIENCE_RETRY_MAX_ATTEMPTS" "1"
Ensure-EnvValue "RESILIENCE_RETRY_BASE_DELAY_SECONDS" "0.25"
Ensure-EnvValue "RESILIENCE_RETRY_MAX_DELAY_SECONDS" "2"
Ensure-EnvValue "RESILIENCE_RETRY_JITTER_SECONDS" "0.10"
Ensure-EnvValue "LOAD_TEST_CONCURRENCY" "20"
Ensure-EnvValue "LOAD_TEST_REQUESTS" "200"
Ensure-EnvValue "LOAD_TEST_P95_THRESHOLD_MS" "750"
Ensure-EnvValue "LOAD_TEST_ERROR_RATE_THRESHOLD_PCT" "1"

Write-Host "`n[1/5] Rebuilding API with resilience layer..." -ForegroundColor Yellow
docker compose build api
if ($LASTEXITCODE -ne 0) { throw "docker compose build api failed" }

Write-Host "`n[2/5] Starting v0.13 API (no new database migration)..." -ForegroundColor Yellow
docker compose up -d --force-recreate api
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

Write-Host "`n[3/5] Waiting for readiness..." -ForegroundColor Yellow
$healthy = $false
for ($i=0; $i -lt 50; $i++) {
    Start-Sleep -Seconds 1
    try {
        $h = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/ready" -TimeoutSec 3
        if (($h.status -eq "ok") -and ($h.version -eq "0.13.0")) { $healthy = $true; break }
    } catch {}
}
if (-not $healthy) { docker compose logs --tail=200 api; throw "API v0.13 did not become ready" }

Write-Host "`n[4/5] Full regression suite..." -ForegroundColor Yellow
docker compose exec -T api pytest -q tests
if ($LASTEXITCODE -ne 0) { throw "Full regression suite failed" }

Write-Host "`n[5/5] Resilience config + Prometheus contract..." -ForegroundColor Yellow
$metrics = (Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8000/metrics" -TimeoutSec 10).Content
$required = @(
    "rate_limit_decisions_total",
    "resilience_fail_open_total",
    "bulkhead_rejections_total",
    "bulkhead_in_flight",
    "circuit_breaker_events_total",
    "circuit_breaker_open",
    "resilience_retries_total"
)
foreach ($name in $required) {
    if ($metrics -notmatch [regex]::Escape($name)) { throw "Resilience metric not found: $name" }
}

docker compose ps
Write-Host "`n=== v0.13 UPGRADE APPLIED ===" -ForegroundColor Green
Write-Host "Next: PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v13.ps1"
