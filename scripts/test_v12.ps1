$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.12 - Observability/SRE Test ===" -ForegroundColor Cyan
Set-Location (Split-Path $PSScriptRoot -Parent)

docker compose exec -T api python -m scripts.test_v12_observability
if ($LASTEXITCODE -ne 0) { throw "v0.12 observability smoke test failed" }

docker compose ps
Write-Host "`n=== v0.12 TEST COMPLETED ===" -ForegroundColor Green
Write-Host "Optional full stack: PowerShell -ExecutionPolicy Bypass -File .\scripts\start_observability_v12.ps1"
