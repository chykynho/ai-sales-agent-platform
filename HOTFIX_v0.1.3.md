# Hotfix v0.1.3

## Corrigido

O smoke test v0.1.2 passava um `byte[]` para `Invoke-RestMethod` no Windows PowerShell 5.1. Nesse ambiente, o corpo podia ser serializado como representação textual dos bytes, fazendo o FastAPI retornar `json_invalid` / `Extra data`.

A v0.1.3 troca somente o envio de POSTs JSON do smoke test por `System.Net.Http.HttpClient` com `StringContent` UTF-8 explícito.

Também mantém o arquivo `.ps1` com BOM UTF-8 para que o Windows PowerShell 5.1 interprete corretamente os literais acentuados.

## Aplicação

Copie `scripts/test_v01.ps1` sobre o arquivo existente no projeto e execute:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v01.ps1
```

Não é necessário reconstruir containers ou apagar volumes, pois este hotfix altera apenas o teste local em PowerShell.
