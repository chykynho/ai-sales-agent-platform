from typing import Protocol
from app.embeddings.types import EmbeddingResult

class EmbeddingProvider(Protocol):
    name: str
    async def embed(self, texts: list[str]) -> EmbeddingResult: ...
    async def close(self) -> None: ...
