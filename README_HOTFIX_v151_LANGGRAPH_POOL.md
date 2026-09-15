# Hotfix v0.15.1 — LangGraph PostgreSQL Pool Hardening

## Motivo

Durante a validação cloud real com Neon PostgreSQL:

1. `AsyncPostgresSaver.from_conn_string()` no runtime manteve uma conexão psycopg única.
2. Essa conexão foi encerrada pelo backend cloud e o primeiro acesso ao checkpoint retornou `psycopg.errors.AdminShutdown`.
3. Ao mover `LANGGRAPH_DATABASE_URL` para Neon POOLED, a conectividade foi restaurada.
4. Em seguida foi necessário executar `checkpointer.setup()` uma única vez para criar:
   - `checkpoint_blobs`
   - `checkpoint_migrations`
   - `checkpoint_writes`
   - `checkpoints`
5. Após o setup, message/state/history do LangGraph funcionaram e persistiram checkpoints.

## Alterações

### `app/agent/runtime.py`
Troca a conexão única do runtime por `psycopg_pool.AsyncConnectionPool`.

Configuração:
- `min_size=0`: não mantém conexão mínima ociosa.
- `max_size=5`: limita conexões do checkpointer.
- `open=False` + `await pool.open()`: lifecycle explícito.
- `check=AsyncConnectionPool.check_connection`: valida conexão ao retirá-la do pool.
- `max_idle=60`: reduz conexões ociosas em runtime serverless.
- `max_lifetime=900`: recicla conexões periodicamente.
- `autocommit=True`, `prepare_threshold=0`, `dict_row`: compatibilidade esperada pelo checkpointer PostgreSQL.

### `scripts/setup_langgraph.py`
Mantém o schema do LangGraph como passo controlado e idempotente de deploy.
Não deve rodar automaticamente em cada instância Cloud Run.

### `tests/test_langgraph_pool_contract.py`
Contrato para impedir regressão para conexão única no runtime e garantir a existência do setup explícito.

## Estratégia de conexão

- Alembic migrations: Neon DIRECT
- LangGraph setup one-off: Neon DIRECT
- SQLAlchemy runtime: Neon POOLED
- LangGraph runtime: Neon POOLED
- Redis runtime: Upstash `rediss://`

## Aplicação

Sobrescrever os arquivos preservando a estrutura do projeto.

Depois:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\normalize_eol.ps1

docker compose build api

docker compose run --rm api pytest -q tests/test_langgraph_pool_contract.py

docker compose run --rm api pytest -q
```

Não usar `docker compose down -v`.
Não usar `--remove-orphans`.
Não usar `git clean`.
Não usar `git add .`.

## Cloud

Antes de subir o serviço final:

1. `alembic upgrade head` com Neon DIRECT.
2. `python -m scripts.setup_langgraph` com `LANGGRAPH_DATABASE_URL` apontando para Neon DIRECT.
3. Bootstrap controlado apenas quando necessário.
4. Runtime com Neon POOLED para `DATABASE_URL` e `LANGGRAPH_DATABASE_URL`.
5. `RUN_MIGRATIONS=false`.
6. `RUN_BOOTSTRAP=false`.
