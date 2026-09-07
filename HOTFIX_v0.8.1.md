# Hotfix v0.8.1

Corrige falso negativo do smoke test WhatsApp.

## Causa

`GET /api/v1/users/me` nao expoe `tenant_id`; portanto `$me.tenant_id` era nulo e o assert de conta WhatsApp falhava apesar do backend retornar o tenant correto.

## Correcao

- obtem `tenant_id` via `GET /api/v1/tenant/config`;
- normaliza comparacoes como string;
- adiciona diagnostico no assert;
- corrige o resumo final do teste.

Nao ha alteracao de backend, migration, banco, Docker ou `.env`.
