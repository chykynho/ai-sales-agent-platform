$ErrorActionPreference = "Stop"

Write-Host "=== v0.15.2 Multi-tool Context Hotfix Validation ===" -ForegroundColor Cyan

Write-Host "[1/4] Focused regression test..." -ForegroundColor Yellow
docker compose exec api python -m pytest -q tests/test_multitool_context_contract.py

Write-Host "[2/4] Commercial fallback contracts..." -ForegroundColor Yellow
docker compose exec api python -m pytest -q tests/test_commercial_price_fallback_contract.py

Write-Host "[3/4] Full regression suite..." -ForegroundColor Yellow
docker compose exec api python -m pytest -q

Write-Host "[4/4] Ruff..." -ForegroundColor Yellow
docker compose exec api python -m ruff check .

Write-Host "=== VALIDACAO LOCAL CONCLUIDA ===" -ForegroundColor Green
