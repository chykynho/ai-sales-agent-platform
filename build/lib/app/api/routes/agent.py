from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runtime import get_sales_graph, internal_thread_id
from app.agent.state import SalesAgentContext
from app.api.deps import CurrentUser, require_roles
from app.db.session import get_db
from app.llm.exceptions import LLMProviderError
from app.llm.factory import create_llm_provider
from app.models.user import User, UserRole
from app.observability.tracing import tracer
from app.schemas.agent import (
    AgentCheckpointRead,
    AgentInterruptRead,
    AgentThreadHistoryResponse,
    AgentThreadMessageRequest,
    AgentThreadMessageResponse,
    AgentThreadResumeRequest,
    AgentThreadStateResponse,
)
from app.services.llm_service import LLMService
from app.services.tool_service import ToolService
from app.services.tenant_config_service import TenantConfigService
from app.tools.exceptions import ToolExecutionError
from app.tools.registry import get_tool_registry

router = APIRouter(prefix="/agent", tags=["agent-runtime"])
THREAD_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$"
HumanReviewer = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.AGENT)),
]


def _config(*, tenant_id: uuid.UUID, thread_id: str) -> dict[str, Any]:
    return {
        "configurable": {
            "thread_id": internal_thread_id(
                tenant_id=str(tenant_id),
                external_thread_id=thread_id,
            )
        }
    }


def _message_to_dict(message: Any) -> dict[str, str]:
    if isinstance(message, dict):
        return {
            "role": str(message.get("role", "unknown")),
            "content": str(message.get("content", "")),
        }
    return {"role": "unknown", "content": str(message)}


def _checkpoint_id(snapshot: Any) -> str | None:
    config = getattr(snapshot, "config", None) or {}
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    raw = configurable.get("checkpoint_id")
    return str(raw) if raw else None


def _interrupts(snapshot: Any) -> list[AgentInterruptRead]:
    result: list[AgentInterruptRead] = []
    for item in tuple(getattr(snapshot, "interrupts", ()) or ()):
        result.append(
            AgentInterruptRead(
                id=str(getattr(item, "id", "")),
                value=getattr(item, "value", None),
            )
        )
    return result


async def _runtime_context(
    *,
    db: AsyncSession,
    current_user: User,
    client_idempotency_key: str,
) -> SalesAgentContext:
    tenant_config = await TenantConfigService().get(db=db, tenant_id=current_user.tenant_id)
    registry = get_tool_registry().filtered(tenant_config.enabled_tools)
    return SalesAgentContext(
        db=db,
        current_user=current_user,
        llm_service=LLMService(create_llm_provider()),
        tool_service=ToolService(registry, tenant_config=tenant_config),
        tenant_config=tenant_config,
        client_idempotency_key=client_idempotency_key,
    )


def _message_response(*, thread_id: str, snapshot: Any) -> AgentThreadMessageResponse:
    values = dict(getattr(snapshot, "values", {}) or {})
    messages = [_message_to_dict(x) for x in values.get("messages", [])]
    pending = _interrupts(snapshot)
    return AgentThreadMessageResponse(
        thread_id=thread_id,
        status="interrupted" if pending else "completed",
        route=str(values.get("route") or "respond"),
        output=str(values.get("final_output") or ""),
        human_required=bool(values.get("human_required", False)),
        human_review_status=str(values.get("human_review_status") or "none"),
        classification=values.get("classification") or {},
        message_count=len(messages),
        agent_run_ids=list(values.get("agent_run_ids", [])),
        tool_call_ids=list(values.get("tool_call_ids", [])),
        interrupts=pending,
    )


def _raise_graph_exception(exc: Exception) -> None:
    if isinstance(exc, LLMProviderError):
        code = status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(
            status_code=code,
            detail={"code": exc.code, "message": str(exc), "retryable": exc.retryable},
        ) from exc
    if isinstance(exc, ToolExecutionError):
        code = (
            status.HTTP_403_FORBIDDEN
            if exc.code == "tool_forbidden"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(
            status_code=code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    raise HTTPException(status_code=500, detail=f"Agent graph execution failed: {exc}") from exc


@router.get("/config")
async def agent_config() -> dict[str, Any]:
    return {
        "runtime": "langgraph",
        "graph": "sales_agent_v0.9",
        "checkpointer": "postgres",
        "tenant_thread_namespace": True,
        "human_interrupts": True,
        "resume_endpoint": "/api/v1/agent/threads/{thread_id}/resume",
        "single_pending_interrupt_policy": True,
        "tenant_configuration": True,
        "tenant_catalog": True,
        "tenant_tool_policy": True,
    }


@router.post(
    "/threads/{thread_id}/messages",
    response_model=AgentThreadMessageResponse,
)
async def send_thread_message(
    payload: AgentThreadMessageRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    thread_id: Annotated[str, Path(pattern=THREAD_PATTERN)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", max_length=200),
    ] = None,
) -> AgentThreadMessageResponse:
    graph = get_sales_graph()
    config = _config(tenant_id=current_user.tenant_id, thread_id=thread_id)

    existing = await graph.aget_state(config)
    if _interrupts(existing):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "thread_interrupted",
                "message": "Thread has a pending human interrupt; resume it before sending a new message.",
            },
        )

    context = await _runtime_context(
        db=db,
        current_user=current_user,
        client_idempotency_key=idempotency_key or str(uuid.uuid4()),
    )
    try:
        with tracer("app.agent").start_as_current_span("agent.langgraph.message") as span:
            span.set_attribute("saas.tenant.id", str(current_user.tenant_id))
            span.set_attribute("agent.thread_id", thread_id)
            await graph.ainvoke(
                {
                    "latest_input": payload.message,
                    "external_thread_id": thread_id,
                    "tenant_id": str(current_user.tenant_id),
                    "messages": [{"role": "user", "content": payload.message}],
                    "human_required": False,
                    "human_review_status": "none",
                    "human_review_note": "",
                    "reviewed_by_user_id": "",
                    "final_output": "",
                },
                config=config,
                context=context,
            )
    except Exception as exc:
        _raise_graph_exception(exc)

    snapshot = await graph.aget_state(config)
    return _message_response(thread_id=thread_id, snapshot=snapshot)


@router.post(
    "/threads/{thread_id}/resume",
    response_model=AgentThreadMessageResponse,
)
async def resume_thread(
    payload: AgentThreadResumeRequest,
    current_user: HumanReviewer,
    db: Annotated[AsyncSession, Depends(get_db)],
    thread_id: Annotated[str, Path(pattern=THREAD_PATTERN)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", max_length=200),
    ] = None,
) -> AgentThreadMessageResponse:
    graph = get_sales_graph()
    config = _config(tenant_id=current_user.tenant_id, thread_id=thread_id)
    snapshot = await graph.aget_state(config)
    values = dict(getattr(snapshot, "values", {}) or {})
    if not values:
        raise HTTPException(status_code=404, detail="Thread not found")

    pending = _interrupts(snapshot)
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "no_pending_interrupt", "message": "Thread has no pending interrupt."},
        )
    if len(pending) != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "multiple_pending_interrupts",
                "message": "v0.5 resume endpoint expects exactly one pending interrupt.",
            },
        )

    resume_value = {
        "decision": payload.decision,
        "note": payload.note or "",
        "reviewer_user_id": str(current_user.id),
    }
    context = await _runtime_context(
        db=db,
        current_user=current_user,
        client_idempotency_key=idempotency_key or str(uuid.uuid4()),
    )
    try:
        with tracer("app.agent").start_as_current_span("agent.langgraph.resume") as span:
            span.set_attribute("saas.tenant.id", str(current_user.tenant_id))
            span.set_attribute("agent.thread_id", thread_id)
            await graph.ainvoke(
                Command(resume={pending[0].id: resume_value}),
                config=config,
                context=context,
            )
    except Exception as exc:
        _raise_graph_exception(exc)

    snapshot_after = await graph.aget_state(config)
    return _message_response(thread_id=thread_id, snapshot=snapshot_after)


@router.get(
    "/threads/{thread_id}/state",
    response_model=AgentThreadStateResponse,
)
async def get_thread_state(
    current_user: CurrentUser,
    thread_id: Annotated[str, Path(pattern=THREAD_PATTERN)],
) -> AgentThreadStateResponse:
    graph = get_sales_graph()
    snapshot = await graph.aget_state(
        _config(tenant_id=current_user.tenant_id, thread_id=thread_id)
    )
    values = dict(getattr(snapshot, "values", {}) or {})
    if not values:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = [_message_to_dict(x) for x in values.get("messages", [])]
    pending = _interrupts(snapshot)
    return AgentThreadStateResponse(
        thread_id=thread_id,
        checkpoint_id=_checkpoint_id(snapshot),
        status="interrupted" if pending else "completed",
        route=values.get("route"),
        human_required=bool(values.get("human_required", False)),
        human_review_status=str(values.get("human_review_status") or "none"),
        human_review_note=str(values.get("human_review_note") or ""),
        reviewed_by_user_id=str(values.get("reviewed_by_user_id") or ""),
        classification=values.get("classification"),
        final_output=values.get("final_output"),
        message_count=len(messages),
        messages=messages,
        agent_run_ids=list(values.get("agent_run_ids", [])),
        tool_call_ids=list(values.get("tool_call_ids", [])),
        next_nodes=list(getattr(snapshot, "next", ()) or ()),
        interrupts=pending,
    )


@router.get(
    "/threads/{thread_id}/history",
    response_model=AgentThreadHistoryResponse,
)
async def get_thread_history(
    current_user: CurrentUser,
    thread_id: Annotated[str, Path(pattern=THREAD_PATTERN)],
    limit: int = Query(default=20, ge=1, le=100),
) -> AgentThreadHistoryResponse:
    graph = get_sales_graph()
    checkpoints: list[AgentCheckpointRead] = []
    async for snapshot in graph.aget_state_history(
        _config(tenant_id=current_user.tenant_id, thread_id=thread_id),
        limit=limit,
    ):
        values = dict(getattr(snapshot, "values", {}) or {})
        messages = values.get("messages", [])
        created_at = getattr(snapshot, "created_at", None)
        checkpoints.append(
            AgentCheckpointRead(
                checkpoint_id=_checkpoint_id(snapshot),
                created_at=str(created_at) if created_at else None,
                route=values.get("route"),
                message_count=len(messages),
                next_nodes=list(getattr(snapshot, "next", ()) or ()),
                interrupt_count=len(tuple(getattr(snapshot, "interrupts", ()) or ())),
            )
        )
    if not checkpoints:
        raise HTTPException(status_code=404, detail="Thread not found")
    return AgentThreadHistoryResponse(thread_id=thread_id, checkpoints=checkpoints)
