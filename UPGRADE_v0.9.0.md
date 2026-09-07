# Upgrade v0.8.2 -> v0.9.0

1. Extraia o ZIP de upgrade sobre a pasta atual.
2. Preserve `.env` e os volumes.
3. Execute:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v09.ps1
```

4. Depois valide:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v09.ps1
```

Nunca use `docker compose down -v` neste upgrade.
