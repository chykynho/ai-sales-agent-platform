from pathlib import Path

import pytest

from app.core.config import Settings


ROOT = Path(__file__).resolve().parents[1]


def test_local_database_url_contract_is_preserved() -> None:
    settings = Settings(
        _env_file=None,
        postgres_user="u",
        postgres_password="p",
        postgres_host="db",
        postgres_port=5432,
        postgres_db="x",
        database_url_env=None,
        langgraph_database_url_env=None,
    )

    assert settings.database_url == "postgresql+asyncpg://u:p@db:5432/x"
    assert settings.langgraph_database_url == "postgresql://u:p@db:5432/x"


def test_neon_libpq_url_is_normalized_for_sqlalchemy_asyncpg() -> None:
    raw = (
        "postgresql://neondb_owner:secret@"
        "ep-example-pooler.sa-east-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    settings = Settings(_env_file=None, database_url_env=raw)

    assert settings.database_url == (
        "postgresql+asyncpg://neondb_owner:secret@"
        "ep-example-pooler.sa-east-1.aws.neon.tech/neondb?ssl=require"
    )


def test_langgraph_keeps_psycopg_neon_tls_parameters() -> None:
    raw = (
        "postgresql://neondb_owner:secret@"
        "ep-example.sa-east-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    settings = Settings(_env_file=None, langgraph_database_url_env=raw)

    assert settings.langgraph_database_url == raw


def test_langgraph_can_use_database_url_when_no_specific_override_exists() -> None:
    raw = (
        "postgresql://neondb_owner:secret@"
        "ep-example-pooler.sa-east-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    settings = Settings(_env_file=None, database_url_env=raw)

    assert settings.langgraph_database_url == raw


def test_rediss_url_is_preserved_for_upstash() -> None:
    settings = Settings(
        _env_file=None,
        redis_url="rediss://default:secret@example.upstash.io:6379",
    )

    assert settings.redis_url.startswith("rediss://")


def test_invalid_external_database_scheme_is_rejected() -> None:
    settings = Settings(_env_file=None, database_url_env="mysql://user:pass@example/db")

    with pytest.raises(ValueError, match="PostgreSQL"):
        _ = settings.database_url


def test_production_dockerfile_uses_cloud_run_port_with_local_fallback() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert 'EXPOSE 8080' in dockerfile
    assert '--port ${PORT:-8000}' in dockerfile


def test_production_defaults_keep_migrations_and_bootstrap_disabled() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "RUN_MIGRATIONS=false" in dockerfile
    assert "RUN_BOOTSTRAP=false" in dockerfile
