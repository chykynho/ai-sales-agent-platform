# Upgrade v0.13.0 — Resiliência, Performance e Load Testing

Base exigida: **v0.12.0 validada**.

## Escopo

- rate limiting distribuído em Redis;
- circuit breaker distribuído em Redis;
- half-open probe após cooldown;
- bulkhead/concurrency limit para chamadas OpenAI;
- retries externos configuráveis sem duplicar retries do SDK por padrão;
- métricas Prometheus de resiliência;
- alertas Grafana/Prometheus para circuit breaker, rate limiting e bulkhead;
- harness de carga seguro com p50/p95/p99, throughput e error rate.

## Branch

```powershell
cd C:\AI\ai-sales-agent-platform-v0.1
git switch main
git pull
git switch -c feature/v0.13-resilience-performance
```

## Aplicação

Extraia o ZIP de upgrade sobre a raiz do projeto e execute:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v13.ps1
```

Não use `docker compose down -v`.

## Validação

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v13.ps1
```

O teste de carga seguro usa `/api/v1/users/me`, sem chamar LLM real e sem gerar custo OpenAI.
