from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool_call import ToolCall
from app.models.user import User, UserRole
from app.tools.exceptions import ToolExecutionError
from app.tools.registry import ToolRegistry
from app.tools.types import ToolContext


class ToolService:
    def __init__(self, registry: ToolRegistry, tenant_config: Any | None = None) -> None:
        self.registry = registry
        self.tenant_config = tenant_config

    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    @classmethod
    def _hash(cls, value: Any) -> str:
        return hashlib.sha256(cls._canonical(value).encode("utf-8")).hexdigest()

    @classmethod
    def _idempotency_key(
        cls,
        *,
        tenant_id: uuid.UUID,
        client_key: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        del arguments
        raw = f"{tenant_id}:{client_key}:{tool_name}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def execute(
        self,
        *,
        db: AsyncSession,
        current_user: User,
        agent_run_id: uuid.UUID,
        provider_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        client_idempotency_key: str,
    ) -> tuple[ToolCall, dict[str, Any]]:
        spec = self.registry.get(tool_name)
        if spec is None:
            raise ToolExecutionError(f"Tool {tool_name!r} is not registered", code="tool_not_allowed")

        # v0.3 policy: VIEWER is read-only. Per-tenant tool policies arrive in a later version.
        if spec.write_action and current_user.role == UserRole.VIEWER:
            raise ToolExecutionError("Current role cannot execute write tools", code="tool_forbidden")

        try:
            parsed = spec.args_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolExecutionError(f"Tool argument validation failed: {exc}", code="tool_validation_error") from exc

        arguments_hash = self._hash(arguments)
        idempotency_key = self._idempotency_key(
            tenant_id=current_user.tenant_id,
            client_key=client_idempotency_key,
            tool_name=tool_name,
            arguments=arguments,
        )
        audit = ToolCall(
            tenant_id=current_user.tenant_id,
            agent_run_id=agent_run_id,
            user_id=current_user.id,
            provider_call_id=provider_call_id,
            tool_name=tool_name,
            status="running",
            is_write_action=spec.write_action,
            arguments_hash=arguments_hash,
            idempotency_key=idempotency_key,
        )
        db.add(audit)
        await db.flush()

        started = time.perf_counter()
        try:
            result = await spec.handler(
                ToolContext(
                    db=db,
                    current_user=current_user,
                    agent_run_id=agent_run_id,
                    provider_call_id=provider_call_id,
                    idempotency_key=idempotency_key,
                    arguments_hash=arguments_hash,
                    tenant_config=self.tenant_config,
                ),
                parsed,
            )
            audit.status = "completed"
            audit.result_hash = self._hash(result)
            audit.latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            await db.commit()
            await db.refresh(audit)
            return audit, result
        except Exception as exc:
            await db.rollback()
            # Re-create the audit after rollback so the failure itself is persisted.
            failed = ToolCall(
                tenant_id=current_user.tenant_id,
                agent_run_id=agent_run_id,
                user_id=current_user.id,
                provider_call_id=provider_call_id,
                tool_name=tool_name,
                status="failed",
                is_write_action=spec.write_action,
                arguments_hash=arguments_hash,
                idempotency_key=idempotency_key,
                latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
                error_code=exc.code if isinstance(exc, ToolExecutionError) else "tool_runtime_error",
                error_message=str(exc)[:2000],
            )
            db.add(failed)
            await db.commit()
            if isinstance(exc, ToolExecutionError):
                raise exc
            raise ToolExecutionError(str(exc), code="tool_runtime_error") from exc
