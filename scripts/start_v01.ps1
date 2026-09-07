$ErrorActionPreference = "Stop"

Write-Host "=== AI Sales Agent Platform v0.1 - Start ===" -ForegroundColor Cyan

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker não encontrado no PATH. Instale/inicie o Docker Desktop antes de continuar."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop não está respondendo. Abra o Docker Desktop e tente novamente."
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    $secretBytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($secretBytes)
    $secret = [Convert]::ToBase64String($secretBytes)
    (Get-Content ".env") -replace '^SECRET_KEY=.*$', "SECRET_KEY=$secret" | Set-Content ".env"
    Write-Host ".env criado e SECRET_KEY aleatória gerada." -ForegroundColor Green
} else {
    Write-Host ".env já existe; nenhuma configuração foi sobrescrita." -ForegroundColor Yellow
}

Write-Host "`nSubindo containers..." -ForegroundColor Yellow
docker compose up --build -d

Write-Host "`nEstado dos containers:" -ForegroundColor Yellow
docker compose ps

Write-Host "`nAcompanhando os últimos logs da API:" -ForegroundColor Yellow
docker compose logs --tail 80 api

Write-Host "`nQuando a API estiver pronta:" -ForegroundColor Green
Write-Host "Swagger: http://localhost:8000/docs"
Write-Host "Health : http://localhost:8000/api/v1/health"
Write-Host "`nDepois execute:"
Write-Host "PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v01.ps1" -ForegroundColor Cyan
