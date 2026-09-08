from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# IMPORTANT (v0.6.1):
# Do not register pgvector.asyncpg.register_vector on this SQLAlchemy engine.
# pgvector.sqlalchemy.VECTOR has its own SQLAlchemy bind/result processors. Its
# bind processor serializes list[float] to PostgreSQL's textual vector format.
# Registering asyncpg's native binary vector codec at the same time makes
# asyncpg expect list/ndarray while SQLAlchemy hands it the already-serialized
# string, producing: ValueError("expected list or ndarray").
engine = create_async_engine(settings.database_url, pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
