from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.redis import redis_client
from app.observability.metrics import (
    RATE_LIMIT_DECISIONS,
    RESILIENCE_FAIL_OPEN,
    enabled as metrics_enabled,
)
from app.resilience.rate_limit import RateLimitDecision, RedisRateLimiter

logger = logging.getLogger("app.resilience.rate_limit")


class ResilienceMiddleware:
    """Rate limiting distribuído de borda para requisições HTTP.

    Usa tenant_id de JWT válido quando disponível; caso contrário, usa hash do IP do cliente.
    Health/metrics/docs ficam isentos para não atrapalhar sondas e scraping.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.rate_limiter = RedisRateLimiter(redis_client)
        self.exempt_paths = {
            item.strip()
            for item in settings.resilience_rate_limit_exempt_paths.split(",")
            if item.strip()
        }

    @staticmethod
    def _headers(scope: Scope) -> dict[str, str]:
        return {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }

    @staticmethod
    def _client_ip(scope: Scope) -> str:
        client = scope.get("client")
        if isinstance(client, (tuple, list)) and client:
            return str(client[0])
        return "unknown"

    def _identity(self, scope: Scope) -> tuple[str, str]:
        headers = self._headers(scope)
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            try:
                payload = decode_access_token(token)
                tenant = str(payload.get("tenant_id") or "").strip()
                if tenant:
                    return "tenant", tenant
            except Exception:
                pass
        ip = self._client_ip(scope)
        digest = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:24]
        return "client", digest

    @staticmethod
    def _key(scope_kind: str, identity: str) -> str:
        return f"resilience:rate:{scope_kind}:{identity}"

    @staticmethod
    def _rate_headers(decision: RateLimitDecision) -> dict[str, str]:
        return {
            "X-RateLimit-Limit": str(decision.limit),
            "X-RateLimit-Remaining": str(decision.remaining),
            "X-RateLimit-Reset": str(decision.retry_after_seconds),
        }

    async def _reject(self, send: Send, decision: RateLimitDecision) -> None:
        payload = json.dumps(
            {
                "detail": {
                    "code": "rate_limit_exceeded",
                    "message": "Limite de requisições excedido. Tente novamente após o período indicado.",
                    "retry_after_seconds": decision.retry_after_seconds,
                }
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"retry-after", str(decision.retry_after_seconds).encode("ascii")),
        ]
        for key, value in self._rate_headers(decision).items():
            headers.append((key.lower().encode("ascii"), value.encode("ascii")))
        await send({"type": "http.response.start", "status": 429, "headers": headers})
        await send({"type": "http.response.body", "body": payload})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.resilience_enabled:
            await self.app(scope, receive, send)
            return
        if not settings.resilience_rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "/")
        if path in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        scope_kind, identity = self._identity(scope)
        try:
            decision = await self.rate_limiter.check(
                key=self._key(scope_kind, identity),
                limit=settings.resilience_rate_limit_requests,
                window_seconds=settings.resilience_rate_limit_window_seconds,
            )
        except Exception as exc:
            if not settings.resilience_fail_open:
                raise
            if metrics_enabled():
                RESILIENCE_FAIL_OPEN.labels("rate_limiter").inc()
            logger.warning(
                "rate_limiter_fail_open",
                extra={"scope": scope_kind, "error": str(exc)},
            )
            await self.app(scope, receive, send)
            return

        if metrics_enabled():
            RATE_LIMIT_DECISIONS.labels(
                scope_kind,
                "allowed" if decision.allowed else "rejected",
            ).inc()

        if not decision.allowed:
            await self._reject(send, decision)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in self._rate_headers(decision).items():
                    headers[key] = value
            await send(message)

        await self.app(scope, receive, send_wrapper)
