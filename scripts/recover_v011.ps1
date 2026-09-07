$ErrorActionPreference = "Stop"

Write-Host "=== AI Sales Agent Platform v0.1.1 - Recovery ===" -ForegroundColor Cyan

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker não encontrado no PATH."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop não está respondendo."
}

Write-Host "`n[1/4] Reconstruindo e iniciando os containers..." -ForegroundColor Yellow
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { throw "Falha no docker compose up." }

Write-Host "`n[2/4] Verificando a API..." -ForegroundColor Yellow
$health = $null
for ($i = 1; $i -le 30; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -TimeoutSec 3
        if ($health.status -eq "ok") { break }
    } catch {
        # A API pode ainda estar aplicando migration/bootstrap.
    }

    $apiState = docker compose ps -a --format json api 2>$null
    if ($apiState -and ($apiState -match '"State":"exited"' -or $apiState -match '"State": "exited"')) {
        Write-Host "`nA API encerrou durante a inicialização. Logs:" -ForegroundColor Red
        docker compose logs --tail 120 api
        throw "API encerrada durante a inicialização."
    }
    Start-Sleep -Seconds 2
}

Write-Host "`n[3/4] Estado dos containers:" -ForegroundColor Yellow
docker compose ps

if (-not $health -or $health.status -ne "ok") {
    Write-Host "`nHealth check não ficou OK. Logs da API:" -ForegroundColor Red
    docker compose logs --tail 120 api
    throw "Health check da API falhou."
}

Write-Host "`nHealth check:" -ForegroundColor Green
$health | ConvertTo-Json

Write-Host "`n[4/4] Últimos logs da API:" -ForegroundColor Yellow
docker compose logs --tail 80 api

Write-Host "`n=== HOTFIX v0.1.1 APLICADO COM SUCESSO ===" -ForegroundColor Green
Write-Host "Agora execute:" -ForegroundColor Cyan
Write-Host "PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v01.ps1"
