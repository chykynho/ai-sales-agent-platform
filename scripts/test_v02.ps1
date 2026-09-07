$ErrorActionPreference = "Stop"
$BaseUrl = "http://localhost:8000/api/v1"

Write-Host "=== AI Sales Agent Platform v0.2.1 - LLM Smoke Test ===" -ForegroundColor Cyan

function New-JsonContent([object]$Object) {
    $json = $Object | ConvertTo-Json -Depth 20 -Compress
    return New-Object System.Net.Http.StringContent($json, [System.Text.Encoding]::UTF8, "application/json")
}

function Invoke-JsonPost([string]$Uri, [object]$Body, [string]$Bearer = $null, [hashtable]$ExtraHeaders = @{}) {
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    try {
        if ($Bearer) {
            $client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", $Bearer)
        }
        foreach ($key in $ExtraHeaders.Keys) {
            $client.DefaultRequestHeaders.Add($key, [string]$ExtraHeaders[$key])
        }
        $content = New-JsonContent $Body
        $response = $client.PostAsync($Uri, $content).GetAwaiter().GetResult()
        $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        $text = [System.Text.Encoding]::UTF8.GetString($bytes)
        if (-not $response.IsSuccessStatusCode) {
            throw "HTTP $([int]$response.StatusCode): $text"
        }
        return $text | ConvertFrom-Json
    }
    finally {
        $client.Dispose()
    }
}

function Invoke-JsonGet([string]$Uri, [string]$Bearer) {
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    try {
        $client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", $Bearer)
        $response = $client.GetAsync($Uri).GetAwaiter().GetResult()
        $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        $text = [System.Text.Encoding]::UTF8.GetString($bytes)
        if (-not $response.IsSuccessStatusCode) {
            throw "HTTP $([int]$response.StatusCode): $text"
        }
        return $text | ConvertFrom-Json
    }
    finally {
        $client.Dispose()
    }
}

Write-Host "`n[1/6] Health..." -ForegroundColor Yellow
$health = Invoke-RestMethod "$BaseUrl/health"
$health | ConvertTo-Json
if (-not $health.postgres -or -not $health.redis) { throw "Infrastructure health failed." }

Write-Host "`n[2/6] Login..." -ForegroundColor Yellow
$login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -Headers @{"X-Tenant-Slug"="demo"} -ContentType "application/x-www-form-urlencoded" -Body "username=admin%40example.com&password=ChangeMe123%21"
$token = $login.access_token
if (-not $token) { throw "JWT not obtained." }
Write-Host "JWT obtained." -ForegroundColor Green

Write-Host "`n[3/6] LLM config..." -ForegroundColor Yellow
$config = Invoke-JsonGet "$BaseUrl/ai/config" $token
$config | ConvertTo-Json -Depth 10

Write-Host "`n[4/6] Text generation..." -ForegroundColor Yellow
$generated = Invoke-JsonPost "$BaseUrl/ai/generate" @{
    input = "Explique em uma frase por que um agente comercial precisa de observabilidade."
} $token
$generated | ConvertTo-Json -Depth 10
if (-not $generated.run_id -or -not $generated.output) { throw "Generate response incomplete." }

Write-Host "`n[5/6] Structured lead classification..." -ForegroundColor Yellow
$classified = Invoke-JsonPost "$BaseUrl/ai/classify-lead" @{
    message = "Quero contratar o plano e também gostaria de falar com um atendente humano."
} $token
$classified | ConvertTo-Json -Depth 10
if (-not $classified.run_id) { throw "Structured run_id missing." }
if ($classified.classification.needs_human -ne $true) { throw "Structured output validation failed: needs_human should be true." }
if ($classified.classification.intent -ne "human_request") { throw "Structured output validation failed: intent should be human_request." }

Write-Host "`n[6/6] Agent run persistence / tenant filter..." -ForegroundColor Yellow

# Strong persistence check: each run returned by the LLM endpoints must be
# independently retrievable from PostgreSQL through the tenant-filtered API.
$generatedRun = Invoke-JsonGet "$BaseUrl/ai/runs/$($generated.run_id)" $token
$classifiedRun = Invoke-JsonGet "$BaseUrl/ai/runs/$($classified.run_id)" $token

if ([string]$generatedRun.id -ne [string]$generated.run_id) { throw "Generate agent_run was not persisted/retrievable." }
if ([string]$classifiedRun.id -ne [string]$classified.run_id) { throw "Structured agent_run was not persisted/retrievable." }
if ($generatedRun.status -ne "completed") { throw "Generate agent_run status is not completed." }
if ($classifiedRun.status -ne "completed") { throw "Structured agent_run status is not completed." }
if ([string]$generatedRun.tenant_id -ne [string]$classifiedRun.tenant_id) { throw "Agent runs do not belong to the same tenant." }

# IMPORTANT for Windows PowerShell 5.1:
# ConvertFrom-Json can emit a JSON array as one array object on the pipeline.
# Do NOT wrap this function call in @(...) here, otherwise it may become a
# one-element outer array and .Count will incorrectly report 1.
$runs = Invoke-JsonGet "$BaseUrl/ai/runs?limit=10" $token

if ($null -eq $runs) {
    $runCount = 0
}
elseif ($runs -is [System.Array]) {
    $runCount = $runs.Count
}
else {
    $runCount = 1
    $runs = @($runs)
}

if ($runCount -lt 2) { throw "Expected at least two persisted agent_runs; API returned $runCount." }

$runIds = @($runs | ForEach-Object { [string]$_.id })
if ($runIds -notcontains [string]$generated.run_id) { throw "Generate agent_run is missing from tenant-filtered list." }
if ($runIds -notcontains [string]$classified.run_id) { throw "Structured agent_run is missing from tenant-filtered list." }

Write-Host "Generate run persisted : $($generatedRun.id)" -ForegroundColor Green
Write-Host "Structured run persisted: $($classifiedRun.id)" -ForegroundColor Green
Write-Host "Tenant                  : $($generatedRun.tenant_id)" -ForegroundColor Green
Write-Host "Persisted runs returned : $runCount" -ForegroundColor Green

Write-Host "`n=== v0.2.1 VALIDADA COM SUCESSO ===" -ForegroundColor Green
Write-Host "Provider: $($config.provider)"
Write-Host "Model   : $($config.model)"
Write-Host "Swagger : http://localhost:8000/docs"
