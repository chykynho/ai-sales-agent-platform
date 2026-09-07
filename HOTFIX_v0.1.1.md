# Hotfix v0.1.1

## Correções

1. Corrige `DuplicateObjectError: type "user_role" already exists` na migration inicial.
2. Aplica a mesma correção preventiva aos ENUMs `conversation_channel` e `message_role`.
3. Regrava os scripts PowerShell em UTF-8 com BOM para Windows PowerShell 5.1, evitando textos como `jÃ¡` e `configuraÃ§Ã£o`.
4. Adiciona `scripts/recover_v011.ps1`, que reconstrói os containers, acompanha a inicialização e valida o health check sem apagar os volumes.

## Causa raiz

A migration criava os ENUMs explicitamente com `.create(..., checkfirst=True)`, mas os objetos `sa.Enum` usados nas colunas ainda tinham criação automática habilitada. Ao criar a tabela, SQLAlchemy executava um segundo `CREATE TYPE`.

A correção usa `postgresql.ENUM(..., create_type=False)` e mantém a criação explícita uma única vez.

## Aplicação

Sobrescreva os arquivos do hotfix na raiz do projeto, preservando seu `.env`, e execute:

`PowerShell -ExecutionPolicy Bypass -File .\scripts\recover_v011.ps1`
