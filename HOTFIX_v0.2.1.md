# Hotfix v0.2.1

## Correção

Corrige um falso negativo no smoke test `scripts/test_v02.ps1` no Windows PowerShell 5.1.

`ConvertFrom-Json` pode entregar um array JSON como um único objeto-array no pipeline. A versão v0.2.0 fazia:

```powershell
$runs = @(Invoke-JsonGet "$BaseUrl/ai/runs?limit=10" $token)
```

Esse `@(...)` podia criar um array externo com apenas um elemento (o array interno), fazendo `$runs.Count` retornar `1` mesmo quando a API havia devolvido dois ou mais `agent_runs`.

## Validação reforçada

A v0.2.1 agora:

1. busca cada `run_id` diretamente em `/ai/runs/{run_id}`;
2. confirma `status = completed`;
3. confirma que os dois runs pertencem ao mesmo tenant;
4. consulta `/ai/runs?limit=10` sem o `@(...)` problemático;
5. normaliza a contagem para Windows PowerShell 5.1;
6. confirma que os dois IDs aparecem na lista filtrada por tenant.

Nenhuma alteração de backend, banco ou migration é necessária.
