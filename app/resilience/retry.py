from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int,
    base_delay_seconds: float,
    max_delay_seconds: float,
    jitter_seconds: float,
    should_retry: Callable[[Exception], bool],
    on_retry: Callable[[int, Exception], None] | None = None,
) -> T:
    attempts = max(1, int(max_attempts))
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            if attempt >= attempts or not should_retry(exc):
                raise
            if on_retry is not None:
                on_retry(attempt, exc)
            delay = min(
                max(0.0, max_delay_seconds),
                max(0.0, base_delay_seconds) * (2 ** (attempt - 1)),
            )
            if jitter_seconds > 0:
                delay += random.uniform(0.0, jitter_seconds)
            await asyncio.sleep(delay)
    raise RuntimeError("retry_async terminou em estado impossível")
