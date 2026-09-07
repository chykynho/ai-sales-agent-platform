$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

Write-Host "=== AI Sales Agent Platform v0.4 - LangGraph Upgrade ===" -ForegroundColor Cyan

docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Engine is not available." }

Write-Host "`n[1/5] Building API with LangGraph dependencies..." -ForegroundColor Yellow
docker compose build api
if ($LASTEXITCODE -ne 0) { throw "docker compose build failed." }

Write-Host "`n[2/5] Creating/upgrading LangGraph checkpoint tables..." -ForegroundColor Yellow
docker compose run --rm api python -m scripts.setup_langgraph
if ($LASTEXITCODE -ne 0) { throw "LangGraph checkpoint setup failed." }

Write-Host "`n[3/5] Starting v0.4 API..." -ForegroundColor Yellow
docker compose up -d api
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed." }

Write-Host "`n[4/5] Waiting for API + LangGraph runtime..." -ForegroundColor Yellow
$ok = $false
for ($i=0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $health = Invoke-RestMethod "http://localhost:8000/api/v1/health" -TimeoutSec 2
        if ($health.postgres -and $health.redis) { $ok = $true; break }
    } catch {}
}
if (-not $ok) {
    docker compose logs --tail=160 api
    throw "API did not become healthy after v0.4 upgrade."
}

Write-Host "`n[5/5] Status and logs..." -ForegroundColor Yellow
docker compose ps
docker compose logs --tail=100 api

Write-Host "`n=== v0.4 UPGRADE APPLIED ===" -ForegroundColor Green
Write-Host "Next: PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v04.ps1"
