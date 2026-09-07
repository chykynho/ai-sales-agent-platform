# Hotfix v0.1.2 — Smoke test UTF-8 no Windows PowerShell 5.1

## Problema corrigido

O `test_v01.ps1` enviava JSON como `String` diretamente para `Invoke-RestMethod`.
No Windows PowerShell 5.1, o corpo pode ser convertido para uma codificação diferente de UTF-8.
O primeiro payload que continha caracteres acentuados era a mensagem `Olá, este é...`, e o FastAPI
respondia `There was an error parsing the body` antes da validação Pydantic.

## Correção

- Todo payload JSON agora é serializado com `ConvertTo-Json -Compress`.
- O JSON é convertido explicitamente para bytes com `[System.Text.Encoding]::UTF8.GetBytes(...)`.
- O Content-Type é `application/json; charset=utf-8`.
- O teste mantém caracteres acentuados e valida o round-trip do texto.
- O smoke test também valida `/users/me`, o endpoint RBAC `/users`, criação de cliente,
  conversa, mensagem e leitura de mensagens.

## Aplicação

Extraia o hotfix sobre a raiz atual do projeto, aceitando sobrescrever `scripts/test_v01.ps1`.
Não é necessário apagar volumes, recriar o banco ou reconstruir containers: o arquivo alterado roda no host Windows.

Execute:

```powershell
cd C:\AIi-sales-agent-platform-v0.1
PowerShell -ExecutionPolicy Bypass -File .\scripts	est_v01.ps1
```

Resultado esperado:

```text
=== v0.1.2 VALIDADA COM SUCESSO ===
```
