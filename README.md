# AI Sales Agent Platform v0.11.0

Plataforma de aprendizado e portfólio orientada a produção para agentes comerciais de IA multi-tenant.

A baseline `v0.10.5` foi validada localmente com 23/23 testes, isolamento Demo × Acme, persistência após restart da API, RAG/pgvector, LangGraph, HITL, WhatsApp em laboratório, OpenAI Realtime real e ponte Twilio Media Streams compatível em laboratório.

## Arquitetura validada até a v0.10.5

- FastAPI com REST e WebSockets.
- JWT, RBAC e isolamento por tenant.
- PostgreSQL, Redis e Alembic.
- OpenAI Responses com GPT-5.6 Terra.
- Tool/function calling com schemas estritos, allowlist, auditoria e idempotência.
- LangGraph com checkpoints persistentes em PostgreSQL.
- Human-in-the-Loop com `interrupt()` / `Command(resume=...)`.
- RAG com `text-embedding-3-small`, pgvector e índice HNSW/cosine.
- Configuração SaaS por tenant: identidade, tools, catálogo, horários e parâmetros de RAG.
- WhatsApp: challenge, assinatura HMAC, idempotência, ACK rápido e processamento em background.
- Voice AI com `gpt-realtime-2.1`, voz `marin` e áudio PCMU.
- Ponte Twilio Media Streams compatível com `media`, `mark`, `clear` e barge-in.

## Foco da v0.11 — Production Telephony Hardening

A v0.11 endurece a borda de telefonia sem afirmar conexão PSTN que ainda não existe:

- `twilio==9.11.0` e `RequestValidator` oficial.
- validação de `X-Twilio-Signature` em webhooks HTTP;
- validação de `X-Twilio-Signature` no handshake WSS;
- endpoint público de chamada recebida por conta/tenant;
- TwiML `<Connect><Stream>` com `statusCallback` e `customParameters`;
- Call Status e Stream Status callbacks auditados;
- readiness de produção por conta Twilio sem expor segredo;
- separação explícita LAB × PROD;
- produção sem `lab_transcript`;
- áudio real `audio/x-mulaw` 8 kHz -> VAD local -> `gpt-transcribe` -> LangGraph/tools -> OpenAI Realtime PCMU;
- Auth Token Twilio somente em variável de ambiente/secret manager; o banco guarda apenas o nome da variável.

## Limite deliberado da v0.11

O caminho de produção processa **o primeiro turno de voz por chamada** por padrão (`VOICE_PRODUCTION_FIRST_TURN_ONLY=true`). O objetivo é validar de forma reproduzível a borda de produção e o pipeline de áudio/STT sem transformar o laboratório em uma falsa alegação de PSTN real.

Ainda não são considerados conectados em produção:

- número/PSTN Twilio real;
- tráfego originado da rede Twilio real;
- conversa multi-turn contínua de produção;
- SIP real.

## Aplicação

Partindo da baseline `v0.10.5`, crie uma branch de trabalho antes do upgrade:

```powershell
git switch main
git pull
git switch -c feature/v0.11-production-telephony
```

Depois aplique o upgrade:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v11.ps1
```

Somente após o upgrade passar, execute:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v11.ps1
```

Consulte `V0.11.md` e `UPGRADE_v0.11.0.md` para escopo, segurança, limitações e sequência completa.
