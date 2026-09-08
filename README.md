# AI Sales Agent Platform v0.14.1

Plataforma SaaS multi-tenant de agentes comerciais de IA, construída como projeto de portfólio orientado a produção.

> **v0.14:** adiciona CI/CD, quality gates e supply-chain security com GitHub Actions, Ruff, Bandit, pip-audit, Gitleaks, Trivy, CycloneDX SBOM, Dependabot e imagem Docker production non-root.

A v0.13.0 permanece como baseline funcional imediatamente anterior: resiliência, performance e load testing sobre a observabilidade/SRE da v0.12.

## Capacidades atuais

- FastAPI REST + WebSockets;
- JWT, RBAC e isolamento multi-tenant;
- PostgreSQL 17, Redis 8, Alembic e pgvector;
- OpenAI Responses, tools/function calling e auditoria;
- LangGraph com checkpoints PostgreSQL;
- Human-in-the-Loop persistente;
- RAG com embeddings OpenAI + pgvector/HNSW;
- configuração SaaS e catálogo por tenant;
- WhatsApp webhook lab com HMAC/idempotência;
- Voice AI com OpenAI Realtime;
- Twilio Media Streams LAB + caminho hardened de produção;
- STT com `gpt-transcribe`, PCMU 8 kHz, VAD e barge-in;
- Prometheus metrics;
- logs estruturados JSON;
- OpenTelemetry tracing;
- dashboards/alertas SRE opcionais com Prometheus, Grafana e Tempo;
- rate limiting distribuído em Redis;
- circuit breaker Redis com half-open probe;
- bulkhead para concorrência OpenAI;
- harness de carga seguro e reproduzível;
- GitHub Actions CI/CD com quality/security/integration gates;
- secret scanning Gitleaks e image scanning Trivy;
- dependency audit com pip-audit e Bandit;
- CycloneDX SBOM e BuildKit provenance;
- Dependabot/CODEOWNERS/SECURITY policy;
- imagem Docker production non-root.


## v0.14 — CI/CD, Quality Gates e Supply Chain Security

A v0.14 adiciona quatro gates no GitHub Actions: qualidade, segredos, segurança da imagem e integração Docker. Tags `v*` disparam delivery para GHCR após scan Trivy, com provenance e SBOM.

O Dockerfile passa a separar `development` e `production`; a imagem de produção roda como `USER app`, sem ferramentas de desenvolvimento/segurança, e `.dockerignore` impede que `.env` e `.git` entrem no contexto.

Validação local:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v14.ps1
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v14.ps1
```

Gates: Ruff, Bandit, 50 testes, coverage >= 25%, pip-audit, CycloneDX SBOM, Gitleaks e Trivy.

## v0.13 — Resiliência, Performance e Load Testing

A v0.13 protege a API contra picos e falhas externas sem remover os mecanismos de observabilidade da v0.12.

### Proteções

- rate limiting atômico em Redis por tenant JWT ou cliente sem JWT;
- HTTP 429 com `Retry-After` e headers `X-RateLimit-*`;
- circuit breaker distribuído em Redis para OpenAI;
- transição `closed -> open -> half-open probe -> closed/open`;
- bulkhead por processo para limitar concorrência LLM;
- fail-open configurável quando o Redis de resiliência fica indisponível;
- retry externo configurável, com 1 tentativa por padrão para não duplicar os retries do SDK OpenAI.

### Teste de carga seguro

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v13.ps1
```

O perfil padrão executa 200 requests com concorrência 20 em `/api/v1/users/me`, portanto não chama LLM real e não gera custo OpenAI. O relatório mostra throughput, error rate e latências min/avg/p50/p95/p99/max.

### Métricas de resiliência

```text
rate_limit_decisions_total
resilience_fail_open_total
bulkhead_rejections_total
bulkhead_in_flight
circuit_breaker_events_total
circuit_breaker_open
resilience_retries_total
```

## v0.12 — Observabilidade/SRE

### Métricas

Endpoint:

```text
http://localhost:8000/metrics
```

A instrumentação cobre HTTP, tenants, LLM/tokens/custo, AgentRun, tools, RAG, Voice/STT/Realtime, Twilio e métricas do processo Python.

IDs únicos (`request_id`, `conversation_id`, `call_sid`, `trace_id`) ficam em logs/traces, não como labels Prometheus. Isso preserva correlação sem criar cardinalidade excessiva.

### Logs

Cada request recebe ou preserva `X-Request-ID` e retorna também `X-Trace-ID`. Logs de aplicação usam JSON e incluem o contexto disponível do tenant/conversa/chamada.

### Tracing

OpenTelemetry instrumenta spans HTTP e integra SQLAlchemy, Redis e HTTPX, além de spans manuais em tools, RAG e Voice. O OTLP exporter é opcional; sem Tempo configurado a API continua operacional.

### Golden Signals

- Latency;
- Traffic;
- Errors;
- Saturation.

### Health

```text
/api/v1/health/live
/api/v1/health/ready
```

Readiness verifica PostgreSQL e Redis.

## Instalação da v0.12

Partindo da branch validada v0.11.1:

```powershell
cd C:\AI\ai-sales-agent-platform-v0.1
git switch feature/v0.11-production-telephony
git pull
git switch -c feature/v0.12-observability-sre
```

Extraia o upgrade e execute:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v12.ps1
```

Alvo esperado:

```text
35 passed
=== v0.12 UPGRADE APPLIED ===
```

Depois execute:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v12.ps1
```

## Stack visual opcional

Depois da validação da API:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\start_observability_v12.ps1
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_observability_stack_v12.ps1
```

URLs:

```text
Prometheus  http://localhost:9090
Grafana     http://localhost:3000
Tempo       http://localhost:3200
```

O dashboard `AI Sales Agent Platform - SRE / Golden Signals` é provisionado automaticamente.

## Limitações explícitas

- PSTN/número Twilio real ainda não conectado;
- Meta WhatsApp Cloud real ainda não conectado;
- Voice production permanece `first_turn_only=true` por padrão;
- Grafana `admin/admin` é somente laboratório local;
- `audioop` ainda existe no código de áudio Python 3.12 e deve ser substituído antes de Python 3.13.

## Documentação

- `V0.14.md` — CI/CD, gates e supply chain;
- `UPGRADE_v0.14.0.md` — aplicação da v0.14;
- `VALIDACAO_v0.14_PTBR.md` — critérios e ruleset recomendado;
- `V0.13.md` — resiliência, performance e load testing;
- `UPGRADE_v0.13.0.md` — aplicação da v0.13;
- `VALIDACAO_v0.13_PTBR.md` — critérios da v0.13;
- `V0.12.md` — arquitetura e escopo;
- `UPGRADE_v0.12.0.md` — aplicação;
- `VALIDACAO_v0.12_PTBR.md` — critérios de teste;
- `V0.11.md` — telefonia hardened;
- `HOTFIX_v0.11.1_PTBR.md` — correção do smoke de áudio.


## v0.14.1 — Hotfix CI package discovery

Corrige o empacotamento no GitHub Actions com descoberta explícita `app*` no `setuptools`. A tag `v0.14.0` permanece imutável; `v0.14.1` deve ser publicada somente após o CI remoto ficar verde.
