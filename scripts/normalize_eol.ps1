param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$isWindows = $env:OS -eq "Windows_NT"

Write-Host "=== EOL NORMALIZER ===" -ForegroundColor Cyan
Write-Host ("OS detectado: {0}" -f ($(if ($isWindows) { "Windows" } else { "Nao-Windows" })))
Write-Host ("Repositorio: {0}" -f $repoRoot)

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$failed = $false

$files = Get-ChildItem -Path $repoRoot -Recurse -File -Filter *.sh |
    Where-Object { $_.FullName -notmatch '[\\/](\.git|\.venv|venv|artifacts|build|dist)[\\/]' }

foreach ($file in $files) {
    $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    $hasCrlf = $text.Contains("`r`n")
    $relative = $file.FullName.Substring($repoRoot.Length).TrimStart('\','/')

    if ($hasCrlf) {
        if ($CheckOnly) {
            Write-Host "[ERRO] $relative usa CRLF" -ForegroundColor Red
            $failed = $true
        }
        else {
            $normalized = $text.Replace("`r`n", "`n")
            [System.IO.File]::WriteAllText($file.FullName, $normalized, $utf8NoBom)
            Write-Host "[FIX]  $relative -> LF" -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "[OK]   $relative -> LF" -ForegroundColor Green
    }
}

if ($CheckOnly -and $failed) {
    throw "Foram encontrados scripts .sh com CRLF. Execute novamente sem -CheckOnly para corrigir."
}

if (-not $CheckOnly) {
    Write-Host "Normalizacao concluida." -ForegroundColor Green
}
