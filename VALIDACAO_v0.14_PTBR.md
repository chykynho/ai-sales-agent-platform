# Validação v0.14 — CI/CD e Supply Chain

## Gate de upgrade

- API pronta em `0.14.0`;
- regressão completa: 50 testes;
- Ruff crítico;
- contratos CI/CD/supply-chain;
- target Docker `production` construído;
- imagem `production` executa como `USER app`.

## Gate completo local

- Ruff;
- Bandit médio/alto;
- pytest + coverage >= 25%;
- pip-audit sem vulnerabilidade conhecida não ignorada;
- SBOM CycloneDX 1.6 gerado;
- Gitleaks sem segredo versionado;
- Trivy sem vulnerabilidade CRITICAL corrigível na imagem production.

## GitHub Actions

Após push da branch, validar os checks:

- `Quality Gate`;
- `Secret Scan`;
- `Container Security Gate`;
- `Docker Integration Gate`.

## Ruleset recomendado para main

No GitHub, em **Settings → Rules → Rulesets**, criar regra para `main` com:

- exigir Pull Request;
- exigir os quatro status checks acima;
- bloquear force push;
- bloquear deleção da branch;
- exigir resolução de conversas antes do merge;
- opcional: exigir commits assinados.

## Release

Após merge validado, uma tag `v0.14.0` dispara `CD - Release Container` e publica a imagem no GHCR somente depois do gate Trivy.
