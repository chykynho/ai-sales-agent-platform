$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

Write-Host "=== AI Sales Agent Platform v0.6.1 - pgvector Binding Recovery ===" -ForegroundColor Cyan

Write-Host "`n[1/4] Rebuilding only the API with the pgvector binding fix..." -ForegroundColor Yellow
docker compose build api
if ($LASTEXITCODE -ne 0) { throw "API build failed." }

docker compose up -d api
if ($LASTEXITCODE -ne 0) { throw "API start failed." }

Write-Host "`n[2/4] Waiting for API..." -ForegroundColor Yellow
$health = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $health = Invoke-RestMethod "http://localhost:8000/api/v1/health" -TimeoutSec 3
        if ($health.status -eq "ok") { break }
    } catch { }
}
if (-not $health -or $health.status -ne "ok") {
    docker compose logs --tail=120 api
    throw "API did not become healthy."
}
$health | ConvertTo-Json -Depth 5

Write-Host "`n[3/4] Verifying pgvector extension and containers..." -ForegroundColor Yellow
docker compose exec -T postgres psql -U aiagent -d aiagent -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
docker compose ps

Write-Host "`n[4/4] Recent API logs..." -ForegroundColor Yellow
docker compose logs --tail=80 api

Write-Host "`n=== HOTFIX v0.6.1 APLICADO COM SUCESSO ===" -ForegroundColor Green
Write-Host "Next: PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v06.ps1"
