# Hotfix EOL - ai-sales-agent-platform-v0.1

Este pacote e um OVERLAY para o projeto existente em:

`C:\AI\ai-sales-agent-platform-v0.1`

## Aplicacao

Extraia o conteudo deste ZIP DIRETAMENTE dentro de:

`C:\AI\ai-sales-agent-platform-v0.1`

Aceite sobrescrever os arquivos existentes quando solicitado.

O ZIP NAO possui uma pasta `ai-sales-agent-platform-v0.1` adicional no nivel raiz.

## Arquivos

- `.gitattributes`
- `Dockerfile`
- `scripts/entrypoint.sh`
- `scripts/normalize_eol.ps1`
- `tests/test_eol_contract.py`

## Validacao inicial

```powershell
cd C:\AI\ai-sales-agent-platform-v0.1
.\scripts\normalize_eol.ps1
git ls-files --eol scripts/entrypoint.sh
```

Esperado para `entrypoint.sh`: `i/lf w/lf` e atributo `eol=lf`.
