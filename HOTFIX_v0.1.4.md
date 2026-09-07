# Hotfix v0.1.4

Corrige a leitura JSON UTF-8 no Windows PowerShell 5.1.

## Causa

O POST da v0.1.3 já comprovava que o texto UTF-8 era enviado, persistido e devolvido corretamente. O GET final ainda usava `Invoke-RestMethod`, que no Windows PowerShell 5.1 pode interpretar respostas `application/json` sem `charset` com codificação inadequada. Isso fazia o assert local divergir embora PostgreSQL/FastAPI estivessem corretos.

## Correção

O smoke test agora lê a resposta HTTP em bytes via `HttpClient` e decodifica explicitamente com `System.Text.Encoding.UTF8` antes de `ConvertFrom-Json`.

Nenhuma alteração no backend, schema, PostgreSQL, Redis ou Docker.
