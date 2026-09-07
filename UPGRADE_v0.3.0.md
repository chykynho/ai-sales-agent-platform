# Upgrade v0.2.1 -> v0.3.0

## O que entra
- Responses API function/tool calling
- tool registry com schemas strict
- `tool_calls` para auditoria
- `leads` para a primeira ação de escrita
- Idempotency-Key com detecção de conflito de payload
- métricas `provider_response_count` e `tool_call_count` em `agent_runs`

## Aplicação
1. Extraia este pacote sobre `C:\AI\ai-sales-agent-platform-v0.1` e aceite sobrescrever.
2. Preserve o `.env` atual (sua OpenAI API key permanece local).
3. Execute `PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v03.ps1`.
4. Execute `PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v03.ps1`.

Não use `docker compose down -v`.
