$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.12 - Stop Observability Stack ===" -ForegroundColor Cyan
Set-Location (Split-Path $PSScriptRoot -Parent)

# Para somente os componentes de observabilidade. Nao remove volumes.
docker compose -f docker-compose.yml -f docker-compose.observability.yml stop grafana prometheus tempo
if ($LASTEXITCODE -ne 0) { throw "Falha ao parar stack de observabilidade" }

# Recria somente a API com o compose base, removendo o endpoint OTLP temporario.
docker compose up -d --force-recreate api
if ($LASTEXITCODE -ne 0) { throw "Falha ao restaurar API no compose base" }

Write-Host "`n=== OBSERVABILITY STACK STOPPED (VOLUMES PRESERVED) ===" -ForegroundColor Green
