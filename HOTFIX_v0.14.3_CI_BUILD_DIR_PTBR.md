# Hotfix v0.14.3 — contrato de build no CI

## Causa
O `pip install ".[dev,security]"` pode criar `build/` temporariamente. A v0.14.2 falhava no GitHub Runner porque o teste exigia ausência física absoluta desse diretório. A primeira revisão da v0.14.3 moveu a regra para `git ls-files`, mas executou esse comando dentro do container de desenvolvimento, que propositalmente não inclui o binário Git nem `.git`.

## Correção final
- `git ls-files` é executado no host/runner, onde o repositório Git existe.
- O pytest dentro do container valida `.gitignore`, `.dockerignore`, workflow e build isolado, sem depender de Git.
- O workflow remove `build`, `dist` e `*.egg-info` após instalar dependências.
- O wheel continua sendo construído em `/tmp/v0143-src`.

A regra de segurança permanece: artefatos de build podem existir temporariamente, mas nunca podem ser rastreados pelo Git nem entrar no contexto final da imagem.
