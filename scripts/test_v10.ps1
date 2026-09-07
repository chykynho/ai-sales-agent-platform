$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.10 - Twilio Media Streams Bridge Test ===" -ForegroundColor Cyan
Set-Location (Split-Path $PSScriptRoot -Parent)

docker compose exec -T api python -m scripts.test_v10_bridge
if ($LASTEXITCODE -ne 0) { throw "v0.10 Twilio bridge smoke test failed" }

docker compose ps
Write-Host "`n=== v0.10 TEST COMPLETED ===" -ForegroundColor Green
