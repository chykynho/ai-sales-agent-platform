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
        throw "Repository hygiene falhou"
    }
}

Write-Host "=== AI Sales Agent Platform v0.15.0 - Full Multi-Cloud/DevSecOps Gate ===" -ForegroundColor Cyan
$artifactDir = Join-Path (Get-Location) "artifacts\v0.15.0"
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null

Write-Host "`n[1/9] Repository hygiene + Ruff..." -ForegroundColor Yellow
Assert-RepositoryHygiene
docker compose exec -T api ruff check app tests scripts
if ($LASTEXITCODE -ne 0) { throw "Ruff falhou" }

Write-Host "`n[2/9] Bandit medium/high..." -ForegroundColor Yellow
docker compose exec -T api bandit -q -r app -ll
if ($LASTEXITCODE -ne 0) { throw "Bandit falhou" }

Write-Host "`n[3/9] Pytest + coverage gate 25%..." -ForegroundColor Yellow
docker compose exec -T api pytest -q tests --cov=app --cov-report=term-missing --cov-report=xml:/tmp/coverage.xml --cov-fail-under=25
if ($LASTEXITCODE -ne 0) { throw "Coverage/test gate falhou" }
$apiId = (docker compose ps -q api).Trim()
if (-not $apiId) { throw "Container API nao encontrado" }
docker cp "${apiId}:/tmp/coverage.xml" "$artifactDir\coverage.xml" | Out-Null

Write-Host "`n[4/9] pip-audit..." -ForegroundColor Yellow
docker compose exec -T api pip-audit . --strict --progress-spinner off
if ($LASTEXITCODE -ne 0) { throw "pip-audit encontrou vulnerabilidade ou falha de coleta" }

Write-Host "`n[5/9] CycloneDX SBOM..." -ForegroundColor Yellow
docker compose exec -T api cyclonedx-py environment --spec-version 1.6 --output-format JSON --output-reproducible --output-file /tmp/sbom-python.cdx.json
if ($LASTEXITCODE -ne 0) { throw "Geracao SBOM falhou" }
docker cp "${apiId}:/tmp/sbom-python.cdx.json" "$artifactDir\sbom-python.cdx.json" | Out-Null

Write-Host "`n[6/9] Gitleaks - historico Git, com redaction..." -ForegroundColor Yellow
$repoMount = "$((Get-Location).Path):/repo"
docker run --rm -v "$repoMount" ghcr.io/gitleaks/gitleaks:v8.30.1 git --redact --no-banner /repo
if ($LASTEXITCODE -ne 0) { throw "Gitleaks encontrou possivel segredo versionado" }

Write-Host "`n[7/9] Trivy - imagem production amd64..." -ForegroundColor Yellow
docker build --target production -t ai-sales-agent-platform:v0.15.0 .
if ($LASTEXITCODE -ne 0) { throw "Build production falhou" }
$imageTar = Join-Path $artifactDir "ai-sales-agent-platform-v0.15.0-amd64.tar"
docker save ai-sales-agent-platform:v0.15.0 -o "$imageTar"
if ($LASTEXITCODE -ne 0) { throw "docker save falhou" }
$artMount = "$($artifactDir):/artifacts"
docker run --rm -v "$artMount" aquasec/trivy:0.73.0 image --input /artifacts/ai-sales-agent-platform-v0.15.0-amd64.tar --severity CRITICAL --ignore-unfixed --exit-code 1 --no-progress
if ($LASTEXITCODE -ne 0) { throw "Trivy encontrou vulnerabilidade CRITICAL corrigivel" }

Write-Host "`n[8/9] Build multi-arquitetura linux/amd64 + linux/arm64..." -ForegroundColor Yellow
docker buildx build --platform linux/amd64,linux/arm64 --target production --output=type=cacheonly .
if ($LASTEXITCODE -ne 0) { throw "Build multi-arquitetura falhou" }

Write-Host "`n[9/9] Contrato CI/CD + smoke de resiliencia..." -ForegroundColor Yellow
docker compose exec -T api pytest -q tests/test_cicd_supply_chain_contract.py
if ($LASTEXITCODE -ne 0) { throw "Contrato CI/CD v0.15 falhou" }
docker compose exec -T api python -m scripts.test_v13_resilience
if ($LASTEXITCODE -ne 0) { throw "Smoke de resiliencia falhou" }

Write-Host "`n=== v0.15.0 MULTI-CLOUD/DEVSECOPS VALIDADA COM SUCESSO ===" -ForegroundColor Green
Write-Host "Platforms: linux/amd64 + linux/arm64" -ForegroundColor Green
Write-Host "Artifacts: $artifactDir" -ForegroundColor Cyan
