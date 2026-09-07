from functools import lru_cache

from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.exceptions import LLMProviderError
from app.llm.providers.mock import MockLLMProvider
from app.llm.providers.openai_provider import OpenAIProvider


@lru_cache(maxsize=1)
def create_llm_provider() -> LLMProvider:
    provider = settings.llm_provider.strip().lower()
    if provider == "mock":
        return MockLLMProvider()
    if provider == "openai":
        return OpenAIProvider()
    raise LLMProviderError(
        f"Unsupported LLM_PROVIDER={settings.llm_provider!r}",
        code="unsupported_provider",
    )


async def close_llm_provider() -> None:
    if create_llm_provider.cache_info().currsize == 0:
        return
    provider = create_llm_provider()
    close = getattr(provider, "close", None)
    if close is not None:
        await close()
    create_llm_provider.cache_clear()
