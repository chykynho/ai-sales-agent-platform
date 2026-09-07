# Validação pré-empacotamento — v0.11

## Resultado no ambiente de empacotamento

- AST Python: 124 arquivos analisados sem erro.
- `compileall`: concluído sem erro.
- Contratos `tests/test_voice_contract.py` + `tests/test_twilio_production_contract.py`: **9 aprovados**.
- Contratos verificados: framing PCMU, TwiML WSS, `media/mark/clear`, start μ-law/8 kHz/mono, assinatura `RequestValidator`, callback HTTPS, parâmetros TwiML e conversão μ-law -> PCM/WAV.

## Limitação deste ambiente

O sandbox de empacotamento não possui todas as dependências do projeto (`openai`, `twilio`, `pgvector`, `pwdlib` etc.) e não conseguiu instalá-las pela rede. Para os contratos isolados do `RequestValidator`, foi usada temporariamente uma implementação compatível com a API e com o código-fonte atual publicado pela Twilio (`compute_signature`/`validate`).

A validação decisiva usa o pacote real `twilio==9.11.0` e todas as dependências dentro do Docker do projeto. Por isso `scripts/upgrade_v11.ps1` executa:

```text
pytest -q tests
```

Partindo da baseline v0.10.5 (23 testes) e dos 5 novos contratos da v0.11, o resultado esperado é **28 testes aprovados**.

Depois, `scripts/test_v11.ps1` executa o smoke test funcional com assinatura HTTP/WSS, callbacks, PCMU, VAD, `gpt-transcribe`, LangGraph/tools e OpenAI Realtime.

## Fronteira de honestidade

A v0.11 prepara e valida localmente a borda de produção. Ela **não** deve ser descrita como PSTN real até uma conta e número Twilio reais estarem conectados e o tráfego for originado da infraestrutura externa da Twilio.
