from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AIGenerateRequest(BaseModel):
    input: str = Field(min_length=1, max_length=20_000)


class TokenUsageRead(BaseModel):
    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int


class AIGenerateResponse(BaseModel):
    run_id: uuid.UUID
    provider: str
    model: str
    output: str
    latency_ms: int
    usage: TokenUsageRead
    estimated_cost_usd: Decimal | None
    cost_is_estimate: bool = True


LeadIntent = Literal[
    "greeting", "product_interest", "pricing", "scheduling", "objection",
    "support", "human_request", "other",
]
LeadTemperature = Literal["cold", "warm", "hot"]


class LeadClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: LeadIntent
    lead_temperature: LeadTemperature
    needs_human: bool
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(min_length=1, max_length=500)


class AIClassifyLeadRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


class AIClassifyLeadResponse(BaseModel):
    run_id: uuid.UUID
    provider: str
    model: str
    classification: LeadClassification
    latency_ms: int
    usage: TokenUsageRead
    estimated_cost_usd: Decimal | None
    cost_is_estimate: bool = True


class ToolAgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


class ToolCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    agent_run_id: uuid.UUID
    tool_name: str
    status: str
    is_write_action: bool
    latency_ms: int | None
    created_at: datetime


class ToolAgentResponse(BaseModel):
    run_id: uuid.UUID
    provider: str
    model: str
    output: str
    tool_calls: list[ToolCallRead]
    latency_ms: int
    usage: TokenUsageRead
    estimated_cost_usd: Decimal | None
    cost_is_estimate: bool = True


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    operation: str
    provider: str
    model: str
    status: str
    provider_request_id: str | None
    schema_name: str | None
    prompt_hash: str
    output_hash: str | None
    input_chars: int
    output_chars: int
    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    provider_response_count: int
    tool_call_count: int
    latency_ms: int | None
    estimated_cost_usd: Decimal | None
    cost_is_estimate: bool
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
