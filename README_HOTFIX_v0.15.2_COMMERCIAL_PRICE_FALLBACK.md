# Hotfix v0.15.2 — Commercial Price Fallback

## Problema observado em teste real no GCP

Fluxo:
1. Cliente perguntou o prazo do Atlas-GCP.
2. O agente recuperou corretamente `23 dias corridos`.
3. Em seguida o cliente perguntou: `E quanto ele custa?`
4. O agente manteve contexto e classificou a intenção como `pricing`, lead `hot`.
5. O agente chamou `check_price`.
6. `check_price` pesquisou apenas `tenant_products`, não encontrou `Atlas-GCP` e retornou `found=false`.
7. O agente encerrou a resposta sem consultar `search_knowledge`, embora o RAG contivesse R$ 842,00.

## Decisão arquitetural

O catálogo estruturado continua sendo a fonte oficial para preço.

- `check_price` é sempre a primeira consulta.
- Se encontrar: `source=catalog`, `authoritative_price=true`.
- Se não encontrar: retorna instrução explícita de fallback para `search_knowledge`.
- O agente deve fazer uma segunda tool call para `search_knowledge`.
- Preço vindo apenas do RAG é tratado como informação documental, não como preço oficial de catálogo.
- `check_price` NÃO chama `KnowledgeService` internamente. Isso preserva separação de responsabilidades e auditabilidade.

## Arquivos

- `app/tools/builtin.py`
- `app/tools/registry.py`
- `app/services/llm_service.py`
- `app/services/tenant_config_service.py`
- `tests/test_commercial_price_fallback_contract.py`

## Aplicação

A partir da raiz do projeto, faça backup/commit do estado local antes de sobrescrever.
Extraia o ZIP preservando a estrutura de diretórios.

Não use `git clean`, `git add .`, `docker compose down -v` ou `--remove-orphans`.

## Testes

```powershell
python -m pytest tests/test_commercial_price_fallback_contract.py -q
python -m pytest -q
python -m ruff check .
```

## Teste funcional esperado

Thread NOVA:

Turno 1:
`Olá. Meu nome é Carlos e estou avaliando o produto Atlas-GCP. Qual é o prazo de entrega?`

Turno 2:
`E quanto ele custa?`

Esperado no Turno 2:
- `intent=pricing`
- contexto resolve `ele -> Atlas-GCP`
- primeira tool: `check_price`
- resultado `found=false`, `fallback_recommended=true`
- segunda tool: `search_knowledge`
- resposta recupera `R$ 842,00`
- resposta deixa claro que a origem é documental/RAG
- nenhuma alucinação de preço

## Observação de versão

Este pacote é candidato a v0.15.2. Não tagueie/publishe antes de:
1. testes unitários/contrato;
2. suíte completa;
3. Ruff;
4. build production;
5. teste local/cloud-real;
6. teste no Cloud Run em nova revisão.
