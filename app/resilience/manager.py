from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.config import settings
from app.db.redis import redis_client
from app.observability.metrics import (
    BULKHEAD_IN_FLIGHT,
    BULKHEAD_REJECTIONS,
    CIRCUIT_BREAKER_EVENTS,
    CIRCUIT_BREAKER_OPEN,
    RESILIENCE_FAIL_OPEN,
    RESILIENCE_RETRIES,
    enabled as metrics_enabled,
)
from app.resilience.bulkhead import AsyncBulkhead, BulkheadConfig
from app.resilience.circuit_breaker import CircuitBreakerConfig, RedisCircuitBreaker
from app.resilience.exceptions import BulkheadRejectedError, CircuitOpenError
from app.resilience.retry import retry_async

logger = logging.getLogger("app.resilience")
T = TypeVar("T")


class ResilienceManager:
    def __init__(self) -> None:
        self.breaker = RedisCircuitBreaker(redis_client)
        self._bulkheads: dict[str, AsyncBulkhead] = {}

    def _bulkhead(self, dependency: str) -> AsyncBulkhead:
        current = self._bulkheads.get(dependency)
        if current is None:
            current = AsyncBulkhead(
                name=dependency,
                config=BulkheadConfig(
                    limit=settings.resilience_bulkhead_llm_concurrency,
                    acquire_timeout_seconds=settings.resilience_bulkhead_acquire_timeout_seconds,
                ),
            )
            self._bulkheads[dependency] = current
        return current

    @staticmethod
    def _circuit_config() -> CircuitBreakerConfig:
        return CircuitBreakerConfig(
            failure_threshold=settings.resilience_circuit_failure_threshold,
            cooldown_seconds=settings.resilience_circuit_cooldown_seconds,
            failure_window_seconds=settings.resilience_circuit_failure_window_seconds,
            probe_lock_seconds=settings.resilience_circuit_probe_lock_seconds,
        )

    async def execute(
        self,
        dependency: str,
        operation: Callable[[], Awaitable[T]],
        *,
        should_retry: Callable[[Exception], bool],
    ) -> T:
        if not settings.resilience_enabled:
            return await operation()

        circuit_config = self._circuit_config()
        if settings.resilience_circuit_breaker_enabled:
            try:
                state = await self.breaker.before_call(dependency, circuit_config)
                if metrics_enabled():
                    CIRCUIT_BREAKER_OPEN.labels(dependency).set(0)
                    if state == "half_open":
                        CIRCUIT_BREAKER_EVENTS.labels(dependency, "half_open_probe").inc()
            except CircuitOpenError:
                if metrics_enabled():
                    CIRCUIT_BREAKER_OPEN.labels(dependency).set(1)
                    CIRCUIT_BREAKER_EVENTS.labels(dependency, "rejected_open").inc()
                raise
            except Exception as exc:
                if not settings.resilience_fail_open:
                    raise
                if metrics_enabled():
                    RESILIENCE_FAIL_OPEN.labels("circuit_breaker").inc()
                logger.warning("circuit_breaker_fail_open", extra={"dependency": dependency, "error": str(exc)})

        bulkhead = self._bulkhead(dependency)

        async def execute_inner() -> T:
            def on_retry(attempt: int, exc: Exception) -> None:
                if metrics_enabled():
                    RESILIENCE_RETRIES.labels(dependency, "scheduled").inc()
                logger.warning(
                    "dependency_retry_scheduled",
                    extra={"dependency": dependency, "attempt": attempt, "error": str(exc)},
                )

            try:
                result = await retry_async(
                    operation,
                    max_attempts=settings.resilience_retry_max_attempts,
                    base_delay_seconds=settings.resilience_retry_base_delay_seconds,
                    max_delay_seconds=settings.resilience_retry_max_delay_seconds,
                    jitter_seconds=settings.resilience_retry_jitter_seconds,
                    should_retry=should_retry,
                    on_retry=on_retry,
                )
            except Exception as exc:
                if settings.resilience_circuit_breaker_enabled and should_retry(exc):
                    try:
                        failures = await self.breaker.record_failure(dependency, circuit_config)
                        if metrics_enabled():
                            CIRCUIT_BREAKER_EVENTS.labels(dependency, "failure").inc()
                            if failures >= circuit_config.failure_threshold:
                                CIRCUIT_BREAKER_OPEN.labels(dependency).set(1)
                                CIRCUIT_BREAKER_EVENTS.labels(dependency, "opened").inc()
                    except Exception as breaker_exc:
                        if not settings.resilience_fail_open:
                            raise breaker_exc from exc
                        if metrics_enabled():
                            RESILIENCE_FAIL_OPEN.labels("circuit_breaker_record").inc()
                raise
            else:
                if settings.resilience_circuit_breaker_enabled:
                    try:
                        await self.breaker.record_success(dependency)
                        if metrics_enabled():
                            CIRCUIT_BREAKER_OPEN.labels(dependency).set(0)
                            CIRCUIT_BREAKER_EVENTS.labels(dependency, "success").inc()
                    except Exception:
                        if not settings.resilience_fail_open:
                            raise
                        if metrics_enabled():
                            RESILIENCE_FAIL_OPEN.labels("circuit_breaker_success").inc()
                return result

        if not settings.resilience_bulkhead_enabled:
            return await execute_inner()

        try:
            async with bulkhead.slot():
                if metrics_enabled():
                    BULKHEAD_IN_FLIGHT.labels(dependency).set(bulkhead.in_flight)
                try:
                    return await execute_inner()
                finally:
                    if metrics_enabled():
                        # Atualização final ocorre ainda dentro do context manager;
                        # o próximo ciclo refletirá imediatamente o valor correto.
                        BULKHEAD_IN_FLIGHT.labels(dependency).set(max(0, bulkhead.in_flight - 1))
        except BulkheadRejectedError:
            if metrics_enabled():
                BULKHEAD_REJECTIONS.labels(dependency).inc()
            raise


resilience_manager = ResilienceManager()
