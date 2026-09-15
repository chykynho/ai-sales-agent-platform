from __future__ import annotations

import asyncio
import logging

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def setup_langgraph() -> None:
    logger.info("Applying LangGraph PostgreSQL checkpoint schema/migrations")

    async with AsyncPostgresSaver.from_conn_string(
        settings.langgraph_database_url
    ) as checkpointer:
        await checkpointer.setup()

    logger.info("LangGraph PostgreSQL checkpoint schema is ready")


if __name__ == "__main__":
    asyncio.run(setup_langgraph())
