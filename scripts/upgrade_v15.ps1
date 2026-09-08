$ErrorActionPreference = "Stop"

function Assert-RepositoryHygiene {
    $tracked = @(git ls-files)
    if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel executar git ls-files no host" }
    $forbidden = @($tracked | Where-Object {
        $_ -match '^(build/|dist/)' -or
        $_ -match '\.egg-info/' -or
        $_ -match '\.whl$'
    })
    if ($forbidden.Count -gt 0) {
        Write-Host "Artefatos de build rastreados pelo Git:" -ForegroundColor Red
        $forbidden | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
        throw "Repository hygiene falhou: artefatos de build rastreados"
    }
}

Write-Host "=== AI Sales Agent Platform v0.15.0 - Multi-Cloud Deployment Readiness ===" -ForegroundColor Cyan

Write-Host "`n[1/7] Repository hygiene + build development..." -ForegroundColor Yellow
Assert-RepositoryHygiene
docker compose build api
if ($LASTEXITCODE -ne 0) { throw "Falha no build development da API" }

Write-Host "`n[2/7] Subindo stack local com migrations/bootstrap habilitados pelo Compose..." -ForegroundColor Yellow
docker compose up -d postgres redis api
if ($LASTEXITCODE -ne 0) { throw "Falha ao iniciar stack v0.15.0" }

Write-Host "`n[3/7] Aguardando readiness v0.15.0..." -ForegroundColor Yellow
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $h = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/ready" -TimeoutSec 3
        if (($h.status -eq "ok") -and ($h.version -eq "0.15.0")) { $healthy = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $healthy) {
    docker compose logs --tail=200 api
    throw "API v0.15.0 did not become ready"
}

Write-Host "`n[4/7] Validando lifecycle local + versao runtime..." -ForegroundColor Yellow
$runtimeVersion = docker compose exec -T api python -c "from app.core.config import settings; print(settings.app_version)"
if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel ler app_version no container" }
if ($runtimeVersion.Trim() -ne "0.15.0") { throw "Versao runtime inesperada: $runtimeVersion" }
docker compose exec -T api sh -lc 'test "$RUN_MIGRATIONS" = "true" && test "$RUN_BOOTSTRAP" = "true"'
if ($LASTEXITCODE -ne 0) { throw "Compose local deve habilitar RUN_MIGRATIONS e RUN_BOOTSTRAP" }

Write-Host "`n[5/7] Full regression suite - alvo 52 testes..." -ForegroundColor Yellow
docker compose exec -T api pytest -q tests
if ($LASTEXITCODE -ne 0) { throw "Regressao v0.15.0 falhou" }

Write-Host "`n[6/7] Ruff + contrato CI/CD multi-cloud..." -ForegroundColor Yellow
docker compose exec -T api ruff check app tests scripts
if ($LASTEXITCODE -ne 0) { throw "Ruff quality gate falhou" }
docker compose exec -T api pytest -q tests/test_cicd_supply_chain_contract.py
if ($LASTEXITCODE -ne 0) { throw "Contrato CI/CD v0.15.0 falhou" }

Write-Host "`n[7/7] Build production amd64 + verificacao non-root..." -ForegroundColor Yellow
docker build --target production -t ai-sales-agent-platform:v0.15.0 .
if ($LASTEXITCODE -ne 0) { throw "Build production v0.15.0 falhou" }
$prodUser = docker image inspect ai-sales-agent-platform:v0.15.0 --format '{{.Config.User}}'
if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel inspecionar imagem production" }
if ($prodUser.Trim() -ne "app") { throw "Imagem production deveria usar USER app; encontrado: $prodUser" }

Write-Host "`n=== v0.15.0 UPGRADE LOCAL VALIDADO ===" -ForegroundColor Green
Write-Host "Runtime    : 0.15.0" -ForegroundColor Green
Write-Host "Regression : 52 testes esperados" -ForegroundColor Green
Write-Host "Production : ai-sales-agent-platform:v0.15.0 (USER app)" -ForegroundColor Green
Write-Host "Next       : PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v15.ps1" -ForegroundColor Cyan
