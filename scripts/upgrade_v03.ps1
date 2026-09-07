$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

Write-Host "=== AI Sales Agent Platform v0.3 - Upgrade ===" -ForegroundColor Cyan

docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Engine is not available." }

Write-Host "`n[1/4] Rebuilding API with v0.3 code..." -ForegroundColor Yellow
docker compose up -d --build api
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed." }

Write-Host "`n[2/4] Waiting for migrations and API startup..." -ForegroundColor Yellow
$ok = $false
for ($i=0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 1
    try {
        $health = Invoke-RestMethod "http://localhost:8000/api/v1/health" -TimeoutSec 2
        if ($health.postgres -and $health.redis) { $ok = $true; break }
    } catch {}
}
if (-not $ok) {
    docker compose logs --tail=120 api
    throw "API did not become healthy after v0.3 upgrade."
}

Write-Host "`n[3/4] Container status..." -ForegroundColor Yellow
docker compose ps

Write-Host "`n[4/4] API logs..." -ForegroundColor Yellow
docker compose logs --tail=80 api

Write-Host "`n=== v0.3 UPGRADE APPLIED ===" -ForegroundColor Green
Write-Host "Next: PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v03.ps1"
