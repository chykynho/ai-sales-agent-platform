# Hotfix v0.15.1 - Version Contract

Corrige o contrato legado `tests/test_cicd_supply_chain_contract.py`, que ainda exigia `0.15.0` depois do bump para `0.15.1`.

O teste passa a:
- exigir explicitamente `0.15.1` no `pyproject.toml`;
- validar que `settings.app_version` e `_default_app_version()` acompanham o `pyproject.toml`;
- validar a resolucao dinamica da versao sem hardcode em `app/core/config.py`;
- incluir os artefatos operacionais da v0.15.1 no contrato de existencia.

Extrair diretamente em `C:\AI\ai-sales-agent-platform-v0.1`, sobrescrevendo o arquivo em `tests`.
