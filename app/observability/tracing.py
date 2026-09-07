from __future__ import annotations

import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor

from app.core.config import settings

logger = logging.getLogger(__name__)
_configured = False
_instrumented = False


def configure_tracing(*, sqlalchemy_engine: Any | None = None, redis_client: Any | None = None) -> None:
    global _configured, _instrumented
    if not settings.observability_enabled or not settings.observability_tracing_enabled:
        return

    if not _configured:
        resource = Resource.create(
            {
                "service.name": settings.observability_service_name,
                "service.version": settings.app_version,
                "deployment.environment": settings.app_env,
            }
        )
        provider = TracerProvider(resource=resource)
        endpoint = str(settings.observability_otlp_endpoint or "").strip()
        if endpoint:
            exporter = OTLPSpanExporter(endpoint=endpoint, timeout=settings.observability_otlp_timeout_seconds)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        if settings.observability_trace_console:
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        _configured = True
        logger.info(
            "OpenTelemetry tracing configured",
            extra={"otel_exporter_configured": bool(endpoint), "otel_service": settings.observability_service_name},
        )

    if _instrumented:
        return
    try:
        HTTPXClientInstrumentor().instrument()
    except Exception:
        logger.exception("Falha ao instrumentar HTTPX com OpenTelemetry")
    try:
        if redis_client is not None:
            RedisInstrumentor.instrument_client(client=redis_client)
        else:
            RedisInstrumentor().instrument()
    except Exception:
        logger.exception("Falha ao instrumentar Redis com OpenTelemetry")
    if sqlalchemy_engine is not None:
        try:
            SQLAlchemyInstrumentor().instrument(engine=sqlalchemy_engine.sync_engine)
        except Exception:
            logger.exception("Falha ao instrumentar SQLAlchemy com OpenTelemetry")
    _instrumented = True


def tracer(name: str = "ai-sales-agent-platform"):
    return trace.get_tracer(name)
