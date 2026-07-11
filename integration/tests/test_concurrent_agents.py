"""Conflict logic must be tested with at least two concurrent agents
(see CLAUDE.md Development Workflow #2). Fill in fixtures/assertions
during implementation, do not delete or skip it.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_two_agents_editing_same_invariant_produce_semantic_conflict() -> None:
    """Two agents that each individually produce a valid diff, but whose
    diffs jointly contradict an invariant, must be reported as a semantic
    conflict rather than silently merged.
    """
    raise NotImplementedError
