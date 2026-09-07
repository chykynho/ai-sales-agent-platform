$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.12 - Observability/SRE Upgrade ===" -ForegroundColor Cyan
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

Ensure-EnvValue "OBSERVABILITY_ENABLED" "true"
Ensure-EnvValue "OBSERVABILITY_LOG_JSON" "true"
Ensure-EnvValue "OBSERVABILITY_METRICS_ENABLED" "true"
Ensure-EnvValue "OBSERVABILITY_TRACING_ENABLED" "true"
Ensure-EnvValue "OBSERVABILITY_SERVICE_NAME" "ai-sales-agent-platform"
Ensure-EnvValue "OBSERVABILITY_OTLP_ENDPOINT" ""
Ensure-EnvValue "OBSERVABILITY_OTLP_TIMEOUT_SECONDS" "5"
Ensure-EnvValue "OBSERVABILITY_TRACE_CONSOLE" "false"
Ensure-EnvValue "OBSERVABILITY_TENANT_LABELS" "true"

Write-Host "`n[1/5] Rebuilding API with Prometheus + OpenTelemetry..." -ForegroundColor Yellow
docker compose build api
if ($LASTEXITCODE -ne 0) { throw "docker compose build api failed" }

Write-Host "`n[2/5] Starting v0.12 API (no new database migration)..." -ForegroundColor Yellow
docker compose up -d --force-recreate api
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

Write-Host "`n[3/5] Waiting for readiness..." -ForegroundColor Yellow
$healthy = $false
for ($i=0; $i -lt 50; $i++) {
    Start-Sleep -Seconds 1
    try {
        $h = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/ready" -TimeoutSec 3
        if ($h.status -eq "ok") { $healthy = $true; break }
    } catch {}
}
if (-not $healthy) { docker compose logs --tail=200 api; throw "API did not become ready" }

Write-Host "`n[4/5] Full regression suite..." -ForegroundColor Yellow
docker compose exec -T api pytest -q tests
if ($LASTEXITCODE -ne 0) { throw "Full regression suite failed" }

Write-Host "`n[5/5] Metrics endpoint + structured log contract..." -ForegroundColor Yellow
$metrics = (Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8000/metrics" -TimeoutSec 10).Content
$required = @(
    "http_requests_total",
    "http_request_duration_seconds",
    "llm_requests_total",
    "llm_tokens_total",
    "tool_calls_total",
    "rag_search_total",
    "voice_sessions_total",
    "twilio_calls_total",
    "process_resident_memory_bytes"
)
foreach ($name in $required) {
    if ($metrics -notmatch [regex]::Escape($name)) { throw "Metric not found: $name" }
}

# Gera ao menos uma linha de log estruturado da aplicacao.
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/live" -Headers @{"X-Request-ID"="v012-upgrade-log-check"} | Out-Null
Start-Sleep -Milliseconds 300
$logs = docker compose logs --tail=80 api | Out-String
if ($logs -notmatch '"message":"http_request_completed"') {
    Write-Host $logs
    throw "Structured JSON request log was not found"
}

docker compose ps
Write-Host "`n=== v0.12 UPGRADE APPLIED ===" -ForegroundColor Green
Write-Host "Metrics : http://localhost:8000/metrics"
Write-Host "Next    : PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v12.ps1"
