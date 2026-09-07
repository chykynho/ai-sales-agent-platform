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

# Usa HttpClient e trata separadamente objetos e listas JSON.
# No Windows PowerShell 5.1, ConvertFrom-Json pode preservar uma matriz JSON como
# um unico System.Object[]. GetAuthList enumera explicitamente cada item.
Add-Type -AssemblyName System.Net.Http
function GetAuthRaw([string]$url, [string]$token) {
    $client = [System.Net.Http.HttpClient]::new()
    try {
        $client.DefaultRequestHeaders.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer", $token)
        $response = $client.GetAsync($url).GetAwaiter().GetResult()
        $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if(-not $response.IsSuccessStatusCode){
            throw "HTTP $([int]$response.StatusCode): $text"
        }
        return [string]$text
    } finally {
        $client.Dispose()
    }
}

function GetAuthObject([string]$url, [string]$token) {
    $text = GetAuthRaw $url $token
    if(-not $text){ return $null }
    return ($text | ConvertFrom-Json)
}

function GetAuthList([string]$url, [string]$token) {
    $text = GetAuthRaw $url $token
    if(-not $text){ return }
    $parsed = $text | ConvertFrom-Json
    if($null -eq $parsed){ return }

    # FastAPI atual devolve lista JSON pura. Enumeramos explicitamente para o
    # pipeline do PowerShell receber cada objeto individualmente.
    if($parsed -is [System.Array]){
        foreach($item in $parsed){ Write-Output $item }
        return
    }

    # Compatibilidade defensiva caso no futuro o endpoint passe a usar wrapper.
    $itemsProperty = $parsed.PSObject.Properties['items']
    if($null -ne $itemsProperty -and $null -ne $parsed.items){
        foreach($item in @($parsed.items)){ Write-Output $item }
        return
    }

    # Se o endpoint retornar um unico objeto, ainda o devolvemos como um item.
    Write-Output $parsed
}

Write-Host "=== CHECKPOINT LOCAL AI SALES AGENT PLATFORM v0.10.5 ===" -ForegroundColor Cyan
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
$demoCfg = GetAuthObject "$Base/tenant/config" $demoToken
$acmeCfg = GetAuthObject "$Base/tenant/config" $acmeToken
if([string]$demoCfg.tenant_id -eq [string]$acmeCfg.tenant_id){ throw "Demo e Acme retornaram o mesmo tenant_id" }
$demoProducts = @(GetAuthList "$Base/tenant/products" $demoToken)
$acmeProducts = @(GetAuthList "$Base/tenant/products" $acmeToken)
$demoProMatches = @($demoProducts | Where-Object { [string]$_.code -eq "PRO" })
$acmeProMatches = @($acmeProducts | Where-Object { [string]$_.code -eq "PRO" })
if($demoProMatches.Count -ne 1){
    Write-Host "[DIAGNOSTICO] Tipo demoProducts: $($demoProducts.GetType().FullName)" -ForegroundColor Magenta
    Write-Host "[DIAGNOSTICO] Quantidade de itens do catalogo Demo: $($demoProducts.Count)" -ForegroundColor Magenta
    $demoRaw = GetAuthRaw "$Base/tenant/products" $demoToken
    Write-Host "[DIAGNOSTICO] JSON bruto Demo: $demoRaw" -ForegroundColor Magenta
    throw "Catalogo Demo deveria ter exatamente 1 produto PRO; encontrados: $($demoProMatches.Count)"
}
if($acmeProMatches.Count -ne 1){ throw "Catalogo Acme deveria ter exatamente 1 produto PRO; encontrados: $($acmeProMatches.Count)" }
$demoPro = $demoProMatches[0]
$acmePro = $acmeProMatches[0]
$culture = [System.Globalization.CultureInfo]::InvariantCulture
$demoPrice = [decimal]::Parse([string]$demoPro.price, $culture)
$acmePrice = [decimal]::Parse([string]$acmePro.price, $culture)
if($demoPrice -eq $acmePrice){ throw "Teste de isolamento fraco: PRO possui mesmo preco nos dois tenants" }
Ok "Tenants isolados: Demo=$($demoCfg.tenant_id) / Acme=$($acmeCfg.tenant_id)"
Ok "Catalogos isolados: Demo PRO=R$ $demoPrice / Acme PRO=R$ $acmePrice"

Write-Host "`n[7/9] Inventario persistido antes do restart..." -ForegroundColor Yellow
$voiceBefore = @(GetAuthList "$Base/channels/voice/sessions?limit=100" $demoToken)
$waBefore = @(GetAuthList "$Base/channels/whatsapp/events?limit=100" $demoToken)
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
$demoCfgAfter = GetAuthObject "$Base/tenant/config" $demoToken
if([string]$demoCfgAfter.tenant_id -ne [string]$demoCfg.tenant_id){ throw "Tenant Demo mudou apos restart" }
$voiceAfter = @(GetAuthList "$Base/channels/voice/sessions?limit=100" $demoToken)
$waAfter = @(GetAuthList "$Base/channels/whatsapp/events?limit=100" $demoToken)
if($voiceAfter.Count -lt $voiceCountBefore){ throw "VoiceSession desapareceu apos restart" }
if($waAfter.Count -lt $waCountBefore){ throw "Channel event desapareceu apos restart" }
Ok "Dados e tenant permaneceram disponiveis apos restart"

Write-Host "`n[9/9] Estado final..." -ForegroundColor Yellow
docker compose ps
$health2 = Invoke-RestMethod "$Base/health"
if($health2.status -ne "ok"){ throw "Health final falhou" }
Ok "API/PostgreSQL/Redis continuam operacionais"

Write-Host "`n=== CHECKPOINT v0.10.5 VALIDADO COM SUCESSO ===" -ForegroundColor Green
Write-Host "Migration       : 0007_voice_realtime"
Write-Host "pgvector        : $vector"
Write-Host "Demo tenant     : $($demoCfg.tenant_id)"
Write-Host "Acme tenant     : $($acmeCfg.tenant_id)"
Write-Host "Demo PRO        : R$ $demoPrice"
Write-Host "Acme PRO        : R$ $acmePrice"
Write-Host "Voice sessions  : $($voiceAfter.Count)"
Write-Host "Channel events  : $($waAfter.Count)"
Write-Host "Swagger         : http://localhost:8000/docs"
