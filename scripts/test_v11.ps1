$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.11.1 - Production Telephony Hardening Test ===" -ForegroundColor Cyan
Set-Location (Split-Path $PSScriptRoot -Parent)

docker compose exec -T api python -m scripts.test_v11_production_voice
if ($LASTEXITCODE -ne 0) { throw "v0.11 production telephony smoke test failed" }

docker compose ps
Write-Host "`n=== v0.11 TEST COMPLETED ===" -ForegroundColor Green
