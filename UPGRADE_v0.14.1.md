# Upgrade v0.14.0 → v0.14.1

Hotfix de CI para tornar o empacotamento Python explícito e reproduzível no GitHub Actions.

## Mudanças

- `pyproject.toml` declara explicitamente o backend PEP 517 `setuptools.build_meta`;
- build requirements fixados: `setuptools>=80,<83` e `wheel>=0.45,<1`;
- `pyproject.toml` passa a descobrir apenas `app*`;
- diretórios operacionais/documentais deixam de ser considerados pacotes Python;
- versão da aplicação passa a `0.14.1`;
- `pip-audit` continua em modo de projeto com `--strict`;
- contrato automatizado cobre package discovery;
- o ambiente de desenvolvimento contém `setuptools`/`wheel` e a validação local constrói o wheel com `--no-build-isolation` dentro do container Python 3.12.

Não há migration de banco. Não remover volumes. Não alterar `.env`.
