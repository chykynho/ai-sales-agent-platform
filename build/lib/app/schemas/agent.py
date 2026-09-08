from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentThreadMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


class AgentThreadResumeRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=2_000)


class AgentInterruptRead(BaseModel):
    id: str
    value: Any


class AgentThreadMessageResponse(BaseModel):
    thread_id: str
    status: Literal["completed", "interrupted"]
    route: str
    output: str
    human_required: bool
    human_review_status: str
    classification: dict[str, Any]
    message_count: int
    agent_run_ids: list[str]
    tool_call_ids: list[str]
    interrupts: list[AgentInterruptRead]


class AgentThreadStateResponse(BaseModel):
    thread_id: str
    checkpoint_id: str | None
    status: Literal["completed", "interrupted"]
    route: str | None
    human_required: bool
    human_review_status: str
    human_review_note: str
    reviewed_by_user_id: str
    classification: dict[str, Any] | None
    final_output: str | None
    message_count: int
    messages: list[dict[str, str]]
    agent_run_ids: list[str]
    tool_call_ids: list[str]
    next_nodes: list[str]
    interrupts: list[AgentInterruptRead]


class AgentCheckpointRead(BaseModel):
    checkpoint_id: str | None
    created_at: str | None
    route: str | None
    message_count: int
    next_nodes: list[str]
    interrupt_count: int


class AgentThreadHistoryResponse(BaseModel):
    thread_id: str
    checkpoints: list[AgentCheckpointRead]
