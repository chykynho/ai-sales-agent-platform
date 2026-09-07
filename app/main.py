from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.agent.runtime import start_agent_runtime, stop_agent_runtime
from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.redis import close_redis, redis_client
from app.db.session import engine
from app.embeddings.factory import close_embedding_provider
from app.llm.factory import close_llm_provider
from app.observability.middleware import ObservabilityMiddleware
from app.observability.tracing import configure_tracing

configure_logging(settings.app_debug)
configure_tracing(sqlalchemy_engine=engine, redis_client=redis_client)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_starting")
    await start_agent_runtime()
    yield
    await stop_agent_runtime()
    await close_llm_provider()
    await close_embedding_provider()
    await close_redis()
    logger.info("application_stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.app_debug,
    lifespan=lifespan,
)
app.add_middleware(ObservabilityMiddleware)
app.include_router(api_router, prefix=settings.api_v1_prefix)

if settings.observability_enabled and settings.observability_metrics_enabled:
    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "version": settings.app_version, "docs": "/docs"}
