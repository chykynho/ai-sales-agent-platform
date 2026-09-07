# Upgrade v0.6.0 — RAG / Knowledge Base

Adds PostgreSQL pgvector, HNSW cosine search, OpenAI embeddings, PDF/DOCX/TXT/Markdown ingestion, tenant-filtered retrieval, document dedup/versioning, and grounded answers with source markers.

Important: the PostgreSQL service switches from `postgres:17-alpine` to `pgvector/pgvector:0.8.6-pg17` while preserving the existing `postgres_data` volume. Do not use `docker compose down -v`.
