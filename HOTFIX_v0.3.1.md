# Hotfix v0.3.1

Corrige falso negativo do smoke test `scripts/test_v03.ps1` no Windows PowerShell 5.1.

## Sintoma

A API retornava `tool_calls` com `check_price` em `status=completed`, mas o teste encerrava com:

`check_price was not completed.`

## Causa

Quando `Where-Object` retorna exatamente um objeto, o Windows PowerShell 5.1 pode tratá-lo como escalar. O teste acessava `.Count` diretamente sobre esse resultado, produzindo uma contagem incorreta.

## Correção

As validações agora materializam explicitamente o resultado do filtro como array antes de contar:

```powershell
@($collection | Where-Object { ... }).Count
```

A correção foi aplicada a:

- `check_price`
- `create_lead`
- replay idempotente de `create_lead`

Nenhuma alteração de backend, banco, migration ou `.env` é necessária.
