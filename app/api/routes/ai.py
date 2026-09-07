from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.config import settings
from app.db.session import get_db
from app.llm.exceptions import LLMProviderError
from app.llm.factory import create_llm_provider
from app.models.agent_run import AgentRun
from app.models.tool_call import ToolCall
from app.schemas.ai import (
    AIClassifyLeadRequest,
    AIClassifyLeadResponse,
    AIGenerateRequest,
    AIGenerateResponse,
    AgentRunRead,
    LeadClassification,
    TokenUsageRead,
    ToolAgentRequest,
    ToolAgentResponse,
    ToolCallRead,
)
from app.services.llm_service import LEAD_CLASSIFIER_INSTRUCTIONS, LLMService
from app.services.tool_service import ToolService
from app.services.tenant_config_service import TenantConfigService
from app.tools.exceptions import ToolExecutionError
from app.tools.registry import get_tool_registry

router = APIRouter(prefix="/ai", tags=["ai"])


def _service() -> LLMService:
    return LLMService(create_llm_provider())


def _raise_provider_http_error(exc: LLMProviderError) -> None:
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_502_BAD_GATEWAY
    if exc.code in {"missing_api_key", "unsupported_provider"}:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    raise HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc), "retryable": exc.retryable},
    ) from exc


def _usage(result) -> TokenUsageRead:
    u = result.usage
    return TokenUsageRead(
        input_tokens=u.input_tokens,
        cached_input_tokens=u.cached_input_tokens,
        cache_write_tokens=u.cache_write_tokens,
        output_tokens=u.output_tokens,
        reasoning_tokens=u.reasoning_tokens,
        total_tokens=u.total_tokens,
    )


@router.get("/config")
async def ai_config(current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, str | bool | int]:
    tenant_config = await TenantConfigService().get(db=db, tenant_id=current_user.tenant_id)
    registry = get_tool_registry().filtered(tenant_config.enabled_tools)
    return {
        "provider": settings.llm_provider,
        "model": settings.openai_model if settings.llm_provider == "openai" else settings.mock_model,
        "openai_key_configured": bool(settings.openai_api_key),
        "reasoning_effort": settings.openai_reasoning_effort,
        "response_storage": False,
        "tool_count": len(registry.definitions()),
        "parallel_tool_calls": False,
        "tenant_config_version": tenant_config.config_version,
        "company_name": tenant_config.company_name,
        "assistant_name": tenant_config.assistant_name,
    }


@router.get("/tools")
async def list_tools(current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]) -> list[dict]:
    tenant_config = await TenantConfigService().get(db=db, tenant_id=current_user.tenant_id)
    return get_tool_registry().filtered(tenant_config.enabled_tools).public_catalog()


@router.post("/generate", response_model=AIGenerateResponse)
async def generate(payload: AIGenerateRequest, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]) -> AIGenerateResponse:
    try:
        run, result = await _service().generate(db=db, current_user=current_user, input_text=payload.input)
    except LLMProviderError as exc:
        _raise_provider_http_error(exc)
    return AIGenerateResponse(
        run_id=run.id, provider=result.provider, model=result.model, output=result.text,
        latency_ms=run.latency_ms or 0, usage=_usage(result),
        estimated_cost_usd=run.estimated_cost_usd, cost_is_estimate=run.cost_is_estimate,
    )


@router.post("/classify-lead", response_model=AIClassifyLeadResponse)
async def classify_lead(payload: AIClassifyLeadRequest, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]) -> AIClassifyLeadResponse:
    try:
        run, result, parsed = await _service().generate_structured(
            db=db, current_user=current_user, input_text=payload.message,
            output_model=LeadClassification, schema_name="lead_classification",
            instructions=LEAD_CLASSIFIER_INSTRUCTIONS, operation="classify_lead",
        )
    except LLMProviderError as exc:
        _raise_provider_http_error(exc)
    return AIClassifyLeadResponse(
        run_id=run.id, provider=result.provider, model=result.model, classification=parsed,
        latency_ms=run.latency_ms or 0, usage=_usage(result),
        estimated_cost_usd=run.estimated_cost_usd, cost_is_estimate=run.cost_is_estimate,
    )


@router.post("/tool-agent", response_model=ToolAgentResponse)
async def tool_agent(
    payload: ToolAgentRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=200)] = None,
) -> ToolAgentResponse:
    client_key = idempotency_key or str(uuid.uuid4())
    tenant_config = await TenantConfigService().get(db=db, tenant_id=current_user.tenant_id)
    registry = get_tool_registry().filtered(tenant_config.enabled_tools)
    try:
        run, result, audits = await _service().run_tool_agent(
            db=db,
            current_user=current_user,
            input_text=payload.message,
            tool_service=ToolService(registry, tenant_config=tenant_config),
            client_idempotency_key=client_key,
            instructions=TenantConfigService.tool_instructions(tenant_config),
        )
    except LLMProviderError as exc:
        _raise_provider_http_error(exc)
    except ToolExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN if exc.code == "tool_forbidden" else status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    return ToolAgentResponse(
        run_id=run.id,
        provider=result.provider,
        model=result.model,
        output=result.text,
        tool_calls=[ToolCallRead.model_validate(a) for a in audits],
        latency_ms=run.latency_ms or 0,
        usage=_usage(result),
        estimated_cost_usd=run.estimated_cost_usd,
        cost_is_estimate=run.cost_is_estimate,
    )


@router.get("/runs", response_model=list[AgentRunRead])
async def list_runs(current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)], limit: int = Query(default=20, ge=1, le=100)) -> list[AgentRun]:
    result = await db.execute(
        select(AgentRun).where(AgentRun.tenant_id == current_user.tenant_id).order_by(AgentRun.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


@router.get("/runs/{run_id}", response_model=AgentRunRead)
async def get_run(run_id: uuid.UUID, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]) -> AgentRun:
    result = await db.execute(select(AgentRun).where(AgentRun.id == run_id, AgentRun.tenant_id == current_user.tenant_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@router.get("/runs/{run_id}/tool-calls", response_model=list[ToolCallRead])
async def get_run_tool_calls(run_id: uuid.UUID, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]) -> list[ToolCall]:
    run_result = await db.execute(select(AgentRun.id).where(AgentRun.id == run_id, AgentRun.tenant_id == current_user.tenant_id))
    if run_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    result = await db.execute(
        select(ToolCall).where(ToolCall.agent_run_id == run_id, ToolCall.tenant_id == current_user.tenant_id).order_by(ToolCall.created_at.asc())
    )
    return list(result.scalars().all())
