# Validação v0.14.1 — CI package discovery

Critérios:

- readiness retorna `0.14.1`;
- regressão completa: 51 testes;
- build wheel local passa sem erro de múltiplos top-level packages;
- Ruff e supply-chain contracts passam;
- imagem production usa `USER app`;
- GitHub Actions Quality Gate conclui a instalação `.[dev,security]`;
- somente após CI verde, criar/push da tag `v0.14.1` para disparar o release GHCR.

## Revisão final do hotfix

- `[build-system]` explícito com `setuptools.build_meta`;
- `setuptools` e `wheel` fazem parte apenas do extra `dev`;
- `pip wheel --no-deps --no-build-isolation .` valida o backend já instalado no container de desenvolvimento;
- a imagem `production` continua sem essas ferramentas como dependências explícitas de runtime.
