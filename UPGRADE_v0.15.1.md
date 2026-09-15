# Upgrade v0.15.1 - Cloud Connectivity

## Objetivo

Preparar a mesma imagem da plataforma para execucao serverless/multi-cloud sem quebrar o ambiente Docker local.

## Alteracoes

- mantem o hardening de EOL para Windows/Linux;
- adiciona suporte a `DATABASE_URL` externa;
- normaliza automaticamente URL Neon/libpq para SQLAlchemy + asyncpg;
- remove `channel_binding` apenas da URL asyncpg e traduz `sslmode=require` para `ssl=require`;
- adiciona `LANGGRAPH_DATABASE_URL` opcional para psycopg/LangGraph;
- preserva `REDIS_URL` e suporta `rediss://` do Upstash;
- imagem `production` passa a escutar `${PORT:-8000}`, compativel com Cloud Run;
- mantem `RUN_MIGRATIONS=false` e `RUN_BOOTSTRAP=false` por padrao em producao;
- Compose local continua usando PostgreSQL/Redis locais e migrations/bootstrap habilitados.

## Estrategia GCP planejada

Runtime Cloud Run:

- `DATABASE_URL` = Neon POOLED
- `LANGGRAPH_DATABASE_URL` = Neon DIRECT (recomendado inicialmente)
- `REDIS_URL` = Upstash `rediss://...`
- `RUN_MIGRATIONS=false`
- `RUN_BOOTSTRAP=false`

Migration/bootstrap controlado:

- executar uma etapa one-off com a URL Neon DIRECT;
- habilitar migrations/bootstrap somente nessa etapa;
- nunca executar migrations automaticamente em cada startup do Cloud Run.

## Aplicacao

Extraia o ZIP diretamente sobre:

`C:\AI\ai-sales-agent-platform-v0.1`

Nao use `git add .`, `git clean`, `docker compose down -v` ou `--remove-orphans`.

Depois rode:

```powershell
cd C:\AI\ai-sales-agent-platform-v0.1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\upgrade_v151.ps1
```

Nao coloque credenciais Neon/Upstash em arquivos versionados.
