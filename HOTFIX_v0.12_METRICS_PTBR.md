# Hotfix v0.12 — endpoint Prometheus sem redirect

## Sintoma

O smoke test da v0.12 falhava em `GET /metrics` com `307 Temporary Redirect` para `/metrics/`.

## Causa

O Prometheus ASGI app estava montado com `app.mount("/metrics", ...)`. O Starlette trata mounts como subaplicações e canonicaliza a raiz do mount com barra final, causando redirect de `/metrics` para `/metrics/`.

## Correção

O endpoint passa a ser uma rota FastAPI exata:

- `GET /metrics` -> `200 OK`
- corpo no formato Prometheus via `generate_latest()`
- Content-Type oficial via `CONTENT_TYPE_LATEST`
- sem redirect 307

Foi adicionado teste de contrato para impedir regressão para `app.mount("/metrics", ...)`.

## Banco/volumes

- Sem migration
- Sem alteração de PostgreSQL
- Sem alteração de Redis
- Sem alteração de `.env`
- Não executar `docker compose down -v`

## Validação

Após sobrescrever os arquivos, execute:

```powershell
docker compose restart api
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v12.ps1
```

O esperado é finalizar com:

```text
=== v0.12 OBSERVABILITY/SRE VALIDADA COM SUCESSO ===
```
