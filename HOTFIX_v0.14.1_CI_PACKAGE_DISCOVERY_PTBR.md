# Hotfix v0.14.1 — GitHub Actions / setuptools package discovery

## Problema

O GitHub Actions falhava no job **Quality Gate**, no passo de instalação `python -m pip install ".[dev,security]"`.

O `setuptools` fazia descoberta automática em flat-layout e encontrava múltiplos diretórios de topo (`app`, `alembic`, `fixtures`, `observability`), abortando o build.

## Correção

- versão da aplicação: `0.14.1`;
- backend PEP 517 explícito (`setuptools.build_meta`) no `pyproject.toml`;
- build requirements explícitos para `setuptools` e `wheel`;
- descoberta de pacote explícita no `pyproject.toml`;
- somente `app*` é empacotado;
- `alembic*`, `fixtures*`, `observability*`, `scripts*` e `tests*` ficam fora do pacote Python;
- mantém `pip-audit . --strict --progress-spinner off`;
- o ambiente `development` instala explicitamente `setuptools`/`wheel`;
- a validação do wheel usa `--no-build-isolation` de forma determinística, sem depender de um backend ausente;
- novo contrato automatizado valida backend e descoberta explícitos.

## Resultado esperado

O passo do GitHub Actions **Instalar dependencias de desenvolvimento e seguranca** deve concluir e liberar Ruff, Bandit, pytest/coverage, pip-audit e SBOM.

A tag `v0.14.0` não deve ser reescrita. Após validação e merge deste hotfix, publicar uma nova tag `v0.14.1`.
