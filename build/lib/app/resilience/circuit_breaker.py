from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.resilience.exceptions import CircuitOpenError


_FAILURE_SCRIPT = r"""
local failures = redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[1])
if failures >= tonumber(ARGV[2]) then
  redis.call('SET', KEYS[2], ARGV[3], 'EX', ARGV[4])
  redis.call('DEL', KEYS[3])
end
return failures
"""


@dataclass(slots=True)
class CircuitBreakerConfig:
    failure_threshold: int
    cooldown_seconds: int
    failure_window_seconds: int
    probe_lock_seconds: int = 10


class RedisCircuitBreaker:
    """Circuit breaker compartilhado entre réplicas usando Redis.

    Redis indisponível deve ser tratado pelo chamador conforme política fail-open.
    """

    def __init__(self, redis_client: Any, *, namespace: str = "resilience:circuit") -> None:
        self.redis = redis_client
        self.namespace = namespace

    def _keys(self, dependency: str) -> tuple[str, str, str]:
        base = f"{self.namespace}:{dependency}"
        return f"{base}:failures", f"{base}:open_until", f"{base}:probe"

    async def before_call(self, dependency: str, config: CircuitBreakerConfig) -> str:
        failures_key, open_key, probe_key = self._keys(dependency)
        del failures_key
        raw = await self.redis.get(open_key)
        if raw is None:
            return "closed"

        now = int(time.time())
        open_until = int(float(raw))
        if open_until > now:
            raise CircuitOpenError(
                f"Circuit breaker de {dependency!r} aberto por mais {open_until - now}s"
            )

        acquired = await self.redis.set(
            probe_key,
            "1",
            ex=max(1, config.probe_lock_seconds),
            nx=True,
        )
        if not acquired:
            raise CircuitOpenError(
                f"Circuit breaker de {dependency!r} aguardando probe half-open"
            )
        return "half_open"

    async def record_success(self, dependency: str) -> None:
        failures_key, open_key, probe_key = self._keys(dependency)
        await self.redis.delete(failures_key, open_key, probe_key)

    async def record_failure(self, dependency: str, config: CircuitBreakerConfig) -> int:
        failures_key, open_key, probe_key = self._keys(dependency)
        now = int(time.time())
        open_until = now + max(1, config.cooldown_seconds)
        raw = await self.redis.eval(
            _FAILURE_SCRIPT,
            3,
            failures_key,
            open_key,
            probe_key,
            max(1, config.failure_window_seconds),
            max(1, config.failure_threshold),
            open_until,
            max(1, config.cooldown_seconds + config.probe_lock_seconds + config.failure_window_seconds),
        )
        return int(raw)

    async def is_open(self, dependency: str) -> bool:
        _failures_key, open_key, _probe_key = self._keys(dependency)
        raw = await self.redis.get(open_key)
        return bool(raw is not None and int(float(raw)) > int(time.time()))
