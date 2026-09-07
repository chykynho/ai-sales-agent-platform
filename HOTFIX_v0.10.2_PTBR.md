# Hotfix v0.10.2 — atualização do contrato de testes das tools

## Problema
O checkpoint consolidado encontrou 5 tools registradas, mas `tests/test_tools.py` ainda esperava exatamente 4.

## Causa
A tool `search_knowledge` foi adicionada na evolução do RAG e passou a fazer parte do registry oficial. O teste antigo não foi atualizado.

## Correção
O teste agora valida explicitamente o conjunto esperado:

- `check_price`
- `get_customer_by_email`
- `check_availability`
- `search_knowledge`
- `create_lead`

Além disso, a validação continua verificando `strict=True`, `additionalProperties=False` e todos os campos obrigatórios do JSON Schema.

## Aplicação
Sobrescreva `tests/test_tools.py` no projeto e rode novamente o checkpoint.

Não é necessário rebuild: o serviço `api` monta `.:/app` no Docker Compose.
