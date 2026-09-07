from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.db.redis import redis_client
from app.db.session import AsyncSessionLocal

router = APIRouter(tags=["health"])


async def _dependency_status() -> tuple[bool, bool]:
    postgres_ok = False
    redis_ok = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        postgres_ok = True
    except Exception:
        postgres_ok = False
    try:
        redis_ok = bool(await redis_client.ping())
    except Exception:
        redis_ok = False
    return postgres_ok, redis_ok


@router.get("/health/live")
async def liveness() -> dict:
    return {"status": "ok", "version": settings.app_version}


@router.get("/health/ready")
async def readiness() -> dict:
    postgres_ok, redis_ok = await _dependency_status()
    return {
        "status": "ok" if postgres_ok and redis_ok else "degraded",
        "postgres": postgres_ok,
        "redis": redis_ok,
        "version": settings.app_version,
    }


@router.get("/health")
async def health() -> dict:
    return await readiness()
