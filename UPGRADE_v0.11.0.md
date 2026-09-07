# Upgrade para v0.11 — Production Telephony Hardening

## Antes de aplicar

A baseline recomendada é `v0.10.5`, com working tree limpo.

Crie uma branch de trabalho:

```powershell
git switch main
git pull
git switch -c feature/v0.11-production-telephony
```

Extraia o ZIP de upgrade sobre a raiz do projeto e preserve `.env`, PostgreSQL, Redis e volumes.

## Aplicação

```powershell
cd C:\AI\ai-sales-agent-platform-v0.1
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v11.ps1
```

O script adiciona somente variáveis ausentes ao `.env` local de desenvolvimento, reconstrói a API por causa da dependência oficial `twilio` e executa a suíte completa de regressão. A baseline tinha 23 testes e a v0.11 adiciona 5 contratos de telefonia; o alvo esperado é **28 testes aprovados**.

Não existe nova migration na v0.11.

## Validação funcional

Após o upgrade:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v11.ps1
```

O smoke test valida assinaturas HTTP/WSS, TwiML, callbacks, áudio PCMU de entrada, `gpt-transcribe`, LangGraph/tools, áudio Realtime de saída e auditoria.

## Depois da validação

```powershell
git status
git add .
git commit -m "v0.11 - production telephony hardening"
git push -u origin feature/v0.11-production-telephony
```

Não faça merge na `main` antes de validar o smoke test e o checkpoint de regressão.
