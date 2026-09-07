# Hotfix v0.11.1 — Smoke test de telefonia/STT mais determinístico

## Sintoma

O caminho de produção funcionou até a transcrição, mas o áudio sintético usado pelo smoke test não representou de forma confiável a frase esperada. Em uma execução, `Quanto custa o Plano PRO?` chegou ao STT como `Onde consta o plano tal.`. O LangGraph então respondeu corretamente sobre um plano inexistente, e o assert de `R$ 997` falhou.

## Diagnóstico

A assinatura Twilio, callbacks, handshake WSS, VAD, STT, LangGraph, geração de áudio Realtime e persistência funcionaram. A falha estava na origem sintética do áudio de teste: a v0.11 usava o modelo Realtime como se fosse um TTS literal.

## Correção

- O áudio do cliente de laboratório agora é gerado pelo endpoint dedicado `POST /v1/audio/speech`.
- Modelo padrão: `gpt-4o-mini-tts-2025-12-15`; fallback automático para `gpt-4o-mini-tts`.
- A frase é mais redundante para resistir à degradação G.711: `Qual é o preço do plano PRO? Repito: qual é o preço do plano PRO?`.
- O WAV é convertido para G.711 mu-law mono/8 kHz, exatamente como o Twilio Media Streams.
- Antes de abrir o Media Stream, o mesmo `gpt-transcribe` faz um preflight e exige intenção de preço + produto PRO.
- O transcript do endpoint de produção continua vindo exclusivamente do áudio enviado ao WebSocket. Nenhum `lab_transcript` é injetado.
- Na sessão persistida, o teste também valida semanticamente o transcript antes de exigir o preço `997`.

## Arquivos alterados

- `scripts/test_v11_production_voice.py`
- `scripts/test_v11.ps1`
- documentação deste hotfix

Não há alteração de banco, migration, API, `.env`, Redis, pgvector ou LangGraph.
