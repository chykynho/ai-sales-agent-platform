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

Write-Host "=== AI Sales Agent Platform v0.14.3 - repository hygiene/package build hotfix ===" -ForegroundColor Cyan

Write-Host "`n[1/6] Repository hygiene no host + rebuild development..." -ForegroundColor Yellow
Assert-RepositoryHygiene
docker compose build api
if ($LASTEXITCODE -ne 0) { throw "Falha no build development da API" }

Write-Host "`n[2/6] Starting v0.14.3 API (sem nova migration)..." -ForegroundColor Yellow
docker compose up -d api
if ($LASTEXITCODE -ne 0) { throw "Falha ao iniciar API v0.14" }

Write-Host "`n[3/6] Waiting for readiness v0.14.3..." -ForegroundColor Yellow
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $h = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/ready" -TimeoutSec 3
        if (($h.status -eq "ok") -and ($h.version -eq "0.14.3")) { $healthy = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $healthy) {
    docker compose logs --tail=200 api
    throw "API v0.14.3 did not become ready"
}

Write-Host "`n[4/6] Full regression suite - alvo 52 testes..." -ForegroundColor Yellow
docker compose exec -T api pytest -q tests
if ($LASTEXITCODE -ne 0) { throw "Regressao v0.14.3 falhou" }

Write-Host "`n[5/6] Package discovery + Ruff + supply-chain contract..." -ForegroundColor Yellow
docker compose exec -T api sh -lc 'rm -rf /tmp/v0143-src /tmp/v0142-wheel && mkdir -p /tmp/v0143-src /tmp/v0142-wheel && cp pyproject.toml README.md /tmp/v0143-src/ && for d in app alembic fixtures observability scripts tests; do if [ -e "$d" ]; then cp -a "$d" /tmp/v0143-src/; fi; done && cd /tmp/v0143-src && python -m pip wheel --no-deps --no-build-isolation . -w /tmp/v0142-wheel'
if ($LASTEXITCODE -ne 0) { throw "Setuptools package discovery/build wheel falhou" }
if (Test-Path .\build) { throw "Artefato build/ nao deve existir na raiz do repositorio" }
if (Get-ChildItem -Path . -Directory -Filter "*.egg-info" -ErrorAction SilentlyContinue) { throw "Artefato *.egg-info nao deve existir na raiz do repositorio" }
docker compose exec -T api ruff check app tests scripts
if ($LASTEXITCODE -ne 0) { throw "Ruff quality gate falhou" }
docker compose exec -T api python -m scripts.test_v14_supply_chain
if ($LASTEXITCODE -ne 0) { throw "Supply-chain contract v0.14.3 falhou" }

Write-Host "`n[6/6] Build da imagem production e verificacao non-root..." -ForegroundColor Yellow
docker build --target production -t ai-sales-agent-platform:v0.14.3 .
if ($LASTEXITCODE -ne 0) { throw "Build production v0.14.3 falhou" }
$prodUser = docker image inspect ai-sales-agent-platform:v0.14.3 --format '{{.Config.User}}'
if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel inspecionar imagem production" }
if ($prodUser.Trim() -ne "app") { throw "Imagem production deveria usar USER app; encontrado: $prodUser" }

Write-Host "`n=== v0.14.3 HOTFIX APPLIED ===" -ForegroundColor Green
Write-Host "Regression : 52 testes esperados" -ForegroundColor Green
Write-Host "Production : ai-sales-agent-platform:v0.14.3 (USER app)" -ForegroundColor Green
Write-Host "Next       : PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v14.ps1" -ForegroundColor Cyan
