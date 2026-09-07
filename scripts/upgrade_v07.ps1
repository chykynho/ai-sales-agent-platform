$ErrorActionPreference="Stop"
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
$Base="http://localhost:8000/api/v1"
Write-Host "=== AI Sales Agent Platform v0.7 - Configurable Multi-Tenant SaaS Upgrade ===" -ForegroundColor Cyan
Write-Host "`n[1/4] Rebuilding API with tenant configuration/catalog..." -ForegroundColor Yellow
docker compose build api
if($LASTEXITCODE -ne 0){throw "api build failed"}
Write-Host "`n[2/4] Starting API and applying 0005_tenant_saas_config..." -ForegroundColor Yellow
docker compose up -d api
if($LASTEXITCODE -ne 0){throw "api start failed"}
Write-Host "`n[3/4] Waiting for health..." -ForegroundColor Yellow
$ok=$false; for($i=0;$i -lt 30;$i++){try{$h=Invoke-RestMethod "$Base/health"; if($h.status -eq "ok"){$ok=$true;break}}catch{}; Start-Sleep -Seconds 1}
if(-not $ok){docker compose logs --tail=120 api; throw "API health timeout"}
Write-Host "`n[4/4] Status and logs..." -ForegroundColor Yellow
docker compose ps
docker compose logs --tail=80 api
Write-Host "`n=== v0.7 UPGRADE APPLIED ===" -ForegroundColor Green
Write-Host "Next: PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v07.ps1"
