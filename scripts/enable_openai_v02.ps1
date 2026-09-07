param(
    [string]$Model = "gpt-5.6-terra"
)
$ErrorActionPreference = "Stop"

function Set-EnvValue([string]$Key, [string]$Value) {
    $lines = Get-Content .env
    $found = $false
    $newLines = foreach ($line in $lines) {
        if ($line -match "^$([regex]::Escape($Key))=") {
            $found = $true
            "$Key=$Value"
        } else { $line }
    }
    if (-not $found) { $newLines += "$Key=$Value" }
    [System.IO.File]::WriteAllLines((Resolve-Path .env), $newLines, (New-Object System.Text.UTF8Encoding($false)))
}

if (-not (Test-Path .env)) {
    throw ".env não encontrado. Execute primeiro scripts\upgrade_v02.ps1."
}

Write-Host "A chave não será passada na linha de comando nem exibida." -ForegroundColor Yellow
$secureKey = Read-Host "Cole sua OPENAI_API_KEY" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}

if ([string]::IsNullOrWhiteSpace($apiKey)) {
    throw "OPENAI_API_KEY vazia."
}

Set-EnvValue "LLM_PROVIDER" "openai"
Set-EnvValue "OPENAI_API_KEY" $apiKey
Set-EnvValue "OPENAI_MODEL" $Model
$apiKey = $null

Write-Host "OpenAI habilitada no .env para $Model." -ForegroundColor Green
Write-Host "Recriando somente a API para recarregar o ambiente..." -ForegroundColor Yellow
docker compose up -d --force-recreate api
Write-Host "Execute novamente .\scripts\test_v02.ps1 para validar a chamada real." -ForegroundColor Cyan
Write-Host "Nota: .env é adequado para desenvolvimento local; em produção usaremos um secret manager." -ForegroundColor DarkGray
