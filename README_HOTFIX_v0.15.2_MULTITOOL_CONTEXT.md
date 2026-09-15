# Hotfix v0.15.2 — Stateless Multi-tool Context Preservation

## Sintoma reproduzido em produção GCP

Na thread comercial Atlas-GCP, o Turno 2 executou corretamente:

1. `check_price` -> catálogo sem o produto, com fallback recomendado;
2. `search_knowledge` -> RAG encontrou `R$ 842,00`;
3. resposta final do modelo -> saudação genérica em vez do preço.

A auditoria confirmou `provider_response_count=3` e `tool_call_count=2`.

## Causa raiz

O `LLMService.run_tool_agent()` usava `store=False` na Responses API, mas a cada tool hop substituía `input_data` por apenas `turn.continuation_items` da resposta mais recente. Depois do segundo tool call, a pergunta original e os resultados anteriores já não estavam presentes no input da chamada final.

## Correção

O hotfix altera somente o orquestrador `app/services/llm_service.py`:

- mantém `store=False` e não introduz estado server-side na OpenAI;
- na primeira continuação, converte o texto original em mensagem `user`;
- acumula o transcript local completo;
- acrescenta `response.output` de cada turno;
- acrescenta cada `function_call_output`;
- preserva pergunta original + resultados de todas as tools até a resposta final.

Nenhuma alteração é feita em RAG, LangGraph, `check_price`, `search_knowledge`, banco, Redis ou tenant isolation.

## Arquivos

- `app/services/llm_service.py` — arquivo completo pronto para sobrescrita.
- `tests/test_multitool_context_contract.py` — regressão funcional para cadeia de duas tools.
- `scripts/validate_v0152_multitool_context.ps1` — validação local.

## Aplicação

Na raiz `C:\AI\ai-sales-agent-platform-v0.1`:

```powershell
Expand-Archive `
  -Path .\hotfix_v0.15.2_multitool_context_fix.zip `
  -DestinationPath . `
  -Force
```

Rebuild apenas da API local, sem tocar PostgreSQL/Redis/volumes:

```powershell
docker compose build api

docker compose up -d `
  --no-deps `
  --force-recreate `
  api
```

Não usar `docker compose down -v` nem `--remove-orphans`.

Validar:

```powershell
PowerShell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\validate_v0152_multitool_context.ps1
```

Após todos os testes locais passarem, repetir uma thread nova no GCP somente depois de rebuild/push/deploy controlado.

## Critério funcional final

Turno 1: Atlas-GCP -> 23 dias corridos.

Turno 2: `E quanto ele custa?` -> `check_price` -> `search_knowledge` -> resposta final contendo `R$ 842,00` como informação documental.
