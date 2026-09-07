from openai import AsyncOpenAI
from app.core.config import settings
from app.embeddings.types import EmbeddingResult

class OpenAIEmbeddingProvider:
    name = "openai"
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds, max_retries=settings.openai_max_retries) if settings.openai_api_key else None

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if self.client is None:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings")
        response = await self.client.embeddings.create(
            model=settings.openai_embedding_model,
            input=texts,
            dimensions=settings.embedding_dimensions,
            encoding_format="float",
        )
        vectors = [list(item.embedding) for item in sorted(response.data, key=lambda x: x.index)]
        usage = getattr(response, "usage", None)
        return EmbeddingResult(model=response.model, vectors=vectors, input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0))

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()
