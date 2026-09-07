$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.13 - Resilience/Performance Test ===" -ForegroundColor Cyan
Set-Location (Split-Path $PSScriptRoot -Parent)

docker compose exec -T api python -m scripts.test_v13_resilience
if ($LASTEXITCODE -ne 0) { throw "v0.13 resilience smoke test failed" }

Write-Host "`n=== SAFE LOAD TEST ===" -ForegroundColor Yellow
docker compose exec -T api python -m scripts.load_test_v13 --requests 200 --concurrency 20 --path /users/me --enforce-thresholds
if ($LASTEXITCODE -ne 0) { throw "v0.13 load test failed" }

docker compose ps
Write-Host "`n=== v0.13 TEST COMPLETED ===" -ForegroundColor Green
