from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.agent.graph import build_sales_agent_graph
from app.core.config import settings

logger = logging.getLogger(__name__)

_checkpointer_cm: Any | None = None
_checkpointer: AsyncPostgresSaver | None = None
_sales_graph: Any | None = None


async def start_agent_runtime() -> None:
    global _checkpointer_cm, _checkpointer, _sales_graph
    if _sales_graph is not None:
        return

    _checkpointer_cm = AsyncPostgresSaver.from_conn_string(settings.langgraph_database_url)
    _checkpointer = await _checkpointer_cm.__aenter__()
    _sales_graph = build_sales_agent_graph(_checkpointer)
    logger.info("LangGraph runtime started with PostgreSQL checkpointing")


async def stop_agent_runtime() -> None:
    global _checkpointer_cm, _checkpointer, _sales_graph
    _sales_graph = None
    _checkpointer = None
    if _checkpointer_cm is not None:
        await _checkpointer_cm.__aexit__(None, None, None)
    _checkpointer_cm = None
    logger.info("LangGraph runtime stopped")


def get_sales_graph():
    if _sales_graph is None:
        raise RuntimeError("LangGraph runtime is not initialized")
    return _sales_graph


def internal_thread_id(*, tenant_id: str, external_thread_id: str) -> str:
    # Tenant namespace is mandatory: two tenants may use the same external ID
    # without sharing checkpoint state.
    return f"tenant:{tenant_id}:thread:{external_thread_id}"
