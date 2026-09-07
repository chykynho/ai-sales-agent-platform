$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.2 - Upgrade ===" -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ".env criado a partir de .env.example" -ForegroundColor Green
}

# Preserve existing v0.1 environment and append only missing v0.2 keys.
$defaults = @{
    "LLM_PROVIDER" = "mock"
    "MOCK_MODEL" = "mock-v0.2"
    "OPENAI_API_KEY" = ""
    "OPENAI_MODEL" = "gpt-5.6-terra"
    "OPENAI_REASONING_EFFORT" = "low"
    "OPENAI_TIMEOUT_SECONDS" = "45"
    "OPENAI_MAX_RETRIES" = "2"
}

$content = Get-Content .env -Raw
foreach ($key in $defaults.Keys) {
    if ($content -notmatch "(?m)^$([regex]::Escape($key))=") {
        Add-Content .env "`n$key=$($defaults[$key])" -Encoding UTF8
        Write-Host "Adicionado ao .env: $key" -ForegroundColor DarkGray
    }
}

Write-Host "`n[1/4] Rebuild da API com SDK OpenAI..." -ForegroundColor Yellow
docker compose up -d --build

Write-Host "`n[2/4] Aguardando health..." -ForegroundColor Yellow
$ok = $false
for ($i=1; $i -le 30; $i++) {
    Start-Sleep -Seconds 2
    try {
        $health = Invoke-RestMethod "http://localhost:8000/api/v1/health"
        if ($health.postgres -and $health.redis) { $ok = $true; break }
    } catch {}
    Write-Host "Tentativa $i/30..." -ForegroundColor DarkGray
}
if (-not $ok) {
    docker compose logs --tail=120 api
    throw "API did not become healthy."
}

Write-Host "`n[3/4] Migration atual..." -ForegroundColor Yellow
docker compose exec -T api alembic current

Write-Host "`n[4/4] Logs recentes..." -ForegroundColor Yellow
docker compose logs --tail=60 api

Write-Host "`n=== UPGRADE v0.2 CONCLUÍDO ===" -ForegroundColor Green
Write-Host "Agora execute:"
Write-Host "PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v02.ps1" -ForegroundColor Cyan
