import hashlib, math
from app.core.config import settings
from app.embeddings.types import EmbeddingResult

class MockEmbeddingProvider:
    name = "mock"
    async def embed(self, texts: list[str]) -> EmbeddingResult:
        vectors=[]
        for text in texts:
            seed=hashlib.sha256(text.lower().encode("utf-8")).digest()
            raw=[]
            for i in range(settings.embedding_dimensions):
                b=seed[i % len(seed)]
                raw.append((b - 127.5) / 127.5)
            norm=math.sqrt(sum(x*x for x in raw)) or 1.0
            vectors.append([x/norm for x in raw])
        return EmbeddingResult(model="mock-embedding-v0.6", vectors=vectors, input_tokens=sum(max(1, len(x)//4) for x in texts))
    async def close(self) -> None:
        return None
