# AI Sales Agent Platform v0.10.0

Production-oriented learning platform for multi-tenant AI sales agents.

Validated layers through v0.9 include FastAPI, JWT/RBAC, PostgreSQL/Redis, OpenAI Responses, tool calling, idempotent write tools, LangGraph durable checkpoints, Human-in-the-Loop, pgvector RAG, configurable multi-tenant SaaS behavior, WhatsApp webhook/channel processing and OpenAI Realtime voice generation.

## v0.10 focus: Twilio Media Streams bridge laboratory

- FastAPI WebSocket endpoint compatible with Twilio bidirectional Media Streams.
- PCMU / 8 kHz / mono framing.
- Real OpenAI Realtime audio forwarded as Twilio `media` frames.
- `mark` playback tracking.
- `clear`-based barge-in behavior.
- Bridge metrics persisted in `voice_sessions` / `voice_events`.
- LangGraph and tenant-scoped tools remain the business reasoning layer.
- Local Twilio-compatible simulator: no PSTN or paid Twilio number is required for this test.

Run:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v10.ps1
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v10.ps1
```

See `V0.10.md` for scope and security boundaries.
