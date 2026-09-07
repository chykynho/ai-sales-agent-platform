$ErrorActionPreference="Stop"
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
Add-Type -AssemblyName System.Net.Http
$Base="http://localhost:8000/api/v1"
function Login([string]$Slug,[string]$Email,[string]$Password){
  $headers=@{"X-Tenant-Slug"=$Slug}; $e=[uri]::EscapeDataString($Email); $p=[uri]::EscapeDataString($Password)
  return (Invoke-RestMethod -Method Post -Uri "$Base/auth/login" -Headers $headers -ContentType "application/x-www-form-urlencoded" -Body "username=$e&password=$p").access_token
}
function JsonCall([string]$Method,[string]$Uri,[object]$Body,[string]$Token){
  $c=[System.Net.Http.HttpClient]::new(); try {
    if($Token){$c.DefaultRequestHeaders.Authorization=[System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer",$Token)}
    $httpMethod=[System.Net.Http.HttpMethod]::new($Method.ToUpperInvariant()); $req=[System.Net.Http.HttpRequestMessage]::new($httpMethod,$Uri)
    if($null -ne $Body){$json=$Body|ConvertTo-Json -Depth 20 -Compress; $req.Content=[System.Net.Http.StringContent]::new($json,[Text.Encoding]::UTF8,"application/json")}
    $r=$c.SendAsync($req).GetAwaiter().GetResult(); $txt=$r.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    if(-not $r.IsSuccessStatusCode){throw "HTTP $([int]$r.StatusCode): $txt"}; if(-not $txt){return $null}; return $txt|ConvertFrom-Json
  } finally {$c.Dispose()}
}
function AuthGet([string]$Uri,[string]$Token){return JsonCall "Get" $Uri $null $Token}
Write-Host "=== AI Sales Agent Platform v0.7.1 - Multi-Tenant SaaS Smoke Test ===" -ForegroundColor Cyan

Write-Host "`n[1/9] Health and provision second tenant with same application..." -ForegroundColor Yellow
$health=Invoke-RestMethod "$Base/health"; if($health.status -ne "ok"){throw "health failed"}
docker compose exec -T api python -m scripts.provision_tenant --slug smoke-acme --name "Acme Treinamentos" --admin-email admin@smoke-acme.local --admin-password "ChangeMe123!" --company-name "Acme Treinamentos" --assistant-name "Ayla" --tone "consultative" --enabled-tools "check_price,check_availability,create_lead" --rag-top-k 2 --rag-min-similarity 0.35 --price-starter 697.00 --price-pro 1497.00 --price-enterprise 3497.00
if($LASTEXITCODE -ne 0){throw "tenant provisioning failed"}

Write-Host "`n[2/9] Login into two tenants and compare runtime profiles..." -ForegroundColor Yellow
$demoToken=Login "demo" "admin@example.com" "ChangeMe123!"; $acmeToken=Login "smoke-acme" "admin@smoke-acme.local" "ChangeMe123!"
if(-not $demoToken -or -not $acmeToken){throw "tenant login failed"}
$demoCfg=AuthGet "$Base/tenant/config" $demoToken; $acmeCfg=AuthGet "$Base/tenant/config" $acmeToken
$demoCfg|ConvertTo-Json -Depth 10; $acmeCfg|ConvertTo-Json -Depth 10
if($demoCfg.tenant_id -eq $acmeCfg.tenant_id){throw "tenant IDs must differ"}
if($acmeCfg.assistant_name -ne "Ayla"){throw "tenant assistant config missing"}

Write-Host "`n[3/9] Tenant-scoped product catalog: same PRO code, different prices..." -ForegroundColor Yellow
$demoProducts=AuthGet "$Base/tenant/products" $demoToken; $acmeProducts=AuthGet "$Base/tenant/products" $acmeToken
$demoPro=@($demoProducts|Where-Object {$_.code -eq "PRO"})[0]; $acmePro=@($acmeProducts|Where-Object {$_.code -eq "PRO"})[0]
Write-Host "Demo PRO : $($demoPro.price)"; Write-Host "Acme PRO : $($acmePro.price)"
if([decimal]$demoPro.price -ne 997){throw "demo PRO price regression"}; if([decimal]$acmePro.price -ne 1497){throw "Acme PRO price mismatch"}

Write-Host "`n[4/9] Tenant tool policy changes model-visible tool catalog..." -ForegroundColor Yellow
$demoTools=AuthGet "$Base/ai/tools" $demoToken; $acmeTools=AuthGet "$Base/ai/tools" $acmeToken
$demoTools|ConvertTo-Json -Depth 10; $acmeTools|ConvertTo-Json -Depth 10
if(@($demoTools|Where-Object {$_.name -eq "search_knowledge"}).Count -ne 1){throw "demo should have search_knowledge"}
if(@($acmeTools|Where-Object {$_.name -eq "search_knowledge"}).Count -ne 0){throw "Acme must not expose disabled search_knowledge"}
if(@($acmeTools).Count -ne 3){throw "Acme tool count must be 3"}

Write-Host "`n[5/9] Same tool-agent code resolves price from each tenant catalog..." -ForegroundColor Yellow
$demoPrice=JsonCall "Post" "$Base/ai/tool-agent" @{message="Use a ferramenta check_price para consultar o preco do produto PRO antes de responder."} $demoToken
$acmePrice=JsonCall "Post" "$Base/ai/tool-agent" @{message="Use a ferramenta check_price para consultar o preco do produto PRO antes de responder."} $acmeToken
$demoPrice|ConvertTo-Json -Depth 10; $acmePrice|ConvertTo-Json -Depth 10
if($demoPrice.output -notmatch "997"){throw "demo agent did not return tenant price"}
if($acmePrice.output -notmatch "1[\.,]?497|1497"){throw "Acme agent did not return tenant price"}

Write-Host "`n[6/9] Update tenant configuration without deploy/restart..." -ForegroundColor Yellow
$before=[int]$acmeCfg.config_version
$acmeUpdated=JsonCall "Patch" "$Base/tenant/config" @{assistant_name="Ayla Sales";tone="direct";rag_top_k=3;rag_min_similarity=0.4;enabled_tools=@("check_price","create_lead")} $acmeToken
$acmeUpdated|ConvertTo-Json -Depth 10
if([int]$acmeUpdated.config_version -le $before){throw "config_version did not increase"}
$acmeTools2=AuthGet "$Base/ai/tools" $acmeToken; if(@($acmeTools2).Count -ne 2){throw "runtime did not reload tool policy"}

Write-Host "`n[7/9] Update Acme PRO price through tenant API; Demo remains unchanged..." -ForegroundColor Yellow
$updatedPro=JsonCall "Put" "$Base/tenant/products/PRO" @{name="Plano PRO";description="Preco configuravel do tenant";currency="BRL";price=1597.00;is_active=$true} $acmeToken
$updatedPro|ConvertTo-Json -Depth 10
$demoProAfter=@((AuthGet "$Base/tenant/products" $demoToken)|Where-Object {$_.code -eq "PRO"})[0]
$acmeProAfter=@((AuthGet "$Base/tenant/products" $acmeToken)|Where-Object {$_.code -eq "PRO"})[0]
if([decimal]$acmeProAfter.price -ne 1597){throw "Acme catalog update failed"}; if([decimal]$demoProAfter.price -ne 997){throw "cross-tenant catalog leak detected"}

Write-Host "`n[8/9] Tenant-specific RAG runtime settings..." -ForegroundColor Yellow
$demoRag=AuthGet "$Base/knowledge/config" $demoToken; $acmeRag=AuthGet "$Base/knowledge/config" $acmeToken
$demoRag|ConvertTo-Json -Depth 10; $acmeRag|ConvertTo-Json -Depth 10
if([int]$acmeRag.rag_top_k -ne 3){throw "Acme RAG top_k not applied"}; if([double]$acmeRag.rag_min_similarity -lt 0.399){throw "Acme RAG similarity not applied"}

Write-Host "`n[9/9] Single deployment / final inventory..." -ForegroundColor Yellow
docker compose ps
$aiDemo=AuthGet "$Base/ai/config" $demoToken; $aiAcme=AuthGet "$Base/ai/config" $acmeToken
$aiDemo|ConvertTo-Json -Depth 10; $aiAcme|ConvertTo-Json -Depth 10
if($aiAcme.company_name -ne "Acme Treinamentos"){throw "tenant identity missing from runtime"}
Write-Host "`n=== v0.7.1 VALIDADA COM SUCESSO ===" -ForegroundColor Green
Write-Host "Demo tenant       : $($demoCfg.tenant_id)"
Write-Host "Acme tenant       : $($acmeCfg.tenant_id)"
Write-Host "Demo PRO          : R$ $($demoProAfter.price)"
Write-Host "Acme PRO          : R$ $($acmeProAfter.price)"
Write-Host "Acme assistant    : $($acmeUpdated.assistant_name)"
Write-Host "Acme config ver   : $($acmeUpdated.config_version)"
Write-Host "Acme enabled tools: $((@($acmeTools2|ForEach-Object {$_.name})) -join ', ')"
Write-Host "Swagger           : http://localhost:8000/docs"
