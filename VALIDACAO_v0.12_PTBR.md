# Validação da v0.12 — Observabilidade / SRE

## Fase A — Upgrade/regressão

Comando:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v12.ps1
```

Critérios:

- API inicia;
- PostgreSQL ready;
- Redis ready;
- `/metrics` disponível;
- log `http_request_completed` em JSON;
- suíte completa com 34 testes aprovados.

## Fase B — Smoke da API observável

Comando:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v12.ps1
```

Critérios:

- `X-Request-ID` preservado;
- `X-Trace-ID` válido com 32 hex;
- liveness/readiness OK;
- endpoint autenticado `/observability/config` OK;
- métricas essenciais presentes;
- métrica por Demo tenant observada;
- métricas não contêm os segredos conhecidos testados.

## Fase C — Stack visual opcional

Iniciar:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\start_observability_v12.ps1
```

Validar:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_observability_stack_v12.ps1
```

Critérios:

- Prometheus encontra `up{job="ai-sales-agent-api"} = 1`;
- Grafana health `database=ok`;
- Tempo `/ready` = HTTP 200;
- Tempo encontra trace com `resource.service.name="ai-sales-agent-platform"`;
- dashboard SRE provisionado.

## Endpoints

```text
API         http://localhost:8000
Swagger     http://localhost:8000/docs
Metrics     http://localhost:8000/metrics
Liveness    http://localhost:8000/api/v1/health/live
Readiness   http://localhost:8000/api/v1/health/ready
Prometheus  http://localhost:9090
Grafana     http://localhost:3000
Tempo       http://localhost:3200
```

## Observação

O stack Prometheus/Grafana/Tempo é laboratório local. Login `admin/admin` do Grafana não deve ser reutilizado em produção.
