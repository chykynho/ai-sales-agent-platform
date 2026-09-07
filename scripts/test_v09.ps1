$ErrorActionPreference = "Stop"
$Base = "http://localhost:8000/api/v1"
$TenantSlug = "demo"
$VoiceAccountId = "smoke-twilio-demo-001"
$Caller = "55119" + (Get-Random -Minimum 10000000 -Maximum 99999999)
$CallId = "CA.smoke.v09." + (Get-Date -Format "yyyyMMddHHmmssfff")

Write-Host "=== AI Sales Agent Platform v0.9 - Realtime Voice Smoke Test ===" -ForegroundColor Cyan

function New-HttpClient { Add-Type -AssemblyName System.Net.Http; return New-Object System.Net.Http.HttpClient }
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
function Get-Auth {
    $login = Invoke-RestMethod -Method Post -Uri "$Base/auth/login" -Headers @{"X-Tenant-Slug"=$TenantSlug} -ContentType "application/x-www-form-urlencoded" -Body @{username="admin@example.com";password="ChangeMe123!"}
    if ([string]::IsNullOrWhiteSpace([string]$login.access_token)) { throw "Login failed" }
    return @{Authorization="Bearer $($login.access_token)"}
}

Write-Host "`n[1/8] Health, login and Voice configuration..." -ForegroundColor Yellow
$health = Invoke-RestMethod "$Base/health"
$Auth = Get-Auth
$config = Invoke-Json "GET" "$Base/channels/voice/config" $null $Auth
$config | ConvertTo-Json -Depth 12
if ($config.openai_realtime.model -ne "gpt-realtime-2.1") { throw "Unexpected Realtime model" }
if ($config.twilio_media_streams.encoding -ne "audio/x-mulaw" -or $config.twilio_media_streams.sample_rate_hz -ne 8000) { throw "Unexpected Twilio media contract" }

Write-Host "`n[2/8] Configure tenant-scoped Voice account in mock mode..." -ForegroundColor Yellow
$accountBody = @{account_sid="ACSMOKEDEMO";display_phone_number="+5511000000000";outbound_mode="mock";is_active=$true}
$account = Invoke-Json "PUT" "$Base/channels/voice/tenant/accounts/$VoiceAccountId" $accountBody $Auth
$account | ConvertTo-Json -Depth 10
if ($account.channel -ne "voice" -or $account.provider -ne "twilio" -or $account.outbound_mode -ne "mock") { throw "Voice account configuration mismatch" }

Write-Host "`n[3/8] Real OpenAI Realtime WebSocket text probe..." -ForegroundColor Yellow
$probe = Invoke-Json "POST" "$Base/channels/voice/realtime/probe" @{message="Responda exatamente REALTIME_OK e nada mais."} $Auth
$probe | ConvertTo-Json -Depth 15
if ($probe.text -notmatch "REALTIME_OK") { throw "Realtime text probe did not return expected marker" }

Write-Host "`n[4/8] Twilio bidirectional Media Streams TwiML contract..." -ForegroundColor Yellow
$streamUrl = [uri]::EscapeDataString("wss://voice.example.test/api/v1/channels/voice/twilio/media")
$twiml = Invoke-Json "GET" "$Base/channels/voice/twiml-preview?stream_url=$streamUrl" $null $Auth
Write-Host $twiml
if ([string]$twiml -notmatch "Connect" -or [string]$twiml -notmatch "Stream") { throw "TwiML preview mismatch" }

Write-Host "`n[5/8] Mock phone turn: LangGraph/tools -> Realtime audio output..." -ForegroundColor Yellow
$turnBody = @{provider_call_id=$CallId;from_address=$Caller;transcript="Quanto custa o Plano PRO? Use a fonte correta."}
$turn = Invoke-Json "POST" "$Base/channels/voice/mock/accounts/$VoiceAccountId/turns" $turnBody $Auth
$turn | ConvertTo-Json -Depth 20
if ($turn.deduplicated -ne $false) { throw "First voice turn was unexpectedly deduplicated" }
if ($turn.session.status -ne "completed" -or $turn.session.assistant_text -notmatch "997") { throw "Voice business response mismatch" }
if ([int64]$turn.session.audio_bytes -le 0 -or [string]::IsNullOrWhiteSpace([string]$turn.session.audio_sha256)) { throw "Realtime did not produce audio bytes" }
$SessionId = [string]$turn.session.id
$ThreadId = [string]$turn.session.external_thread_id

Write-Host "`n[6/8] Idempotent replay of same provider call id..." -ForegroundColor Yellow
$replay = Invoke-Json "POST" "$Base/channels/voice/mock/accounts/$VoiceAccountId/turns" $turnBody $Auth
$replay | ConvertTo-Json -Depth 15
if ($replay.deduplicated -ne $true -or [string]$replay.session.id -ne $SessionId) { throw "Voice call replay was not idempotent" }

Write-Host "`n[7/8] LangGraph Voice thread persisted with tenant price..." -ForegroundColor Yellow
$state = Invoke-Json "GET" "$Base/agent/threads/$ThreadId/state" $null $Auth
$state | ConvertTo-Json -Depth 15
if ($state.final_output -notmatch "997" -or $state.message_count -lt 2) { throw "Voice LangGraph state mismatch" }

Write-Host "`n[8/8] Voice session/event audit and single deployment..." -ForegroundColor Yellow
$sessions = Invoke-Json "GET" "$Base/channels/voice/sessions?limit=20" $null $Auth
$events = Invoke-Json "GET" "$Base/channels/voice/sessions/$SessionId/events" $null $Auth
@($sessions | Where-Object {$_.id -eq $SessionId}) | ConvertTo-Json -Depth 15
$events | ConvertTo-Json -Depth 15
if (@($events).Count -lt 2) { throw "Expected inbound transcript and outbound audio events" }
if (@($events | Where-Object {$_.event_type -eq "realtime_audio" -and $_.audio_bytes -gt 0}).Count -lt 1) { throw "Realtime audio audit event missing" }
docker compose ps

Write-Host "`n=== v0.9 VALIDADA COM SUCESSO ===" -ForegroundColor Green
Write-Host "Realtime model : $($config.openai_realtime.model)"
Write-Host "Voice          : $($config.openai_realtime.voice)"
Write-Host "Realtime probe : $($probe.text)"
Write-Host "Call ID        : $CallId"
Write-Host "Session        : $SessionId"
Write-Host "Thread         : $ThreadId"
Write-Host "Business text  : $($turn.session.assistant_text)"
Write-Host "Audio bytes    : $($turn.session.audio_bytes)"
Write-Host "Audio SHA256   : $($turn.session.audio_sha256)"
Write-Host "Swagger        : http://localhost:8000/docs"
