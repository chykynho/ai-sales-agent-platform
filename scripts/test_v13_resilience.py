from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid

import httpx

from app.core.config import settings
from app.db.redis import redis_client
from app.resilience.bulkhead import AsyncBulkhead, BulkheadConfig
from app.resilience.circuit_breaker import CircuitBreakerConfig, RedisCircuitBreaker
from app.resilience.exceptions import BulkheadRejectedError, CircuitOpenError
from app.resilience.rate_limit import RedisRateLimiter
from app.resilience.retry import retry_async

BASE = "http://127.0.0.1:8000"
API = BASE + "/api/v1"


def login(client: httpx.Client) -> str:
    response = client.post(
        API + "/auth/login",
        headers={"X-Tenant-Slug": settings.bootstrap_tenant_slug},
        data={"username": settings.bootstrap_admin_email, "password": settings.bootstrap_admin_password},
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


async def functional_resilience_checks() -> dict:
    suffix = uuid.uuid4().hex[:10]

    # Rate limiter atomico em Redis com namespace isolado de smoke.
    limiter = RedisRateLimiter(redis_client)
    rate_key = f"resilience:smoke:rate:{suffix}"
    decisions = [
        await limiter.check(key=rate_key, limit=3, window_seconds=10)
        for _ in range(4)
    ]
    assert [d.allowed for d in decisions] == [True, True, True, False]

    # Circuit breaker real em Redis, mas dependência isolada de smoke.
    dependency = f"smoke-resilience-{suffix}"
    breaker = RedisCircuitBreaker(redis_client)
    config = CircuitBreakerConfig(
        failure_threshold=2,
        cooldown_seconds=2,
        failure_window_seconds=10,
        probe_lock_seconds=3,
    )
    await breaker.record_failure(dependency, config)
    await breaker.record_failure(dependency, config)
    try:
        await breaker.before_call(dependency, config)
    except CircuitOpenError:
        rejected_open = True
    else:
        rejected_open = False
    assert rejected_open is True
    await asyncio.sleep(2.1)
    state = await breaker.before_call(dependency, config)
    assert state == "half_open"
    await breaker.record_success(dependency)
    assert await breaker.is_open(dependency) is False

    # Bulkhead local.
    bulkhead = AsyncBulkhead(name="smoke", config=BulkheadConfig(limit=1, acquire_timeout_seconds=0.02))
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        async with bulkhead.slot():
            entered.set()
            await release.wait()

    task = asyncio.create_task(holder())
    await entered.wait()
    bulkhead_rejected = False
    try:
        try:
            async with bulkhead.slot():
                pass
        except BulkheadRejectedError:
            bulkhead_rejected = True
    finally:
        release.set()
        await task
    assert bulkhead_rejected is True

    # Retry deterministico.
    attempts = 0

    async def flaky():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise RuntimeError("transient-smoke")
        return "ok"

    retry_result = await retry_async(
        flaky,
        max_attempts=2,
        base_delay_seconds=0,
        max_delay_seconds=0,
        jitter_seconds=0,
        should_retry=lambda exc: isinstance(exc, RuntimeError),
    )
    assert retry_result == "ok" and attempts == 2

    await redis_client.delete(rate_key)
    failures_key, open_key, probe_key = breaker._keys(dependency)
    await redis_client.delete(failures_key, open_key, probe_key)

    return {
        "rate_limit": "3 allowed + 1 rejected",
        "circuit_breaker": "open -> reject -> half_open -> closed",
        "bulkhead": "capacity rejection validated",
        "retry": f"success on attempt {attempts}",
    }


def main() -> int:
    expected_version = settings.app_version
    print(f"=== AI Sales Agent Platform {expected_version} - Resilience/Performance Smoke Test ===")
    with httpx.Client(timeout=15.0) as client:
        print(f"\n[1/6] Liveness/readiness {expected_version}...")
        live = client.get(API + "/health/live")
        live.raise_for_status()
        ready = client.get(API + "/health/ready")
        ready.raise_for_status()
        assert live.json()["version"] == expected_version
        assert ready.json()["status"] == "ok"
        print(json.dumps(ready.json(), ensure_ascii=False, indent=2))

        print("\n[2/6] Login + headers de rate limit...")
        token = login(client)
        auth = {"Authorization": "Bearer " + token}
        response = client.get(API + "/resilience/config", headers=auth)
        response.raise_for_status()
        assert response.headers.get("x-ratelimit-limit")
        config = response.json()
        assert config["enabled"] is True
        assert config["rate_limit"]["distributed_backend"] == "redis"
        assert config["circuit_breaker"]["half_open_probe"] is True
        print(json.dumps(config, ensure_ascii=False, indent=2))

        print("\n[3/6] Status do circuit breaker OpenAI...")
        status_response = client.get(API + "/resilience/status", headers=auth)
        status_response.raise_for_status()
        status_data = status_response.json()
        assert status_data["status"] == "ok"
        print(json.dumps(status_data, ensure_ascii=False, indent=2))

        print("\n[4/6] Rate limit/Circuit breaker/Bulkhead/Retry funcionais...")
        functional = asyncio.run(functional_resilience_checks())
        print(json.dumps(functional, ensure_ascii=False, indent=2))

        print("\n[5/6] Metricas Prometheus de resiliencia...")
        metrics = client.get(BASE + "/metrics")
        metrics.raise_for_status()
        required = (
            "rate_limit_decisions_total",
            "resilience_fail_open_total",
            "bulkhead_rejections_total",
            "bulkhead_in_flight",
            "circuit_breaker_events_total",
            "circuit_breaker_open",
            "resilience_retries_total",
        )
        missing = [item for item in required if item not in metrics.text]
        assert not missing, f"Metricas ausentes: {missing}"
        print(f"[OK] {len(required)} metricas/contratos de resiliencia encontrados")

        print("\n[6/6] Sem exposicao de segredos...")
        for forbidden in ("OPENAI_API_KEY", "TWILIO_AUTH_TOKEN", settings.bootstrap_admin_password):
            assert forbidden not in metrics.text
        root = client.get(BASE + "/")
        root.raise_for_status()
        assert root.json()["version"] == expected_version
        print(f"[OK] / reporta {expected_version} e /metrics nao expoe segredos conhecidos")

    print(f"\n=== {expected_version} RESILIENCIA VALIDADA COM SUCESSO ===")
    print("Next: python -m scripts.load_test_v13 --requests 200 --concurrency 20 --enforce-thresholds")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"resilience smoke test failed: {type(exc).__name__}({exc})", file=sys.stderr)
        raise
