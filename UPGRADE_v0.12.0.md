# Upgrade v0.11.1 → v0.12.0

## Pré-requisito

Executar sobre a branch/commit validado da v0.11.1. Não partir da `main` v0.10.5, pois a v0.12 inclui e preserva o hardening de telefonia da v0.11.1.

## Branch recomendada

```powershell
cd C:\AI\ai-sales-agent-platform-v0.1
git status
git switch feature/v0.11-production-telephony
git pull
git switch -c feature/v0.12-observability-sre
```

## Aplicação

Extraia o ZIP de upgrade sobre:

```text
C:\AI\ai-sales-agent-platform-v0.1
```

Aceite sobrescrever os arquivos existentes.

Não apague `.env`, PostgreSQL, Redis ou volumes.

Não execute `docker compose down -v`.

Depois execute somente:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v12.ps1
```

O script:

1. adiciona apenas as variáveis de observabilidade ausentes ao `.env`;
2. rebuilda a API com Prometheus/OpenTelemetry;
3. recria somente a API;
4. valida readiness PostgreSQL/Redis;
5. executa a suíte completa `pytest -q tests`;
6. valida `/metrics` e logs estruturados JSON.

## Resultado esperado

```text
34 passed
=== v0.12 UPGRADE APPLIED ===
```

Após o upgrade ser aprovado, execute separadamente:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v12.ps1
```

Somente depois do smoke da API, o stack visual opcional pode ser iniciado:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\start_observability_v12.ps1
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_observability_stack_v12.ps1
```

Para parar apenas Prometheus/Grafana/Tempo e voltar a API ao compose base:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\stop_observability_v12.ps1
```

Nenhum desses scripts remove volumes.
