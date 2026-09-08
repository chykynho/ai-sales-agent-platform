from dataclasses import dataclass

@dataclass(slots=True)
class EmbeddingResult:
    model: str
    vectors: list[list[float]]
    input_tokens: int = 0
