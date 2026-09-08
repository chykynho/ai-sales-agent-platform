# Upgrade v0.13.0 → v0.14.0

## Pré-requisito

Partir da `main` validada em `v0.13.0`.

```powershell
cd C:\AI\ai-sales-agent-platform-v0.1
git status
git switch main
git pull origin main
git switch -c feature/v0.14-cicd-supply-chain
```

Extraia o ZIP de upgrade sobre a pasta do projeto, aceitando sobrescrever.

Não apague `.env`, PostgreSQL, Redis ou volumes. Não use `docker compose down -v`.

## Aplicação

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v14.ps1
```

Alvo esperado:

```text
50 passed
=== v0.14 UPGRADE APPLIED ===
```

Depois rode o gate completo:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v14.ps1
```

Esse segundo passo consulta serviços de vulnerabilidade e pode baixar as imagens Gitleaks/Trivy na primeira execução.
