"""Per-tenant, per-session rate limiting at the gateway edge.

Only enforcement point for external traffic volume; internal service-to-
service calls are not rate limited here (they are bounded by the Agent
Pool's own capacity limits instead).

In-memory token bucket, single-instance only: no shared store (Redis or
similar) is configured for this service, so a multi-replica gateway
deployment would need one before this limiter's counts would be accurate
across replicas. Not a problem this task needs to solve.
"""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self._capacity = requests_per_minute
        self._refill_rate = requests_per_minute / 60.0  # tokens per second
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_refill)
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        """Return whether a request identified by `key` (typically
        "tenant:session") is within the configured rate.
        """
        async with self._lock:
            now = time.monotonic()
            tokens, last_refill = self._buckets.get(key, (float(self._capacity), now))

            elapsed = now - last_refill
            tokens = min(self._capacity, tokens + elapsed * self._refill_rate)

            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return False

            self._buckets[key] = (tokens - 1.0, now)
            return True
