from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "TokenUsage") -> None:
        self.input_tokens += other.input_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.output_tokens += other.output_tokens
        self.reasoning_tokens += other.reasoning_tokens
        self.total_tokens += other.total_tokens


@dataclass(slots=True)
class LLMResult:
    provider: str
    model: str
    text: str
    request_id: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    structured_data: dict[str, Any] | None = None
    provider_response_count: int = 1
    tool_call_count: int = 0


@dataclass(slots=True)
class ToolCallRequest:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ToolTurnResult:
    provider: str
    model: str
    text: str
    request_id: str | None
    usage: TokenUsage
    tool_calls: list[ToolCallRequest]
    continuation_items: list[Any]
