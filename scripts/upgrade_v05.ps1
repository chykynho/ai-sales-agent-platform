$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$BaseUrl = "http://localhost:8000/api/v1"

Write-Host "=== AI Sales Agent Platform v0.5 - Human-in-the-Loop Upgrade ===" -ForegroundColor Cyan

function Wait-Api {
    for ($i=0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 1
        try {
            $health = Invoke-RestMethod "$BaseUrl/health" -TimeoutSec 2
            if ($health.postgres -and $health.redis) { return }
        } catch {}
    }
    throw "API did not become healthy."
}

Write-Host "`n[1/4] Rebuilding API with v0.5 HITL code..." -ForegroundColor Yellow
docker compose build api
if ($LASTEXITCODE -ne 0) { throw "docker compose build api failed." }

Write-Host "`n[2/4] Starting v0.5 API..." -ForegroundColor Yellow
docker compose up -d api
if ($LASTEXITCODE -ne 0) { throw "docker compose up -d api failed." }

Write-Host "`n[3/4] Waiting for API and PostgreSQL checkpointer..." -ForegroundColor Yellow
Wait-Api

Write-Host "`n[4/4] Status, config and logs..." -ForegroundColor Yellow
docker compose ps
$login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -Headers @{"X-Tenant-Slug"="demo"} -ContentType "application/x-www-form-urlencoded" -Body "username=admin%40example.com&password=ChangeMe123%21"
$headers = @{Authorization="Bearer $($login.access_token)"}
$config = Invoke-RestMethod "$BaseUrl/agent/config" -Headers $headers
$config | ConvertTo-Json -Depth 10
if (-not $config.human_interrupts -or $config.graph -ne "sales_agent_v0.5") {
    throw "v0.5 HITL config is not active."
}
docker compose logs --tail=60 api

Write-Host "`n=== v0.5 UPGRADE APPLIED ===" -ForegroundColor Green
Write-Host "Next: PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v05.ps1"
