from __future__ import annotations

import asyncio

import pytest

from app.rate_limit import RateLimiter


@pytest.mark.asyncio
async def test_allows_up_to_capacity_then_denies():
    limiter = RateLimiter(requests_per_minute=3)

    results = [await limiter.allow("tenant-a:user-1") for _ in range(4)]

    assert results == [True, True, True, False]


@pytest.mark.asyncio
async def test_buckets_are_independent_per_key():
    limiter = RateLimiter(requests_per_minute=1)

    assert await limiter.allow("tenant-a:user-1") is True
    assert await limiter.allow("tenant-a:user-1") is False
    assert await limiter.allow("tenant-b:user-2") is True


@pytest.mark.asyncio
async def test_concurrent_callers_never_exceed_capacity():
    limiter = RateLimiter(requests_per_minute=5)

    results = await asyncio.gather(*[limiter.allow("tenant-a:user-1") for _ in range(20)])

    assert sum(1 for allowed in results if allowed) == 5
