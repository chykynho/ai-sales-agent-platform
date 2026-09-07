# Upgrade v0.3.1 → v0.4.0

1. Extract the upgrade ZIP over the existing project directory.
2. Keep the existing `.env`, PostgreSQL volume, Redis volume, and OpenAI key.
3. Run:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v04.ps1
```

4. When the upgrade reports success, run:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v04.ps1
```

Do **not** run `docker compose down -v`.
