$ErrorActionPreference="Stop"
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
Add-Type -AssemblyName System.Net.Http
$Base="http://localhost:8000/api/v1"
function JsonPost([string]$Uri,[object]$Body,[string]$Token){
  $c=[System.Net.Http.HttpClient]::new(); try {
    if($Token){$c.DefaultRequestHeaders.Authorization=[System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer",$Token)}
    $json=$Body|ConvertTo-Json -Depth 20 -Compress
    $content=[System.Net.Http.StringContent]::new($json,[Text.Encoding]::UTF8,"application/json")
    $r=$c.PostAsync($Uri,$content).GetAwaiter().GetResult(); $txt=$r.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    if(-not $r.IsSuccessStatusCode){throw "HTTP $([int]$r.StatusCode): $txt"}; return $txt|ConvertFrom-Json
  } finally {$c.Dispose()}
}
function Upload([string]$Path,[string]$FileName,[string]$Token){
  $c=[System.Net.Http.HttpClient]::new(); try {
    $c.DefaultRequestHeaders.Authorization=[System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer",$Token)
    $m=[System.Net.Http.MultipartFormDataContent]::new(); $bytes=[IO.File]::ReadAllBytes($Path); $bc=[System.Net.Http.ByteArrayContent]::new($bytes)
    $bc.Headers.ContentType=[System.Net.Http.Headers.MediaTypeHeaderValue]::new("text/markdown"); $m.Add($bc,"file",$FileName)
    $r=$c.PostAsync("$Base/knowledge/documents",$m).GetAwaiter().GetResult(); $txt=$r.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    if(-not $r.IsSuccessStatusCode){throw "HTTP $([int]$r.StatusCode): $txt"}; return $txt|ConvertFrom-Json
  } finally {$c.Dispose()}
}
Write-Host "=== AI Sales Agent Platform v0.6 - RAG Smoke Test ===" -ForegroundColor Cyan
Write-Host "`n[1/7] Health, login and RAG config..." -ForegroundColor Yellow
$health=Invoke-RestMethod "$Base/health"; if($health.status -ne "ok"){throw "health failed"}
$headers=@{"X-Tenant-Slug"="demo"}; $form="username=admin%40example.com&password=ChangeMe123%21"
$login=Invoke-RestMethod -Method Post -Uri "$Base/auth/login" -Headers $headers -ContentType "application/x-www-form-urlencoded" -Body $form
$token=$login.access_token; if(-not $token){throw "login failed"}
$auth=@{Authorization="Bearer $token"}; $cfg=Invoke-RestMethod "$Base/knowledge/config" -Headers $auth; $cfg|ConvertTo-Json -Depth 10
if($cfg.vector_backend -notmatch "pgvector"){throw "pgvector config missing"}

Write-Host "`n[2/7] Ingest document and create embeddings..." -ForegroundColor Yellow
$fixture=Join-Path $PSScriptRoot "..\fixtures\knowledge\demo_knowledge.md"
$ingest=Upload $fixture "demo_knowledge.md" $token; $ingest|ConvertTo-Json -Depth 10
if($ingest.document.chunk_count -lt 1){throw "no chunks created"}
if($ingest.document.status -ne "active"){throw "document not active"}

Write-Host "`n[3/7] Deduplicate exact same file..." -ForegroundColor Yellow
$dupe=Upload $fixture "demo_knowledge.md" $token; $dupe|ConvertTo-Json -Depth 10
if(-not $dupe.deduplicated){throw "exact duplicate was not deduplicated"}
if($dupe.document.id -ne $ingest.document.id){throw "dedup returned a different document"}

Write-Host "`n[4/7] Semantic vector search..." -ForegroundColor Yellow
$search=JsonPost "$Base/knowledge/search" @{query="Qual é o prazo para colocar o Enterprise em funcionamento?";top_k=3} $token; $search|ConvertTo-Json -Depth 12
$sources=@($search.sources); if($sources.Count -lt 1){throw "RAG search returned no sources"}
if($sources[0].filename -ne "demo_knowledge.md"){throw "unexpected top source"}

Write-Host "`n[5/7] Grounded RAG answer + citations..." -ForegroundColor Yellow
$query=JsonPost "$Base/knowledge/query" @{query="Qual é o prazo de implantação do Plano Enterprise?";top_k=3} $token; $query|ConvertTo-Json -Depth 12
if(-not $query.answer){throw "empty RAG answer"}; if(@($query.sources).Count -lt 1){throw "RAG answer has no sources"}
if($query.answer -notmatch "5" -or $query.answer -notmatch "S1"){throw "answer did not preserve grounded fact/citation"}

Write-Host "`n[6/7] Version same filename with changed content..." -ForegroundColor Yellow
$tmpDir=Join-Path $env:TEMP "ai-sales-v06"; New-Item -ItemType Directory -Force -Path $tmpDir|Out-Null; $tmp=Join-Path $tmpDir "demo_knowledge_v2.md"
$v2=(Get-Content $fixture -Raw)+"`n`n## SLA adicional`nNa versão 2, o onboarding técnico inclui uma revisão de arquitetura antes da ativação.`n"
[IO.File]::WriteAllText($tmp,$v2,[Text.UTF8Encoding]::new($false))
$ingest2=Upload $tmp "demo_knowledge.md" $token; $ingest2|ConvertTo-Json -Depth 10
if($ingest2.document.version -ne 2){throw "expected document version 2"}
$docs=Invoke-RestMethod "$Base/knowledge/documents" -Headers $auth; $same=@($docs|Where-Object {$_.filename -eq "demo_knowledge.md"})
if(@($same|Where-Object {$_.status -eq "active"}).Count -ne 1){throw "expected exactly one active version"}
if(@($same|Where-Object {$_.status -eq "superseded"}).Count -lt 1){throw "previous version was not superseded"}

Write-Host "`n[7/7] PostgreSQL vector extension and document inventory..." -ForegroundColor Yellow
docker compose exec -T postgres psql -U aiagent -d aiagent -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
$docs|ConvertTo-Json -Depth 10
Write-Host "`n=== v0.6 VALIDADA COM SUCESSO ===" -ForegroundColor Green
Write-Host "Embedding model : $($cfg.embedding_model)"
Write-Host "Document v1    : $($ingest.document.id)"
Write-Host "Document v2    : $($ingest2.document.id)"
Write-Host "Top similarity : $($sources[0].similarity)"
Write-Host "RAG run         : $($query.run_id)"
Write-Host "Swagger         : http://localhost:8000/docs"
