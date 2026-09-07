$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"
Write-Host "=== AI Sales Agent Platform v0.6 - RAG / pgvector Upgrade ===" -ForegroundColor Cyan

if (-not (Test-Path ".env")) { throw ".env not found. Run from project root." }

$envText = Get-Content .env -Raw
$defaults = @{
  "EMBEDDING_PROVIDER" = "openai"
  "OPENAI_EMBEDDING_MODEL" = "text-embedding-3-small"
  "EMBEDDING_DIMENSIONS" = "1536"
  "EMBEDDING_BATCH_SIZE" = "64"
  "KNOWLEDGE_MAX_UPLOAD_MB" = "10"
  "KNOWLEDGE_CHUNK_CHARS" = "1200"
  "KNOWLEDGE_CHUNK_OVERLAP_CHARS" = "200"
  "RAG_TOP_K" = "5"
  "RAG_MIN_SIMILARITY" = "0.15"
}
foreach ($kv in $defaults.GetEnumerator()) {
  if ($envText -notmatch "(?m)^$([regex]::Escape($kv.Key))=") {
    Add-Content .env "`n$($kv.Key)=$($kv.Value)" -Encoding UTF8
  }
}

Write-Host "`n[1/5] Switching PostgreSQL 17 container to pgvector image (volume preserved)..." -ForegroundColor Yellow
docker compose pull postgres
if ($LASTEXITCODE -ne 0) { throw "Could not pull pgvector PostgreSQL image." }
docker compose up -d postgres redis
if ($LASTEXITCODE -ne 0) { throw "Could not start PostgreSQL/Redis." }

Write-Host "`n[2/5] Building API with RAG dependencies..." -ForegroundColor Yellow
docker compose build api
if ($LASTEXITCODE -ne 0) { throw "API build failed." }

Write-Host "`n[3/5] Starting API and applying 0004_knowledge_rag migration..." -ForegroundColor Yellow
docker compose up -d api
if ($LASTEXITCODE -ne 0) { throw "API start failed." }

Write-Host "`n[4/5] Waiting for API..." -ForegroundColor Yellow
$ok=$false
for($i=0;$i -lt 30;$i++) {
  Start-Sleep -Seconds 1
  try { $h=Invoke-RestMethod http://localhost:8000/api/v1/health -TimeoutSec 3; if($h.status -eq "ok"){$ok=$true;break} } catch {}
}
if(-not $ok){ docker compose logs --tail=120 api; throw "API did not become healthy." }

Write-Host "`n[5/5] pgvector + knowledge config..." -ForegroundColor Yellow
docker compose exec -T postgres psql -U aiagent -d aiagent -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
docker compose ps
docker compose logs --tail=80 api
Write-Host "`n=== v0.6 UPGRADE APPLIED ===" -ForegroundColor Green
Write-Host "Next: PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v06.ps1"
