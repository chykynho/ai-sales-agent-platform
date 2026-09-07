# Upgrade v0.1.4 -> v0.2.0

1. Extraia este ZIP sobre a raiz atual `C:\AI\ai-sales-agent-platform-v0.1`, aceitando sobrescrever os arquivos.
2. O pacote **não contém `.env`** e não apaga dados/volumes.
3. Execute:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v02.ps1
```

4. Depois valide sem custo com provider mock:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v02.ps1
```

5. Somente depois, para uma chamada real OpenAI:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\enable_openai_v02.ps1
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v02.ps1
```

A chave é solicitada de forma segura pelo PowerShell; não a coloque na linha de comando, no Git ou no chat.
