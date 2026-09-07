$ErrorActionPreference = "Stop"
$Base = "http://localhost:8000/api/v1"

function Ok($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "[AVISO] $msg" -ForegroundColor Yellow }

function Invoke-NativeCaptured([string]$Command) {
    # Windows PowerShell 5.1 converte stderr de executaveis nativos em NativeCommandError
    # quando usamos 2>&1 com ErrorActionPreference=Stop. O cmd.exe faz a uniao dos
    # streams antes de devolver o texto ao PowerShell, preservando o exit code real.
    $output = cmd.exe /d /s /c "$Command 2>&1" | Out-String
    $exitCode = $LASTEXITCODE
    return [PSCustomObject]@{
        Output = [string]$output
        ExitCode = [int]$exitCode
    }
}

function Login([string]$slug, [string]$email, [string]$password) {
    $body = "username=$([uri]::EscapeDataString($email))&password=$([uri]::EscapeDataString($password))"
    $r = Invoke-RestMethod -Method Post -Uri "$Base/auth/login" -Headers @{"X-Tenant-Slug"=$slug} -ContentType "application/x-www-form-urlencoded" -Body $body
    if(-not $r.access_token) { throw "Falha no login do tenant $slug" }
    return [string]$r.access_token
}

function GetAuth([string]$url, [string]$token) {
    return Invoke-RestMethod -Method Get -Uri $url -Headers @{Authorization="Bearer $token"}
}

Write-Host "=== CHECKPOINT LOCAL AI SALES AGENT PLATFORM v0.10.1 ===" -ForegroundColor Cyan
Write-Host "Objetivo: regressao local + persistencia + isolamento, sem apagar volumes." -ForegroundColor DarkGray

Write-Host "`n[1/9] Containers e health..." -ForegroundColor Yellow
docker compose ps
if($LASTEXITCODE -ne 0){ throw "docker compose ps falhou" }
$health = Invoke-RestMethod "$Base/health"
if($health.status -ne "ok"){ throw "Health da API nao esta OK" }
Ok "API respondeu health=ok"

Write-Host "`n[2/9] Migration atual e pgvector..." -ForegroundColor Yellow
$alembicResult = Invoke-NativeCaptured 'docker compose exec -T api alembic current'
$alembic = $alembicResult.Output
Write-Host $alembic
if($alembicResult.ExitCode -ne 0){ throw "alembic current falhou (exit code $($alembicResult.ExitCode))" }
if($alembic -notmatch "0007_voice_realtime"){ throw "Migration esperada 0007_voice_realtime nao encontrada" }
Ok "Banco esta na migration 0007_voice_realtime"

$vectorResult = Invoke-NativeCaptured "docker compose exec -T postgres psql -U aiagent -d aiagent -tAc `"SELECT extversion FROM pg_extension WHERE extname='vector';`""
if($vectorResult.ExitCode -ne 0){
    Write-Host $vectorResult.Output
    throw "Consulta da extensao pgvector falhou (exit code $($vectorResult.ExitCode))"
}
$vector = $vectorResult.Output.Trim()
if(-not $vector){ throw "Extensao pgvector nao encontrada" }
Ok "pgvector ativo: $vector"

Write-Host "`n[3/9] Redis..." -ForegroundColor Yellow
$redisResult = Invoke-NativeCaptured 'docker compose exec -T redis redis-cli ping'
$redis = $redisResult.Output.Trim()
if($redisResult.ExitCode -ne 0 -or $redis -ne "PONG"){
    Write-Host $redisResult.Output
    throw "Redis nao respondeu PONG"
}
Ok "Redis respondeu PONG"

Write-Host "`n[4/9] Compilacao Python..." -ForegroundColor Yellow
docker compose exec -T api python -m compileall -q app scripts
if($LASTEXITCODE -ne 0){ throw "compileall falhou" }
Ok "app/ e scripts/ compilam sem erro de sintaxe"

Write-Host "`n[5/9] Testes automatizados pytest..." -ForegroundColor Yellow
docker compose exec -T api pytest -q tests
if($LASTEXITCODE -ne 0){ throw "pytest falhou" }
Ok "Suite pytest concluida"

Write-Host "`n[6/9] Login e isolamento Demo x Acme..." -ForegroundColor Yellow
$demoToken = Login "demo" "admin@example.com" "ChangeMe123!"
$acmeToken = Login "smoke-acme" "admin@smoke-acme.local" "ChangeMe123!"
$demoCfg = GetAuth "$Base/tenant/config" $demoToken
$acmeCfg = GetAuth "$Base/tenant/config" $acmeToken
if([string]$demoCfg.tenant_id -eq [string]$acmeCfg.tenant_id){ throw "Demo e Acme retornaram o mesmo tenant_id" }
$demoProducts = @(GetAuth "$Base/tenant/products" $demoToken)
$acmeProducts = @(GetAuth "$Base/tenant/products" $acmeToken)
$demoPro = @($demoProducts | Where-Object {$_.code -eq "PRO"})[0]
$acmePro = @($acmeProducts | Where-Object {$_.code -eq "PRO"})[0]
if(-not $demoPro -or -not $acmePro){ throw "Produto PRO nao encontrado em um dos tenants" }
if([decimal]$demoPro.price -eq [decimal]$acmePro.price){ throw "Teste de isolamento fraco: PRO possui mesmo preco nos dois tenants" }
Ok "Tenants isolados: Demo=$($demoCfg.tenant_id) / Acme=$($acmeCfg.tenant_id)"
Ok "Catalogos isolados: Demo PRO=R$ $($demoPro.price) / Acme PRO=R$ $($acmePro.price)"

Write-Host "`n[7/9] Inventario persistido antes do restart..." -ForegroundColor Yellow
$voiceBefore = @(GetAuth "$Base/channels/voice/sessions?limit=100" $demoToken)
$waBefore = @(GetAuth "$Base/channels/whatsapp/events?limit=100" $demoToken)
$voiceCountBefore = $voiceBefore.Count
$waCountBefore = $waBefore.Count
Info "Voice sessions visiveis: $voiceCountBefore"
Info "Channel events visiveis: $waCountBefore"
if($voiceCountBefore -lt 1){ Warn "Nenhuma VoiceSession encontrada; persistencia de voz nao sera comparada por contagem." }

Write-Host "`n[8/9] Restart somente da API + validacao de persistencia..." -ForegroundColor Yellow
docker compose restart api
if($LASTEXITCODE -ne 0){ throw "Restart da API falhou" }

$ready = $false
for($i=0; $i -lt 40; $i++){
    Start-Sleep -Seconds 1
    try {
        $h = Invoke-RestMethod "$Base/health" -TimeoutSec 3
        if($h.status -eq "ok"){ $ready = $true; break }
    } catch {}
}
if(-not $ready){ throw "API nao voltou apos restart" }
Ok "API voltou apos restart"

# JWT anterior deve continuar valido porque o SECRET_KEY nao mudou.
$demoCfgAfter = GetAuth "$Base/tenant/config" $demoToken
if([string]$demoCfgAfter.tenant_id -ne [string]$demoCfg.tenant_id){ throw "Tenant Demo mudou apos restart" }
$voiceAfter = @(GetAuth "$Base/channels/voice/sessions?limit=100" $demoToken)
$waAfter = @(GetAuth "$Base/channels/whatsapp/events?limit=100" $demoToken)
if($voiceAfter.Count -lt $voiceCountBefore){ throw "VoiceSession desapareceu apos restart" }
if($waAfter.Count -lt $waCountBefore){ throw "Channel event desapareceu apos restart" }
Ok "Dados e tenant permaneceram disponiveis apos restart"

Write-Host "`n[9/9] Estado final..." -ForegroundColor Yellow
docker compose ps
$health2 = Invoke-RestMethod "$Base/health"
if($health2.status -ne "ok"){ throw "Health final falhou" }
Ok "API/PostgreSQL/Redis continuam operacionais"

Write-Host "`n=== CHECKPOINT v0.10.1 VALIDADO COM SUCESSO ===" -ForegroundColor Green
Write-Host "Migration       : 0007_voice_realtime"
Write-Host "pgvector        : $vector"
Write-Host "Demo tenant     : $($demoCfg.tenant_id)"
Write-Host "Acme tenant     : $($acmeCfg.tenant_id)"
Write-Host "Demo PRO        : R$ $($demoPro.price)"
Write-Host "Acme PRO        : R$ $($acmePro.price)"
Write-Host "Voice sessions  : $($voiceAfter.Count)"
Write-Host "Channel events  : $($waAfter.Count)"
Write-Host "Swagger         : http://localhost:8000/docs"
