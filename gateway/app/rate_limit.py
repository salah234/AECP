"""Per-tenant, per-session rate limiting at the gateway edge.

Only enforcement point for external traffic volume; internal service-to-
service calls are not rate limited here (they are bounded by the Agent
Pool's own capacity limits instead).
"""

from __future__ import annotations


class RateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        raise NotImplementedError

    async def allow(self, key: str) -> bool:
        """Return whether a request identified by `key` (typically
        "tenant:session") is within the configured rate.
        """
        raise NotImplementedError
