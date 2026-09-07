# Upgrade v0.4 → v0.5

1. Extraia o ZIP de upgrade sobre o diretório atual do projeto.
2. Preserve `.env`, PostgreSQL, Redis e volumes Docker.
3. Não execute `docker compose down -v`.
4. Execute:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v05.ps1
```

5. Se o upgrade terminar com `v0.5 UPGRADE APPLIED`, execute:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v05.ps1
```

A v0.5 não adiciona migration de domínio: o interrupt é persistido pelas tabelas de checkpoint LangGraph já instaladas na v0.4.
