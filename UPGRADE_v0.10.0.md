# Upgrade v0.9 -> v0.10

v0.10 adds the Twilio bidirectional Media Streams WebSocket bridge laboratory.

There is **no new Alembic migration**. Existing `voice_sessions` and `voice_events` store bridge metrics in JSON metadata.

Preserve `.env`, PostgreSQL, Redis, pgvector, LangGraph checkpoints and all Docker volumes.

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v10.ps1
```

Then validate:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v10.ps1
```
