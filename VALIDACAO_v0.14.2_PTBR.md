# Validação v0.14.2

Critérios:
- 52 testes passam;
- wheel é construído em `/tmp/v0142-src`;
- `build/` e `*.egg-info/` não existem na raiz;
- Ruff/Bandit/coverage/pip-audit/Gitleaks/Trivy passam;
- imagem production usa `USER app`;
- CI remoto fica verde;
- tag v0.14.2 dispara CD/GHCR.
