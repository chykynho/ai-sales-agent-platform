# Hotfix do Checkpoint Local v0.10.1

Este hotfix corrige um falso erro do Windows PowerShell 5.1 ao capturar comandos nativos que escrevem mensagens informativas em stderr.

## Sintoma corrigido

O comando `alembic current` imprime linhas `INFO` em stderr. Com `$ErrorActionPreference = "Stop"` e `2>&1`, o PowerShell 5.1 pode transformar essas linhas em `NativeCommandError`, mesmo quando o processo termina com exit code 0.

## O que foi alterado

- Criada a função `Invoke-NativeCaptured`.
- `alembic current`, `psql` e `redis-cli` passam a ser executados via `cmd.exe`, que consolida stdout/stderr antes de devolver a saída ao PowerShell.
- O script avalia o exit code real do processo.
- Nenhuma alteração é feita na API, no banco, no Redis, no `.env` ou nos volumes.

## Como aplicar

Copie `test_checkpoint_v10.ps1` para a pasta `scripts` do projeto, sobrescrevendo o anterior.

```powershell
cd C:\AI\ai-sales-agent-platform-v0.1
copy .\test_checkpoint_v10.ps1 .\scripts\test_checkpoint_v10.ps1 -Force
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_checkpoint_v10.ps1
```

O resultado esperado ao final é:

```text
=== CHECKPOINT v0.10.1 VALIDADO COM SUCESSO ===
```
