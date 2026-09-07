$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$BaseUrl = "http://localhost:8000/api/v1"

Write-Host "=== AI Sales Agent Platform v0.4 - LangGraph Persistence Smoke Test ===" -ForegroundColor Cyan

function New-JsonContent([object]$Object) {
    $json = $Object | ConvertTo-Json -Depth 40 -Compress
    return New-Object System.Net.Http.StringContent($json, [System.Text.Encoding]::UTF8, "application/json")
}
function Invoke-JsonPost([string]$Uri, [object]$Body, [string]$Bearer, [hashtable]$ExtraHeaders = @{}) {
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    try {
        $client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", $Bearer)
        foreach ($key in $ExtraHeaders.Keys) { $client.DefaultRequestHeaders.Add($key, [string]$ExtraHeaders[$key]) }
        $response = $client.PostAsync($Uri, (New-JsonContent $Body)).GetAwaiter().GetResult()
        $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        $text = [System.Text.Encoding]::UTF8.GetString($bytes)
        if (-not $response.IsSuccessStatusCode) { throw "HTTP $([int]$response.StatusCode): $text" }
        return $text | ConvertFrom-Json
    } finally { $client.Dispose() }
}
function Invoke-JsonGet([string]$Uri, [string]$Bearer) {
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    try {
        $client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", $Bearer)
        $response = $client.GetAsync($Uri).GetAwaiter().GetResult()
        $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        $text = [System.Text.Encoding]::UTF8.GetString($bytes)
        if (-not $response.IsSuccessStatusCode) { throw "HTTP $([int]$response.StatusCode): $text" }
        return $text | ConvertFrom-Json
    } finally { $client.Dispose() }
}
function Wait-Api {
    for ($i=0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        try {
            $health = Invoke-RestMethod "$BaseUrl/health" -TimeoutSec 2
            if ($health.postgres -and $health.redis) { return }
        } catch {}
    }
    throw "API did not become healthy."
}

Write-Host "`n[1/8] Health, login and LangGraph config..." -ForegroundColor Yellow
$health = Invoke-RestMethod "$BaseUrl/health"
if (-not $health.postgres -or -not $health.redis) { throw "Infrastructure health failed." }
$login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -Headers @{"X-Tenant-Slug"="demo"} -ContentType "application/x-www-form-urlencoded" -Body "username=admin%40example.com&password=ChangeMe123%21"
$token = $login.access_token
if (-not $token) { throw "JWT not obtained." }
$config = Invoke-JsonGet "$BaseUrl/agent/config" $token
$config | ConvertTo-Json -Depth 10
if ($config.runtime -ne "langgraph" -or $config.checkpointer -ne "postgres") { throw "LangGraph/Postgres config not active." }

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddHHmmssfff")
$thread = "smoke-$stamp"

Write-Host "`n[2/8] First turn: pricing routed through graph + tool..." -ForegroundColor Yellow
$turn1 = Invoke-JsonPost "$BaseUrl/agent/threads/$thread/messages" @{
    message = "Quanto custa o Plano PRO? Consulte a fonte correta antes de responder."
} $token @{"Idempotency-Key"="graph-price-$stamp"}
$turn1 | ConvertTo-Json -Depth 20
if ($turn1.route -ne "tool_agent") { throw "Expected tool_agent route on pricing turn, got $($turn1.route)." }
if (@($turn1.tool_call_ids).Count -lt 1) { throw "Pricing graph turn did not execute a tool." }
if ($turn1.message_count -lt 2) { throw "Thread did not persist user + assistant messages." }

Write-Host "`n[3/8] Checkpoint state before restart..." -ForegroundColor Yellow
$stateBefore = Invoke-JsonGet "$BaseUrl/agent/threads/$thread/state" $token
$stateBefore | ConvertTo-Json -Depth 20
if (-not $stateBefore.checkpoint_id) { throw "Checkpoint ID missing before restart." }
if ($stateBefore.message_count -lt 2) { throw "Checkpoint did not contain conversation messages." }
$checkpointBefore = $stateBefore.checkpoint_id
$messageCountBefore = [int]$stateBefore.message_count

Write-Host "`n[4/8] Restart API process to prove durable PostgreSQL checkpoints..." -ForegroundColor Yellow
docker compose restart api
if ($LASTEXITCODE -ne 0) { throw "docker compose restart api failed." }
Wait-Api
$login2 = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -Headers @{"X-Tenant-Slug"="demo"} -ContentType "application/x-www-form-urlencoded" -Body "username=admin%40example.com&password=ChangeMe123%21"
$token = $login2.access_token
if (-not $token) { throw "JWT not obtained after restart." }

Write-Host "`n[5/8] Recover same thread after restart..." -ForegroundColor Yellow
$stateAfter = Invoke-JsonGet "$BaseUrl/agent/threads/$thread/state" $token
$stateAfter | ConvertTo-Json -Depth 20
if ($stateAfter.message_count -ne $messageCountBefore) { throw "Conversation state was not recovered after restart." }
if ($stateAfter.checkpoint_id -ne $checkpointBefore) { throw "Expected same latest checkpoint immediately after restart." }
Write-Host "Persistent checkpoint recovered after API restart." -ForegroundColor Green

Write-Host "`n[6/8] Second turn on same thread..." -ForegroundColor Yellow
$turn2 = Invoke-JsonPost "$BaseUrl/agent/threads/$thread/messages" @{
    message = "E quanto custa o Plano STARTER?"
} $token @{"Idempotency-Key"="graph-starter-$stamp"}
$turn2 | ConvertTo-Json -Depth 20
if ($turn2.route -ne "tool_agent") { throw "Expected tool_agent route on second pricing turn, got $($turn2.route)." }
if ($turn2.message_count -le $messageCountBefore) { throw "Thread did not accumulate conversation state across turns." }
if (@($turn2.tool_call_ids).Count -lt 2) { throw "Expected accumulated tool call history after second turn." }

Write-Host "`n[7/8] Deterministic human handoff branch..." -ForegroundColor Yellow
$turn3 = Invoke-JsonPost "$BaseUrl/agent/threads/$thread/messages" @{
    message = "Quero falar com um atendente humano agora."
} $token @{"Idempotency-Key"="graph-handoff-$stamp"}
$turn3 | ConvertTo-Json -Depth 20
if ($turn3.route -ne "handoff" -or -not $turn3.human_required) { throw "Human handoff conditional edge was not selected." }

Write-Host "`n[8/8] Checkpoint history..." -ForegroundColor Yellow
$history = Invoke-JsonGet "$BaseUrl/agent/threads/$thread/history?limit=30" $token
$history | ConvertTo-Json -Depth 20
$checkpointCount = @($history.checkpoints).Count
if ($checkpointCount -lt 6) { throw "Expected multiple node checkpoints, got $checkpointCount." }
$finalState = Invoke-JsonGet "$BaseUrl/agent/threads/$thread/state" $token
if ($finalState.message_count -lt 6) { throw "Expected at least 3 user/assistant turn pairs." }

Write-Host "`n=== v0.4 VALIDADA COM SUCESSO ===" -ForegroundColor Green
Write-Host "Thread          : $thread"
Write-Host "Checkpoints     : $checkpointCount"
Write-Host "Messages        : $($finalState.message_count)"
Write-Host "Final route     : $($finalState.route)"
Write-Host "Human required  : $($finalState.human_required)"
Write-Host "Swagger         : http://localhost:8000/docs"
