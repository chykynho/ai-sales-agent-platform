# Hotfix v0.6.1 — SQLAlchemy + asyncpg + pgvector binding

## Sintoma

O upload RAG falhava no INSERT de `knowledge_chunks.embedding` com:

```text
ValueError: expected list or ndarray
asyncpg.exceptions.DataError: invalid input for query argument ...
```

O traceback mostrava que o parâmetro do embedding chegava ao codec asyncpg como uma string no formato `[...]`.

## Causa

A v0.6 registrava simultaneamente duas camadas de adaptação para o tipo `vector`:

1. `pgvector.sqlalchemy.VECTOR`, cujo bind processor serializa o vetor para a representação textual PostgreSQL;
2. `pgvector.asyncpg.register_vector`, cujo codec binário espera receber `list`, `ndarray` ou `Vector`.

Com as duas ativas, SQLAlchemy convertia `list[float]` em `str` e o codec asyncpg tentava tratar essa `str` como vetor Python.

## Correção

A engine SQLAlchemy/asyncpg passa a usar somente `pgvector.sqlalchemy.VECTOR` para binding e leitura. O registro manual de `pgvector.asyncpg.register_vector` foi removido de `app/db/session.py`.

Isso preserva:

- `Mapped[list[float]] = mapped_column(VECTOR(1536))`;
- inserts usando `list[float]`;
- `cosine_distance(query_vector)` no SQLAlchemy;
- HNSW/cosine no PostgreSQL;
- toda a persistência existente.

## Banco

Não há migration nova e não há alteração de schema.

O request que falhou estava dentro de uma transação que não conseguiu commit; portanto não é necessário apagar a Knowledge Base nem os volumes. O smoke test pode ser reexecutado após rebuild da API.
