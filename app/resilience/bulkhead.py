from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

from app.resilience.exceptions import BulkheadRejectedError


@dataclass(slots=True)
class BulkheadConfig:
    limit: int
    acquire_timeout_seconds: float


class AsyncBulkhead:
    def __init__(self, *, name: str, config: BulkheadConfig) -> None:
        self.name = name
        self.config = config
        self._semaphore = asyncio.Semaphore(max(1, config.limit))
        self._in_flight = 0
        self._lock = asyncio.Lock()

    @property
    def in_flight(self) -> int:
        return self._in_flight

    @asynccontextmanager
    async def slot(self):
        acquired = False
        try:
            try:
                await asyncio.wait_for(
                    self._semaphore.acquire(),
                    timeout=max(0.001, self.config.acquire_timeout_seconds),
                )
                acquired = True
            except TimeoutError as exc:
                raise BulkheadRejectedError(
                    f"Bulkhead {self.name!r} sem capacidade disponível"
                ) from exc
            async with self._lock:
                self._in_flight += 1
            yield
        finally:
            if acquired:
                async with self._lock:
                    self._in_flight = max(0, self._in_flight - 1)
                self._semaphore.release()
