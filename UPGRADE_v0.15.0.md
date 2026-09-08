# Upgrade v0.15.0 - Multi-Cloud Deployment Readiness

## Objetivo
Preparar a mesma imagem de producao para AWS, Google Cloud, Azure e OCI, preservando a baseline v0.14.3.

## Mudancas
- imagem validada para `linux/amd64` e `linux/arm64`;
- release GHCR passa a publicar manifest multi-platform com provenance e SBOM;
- `APP_VERSION` usa a versao do pacote/`pyproject.toml` como default, sem hardcode em `Settings`;
- `RUN_MIGRATIONS` e `RUN_BOOTSTRAP` controlam o ciclo de inicializacao;
- imagem production e segura por default: ambos os controles ficam `false`;
- Docker Compose local preserva o comportamento anterior usando ambos como `true`;
- CI ganha `Multi-Architecture Gate`;
- cleanup do CI nao usa `--remove-orphans`.

## Aplicacao
Extraia o ZIP de upgrade na raiz do projeto aceitando sobrescrita. O arquivo `.env` nao faz parte do ZIP.

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v15.ps1
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v15.ps1
```

## Cloud/serverless
Em runtime serverless, use normalmente:

```text
RUN_MIGRATIONS=false
RUN_BOOTSTRAP=false
```

Migrations e bootstrap devem ser executados como um job controlado antes da promocao da aplicacao.
