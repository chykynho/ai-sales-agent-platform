# AI Sales Agent Platform — Documentação pt_BR

Versão consolidada: **v0.10**

## Documentos

1. `01_Documentacao_Tecnica_AI_Sales_Agent_Platform_v0.10_PTBR.docx` — visão técnica completa, stack, versões, multi-tenancy, RAG, WhatsApp, Voice AI, segurança e roadmap.
2. `02_Guia_Instalacao_Execucao_Testes_v0.10_PTBR.docx` — comandos, execução no Windows, preservação de dados, smoke tests e troubleshooting.
3. `03_Arquitetura_Decisoes_Tecnicas_v0.10_PTBR.docx` — decisões arquiteturais e trade-offs em formato ADR resumido.
4. `04_Roteiro_Entrevista_Demonstracao_v0.10_PTBR.docx` — pitch, roteiro de demo, perguntas prováveis, histórias STAR e limites que não devem ser superestimados.

## Estado atual

A plataforma possui FastAPI, PostgreSQL, Redis, JWT/RBAC, OpenAI, tool calling, LangGraph, HITL, RAG/pgvector, SaaS multi-tenant, arquitetura WhatsApp, OpenAI Realtime e ponte Twilio-compatible com barge-in em laboratório.

## Diretório local usado nos testes

```powershell
C:\AI\ai-sales-agent-platform-v0.1
```

## Regra operacional crítica

Não execute `docker compose down -v` no ambiente atual, pois os volumes preservam PostgreSQL, RAG, checkpoints e histórico.

## Limites atuais

- Meta Cloud real ainda não conectado.
- PSTN/número Twilio real ainda não conectado.
- X-Twilio-Signature real ainda não validado.
- O laboratório v0.10 usa cliente Twilio-compatible e transcript injetado para teste determinístico.
