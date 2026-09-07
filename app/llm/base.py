from __future__ import annotations

from typing import Any, Protocol

from app.llm.types import LLMResult, ToolTurnResult


class LLMProvider(Protocol):
    name: str

    async def generate(
        self,
        *,
        input_text: str,
        instructions: str,
        model: str,
    ) -> LLMResult: ...

    async def generate_structured(
        self,
        *,
        input_text: str,
        instructions: str,
        model: str,
        schema_name: str,
        json_schema: dict[str, Any],
    ) -> LLMResult: ...

    async def generate_with_tools(
        self,
        *,
        input_data: str | list[Any],
        instructions: str,
        model: str,
        tools: list[dict[str, Any]],
    ) -> ToolTurnResult: ...
