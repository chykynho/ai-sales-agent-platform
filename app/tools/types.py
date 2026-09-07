from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@dataclass(slots=True)
class ToolContext:
    db: AsyncSession
    current_user: User
    agent_run_id: uuid.UUID
    provider_call_id: str
    idempotency_key: str
    arguments_hash: str
    tenant_config: Any | None = None


ToolHandler = Callable[[ToolContext, BaseModel], Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: ToolHandler
    write_action: bool = False

    @staticmethod
    def _openai_schema(value: Any) -> Any:
        # Pydantic emits annotations such as `title` and `format=email`.
        # They are useful for local validation but unnecessary for the model tool schema.
        # Keep the provider-facing schema inside the strict Structured Outputs subset;
        # the Pydantic model remains the authoritative backend validator.
        if isinstance(value, dict):
            return {
                key: ToolSpec._openai_schema(item)
                for key, item in value.items()
                if key not in {"title", "format", "default"}
            }
        if isinstance(value, list):
            return [ToolSpec._openai_schema(item) for item in value]
        return value

    def definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self._openai_schema(self.args_model.model_json_schema()),
            "strict": True,
        }
