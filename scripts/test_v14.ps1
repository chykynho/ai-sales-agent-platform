$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.14.2 - Full Quality/Supply Chain Gate ===" -ForegroundColor Cyan

$artifactDir = Join-Path (Get-Location) "artifacts\v0.14.2"
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null

Write-Host "`n[1/7] Ruff..." -ForegroundColor Yellow
docker compose exec -T api ruff check app tests scripts
if ($LASTEXITCODE -ne 0) { throw "Ruff falhou" }

Write-Host "`n[2/7] Bandit medium/high..." -ForegroundColor Yellow
docker compose exec -T api bandit -q -r app -ll
if ($LASTEXITCODE -ne 0) { throw "Bandit falhou" }

Write-Host "`n[3/7] Pytest + coverage gate 25%..." -ForegroundColor Yellow
docker compose exec -T api pytest -q tests --cov=app --cov-report=term-missing --cov-report=xml:/tmp/coverage.xml --cov-fail-under=25
if ($LASTEXITCODE -ne 0) { throw "Coverage/test gate falhou" }
$apiId = (docker compose ps -q api).Trim()
if (-not $apiId) { throw "Container API nao encontrado" }
docker cp "${apiId}:/tmp/coverage.xml" "$artifactDir\coverage.xml" | Out-Null

Write-Host "`n[4/7] pip-audit..." -ForegroundColor Yellow
docker compose exec -T api pip-audit . --strict --progress-spinner off
if ($LASTEXITCODE -ne 0) { throw "pip-audit encontrou vulnerabilidade ou falha de coleta" }

Write-Host "`n[5/7] CycloneDX SBOM..." -ForegroundColor Yellow
docker compose exec -T api cyclonedx-py environment --spec-version 1.6 --output-format JSON --output-reproducible --output-file /tmp/sbom-python.cdx.json
if ($LASTEXITCODE -ne 0) { throw "Geracao SBOM falhou" }
docker cp "${apiId}:/tmp/sbom-python.cdx.json" "$artifactDir\sbom-python.cdx.json" | Out-Null

Write-Host "`n[6/7] Gitleaks - historico Git, com redaction..." -ForegroundColor Yellow
$repoMount = "$((Get-Location).Path):/repo"
docker run --rm -v "$repoMount" ghcr.io/gitleaks/gitleaks:v8.30.1 git --redact --no-banner /repo
if ($LASTEXITCODE -ne 0) { throw "Gitleaks encontrou possivel segredo versionado" }

Write-Host "`n[7/7] Trivy - imagem production; CRITICAL corrigivel bloqueia..." -ForegroundColor Yellow
docker build --target production -t ai-sales-agent-platform:v0.14.2 .
if ($LASTEXITCODE -ne 0) { throw "Build production falhou" }
$imageTar = Join-Path $artifactDir "ai-sales-agent-platform-v0.14.2.tar"
docker save ai-sales-agent-platform:v0.14.2 -o "$imageTar"
if ($LASTEXITCODE -ne 0) { throw "docker save falhou" }
$artMount = "$($artifactDir):/artifacts"
docker run --rm -v "$artMount" aquasec/trivy:0.73.0 image --input /artifacts/ai-sales-agent-platform-v0.14.2.tar --severity CRITICAL --ignore-unfixed --exit-code 1 --no-progress
if ($LASTEXITCODE -ne 0) { throw "Trivy encontrou vulnerabilidade CRITICAL corrigivel" }

Write-Host "`n=== v0.14.2 QUALITY/SUPPLY CHAIN VALIDADA COM SUCESSO ===" -ForegroundColor Green
Write-Host "Artifacts: $artifactDir" -ForegroundColor Cyan
Write-Host "- coverage.xml" -ForegroundColor Cyan
Write-Host "- sbom-python.cdx.json" -ForegroundColor Cyan
