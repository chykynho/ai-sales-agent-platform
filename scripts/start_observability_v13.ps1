$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.13 - Start Observability/Resilience Stack ===" -ForegroundColor Cyan
Set-Location (Split-Path $PSScriptRoot -Parent)

$compose = @("-f", "docker-compose.yml", "-f", "docker-compose.observability.yml")

docker compose @compose up -d --force-recreate api prometheus tempo grafana
if ($LASTEXITCODE -ne 0) { throw "Falha ao iniciar stack de observabilidade" }

Write-Host "`nAguardando API/Prometheus/Tempo/Grafana..." -ForegroundColor Yellow
$apiOk=$false; $promOk=$false; $tempoOk=$false; $grafanaOk=$false
for($i=0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r=Invoke-RestMethod "http://localhost:8000/api/v1/health/ready" -TimeoutSec 2
        if(($r.status -eq "ok") -and ($r.version -eq "0.13.0")){$apiOk=$true}
    } catch {}
    try { $r=Invoke-WebRequest -UseBasicParsing "http://localhost:9090/-/ready" -TimeoutSec 2; if($r.StatusCode -eq 200){$promOk=$true} } catch {}
    try { $r=Invoke-WebRequest -UseBasicParsing "http://localhost:3200/ready" -TimeoutSec 2; if($r.StatusCode -eq 200){$tempoOk=$true} } catch {}
    try { if((Invoke-RestMethod "http://localhost:3000/api/health" -TimeoutSec 2).database -eq "ok"){$grafanaOk=$true} } catch {}
    if($apiOk -and $promOk -and $tempoOk -and $grafanaOk){ break }
}
if(-not ($apiOk -and $promOk -and $tempoOk -and $grafanaOk)) {
    docker compose @compose ps
    throw "Stack nao ficou pronta: api=$apiOk prometheus=$promOk tempo=$tempoOk grafana=$grafanaOk"
}

docker compose @compose ps
Write-Host "`n=== OBSERVABILITY/RESILIENCE STACK READY ===" -ForegroundColor Green
Write-Host "API        : http://localhost:8000"
Write-Host "Metrics    : http://localhost:8000/metrics"
Write-Host "Prometheus : http://localhost:9090"
Write-Host "Grafana    : http://localhost:3000  (admin/admin - somente laboratorio local)"
Write-Host "Tempo      : http://localhost:3200"
Write-Host "`nNext: PowerShell -ExecutionPolicy Bypass -File .\scripts\test_observability_stack_v13.ps1"
