# AI Sales Agent Platform v0.12.0

Plataforma SaaS multi-tenant de agentes comerciais de IA, construída como projeto de portfólio orientado a produção.

> **v0.12:** adiciona Observabilidade/SRE com logs JSON correlacionados, Prometheus, OpenTelemetry, Golden Signals, health separado em liveness/readiness e stack local opcional Prometheus + Grafana + Tempo.

A v0.11.1 permanece como baseline funcional imediatamente anterior: telefonia hardened com `X-Twilio-Signature`, callbacks de chamada/stream, PCMU → VAD → `gpt-transcribe` → LangGraph/tools → OpenAI Realtime, mantendo `PSTN connected=false` até existir conexão Twilio real.

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
- dashboards/alertas SRE opcionais com Prometheus, Grafana e Tempo.

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
34 passed
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

- `V0.12.md` — arquitetura e escopo;
- `UPGRADE_v0.12.0.md` — aplicação;
- `VALIDACAO_v0.12_PTBR.md` — critérios de teste;
- `V0.11.md` — telefonia hardened;
- `HOTFIX_v0.11.1_PTBR.md` — correção do smoke de áudio.
