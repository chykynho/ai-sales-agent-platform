$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$BaseUrl = "http://localhost:8000/api/v1"

Write-Host "=== AI Sales Agent Platform v0.5 - Human-in-the-Loop Smoke Test ===" -ForegroundColor Cyan

function New-JsonContent([object]$Object) {
    $json = $Object | ConvertTo-Json -Depth 50 -Compress
    return New-Object System.Net.Http.StringContent($json, [System.Text.Encoding]::UTF8, "application/json")
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
function Invoke-JsonPostCapture([string]$Uri, [object]$Body, [string]$Bearer, [hashtable]$ExtraHeaders = @{}) {
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    try {
        $client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", $Bearer)
        foreach ($key in $ExtraHeaders.Keys) { $client.DefaultRequestHeaders.Add($key, [string]$ExtraHeaders[$key]) }
        $response = $client.PostAsync($Uri, (New-JsonContent $Body)).GetAwaiter().GetResult()
        $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        $text = [System.Text.Encoding]::UTF8.GetString($bytes)
        $parsed = $null
        if ($text) { try { $parsed = $text | ConvertFrom-Json } catch {} }
        return [PSCustomObject]@{ StatusCode=[int]$response.StatusCode; Text=$text; Json=$parsed }
    } finally { $client.Dispose() }
}
function Login {
    $login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -Headers @{"X-Tenant-Slug"="demo"} -ContentType "application/x-www-form-urlencoded" -Body "username=admin%40example.com&password=ChangeMe123%21"
    if (-not $login.access_token) { throw "JWT not obtained." }
    return $login.access_token
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

Write-Host "`n[1/9] Health, login and HITL config..." -ForegroundColor Yellow
$health = Invoke-RestMethod "$BaseUrl/health"
if (-not $health.postgres -or -not $health.redis) { throw "Infrastructure health failed." }
$token = Login
$config = Invoke-JsonGet "$BaseUrl/agent/config" $token
$config | ConvertTo-Json -Depth 10
if ($config.graph -ne "sales_agent_v0.5" -or -not $config.human_interrupts) { throw "v0.5 HITL config not active." }

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddHHmmssfff")
$approveThread = "hitl-approve-$stamp"
$rejectThread = "hitl-reject-$stamp"

Write-Host "`n[2/9] Normal graph path still works..." -ForegroundColor Yellow
$normalThread = "hitl-normal-$stamp"
$normal = Invoke-JsonPost "$BaseUrl/agent/threads/$normalThread/messages" @{
    message = "Quanto custa o Plano PRO? Consulte a fonte correta antes de responder."
} $token @{"Idempotency-Key"="hitl-normal-$stamp"}
$normal | ConvertTo-Json -Depth 20
if ($normal.status -ne "completed" -or $normal.route -ne "tool_agent") { throw "Normal tool route regressed in v0.5." }

Write-Host "`n[3/9] Trigger human interrupt..." -ForegroundColor Yellow
$pending = Invoke-JsonPost "$BaseUrl/agent/threads/$approveThread/messages" @{
    message = "Quero falar com um atendente humano agora."
} $token @{"Idempotency-Key"="hitl-request-$stamp"}
$pending | ConvertTo-Json -Depth 30
if ($pending.status -ne "interrupted") { throw "Expected interrupted status." }
if ($pending.route -ne "handoff_pending" -or -not $pending.human_required) { throw "Handoff was not paused for review." }
if ($pending.human_review_status -ne "pending") { throw "Expected pending human review status." }
if (@($pending.interrupts).Count -ne 1) { throw "Expected exactly one interrupt." }
if ($pending.interrupts[0].value.type -ne "human_handoff_approval") { throw "Unexpected interrupt type." }
$interruptId = [string]$pending.interrupts[0].id
Write-Host "Pending interrupt: $interruptId" -ForegroundColor Green

Write-Host "`n[4/9] Inspect pending state, then restart API..." -ForegroundColor Yellow
$stateBefore = Invoke-JsonGet "$BaseUrl/agent/threads/$approveThread/state" $token
$stateBefore | ConvertTo-Json -Depth 30
if ($stateBefore.status -ne "interrupted") { throw "State does not expose pending interrupt." }
if (@($stateBefore.interrupts).Count -ne 1) { throw "State lost interrupt metadata." }
$checkpointBefore = [string]$stateBefore.checkpoint_id
docker compose restart api
if ($LASTEXITCODE -ne 0) { throw "docker compose restart api failed." }
Wait-Api
$token = Login
$stateAfter = Invoke-JsonGet "$BaseUrl/agent/threads/$approveThread/state" $token
if ($stateAfter.status -ne "interrupted") { throw "Pending interrupt did not survive API restart." }
if ([string]$stateAfter.checkpoint_id -ne $checkpointBefore) { throw "Latest interrupted checkpoint changed across restart." }
if ([string]$stateAfter.interrupts[0].id -ne $interruptId) { throw "Interrupt ID changed across restart." }
Write-Host "Pending interrupt recovered after API restart." -ForegroundColor Green

Write-Host "`n[5/9] Block new messages while thread is interrupted..." -ForegroundColor Yellow
$blocked = Invoke-JsonPostCapture "$BaseUrl/agent/threads/$approveThread/messages" @{
    message = "Esta mensagem não deve iniciar um novo turno enquanto há revisão pendente."
} $token @{"Idempotency-Key"="blocked-$stamp"}
$blocked.Text
if ($blocked.StatusCode -ne 409) { throw "Expected HTTP 409 for an interrupted thread, got $($blocked.StatusCode)." }
if ($blocked.Json.detail.code -ne "thread_interrupted") { throw "Unexpected blocked-message error code." }

Write-Host "`n[6/9] Approve and resume exact interrupt..." -ForegroundColor Yellow
$approved = Invoke-JsonPost "$BaseUrl/agent/threads/$approveThread/resume" @{
    decision = "approve"
    note = "Aprovado no smoke test v0.5."
} $token @{"Idempotency-Key"="resume-approve-$stamp"}
$approved | ConvertTo-Json -Depth 30
if ($approved.status -ne "completed") { throw "Thread did not complete after approval." }
if ($approved.route -ne "handoff" -or -not $approved.human_required) { throw "Approved handoff did not complete correctly." }
if ($approved.human_review_status -ne "approved") { throw "Approved review status not persisted." }
if (@($approved.interrupts).Count -ne 0) { throw "Interrupt should be cleared after resume." }
$approvedState = Invoke-JsonGet "$BaseUrl/agent/threads/$approveThread/state" $token
if (-not $approvedState.reviewed_by_user_id) { throw "Reviewer user ID was not persisted in checkpoint state." }
if ($approvedState.human_review_note -ne "Aprovado no smoke test v0.5.") { throw "Review note was not persisted." }
$duplicateResume = Invoke-JsonPostCapture "$BaseUrl/agent/threads/$approveThread/resume" @{ decision="approve"; note="duplicate" } $token
if ($duplicateResume.StatusCode -ne 409 -or $duplicateResume.Json.detail.code -ne "no_pending_interrupt") { throw "Completed thread accepted a duplicate resume." }

Write-Host "`n[7/9] Reject path on a separate thread..." -ForegroundColor Yellow
$rejectPending = Invoke-JsonPost "$BaseUrl/agent/threads/$rejectThread/messages" @{
    message = "Preciso falar com uma pessoa, por favor."
} $token @{"Idempotency-Key"="hitl-reject-request-$stamp"}
if ($rejectPending.status -ne "interrupted") { throw "Reject test thread did not interrupt." }
$rejected = Invoke-JsonPost "$BaseUrl/agent/threads/$rejectThread/resume" @{
    decision = "reject"
    note = "Equipe humana indisponível; IA pode continuar."
} $token @{"Idempotency-Key"="resume-reject-$stamp"}
$rejected | ConvertTo-Json -Depth 30
if ($rejected.status -ne "completed") { throw "Reject resume did not complete." }
if ($rejected.route -ne "handoff_rejected" -or $rejected.human_required) { throw "Rejected handoff state is incorrect." }
if ($rejected.human_review_status -ne "rejected") { throw "Rejected review status not persisted." }

Write-Host "`n[8/9] Checkpoint history includes interrupt state..." -ForegroundColor Yellow
$history = Invoke-JsonGet "$BaseUrl/agent/threads/$approveThread/history?limit=40" $token
$history | ConvertTo-Json -Depth 30
$interruptCheckpoints = @($history.checkpoints | Where-Object { [int]$_.interrupt_count -gt 0 })
if ($interruptCheckpoints.Count -lt 1) { throw "Checkpoint history does not expose the interrupt." }

Write-Host "`n[9/9] Final state summary..." -ForegroundColor Yellow
$final = Invoke-JsonGet "$BaseUrl/agent/threads/$approveThread/state" $token
$final | ConvertTo-Json -Depth 20
if ($final.status -ne "completed" -or $final.human_review_status -ne "approved") { throw "Final approved state is inconsistent." }

Write-Host "`n=== v0.5 VALIDADA COM SUCESSO ===" -ForegroundColor Green
Write-Host "Approve thread      : $approveThread"
Write-Host "Interrupt ID        : $interruptId"
Write-Host "Interrupted restart : validated"
Write-Host "Blocked new message : validated (409)"
Write-Host "Approve resume      : validated"
Write-Host "Reject resume       : validated"
Write-Host "Interrupt history   : $($interruptCheckpoints.Count) checkpoint(s)"
Write-Host "Swagger             : http://localhost:8000/docs"
