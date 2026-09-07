# Hotfix v0.7.1

Corrige o smoke test multi-tenant no Windows/Docker.

## Causa

O teste executava `python scripts/provision_tenant.py` dentro do container. Nesse modo, o Python usa `/app/scripts` como entrada principal do `sys.path`, e `from app...` pode falhar com `ModuleNotFoundError: No module named 'app'`.

## Correção

O teste passa a executar o provisionador como módulo a partir do `WORKDIR=/app`:

```bash
python -m scripts.provision_tenant
```

Não há alteração de banco, migration, `.env`, PostgreSQL, Redis ou volumes. Não é necessário rebuild da API.
