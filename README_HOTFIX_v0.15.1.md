# HOTFIX v0.15.1 - aplicar por sobrescrita

Este ZIP e um overlay. O nivel raiz do ZIP contem diretamente os arquivos/pastas que devem substituir ou ser adicionados no repositorio existente.

Destino correto:

`C:\AI\ai-sales-agent-platform-v0.1`

Ao abrir o ZIP, voce deve ver diretamente:

- `.gitattributes`
- `Dockerfile`
- `pyproject.toml`
- `app\`
- `scripts\`
- `tests\`
- documentacao `.md`

Nao existe uma pasta `ai-sales-agent-platform-v0.1` dentro do ZIP.

Preservar `.env`, banco, volumes Docker e `docs\Documentacao de CICD.docx`.
