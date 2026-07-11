"""Explicit state machine for task node lifecycle.

CLAUDE.md favors explicit state machines over implicit control flow for
this repo's own coordination logic — correctness of sequencing matters
more than throughput here. Every transition below must be an intentional,
named edge; there is no catch-all default transition.
"""

from __future__ import annotations

from enum import Enum, auto


class TaskState(Enum):
    PENDING = auto()
    BLOCKED = auto()
    ASSIGNED = auto()
    IN_PROGRESS = auto()
    IN_REVIEW = auto()
    ESCALATED = auto()
    DONE = auto()
    ABANDONED = auto()


class InvalidTransitionError(Exception):
    """Raised when a requested state transition has no defined edge."""


# The explicit transition table. Populated during implementation; any
# (from_state, event) pair not present here must raise
# InvalidTransitionError rather than silently no-op.
TRANSITIONS: dict[tuple[TaskState, str], TaskState] = {}


class TaskStateMachine:
    """Wraps a single task node's lifecycle state and enforces the
    transition table above.
    """

    def __init__(self, task_id: str, initial: TaskState = TaskState.PENDING) -> None:
        raise NotImplementedError

    @property
    def state(self) -> TaskState:
        raise NotImplementedError

    def apply(self, event: str) -> TaskState:
        """Apply a named event, returning the new state.

        Raises InvalidTransitionError if the current state has no defined
        edge for this event.
        """
        raise NotImplementedError
