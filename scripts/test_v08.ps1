$ErrorActionPreference = "Stop"
$Base = "http://localhost:8000/api/v1"
$TenantSlug = "demo"
$PhoneNumberId = "smoke-wa-demo-001"
$Sender = "55119" + (Get-Random -Minimum 10000000 -Maximum 99999999)
$VerifyToken = "local-v08-verify-token"
$AppSecret = "local-v08-app-secret-change-me"
$Wamid = "wamid.smoke.v08." + (Get-Date -Format "yyyyMMddHHmmssfff")

Write-Host "=== AI Sales Agent Platform v0.8.2 - WhatsApp Channel Smoke Test ===" -ForegroundColor Cyan

function New-HttpClient {
    Add-Type -AssemblyName System.Net.Http
    return New-Object System.Net.Http.HttpClient
}

function Invoke-Json([string]$Method, [string]$Url, $Body=$null, [hashtable]$Headers=@{}) {
    $client = New-HttpClient
    try {
        $req = New-Object System.Net.Http.HttpRequestMessage((New-Object System.Net.Http.HttpMethod($Method)), $Url)
        foreach ($k in $Headers.Keys) { $req.Headers.TryAddWithoutValidation($k, [string]$Headers[$k]) | Out-Null }
        if ($null -ne $Body) {
            $json = if ($Body -is [string]) { $Body } else { $Body | ConvertTo-Json -Depth 30 -Compress }
            $req.Content = New-Object System.Net.Http.StringContent($json, [Text.Encoding]::UTF8, "application/json")
        }
        $response = $client.SendAsync($req).Result
        $bytes = $response.Content.ReadAsByteArrayAsync().Result
        $txt = [Text.Encoding]::UTF8.GetString($bytes)
        if (-not $response.IsSuccessStatusCode) { throw "HTTP $([int]$response.StatusCode): $txt" }
        if ([string]::IsNullOrWhiteSpace($txt)) { return $null }
        try { return $txt | ConvertFrom-Json } catch { return $txt }
    } finally { $client.Dispose() }
}

function Get-DemoAuth {
    $freshLogin = Invoke-RestMethod -Method Post -Uri "$Base/auth/login" -Headers @{"X-Tenant-Slug"=$TenantSlug} -ContentType "application/x-www-form-urlencoded" -Body @{ username="admin@example.com"; password="ChangeMe123!" }
    if ([string]::IsNullOrWhiteSpace([string]$freshLogin.access_token)) { throw "Login did not return access_token" }
    return @{ Authorization = "Bearer $($freshLogin.access_token)" }
}

function Invoke-JsonWithAuthRetry([string]$Method, [string]$Url, $Body=$null) {
    try {
        return Invoke-Json $Method $Url $Body $script:Auth
    } catch {
        if ($_.Exception.Message -like "HTTP 401:*") {
            Write-Host "JWT rejected during smoke test; refreshing login once and retrying..." -ForegroundColor DarkYellow
            $script:Auth = Get-DemoAuth
            return Invoke-Json $Method $Url $Body $script:Auth
        }
        throw
    }
}

Write-Host "`n[1/8] Health, login and channel config..." -ForegroundColor Yellow
$health = Invoke-RestMethod "$Base/health"
$Auth = Get-DemoAuth
$me = Invoke-Json "GET" "$Base/users/me" $null $Auth
$tenantConfig = Invoke-Json "GET" "$Base/tenant/config" $null $Auth
$TenantId = [string]$tenantConfig.tenant_id
if ([string]::IsNullOrWhiteSpace($TenantId)) { throw "Tenant config did not return tenant_id" }
$config = Invoke-Json "GET" "$Base/channels/config" $null $Auth
$config | ConvertTo-Json -Depth 10
if ($config.whatsapp.webhook_processing -ne "ack-first-background") { throw "Unexpected webhook mode" }

Write-Host "`n[2/8] Configure tenant-scoped WhatsApp account in mock outbound mode..." -ForegroundColor Yellow
$accountBody = @{ business_account_id="smoke-waba-demo"; display_phone_number="5511000000000"; outbound_mode="mock"; is_active=$true }
$account = Invoke-Json "PUT" "$Base/channels/tenant/whatsapp/$PhoneNumberId" $accountBody $Auth
$account | ConvertTo-Json -Depth 10
if (([string]$account.tenant_id).Trim() -ne $TenantId.Trim() -or ([string]$account.outbound_mode).Trim().ToLowerInvariant() -ne "mock") {
    Write-Host "Expected tenant : $TenantId"
    Write-Host "Account tenant  : $($account.tenant_id)"
    Write-Host "Outbound mode   : $($account.outbound_mode)"
    throw "Channel account tenant/mode mismatch"
}

Write-Host "`n[3/8] Meta webhook verification challenge + wrong-token rejection..." -ForegroundColor Yellow
$challenge = "v08-challenge-12345"
$verifyUrl = "$Base/channels/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=$VerifyToken&hub.challenge=$challenge"
$verified = Invoke-RestMethod -Uri $verifyUrl -Method Get
if ([string]$verified -ne $challenge) { throw "Webhook challenge verification failed" }
$badRejected = $false
try { Invoke-RestMethod -Uri "$Base/channels/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=x" -Method Get | Out-Null }
catch { if ($_.Exception.Response.StatusCode.value__ -eq 403) { $badRejected = $true } }
if (-not $badRejected) { throw "Wrong webhook token was not rejected" }
Write-Host "Webhook verification validated."

Write-Host "`n[4/8] Signed inbound WhatsApp text -> fast ACK..." -ForegroundColor Yellow
$payload = @{
  object="whatsapp_business_account"
  entry=@(@{
    id="smoke-waba-demo"
    changes=@(@{
      field="messages"
      value=@{
        messaging_product="whatsapp"
        metadata=@{ display_phone_number="5511000000000"; phone_number_id=$PhoneNumberId }
        contacts=@(@{ profile=@{name="Cliente Smoke WhatsApp"}; wa_id=$Sender })
        messages=@(@{ from=$Sender; id=$Wamid; timestamp="1788780000"; type="text"; text=@{body="Quanto custa o Plano PRO? Use a fonte correta."} })
      }
    })
  })
}
$json = $payload | ConvertTo-Json -Depth 30 -Compress
$bytes = [Text.Encoding]::UTF8.GetBytes($json)
$hmac = New-Object System.Security.Cryptography.HMACSHA256
$hmac.Key = [Text.Encoding]::UTF8.GetBytes($AppSecret)
$sigBytes = $hmac.ComputeHash($bytes)
$signature = "sha256=" + (($sigBytes | ForEach-Object { $_.ToString("x2") }) -join "")
$hmac.Dispose()
$ack = Invoke-Json "POST" "$Base/channels/whatsapp/webhook" $json @{"X-Hub-Signature-256"=$signature}
$ack | ConvertTo-Json -Depth 8
if ($ack.accepted -ne 1) { throw "Expected one accepted inbound message" }

Write-Host "`n[5/8] Idempotent replay of same provider message id..." -ForegroundColor Yellow
$replay = Invoke-Json "POST" "$Base/channels/whatsapp/webhook" $json @{"X-Hub-Signature-256"=$signature}
$replay | ConvertTo-Json -Depth 8
if ($replay.duplicate -ne 1 -or $replay.accepted -ne 0) { throw "Webhook replay was not deduplicated" }

Write-Host "`n[6/8] Poll background processing and inspect outbound mock delivery..." -ForegroundColor Yellow
# Refresh before polling so a long/paused interactive smoke run cannot carry a stale JWT.
$Auth = Get-DemoAuth
$events = $null
$inbound = $null
$outbound = $null
for ($i=0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 750
    $events = Invoke-JsonWithAuthRetry "GET" "$Base/channels/whatsapp/events?limit=30" $null
    $inbound = @($events | Where-Object { $_.provider_event_id -eq $Wamid }) | Select-Object -First 1
    $outbound = @($events | Where-Object { $_.direction -eq "outbound" -and $_.to_address -eq $Sender }) | Select-Object -First 1
    if ($null -ne $inbound -and $inbound.status -eq "completed" -and $null -ne $outbound -and $outbound.status -eq "sent") { break }
}
if ($null -eq $inbound -or $inbound.status -ne "completed") {
    $events | ConvertTo-Json -Depth 12
    throw "Inbound event did not complete"
}
if ($null -eq $outbound -or $outbound.content_text -notmatch "997") {
    $events | ConvertTo-Json -Depth 12
    throw "Outbound mock response did not contain tenant price 997"
}
@($inbound,$outbound) | ConvertTo-Json -Depth 12

Write-Host "`n[7/8] LangGraph thread created from WhatsApp identity..." -ForegroundColor Yellow
$threadId = "wa-$Sender"
$state = Invoke-JsonWithAuthRetry "GET" "$Base/agent/threads/$threadId/state" $null
$state | ConvertTo-Json -Depth 15
if ($state.message_count -lt 2 -or $state.final_output -notmatch "997") { throw "WhatsApp LangGraph state mismatch" }

Write-Host "`n[8/8] Channel account inventory and single deployment..." -ForegroundColor Yellow
$accounts = Invoke-JsonWithAuthRetry "GET" "$Base/channels/tenant/accounts" $null
$accounts | ConvertTo-Json -Depth 10
docker compose ps

Write-Host "`n=== v0.8.2 VALIDADA COM SUCESSO ===" -ForegroundColor Green
Write-Host "Tenant          : $TenantId"
Write-Host "Phone number ID : $PhoneNumberId"
Write-Host "Inbound wamid   : $Wamid"
Write-Host "Inbound status  : $($inbound.status)"
Write-Host "Outbound mode   : $($account.outbound_mode)"
Write-Host "Outbound text   : $($outbound.content_text)"
Write-Host "Thread          : $threadId"
Write-Host "Swagger         : http://localhost:8000/docs"
