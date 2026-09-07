$ErrorActionPreference = "Stop"
Write-Host "=== AI Sales Agent Platform v0.12 - Prometheus/Grafana/Tempo Test ===" -ForegroundColor Cyan
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "`n[1/5] Gerando trafego rastreavel..." -ForegroundColor Yellow
for($i=1; $i -le 4; $i++) {
    Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/live" -Headers @{"X-Request-ID"="v012-stack-$i"} | Out-Null
}
Start-Sleep -Seconds 7

Write-Host "`n[2/5] Prometheus target + metricas..." -ForegroundColor Yellow
$q=[uri]::EscapeDataString('up{job="ai-sales-agent-api"}')
$prom=Invoke-RestMethod -Uri ("http://localhost:9090/api/v1/query?query="+$q) -TimeoutSec 10
if($prom.status -ne "success" -or @($prom.data.result).Count -lt 1){ throw "Prometheus nao encontrou target da API" }
$value=[double]$prom.data.result[0].value[1]
if($value -ne 1){ throw "Prometheus target API nao esta UP" }
Write-Host "[OK] Prometheus scrape up=1" -ForegroundColor Green

Write-Host "`n[3/5] Grafana health..." -ForegroundColor Yellow
$g=Invoke-RestMethod -Uri "http://localhost:3000/api/health" -TimeoutSec 10
if($g.database -ne "ok"){ throw "Grafana database health != ok" }
Write-Host "[OK] Grafana operacional" -ForegroundColor Green

Write-Host "`n[4/5] Tempo readiness + traces da aplicacao..." -ForegroundColor Yellow
$t=Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:3200/ready" -TimeoutSec 10
if($t.StatusCode -ne 200){ throw "Tempo readiness falhou" }
$query=[uri]::EscapeDataString('{ resource.service.name = "ai-sales-agent-platform" }')
$traceFound=$false
$traceCount=0
for($i=0; $i -lt 12; $i++) {
    try {
        $search=Invoke-RestMethod -Uri ("http://localhost:3200/api/search?q="+$query) -TimeoutSec 10
        $traceCount=@($search.traces).Count
        if($traceCount -gt 0){ $traceFound=$true; break }
    } catch {}
    Start-Sleep -Seconds 2
}
if(-not $traceFound){ throw "Tempo nao encontrou traces do service.name ai-sales-agent-platform" }
Write-Host "[OK] Tempo encontrou $traceCount trace(s)" -ForegroundColor Green

Write-Host "`n[5/5] Estado final..." -ForegroundColor Yellow
docker compose -f docker-compose.yml -f docker-compose.observability.yml ps

Write-Host "`n=== v0.12 FULL OBSERVABILITY STACK VALIDATED ===" -ForegroundColor Green
Write-Host "Prometheus : http://localhost:9090"
Write-Host "Grafana    : http://localhost:3000"
Write-Host "Dashboard  : AI Sales Agent Platform - SRE / Golden Signals"
Write-Host "Tempo      : http://localhost:3200"
