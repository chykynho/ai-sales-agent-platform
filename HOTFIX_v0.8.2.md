# Hotfix v0.8.2

Corrige o smoke test WhatsApp quando o bearer usado nas etapas iniciais passa a ser rejeitado no polling autenticado.

## Alterações
- centraliza login em `Get-DemoAuth`;
- renova o JWT imediatamente antes do polling de background;
- em chamadas autenticadas de polling/state/inventory, faz um único relogin e retry quando recebe HTTP 401;
- não altera API, banco, migration, Docker, `.env` ou fluxo WhatsApp.

## Aplicação
Sobrescreva `scripts/test_v08.ps1` e execute:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v08.ps1
```
