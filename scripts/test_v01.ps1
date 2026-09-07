$ErrorActionPreference = "Stop"

Write-Host "=== AI Sales Agent Platform v0.1.4 - Smoke Test ===" -ForegroundColor Cyan

Add-Type -AssemblyName System.Net.Http
$script:HttpClient = New-Object System.Net.Http.HttpClient


function Invoke-Utf8JsonGet {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [Parameter(Mandatory = $false)]
        [hashtable]$Headers = @{}
    )

    $request = New-Object System.Net.Http.HttpRequestMessage -ArgumentList ([System.Net.Http.HttpMethod]::Get), $Uri
    $response = $null

    try {
        foreach ($key in $Headers.Keys) {
            [void]$request.Headers.TryAddWithoutValidation([string]$key, [string]$Headers[$key])
        }

        $response = $script:HttpClient.SendAsync($request).GetAwaiter().GetResult()
        $responseBytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        $responseText = [System.Text.Encoding]::UTF8.GetString($responseBytes)

        if (-not $response.IsSuccessStatusCode) {
            throw "HTTP $([int]$response.StatusCode) $($response.ReasonPhrase): $responseText"
        }

        if ([string]::IsNullOrWhiteSpace($responseText)) {
            return $null
        }

        return $responseText | ConvertFrom-Json
    }
    finally {
        if ($null -ne $response) { $response.Dispose() }
        if ($null -ne $request) { $request.Dispose() }
    }
}

function Invoke-Utf8JsonPost {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [Parameter(Mandatory = $true)]
        [hashtable]$Headers,

        [Parameter(Mandatory = $true)]
        [object]$Body
    )

    $json = $Body | ConvertTo-Json -Depth 10 -Compress
    $request = New-Object System.Net.Http.HttpRequestMessage -ArgumentList ([System.Net.Http.HttpMethod]::Post), $Uri
    $response = $null

    try {
        foreach ($key in $Headers.Keys) {
            [void]$request.Headers.TryAddWithoutValidation([string]$key, [string]$Headers[$key])
        }

        $request.Content = New-Object System.Net.Http.StringContent -ArgumentList $json, ([System.Text.Encoding]::UTF8), "application/json"
        $response = $script:HttpClient.SendAsync($request).GetAwaiter().GetResult()
        $responseText = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()

        if (-not $response.IsSuccessStatusCode) {
            throw "HTTP $([int]$response.StatusCode) $($response.ReasonPhrase): $responseText"
        }

        if ([string]::IsNullOrWhiteSpace($responseText)) {
            return $null
        }

        return $responseText | ConvertFrom-Json
    }
    finally {
        if ($null -ne $response) { $response.Dispose() }
        if ($null -ne $request) { $request.Dispose() }
    }
}

try {
    Write-Host "`n[1/7] Containers..." -ForegroundColor Yellow
    docker compose ps
    if ($LASTEXITCODE -ne 0) { throw "docker compose ps failed." }

    Write-Host "`n[2/7] Health..." -ForegroundColor Yellow
    $health = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health"
    $health | ConvertTo-Json
    if ($health.status -ne "ok" -or -not $health.postgres -or -not $health.redis) {
        throw "Health check is not OK."
    }

    Write-Host "`n[3/7] Login..." -ForegroundColor Yellow
    $loginBody = @{ username = "admin@example.com"; password = "ChangeMe123!" }
    $loginHeaders = @{ "X-Tenant-Slug" = "demo" }
    $tokenResponse = Invoke-RestMethod `
        -Method Post `
        -Uri "http://localhost:8000/api/v1/auth/login" `
        -Headers $loginHeaders `
        -ContentType "application/x-www-form-urlencoded" `
        -Body $loginBody

    $token = $tokenResponse.access_token
    if (-not $token) { throw "JWT token was not returned." }
    Write-Host "JWT obtained." -ForegroundColor Green

    $headers = @{ Authorization = "Bearer $token" }

    Write-Host "`n[4/7] Authenticated user / RBAC..." -ForegroundColor Yellow
    $currentUser = Invoke-RestMethod `
        -Method Get `
        -Uri "http://localhost:8000/api/v1/users/me" `
        -Headers $headers
    $currentUser | ConvertTo-Json

    $users = Invoke-RestMethod `
        -Method Get `
        -Uri "http://localhost:8000/api/v1/users" `
        -Headers $headers
    if ($null -eq $users) { throw "RBAC users endpoint did not return a response." }
    Write-Host "RBAC ADMIN/MANAGER endpoint validated." -ForegroundColor Green

    Write-Host "`n[5/7] Create customer..." -ForegroundColor Yellow
    $runId = Get-Date -Format "yyyyMMddHHmmssfff"
    $customerPayload = @{
        external_id = "smoke-$runId"
        name        = "Cliente Teste Árvore"
        email       = "cliente+$runId@example.com"
        phone       = "+5511999999999"
    }
    $customer = Invoke-Utf8JsonPost `
        -Uri "http://localhost:8000/api/v1/customers" `
        -Headers $headers `
        -Body $customerPayload
    $customer | ConvertTo-Json
    if (-not $customer.id) { throw "Customer ID was not returned." }

    Write-Host "`n[6/7] Create conversation..." -ForegroundColor Yellow
    $conversationPayload = @{
        customer_id = $customer.id
        channel     = "web"
    }
    $conversation = Invoke-Utf8JsonPost `
        -Uri "http://localhost:8000/api/v1/conversations" `
        -Headers $headers `
        -Body $conversationPayload
    $conversation | ConvertTo-Json
    if (-not $conversation.id) { throw "Conversation ID was not returned." }

    Write-Host "`n[7/7] Create and read UTF-8 message..." -ForegroundColor Yellow
    $messagePayload = @{
        role    = "user"
        content = "Olá, este é o teste UTF-8 da v0.1.4: ação, coração, informação."
    }
    $message = Invoke-Utf8JsonPost `
        -Uri "http://localhost:8000/api/v1/conversations/$($conversation.id)/messages" `
        -Headers $headers `
        -Body $messagePayload
    $message | ConvertTo-Json

    if (-not $message.id) { throw "Message ID was not returned." }
    if ($message.content -ne $messagePayload.content) {
        throw "UTF-8 round-trip failed. Expected '$($messagePayload.content)' but received '$($message.content)'."
    }

    $messages = Invoke-Utf8JsonGet `
        -Uri "http://localhost:8000/api/v1/conversations/$($conversation.id)/messages" `
        -Headers $headers

    if ($null -eq $messages) { throw "Message list endpoint did not return a response." }

    $storedMessage = @($messages) | Where-Object { $_.id -eq $message.id } | Select-Object -First 1
    if ($null -eq $storedMessage) { throw "Created message was not found in the message list." }
    if ($storedMessage.content -ne $messagePayload.content) {
        Write-Host "Expected: $($messagePayload.content)" -ForegroundColor DarkYellow
        Write-Host "Received: $($storedMessage.content)" -ForegroundColor DarkYellow
        throw "UTF-8 database round-trip failed."
    }

    Write-Host "UTF-8 JSON + database round-trip validated." -ForegroundColor Green
    Write-Host "`n=== v0.1.4 VALIDADA COM SUCESSO ===" -ForegroundColor Green
    Write-Host "Swagger: http://localhost:8000/docs"
}
finally {
    if ($null -ne $script:HttpClient) { $script:HttpClient.Dispose() }
}
