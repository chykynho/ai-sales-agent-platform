from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agent.graph import build_sales_agent_graph
from app.core.config import settings

logger = logging.getLogger(__name__)

_checkpointer_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None
_sales_graph: Any | None = None


async def start_agent_runtime() -> None:
    global _checkpointer_pool, _checkpointer, _sales_graph

    if _sales_graph is not None:
        return

    pool = AsyncConnectionPool(
        conninfo=settings.langgraph_database_url,
        min_size=0,
        max_size=5,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        check=AsyncConnectionPool.check_connection,
        max_idle=60.0,
        max_lifetime=900.0,
        reconnect_timeout=30.0,
        name="langgraph-checkpoint-pool",
    )

    try:
        await pool.open()
        _checkpointer_pool = pool
        _checkpointer = AsyncPostgresSaver(pool)
        _sales_graph = build_sales_agent_graph(_checkpointer)

        logger.info(
            "LangGraph runtime started with PostgreSQL checkpoint pooling",
            extra={
                "langgraph_pool_min_size": 0,
                "langgraph_pool_max_size": 5,
            },
        )
    except Exception:
        await pool.close()
        _checkpointer_pool = None
        _checkpointer = None
        _sales_graph = None
        raise


async def stop_agent_runtime() -> None:
    global _checkpointer_pool, _checkpointer, _sales_graph

    _sales_graph = None
    _checkpointer = None

    if _checkpointer_pool is not None:
        await _checkpointer_pool.close()

    _checkpointer_pool = None
    logger.info("LangGraph runtime stopped")


def get_sales_graph():
    if _sales_graph is None:
        raise RuntimeError("LangGraph runtime is not initialized")
    return _sales_graph


def internal_thread_id(*, tenant_id: str, external_thread_id: str) -> str:
    # Tenant namespace is mandatory: two tenants may use the same external ID
    # without sharing checkpoint state.
    return f"tenant:{tenant_id}:thread:{external_thread_id}"
