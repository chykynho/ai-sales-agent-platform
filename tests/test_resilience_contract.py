from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from prometheus_client import generate_latest

from app.core.config import settings
from app.resilience.bulkhead import AsyncBulkhead, BulkheadConfig
from app.resilience.circuit_breaker import CircuitBreakerConfig, RedisCircuitBreaker
from app.resilience.exceptions import BulkheadRejectedError, CircuitOpenError
from app.resilience.rate_limit import RedisRateLimiter
from app.resilience.retry import retry_async


class FakeEvalRedis:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def eval(self, *args):
        self.calls.append(args)
        return self.result


class FakeCircuitRedis:
    def __init__(self, *, open_until: int | None = None, set_result=True, failure_count=1):
        self.open_until = open_until
        self.set_result = set_result
        self.failure_count = failure_count
        self.deleted = []

    async def get(self, key):
        del key
        return self.open_until

    async def set(self, *args, **kwargs):
        del args, kwargs
        return self.set_result

    async def delete(self, *keys):
        self.deleted.extend(keys)
        return len(keys)

    async def eval(self, *args):
        del args
        return self.failure_count


def test_v013_settings_contract():
    assert settings.app_version == "0.13.0"
    assert settings.resilience_enabled is True
    assert settings.resilience_rate_limit_enabled is True
    assert settings.resilience_circuit_breaker_enabled is True
    assert settings.resilience_bulkhead_enabled is True
    assert settings.resilience_retry_max_attempts >= 1


@pytest.mark.asyncio
async def test_rate_limiter_returns_atomic_decision():
    redis = FakeEvalRedis([3, 41])
    limiter = RedisRateLimiter(redis)
    decision = await limiter.check(key="tenant:1", limit=5, window_seconds=60)
    assert decision.allowed is True
    assert decision.current == 3
    assert decision.remaining == 2
    assert decision.retry_after_seconds == 41
    assert redis.calls


@pytest.mark.asyncio
async def test_rate_limiter_rejects_above_limit():
    limiter = RedisRateLimiter(FakeEvalRedis([6, 17]))
    decision = await limiter.check(key="tenant:1", limit=5, window_seconds=60)
    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.retry_after_seconds == 17


@pytest.mark.asyncio
async def test_circuit_breaker_rejects_while_open():
    redis = FakeCircuitRedis(open_until=int(time.time()) + 20)
    breaker = RedisCircuitBreaker(redis)
    config = CircuitBreakerConfig(5, 30, 60, 10)
    with pytest.raises(CircuitOpenError):
        await breaker.before_call("openai", config)


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_probe_and_success_close():
    redis = FakeCircuitRedis(open_until=int(time.time()) - 1, set_result=True)
    breaker = RedisCircuitBreaker(redis)
    config = CircuitBreakerConfig(5, 30, 60, 10)
    state = await breaker.before_call("openai", config)
    assert state == "half_open"
    await breaker.record_success("openai")
    assert len(redis.deleted) == 3


@pytest.mark.asyncio
async def test_bulkhead_rejects_when_capacity_exhausted():
    bulkhead = AsyncBulkhead(
        name="openai",
        config=BulkheadConfig(limit=1, acquire_timeout_seconds=0.02),
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        async with bulkhead.slot():
            entered.set()
            await release.wait()

    task = asyncio.create_task(holder())
    await entered.wait()
    try:
        with pytest.raises(BulkheadRejectedError):
            async with bulkhead.slot():
                pass
    finally:
        release.set()
        await task


@pytest.mark.asyncio
async def test_retry_async_retries_retryable_failure_then_succeeds():
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient")
        return "ok"

    result = await retry_async(
        operation,
        max_attempts=2,
        base_delay_seconds=0,
        max_delay_seconds=0,
        jitter_seconds=0,
        should_retry=lambda exc: isinstance(exc, RuntimeError),
    )
    assert result == "ok"
    assert attempts == 2


def test_resilience_metrics_and_files_contract():
    from app.observability import metrics  # noqa: F401

    text = generate_latest().decode("utf-8")
    for name in (
        "rate_limit_decisions_total",
        "resilience_fail_open_total",
        "bulkhead_rejections_total",
        "bulkhead_in_flight",
        "circuit_breaker_events_total",
        "circuit_breaker_open",
        "resilience_retries_total",
    ):
        assert name in text

    root = Path(__file__).resolve().parents[1]
    middleware = (root / "app/resilience/middleware.py").read_text(encoding="utf-8")
    assert "X-RateLimit-Limit" in middleware
    assert "retry-after" in middleware.lower()
    assert "decode_access_token" in middleware
    assert (root / "scripts/load_test_v13.py").exists()
