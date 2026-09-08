# Upgrade v0.14.2

1. Parta da `main` com v0.14.1.
2. Crie `hotfix/v0.14.2-repo-hygiene`.
3. Remova localmente `build/`, `dist/` e `*.egg-info/` antes de aplicar o ZIP.
4. Extraia o hotfix v0.14.2 sobre a raiz.
5. Rode `scripts/upgrade_v14.ps1`.
6. Rode `scripts/test_v14.ps1`.
7. Só então faça commit/tag/push.

Não use `docker compose down -v`.
