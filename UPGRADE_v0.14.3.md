# Upgrade v0.14.3

Hotfix do contrato de repository hygiene do CI. A verificação de arquivos rastreados roda no host/GitHub Runner via `git ls-files`; o container não precisa conter Git. Sem migration.
