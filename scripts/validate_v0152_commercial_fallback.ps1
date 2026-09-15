$ErrorActionPreference = "Stop"

Write-Host "=== v0.15.2 Commercial Price Fallback - Validation ===" -ForegroundColor Cyan

Write-Host "`n[1/3] Contract test" -ForegroundColor Yellow
python -m pytest tests/test_commercial_price_fallback_contract.py -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n[2/3] Full pytest" -ForegroundColor Yellow
python -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n[3/3] Ruff" -ForegroundColor Yellow
python -m ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n[OK] Validation passed." -ForegroundColor Green
