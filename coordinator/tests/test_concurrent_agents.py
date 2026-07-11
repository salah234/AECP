"""Scheduling logic must be tested with at least two concurrent agents
(see CLAUDE.md Development Workflow #2). This is the required test; fill
in fixtures/assertions during implementation, do not delete or skip it.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_scheduler_does_not_double_assign_overlapping_ownership() -> None:
    """Two ready task nodes with overlapping ownership boundaries must
    never both be assigned in the same schedule tick.
    """
    raise NotImplementedError
