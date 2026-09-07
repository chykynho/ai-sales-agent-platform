$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$BaseUrl = "http://localhost:8000/api/v1"

Write-Host "=== AI Sales Agent Platform v0.3.1 - Tool Calling Smoke Test ===" -ForegroundColor Cyan

function New-JsonContent([object]$Object) {
    $json = $Object | ConvertTo-Json -Depth 30 -Compress
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

Write-Host "`n[1/7] Health and login..." -ForegroundColor Yellow
$health = Invoke-RestMethod "$BaseUrl/health"
if (-not $health.postgres -or -not $health.redis) { throw "Infrastructure health failed." }
$login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -Headers @{"X-Tenant-Slug"="demo"} -ContentType "application/x-www-form-urlencoded" -Body "username=admin%40example.com&password=ChangeMe123%21"
$token = $login.access_token
if (-not $token) { throw "JWT not obtained." }

Write-Host "`n[2/7] Tool catalog..." -ForegroundColor Yellow
$config = Invoke-JsonGet "$BaseUrl/ai/config" $token
$tools = Invoke-JsonGet "$BaseUrl/ai/tools" $token
$config | ConvertTo-Json -Depth 10
$tools | ConvertTo-Json -Depth 10
if ($config.tool_count -ne 4) { throw "Expected four tools." }

Write-Host "`n[3/7] Read-only tool: check_price..." -ForegroundColor Yellow
$priceKey = "smoke-price-" + [DateTime]::UtcNow.ToString("yyyyMMddHHmmssfff")
$price = Invoke-JsonPost "$BaseUrl/ai/tool-agent" @{
    message = "Use obrigatoriamente a ferramenta check_price para consultar o preço do produto PRO. Não invente o preço."
} $token @{"Idempotency-Key"=$priceKey}
$price | ConvertTo-Json -Depth 20
if (-not $price.run_id) { throw "Price tool run_id missing." }
$priceCalls = @($price.tool_calls)
if (@($priceCalls | Where-Object { $_.tool_name -eq "check_price" -and $_.status -eq "completed" }).Count -lt 1) { throw "check_price was not completed." }

Write-Host "`n[4/7] Write tool: create_lead..." -ForegroundColor Yellow
$stamp = [DateTime]::UtcNow.ToString("yyyyMMddHHmmssfff")
$email = "maria+$stamp@example.com"
$leadKey = "smoke-lead-$stamp"
$lead = Invoke-JsonPost "$BaseUrl/ai/tool-agent" @{
    message = "Use obrigatoriamente a ferramenta create_lead para cadastrar Maria Silva, email $email, interesse Plano PRO. Só confirme depois da ferramenta."
} $token @{"Idempotency-Key"=$leadKey}
$lead | ConvertTo-Json -Depth 20
if (-not $lead.run_id) { throw "Lead tool run_id missing." }
$leadCalls = @($lead.tool_calls)
if (@($leadCalls | Where-Object { $_.tool_name -eq "create_lead" -and $_.status -eq "completed" }).Count -lt 1) { throw "create_lead was not completed." }

Write-Host "`n[5/7] Idempotent replay of write tool..." -ForegroundColor Yellow
$leadReplay = Invoke-JsonPost "$BaseUrl/ai/tool-agent" @{
    message = "Use obrigatoriamente a ferramenta create_lead para cadastrar Maria Silva, email $email, interesse Plano PRO. Só confirme depois da ferramenta."
} $token @{"Idempotency-Key"=$leadKey}
$leadReplay | ConvertTo-Json -Depth 20
if (@($leadReplay.tool_calls | Where-Object { $_.tool_name -eq "create_lead" -and $_.status -eq "completed" }).Count -lt 1) { throw "Idempotent create_lead replay failed." }
$leadRows = Invoke-JsonGet "$BaseUrl/leads?email=$([System.Uri]::EscapeDataString($email))" $token
if ($null -eq $leadRows) { $leadCount = 0 } elseif ($leadRows -is [System.Array]) { $leadCount = $leadRows.Count } else { $leadCount = 1 }
if ($leadCount -ne 1) { throw "Idempotency failed: expected exactly one lead for $email, got $leadCount." }
Write-Host "Single persisted lead confirmed after replay." -ForegroundColor Green

Write-Host "`n[6/7] Audit trail per agent_run..." -ForegroundColor Yellow
$priceAudit = Invoke-JsonGet "$BaseUrl/ai/runs/$($price.run_id)/tool-calls" $token
$leadAudit = Invoke-JsonGet "$BaseUrl/ai/runs/$($lead.run_id)/tool-calls" $token
if (@($priceAudit).Count -lt 1) { throw "Price tool audit missing." }
if (@($leadAudit).Count -lt 1) { throw "Lead tool audit missing." }
Write-Host "Price tool audit records: $(@($priceAudit).Count)" -ForegroundColor Green
Write-Host "Lead tool audit records : $(@($leadAudit).Count)" -ForegroundColor Green

Write-Host "`n[7/7] Agent run metrics..." -ForegroundColor Yellow
$priceRun = Invoke-JsonGet "$BaseUrl/ai/runs/$($price.run_id)" $token
$leadRun = Invoke-JsonGet "$BaseUrl/ai/runs/$($lead.run_id)" $token
$priceRun | ConvertTo-Json -Depth 10
$leadRun | ConvertTo-Json -Depth 10
if ($priceRun.tool_call_count -lt 1 -or $priceRun.provider_response_count -lt 2) { throw "Price run metrics are incomplete." }
if ($leadRun.tool_call_count -lt 1 -or $leadRun.provider_response_count -lt 2) { throw "Lead run metrics are incomplete." }

Write-Host "`n=== v0.3.1 VALIDADA COM SUCESSO ===" -ForegroundColor Green
Write-Host "Provider : $($config.provider)"
Write-Host "Model    : $($config.model)"
Write-Host "Price run: $($price.run_id)"
Write-Host "Lead run : $($lead.run_id)"
Write-Host "Swagger  : http://localhost:8000/docs"
