from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
from dataclasses import dataclass

import httpx

from app.core.config import settings

BASE = "http://127.0.0.1:8000"
API = BASE + "/api/v1"


@dataclass(slots=True)
class Sample:
    status_code: int
    latency_ms: float
    error: str | None = None


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil((pct / 100) * len(ordered)) - 1))
    return ordered[idx]


async def login(client: httpx.AsyncClient) -> str:
    response = await client.post(
        API + "/auth/login",
        headers={"X-Tenant-Slug": settings.bootstrap_tenant_slug},
        data={
            "username": settings.bootstrap_admin_email,
            "password": settings.bootstrap_admin_password,
        },
    )
    response.raise_for_status()
    token = str(response.json().get("access_token") or "")
    if not token:
        raise RuntimeError("Login nao retornou access_token")
    return token


async def run_load(*, total: int, concurrency: int, path: str) -> dict:
    limits = httpx.Limits(
        max_connections=max(10, concurrency * 2),
        max_keepalive_connections=max(10, concurrency),
    )
    async with httpx.AsyncClient(timeout=20.0, limits=limits) as client:
        token = await login(client)
        headers = {"Authorization": "Bearer " + token, "X-Load-Test-Profile": "v013-safe"}
        semaphore = asyncio.Semaphore(max(1, concurrency))
        samples: list[Sample] = []

        async def one_request(index: int) -> None:
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.get(API + path, headers={**headers, "X-Request-ID": f"v013-load-{index}"})
                    latency = (time.perf_counter() - started) * 1000
                    samples.append(Sample(response.status_code, latency))
                except Exception as exc:
                    latency = (time.perf_counter() - started) * 1000
                    samples.append(Sample(0, latency, str(exc)))

        started_all = time.perf_counter()
        await asyncio.gather(*(one_request(i) for i in range(total)))
        wall_seconds = max(0.0001, time.perf_counter() - started_all)

    latencies = [s.latency_ms for s in samples]
    failures = [s for s in samples if s.status_code < 200 or s.status_code >= 400]
    error_rate = (len(failures) / max(1, len(samples))) * 100
    statuses: dict[str, int] = {}
    for sample in samples:
        key = str(sample.status_code)
        statuses[key] = statuses.get(key, 0) + 1

    return {
        "profile": "v013-safe",
        "path": path,
        "requests": len(samples),
        "concurrency": concurrency,
        "duration_seconds": round(wall_seconds, 3),
        "throughput_rps": round(len(samples) / wall_seconds, 2),
        "latency_ms": {
            "min": round(min(latencies), 3) if latencies else 0,
            "avg": round(statistics.mean(latencies), 3) if latencies else 0,
            "p50": round(percentile(latencies, 50), 3),
            "p95": round(percentile(latencies, 95), 3),
            "p99": round(percentile(latencies, 99), 3),
            "max": round(max(latencies), 3) if latencies else 0,
        },
        "error_rate_pct": round(error_rate, 3),
        "status_codes": statuses,
        "thresholds": {
            "p95_ms": settings.load_test_p95_threshold_ms,
            "error_rate_pct": settings.load_test_error_rate_threshold_pct,
        },
    }


async def amain() -> int:
    parser = argparse.ArgumentParser(description="Load test seguro da AI Sales Agent Platform v0.13")
    parser.add_argument("--requests", type=int, default=settings.load_test_requests)
    parser.add_argument("--concurrency", type=int, default=settings.load_test_concurrency)
    parser.add_argument("--path", default="/users/me")
    parser.add_argument("--enforce-thresholds", action="store_true")
    args = parser.parse_args()

    total = max(1, args.requests)
    concurrency = max(1, min(args.concurrency, total))
    result = await run_load(total=total, concurrency=concurrency, path=args.path)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.enforce_thresholds:
        if result["error_rate_pct"] > settings.load_test_error_rate_threshold_pct:
            raise AssertionError(
                f"Error rate {result['error_rate_pct']}% acima de {settings.load_test_error_rate_threshold_pct}%"
            )
        if result["latency_ms"]["p95"] > settings.load_test_p95_threshold_ms:
            raise AssertionError(
                f"p95 {result['latency_ms']['p95']}ms acima de {settings.load_test_p95_threshold_ms}ms"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
