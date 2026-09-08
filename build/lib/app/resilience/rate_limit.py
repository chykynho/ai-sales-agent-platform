from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_RATE_LIMIT_SCRIPT = r"""
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


@dataclass(slots=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int
    current: int


class RedisRateLimiter:
    def __init__(self, redis_client: Any) -> None:
        self.redis = redis_client

    async def check(self, *, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        raw = await self.redis.eval(_RATE_LIMIT_SCRIPT, 1, key, int(window_seconds))
        current = int(raw[0])
        ttl = max(1, int(raw[1]))
        remaining = max(0, int(limit) - current)
        return RateLimitDecision(
            allowed=current <= int(limit),
            limit=int(limit),
            remaining=remaining,
            retry_after_seconds=ttl,
            current=current,
        )
