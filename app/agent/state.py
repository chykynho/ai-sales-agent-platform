from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, TypedDict


def append_strings(left: list[str] | None, right: list[str] | None) -> list[str]:
    return list(left or []) + list(right or [])


def append_messages(
    left: list[dict[str, str]] | None,
    right: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    return list(left or []) + list(right or [])


class SalesAgentState(TypedDict, total=False):
    # Keep checkpointed conversation state JSON-only. This makes persistence
    # portable and works cleanly with strict checkpoint deserialization.
    messages: Annotated[list[dict[str, str]], append_messages]
    latest_input: str
    external_thread_id: str
    tenant_id: str
    classification: dict[str, Any]
    route: str
    human_required: bool
    human_review_status: str
    human_review_note: str
    reviewed_by_user_id: str
    final_output: str
    agent_run_ids: Annotated[list[str], append_strings]
    tool_call_ids: Annotated[list[str], append_strings]


@dataclass
class SalesAgentContext:
    # Runtime-only dependencies are deliberately typed as Any so they never
    # become part of the checkpoint/state schema.
    db: Any
    current_user: Any
    llm_service: Any
    tool_service: Any
    tenant_config: Any
    client_idempotency_key: str
