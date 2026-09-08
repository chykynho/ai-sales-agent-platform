# Hotfix v0.14 — pip-audit em modo de projeto

## Sintoma

O gate `pip-audit --strict` executado sobre o ambiente instalado tentava consultar o pacote local `ai-sales-agent-platform==0.14.0` no PyPI e encerrava com erro porque o projeto não é publicado no PyPI.

## Correção

O gate passa a usar:

```bash
pip-audit . --strict --progress-spinner off
```

O argumento `.` ativa o modo de auditoria de projeto local, lendo o `pyproject.toml` e auditando as dependências do projeto sem exigir que o pacote raiz `ai-sales-agent-platform` exista no PyPI.

`--strict` permanece ativo. Portanto, vulnerabilidades conhecidas ou dependências que não possam ser auditadas continuam bloqueando o gate.

## Arquivos alterados

- `scripts/test_v14.ps1`
- `.github/workflows/ci.yml`
- `scripts/test_v14_supply_chain.py`
- `tests/test_cicd_supply_chain_contract.py`

## Execução

Após extrair este hotfix sobre o projeto:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v14.ps1
```

Não é necessário rebuildar a API, reiniciar PostgreSQL/Redis nem alterar `.env`.
