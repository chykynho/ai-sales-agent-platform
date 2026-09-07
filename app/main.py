from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.agent.runtime import start_agent_runtime, stop_agent_runtime
from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.redis import close_redis
from app.llm.factory import close_llm_provider
from app.embeddings.factory import close_embedding_provider

configure_logging(settings.app_debug)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (%s)", settings.app_name, settings.app_env)
    await start_agent_runtime()
    yield
    await stop_agent_runtime()
    await close_llm_provider()
    await close_embedding_provider()
    await close_redis()
    logger.info("Application stopped")


app = FastAPI(
    title=settings.app_name,
    version="0.10.0",
    debug=settings.app_debug,
    lifespan=lifespan,
)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "version": "0.10.0", "docs": "/docs"}
