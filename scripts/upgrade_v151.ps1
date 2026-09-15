$ErrorActionPreference = "Stop"

function Assert-LastExitCode([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw $Message }
}

function Assert-RepositoryHygiene {
    $tracked = @(git ls-files)
    Assert-LastExitCode "Nao foi possivel executar git ls-files no host"
    $forbidden = @($tracked | Where-Object {
        $_ -match '^(build/|dist/)' -or
        $_ -match '\.egg-info/' -or
        $_ -match '\.whl$'
    })
    if ($forbidden.Count -gt 0) {
        Write-Host "Artefatos de build rastreados pelo Git:" -ForegroundColor Red
        $forbidden | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
        throw "Repository hygiene falhou"
    }
}

Write-Host "=== AI Sales Agent Platform v0.15.1 - Cloud Connectivity ===" -ForegroundColor Cyan

Write-Host "`n[1/8] Normalizando/validando EOL Linux..." -ForegroundColor Yellow
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\normalize_eol.ps1"
Assert-LastExitCode "Normalizacao EOL falhou"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\normalize_eol.ps1" -CheckOnly
Assert-LastExitCode "Contrato EOL falhou"

Write-Host "`n[2/8] Repository hygiene + build development..." -ForegroundColor Yellow
Assert-RepositoryHygiene
docker compose build api
Assert-LastExitCode "Falha no build development da API"

Write-Host "`n[3/8] Subindo stack local preservando PostgreSQL/Redis locais..." -ForegroundColor Yellow
docker compose up -d postgres redis api
Assert-LastExitCode "Falha ao iniciar stack local v0.15.1"

Write-Host "`n[4/8] Aguardando readiness v0.15.1..." -ForegroundColor Yellow
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $h = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/ready" -TimeoutSec 3
        if (($h.status -eq "ok") -and ($h.version -eq "0.15.1")) {
            $healthy = $true
            break
        }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $healthy) {
    docker compose logs --tail=200 api
    throw "API v0.15.1 did not become ready"
}

Write-Host "`n[5/8] Contratos EOL + Cloud Connectivity..." -ForegroundColor Yellow
docker compose exec -T api pytest -q tests/test_eol_contract.py tests/test_cloud_connectivity_contract.py
Assert-LastExitCode "Contratos v0.15.1 falharam"

Write-Host "`n[6/8] Regressao completa + Ruff..." -ForegroundColor Yellow
docker compose exec -T api pytest -q tests
Assert-LastExitCode "Regressao v0.15.1 falhou"
docker compose exec -T api ruff check app tests scripts
Assert-LastExitCode "Ruff falhou"

Write-Host "`n[7/8] Build production + non-root + Cloud Run PORT..." -ForegroundColor Yellow
docker build --target production -t ai-sales-agent-platform:v0.15.1 .
Assert-LastExitCode "Build production v0.15.1 falhou"
$prodUser = docker image inspect ai-sales-agent-platform:v0.15.1 --format '{{.Config.User}}'
Assert-LastExitCode "Nao foi possivel inspecionar USER da imagem"
if ($prodUser.Trim() -ne "app") { throw "Imagem production deveria usar USER app; encontrado: $prodUser" }
$prodCmd = docker image inspect ai-sales-agent-platform:v0.15.1 --format '{{json .Config.Cmd}}'
Assert-LastExitCode "Nao foi possivel inspecionar CMD da imagem"
if ($prodCmd -notmatch '\$\{PORT:-8000\}') { throw "Imagem production nao respeita Cloud Run PORT" }

Write-Host "`n[8/8] Validando defaults de producao..." -ForegroundColor Yellow
docker run --rm --entrypoint sh ai-sales-agent-platform:v0.15.1 -lc 'test "$RUN_MIGRATIONS" = "false" && test "$RUN_BOOTSTRAP" = "false"'
Assert-LastExitCode "Defaults de producao RUN_MIGRATIONS/RUN_BOOTSTRAP incorretos"

Write-Host "`n=== v0.15.1 CLOUD CONNECTIVITY VALIDADA ===" -ForegroundColor Green
Write-Host "Local      : PostgreSQL/Redis locais preservados" -ForegroundColor Green
Write-Host "Cloud DB   : DATABASE_URL -> SQLAlchemy/asyncpg" -ForegroundColor Green
Write-Host "LangGraph  : LANGGRAPH_DATABASE_URL -> psycopg" -ForegroundColor Green
Write-Host "Redis TLS  : REDIS_URL aceita rediss://" -ForegroundColor Green
Write-Host "Cloud Run  : PORT dinamico com fallback 8000" -ForegroundColor Green
Write-Host "Production : migrations/bootstrap desabilitados por padrao" -ForegroundColor Green
