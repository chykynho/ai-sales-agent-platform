# Validacao v0.15 - PT-BR

## Gates locais
1. Repository hygiene.
2. Ruff.
3. Bandit.
4. Pytest + coverage >= 25%.
5. pip-audit.
6. CycloneDX SBOM.
7. Gitleaks.
8. Trivy na imagem production amd64.
9. Build multi-arquitetura `linux/amd64,linux/arm64`.
10. Docker Integration Gate com PostgreSQL, Redis, readiness e resilience smoke.

## Gates remotos
O `ci.yml` deve exibir:
- Quality Gate;
- Secret Scan;
- Container Security Gate;
- Multi-Architecture Gate;
- Docker Integration Gate.

O `release.yml`, disparado por tag `v*`, deve publicar no GHCR um manifest com `linux/amd64` e `linux/arm64`, provenance e SBOM.
