from functools import lru_cache
from app.core.config import settings
from app.embeddings.providers.mock import MockEmbeddingProvider
from app.embeddings.providers.openai_provider import OpenAIEmbeddingProvider

@lru_cache(maxsize=1)
def create_embedding_provider():
    name=settings.embedding_provider.strip().lower()
    if name == "openai": return OpenAIEmbeddingProvider()
    if name == "mock": return MockEmbeddingProvider()
    raise RuntimeError(f"Unsupported EMBEDDING_PROVIDER={settings.embedding_provider!r}")

async def close_embedding_provider() -> None:
    if create_embedding_provider.cache_info().currsize:
        provider=create_embedding_provider()
        await provider.close()
        create_embedding_provider.cache_clear()
