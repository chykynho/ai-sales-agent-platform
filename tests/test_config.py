from app.core.config import Settings


def test_database_url():
    s = Settings(
        postgres_user="u",
        postgres_password="p",
        postgres_host="db",
        postgres_port=5432,
        postgres_db="x",
    )
    assert s.database_url == "postgresql+asyncpg://u:p@db:5432/x"
