from __future__ import annotations

import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings


async def main() -> None:
    async with AsyncPostgresSaver.from_conn_string(settings.langgraph_database_url) as checkpointer:
        await checkpointer.setup()
    print("[langgraph-setup] PostgreSQL checkpoint tables are ready.")


if __name__ == "__main__":
    asyncio.run(main())
