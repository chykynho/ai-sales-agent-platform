# Hotfix v0.14.2 — Higiene do repositório

## Problema
O build local do wheel da v0.14.1 gerou `build/` e `ai_sales_agent_platform.egg-info/` na raiz montada. Um `git add .` incluiu esses artefatos no commit publicado.

## Correção
- remove os artefatos gerados do repositório;
- adiciona `build/`, `dist/`, `*.egg-info/` e `*.whl` ao `.gitignore`;
- exclui os mesmos artefatos do contexto Docker;
- constrói o wheel em `/tmp/v0142-src`, isolado da raiz montada;
- adiciona contrato que exige ausência desses artefatos;
- versão passa para `0.14.2`.

A tag `v0.14.1` não deve ser reescrita.
