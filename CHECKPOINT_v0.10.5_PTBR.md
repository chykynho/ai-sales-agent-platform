# Hotfix do Checkpoint v0.10.5

Corrige a leitura de listas JSON no Windows PowerShell 5.1.

## Causa

`ConvertFrom-Json` pode preservar uma matriz JSON como um único `System.Object[]`. O checkpoint v0.10.4 encapsulava esse retorno e o `Where-Object` não recebia os produtos individualmente.

## Correção

- `GetAuthRaw`: lê o corpo HTTP como texto.
- `GetAuthObject`: desserializa respostas de objeto único.
- `GetAuthList`: enumera explicitamente cada elemento de uma matriz JSON.
- Compatibilidade defensiva com respostas futuras no formato `{ "items": [...] }`.
- Em caso de catálogo vazio/inesperado, imprime o JSON bruto para diagnóstico.
- A mesma leitura de lista é aplicada a `voice_sessions` e eventos WhatsApp.

Não requer rebuild, restart manual, alteração de `.env` ou migration.
