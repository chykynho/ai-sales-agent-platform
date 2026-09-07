from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.config import settings

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/config")
async def observability_config(current_user: CurrentUser) -> dict:
    del current_user
    return {
        "enabled": settings.observability_enabled,
        "service_name": settings.observability_service_name,
        "app_version": settings.app_version,
        "json_logs": settings.observability_log_json,
        "metrics": {
            "enabled": settings.observability_metrics_enabled,
            "endpoint": "/metrics",
            "tenant_labels": settings.observability_tenant_labels,
        },
        "tracing": {
            "enabled": settings.observability_tracing_enabled,
            "otlp_exporter_configured": bool(settings.observability_otlp_endpoint),
            "console_exporter": settings.observability_trace_console,
        },
        "sre": {
            "golden_signals": ["latency", "traffic", "errors", "saturation"],
            "liveness": f"{settings.api_v1_prefix}/health/live",
            "readiness": f"{settings.api_v1_prefix}/health/ready",
        },
    }
