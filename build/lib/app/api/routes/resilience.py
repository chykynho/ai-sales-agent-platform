from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.config import settings
from app.resilience.manager import resilience_manager
from app.observability.metrics import CIRCUIT_BREAKER_OPEN, enabled as metrics_enabled

router = APIRouter(prefix="/resilience", tags=["resilience"])


@router.get("/config")
async def resilience_config(current_user: CurrentUser) -> dict:
    del current_user
    return {
        "enabled": settings.resilience_enabled,
        "fail_open": settings.resilience_fail_open,
        "app_version": settings.app_version,
        "rate_limit": {
            "enabled": settings.resilience_rate_limit_enabled,
            "requests": settings.resilience_rate_limit_requests,
            "window_seconds": settings.resilience_rate_limit_window_seconds,
            "distributed_backend": "redis",
            "scope": "tenant-jwt-or-client-ip",
        },
        "bulkhead": {
            "enabled": settings.resilience_bulkhead_enabled,
            "llm_concurrency": settings.resilience_bulkhead_llm_concurrency,
            "acquire_timeout_seconds": settings.resilience_bulkhead_acquire_timeout_seconds,
            "scope": "per-api-process",
        },
        "circuit_breaker": {
            "enabled": settings.resilience_circuit_breaker_enabled,
            "failure_threshold": settings.resilience_circuit_failure_threshold,
            "failure_window_seconds": settings.resilience_circuit_failure_window_seconds,
            "cooldown_seconds": settings.resilience_circuit_cooldown_seconds,
            "distributed_backend": "redis",
            "half_open_probe": True,
        },
        "retry": {
            "outer_max_attempts": settings.resilience_retry_max_attempts,
            "openai_sdk_max_retries": settings.openai_max_retries,
            "policy": "sdk-first; outer retry disabled by default to avoid retry amplification",
        },
        "load_test": {
            "default_concurrency": settings.load_test_concurrency,
            "default_requests": settings.load_test_requests,
            "p95_threshold_ms": settings.load_test_p95_threshold_ms,
            "error_rate_threshold_pct": settings.load_test_error_rate_threshold_pct,
        },
    }


@router.get("/status")
async def resilience_status(current_user: CurrentUser) -> dict:
    del current_user
    openai_open = False
    degraded = False
    error: str | None = None
    if settings.resilience_circuit_breaker_enabled:
        try:
            openai_open = await resilience_manager.breaker.is_open("openai")
        except Exception as exc:
            degraded = True
            error = str(exc)[:300]
    if metrics_enabled():
        CIRCUIT_BREAKER_OPEN.labels("openai").set(1 if openai_open else 0)
    return {
        "status": "degraded" if degraded else "ok",
        "openai_circuit_open": openai_open,
        "redis_resilience_state_available": not degraded,
        "error": error,
    }
