# Política de Segurança

## Versões suportadas

A linha `main` e a tag estável mais recente recebem correções de segurança.

## Como reportar uma vulnerabilidade

Não abra issue pública contendo credenciais, tokens, PII ou detalhes exploráveis. Use o canal privado de Security Advisories do GitHub quando disponível.

Inclua, quando possível:

- componente/versão afetada;
- passos mínimos para reproduzir;
- impacto observado;
- mitigação sugerida;
- evidência sem expor segredos reais.

## Controles do repositório

A v0.14 adiciona gates para testes, Ruff, Bandit, `pip-audit`, Gitleaks, Trivy, SBOM CycloneDX, build da imagem `production` e integração Docker.
