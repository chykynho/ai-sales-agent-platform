from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from opentelemetry.trace import SpanKind, Status, StatusCode
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.context import bind_context, clear_context, reset_context, tenant_id, trace_ids
from app.observability.metrics import (
    HTTP_DURATION,
    HTTP_ERRORS,
    HTTP_IN_FLIGHT,
    HTTP_REQUESTS,
    TENANT_REQUESTS,
    enabled as metrics_enabled,
    safe_tenant_label,
)
from app.observability.tracing import tracer

logger = logging.getLogger("app.http")


class ObservabilityMiddleware:
    """Middleware ASGI puro para preservar ContextVars do endpoint/dependencias."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        incoming_request_id = str(headers.get("x-request-id") or "").strip()
        request_id = incoming_request_id[:128] if incoming_request_id else uuid.uuid4().hex
        tokens = bind_context(request_id=request_id)
        started = time.perf_counter()
        method = str(scope.get("method") or "GET").upper()
        fallback_route = str(scope.get("path") or "/")
        span_name = f"HTTP {method} {fallback_route}"
        status_code = 500
        tr = tracer("app.http")

        if metrics_enabled():
            HTTP_IN_FLIGHT.inc()

        try:
            with tr.start_as_current_span(span_name, kind=SpanKind.SERVER) as span:
                span.set_attribute("http.request.method", method)
                span.set_attribute("url.path", fallback_route)
                server = scope.get("server")
                if isinstance(server, (tuple, list)) and server:
                    span.set_attribute("server.address", str(server[0]))

                async def send_wrapper(message: Message) -> None:
                    nonlocal status_code
                    if message["type"] == "http.response.start":
                        status_code = int(message.get("status", 500))
                        response_headers = MutableHeaders(scope=message)
                        response_headers["X-Request-ID"] = request_id
                        trace_id, _span_id = trace_ids()
                        if trace_id:
                            response_headers["X-Trace-ID"] = trace_id
                    await send(message)

                try:
                    await self.app(scope, receive, send_wrapper)
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)[:200]))
                    raise
                finally:
                    route = getattr(scope.get("route"), "path", None) or "__unmatched__"
                    span.update_name(f"HTTP {method} {route}")
                    span.set_attribute("http.route", route)
                    span.set_attribute("http.response.status_code", status_code)
                    current_tenant = tenant_id()
                    if current_tenant:
                        span.set_attribute("saas.tenant.id", current_tenant)
        finally:
            elapsed = max(0.0, time.perf_counter() - started)
            route = getattr(scope.get("route"), "path", None) or "__unmatched__"
            current_tenant = tenant_id()
            if metrics_enabled():
                HTTP_IN_FLIGHT.dec()
                HTTP_REQUESTS.labels(method, route, str(status_code)).inc()
                HTTP_DURATION.labels(method, route).observe(elapsed)
                if status_code >= 500:
                    HTTP_ERRORS.labels(method, route, str(status_code)).inc()
                if current_tenant:
                    TENANT_REQUESTS.labels(safe_tenant_label(current_tenant), route).inc()
            logger.info(
                "http_request_completed",
                extra={
                    "http_method": method,
                    "http_route": route,
                    "http_status": status_code,
                    "duration_ms": round(elapsed * 1000, 3),
                },
            )
            reset_context(tokens)
            clear_context()
