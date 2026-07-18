"""Explicit state machine for task node lifecycle.

CLAUDE.md favors explicit state machines over implicit control flow for
this repo's own coordination logic — correctness of sequencing matters
more than throughput here. Every transition below must be an intentional,
named edge; there is no catch-all default transition.

This mirrors aecp.common.v1.TaskStatus (the wire enum TaskGraph persists)
but is the Coordinator's own authoritative sequencing logic: Scheduler,
AssignmentEngine, and TradeoffResolver drive it by name (see their calls
to TaskStateMachine.apply), and the resulting state is what gets pushed
back to TaskGraphService.UpdateTaskStatus — never the other way around.
"""

from __future__ import annotations

from enum import Enum, auto

from app.common.v1 import common_pb2


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


# The explicit transition table. Any (from_state, event) pair not present
# here must raise InvalidTransitionError rather than silently no-op.
#
#   PENDING  --assign--------------> ASSIGNED
#   PENDING  --block---------------> BLOCKED
#   BLOCKED  --unblock-------------> PENDING     (re-enters the ready queue)
#   ASSIGNED --start_progress------> IN_PROGRESS (Agent Pool confirmed spawn)
#   ASSIGNED --report_blocker------> BLOCKED     (spawn failed / immediate blocker)
#   ASSIGNED --escalate------------> ESCALATED   (agent found task too big at hydration)
#   IN_PROGRESS --complete---------> IN_REVIEW
#   IN_PROGRESS --report_blocker---> BLOCKED
#   IN_PROGRESS --escalate---------> ESCALATED
#   IN_REVIEW --approve------------> DONE
#   IN_REVIEW --request_changes----> IN_PROGRESS
#   IN_REVIEW --reject-------------> ABANDONED
#   ESCALATED --approve_escalation-> IN_PROGRESS (TradeoffResolver approved the bump)
#   ESCALATED --deny_escalation----> BLOCKED     (must wait on a human, not proceed)
#   * --abandon---------------------> ABANDONED  (from any non-terminal state)
#
# DONE and ABANDONED are terminal: no outgoing edges.
TRANSITIONS: dict[tuple[TaskState, str], TaskState] = {
    (TaskState.PENDING, "assign"): TaskState.ASSIGNED,
    (TaskState.PENDING, "block"): TaskState.BLOCKED,
    (TaskState.PENDING, "abandon"): TaskState.ABANDONED,
    (TaskState.BLOCKED, "unblock"): TaskState.PENDING,
    (TaskState.BLOCKED, "abandon"): TaskState.ABANDONED,
    (TaskState.ASSIGNED, "start_progress"): TaskState.IN_PROGRESS,
    (TaskState.ASSIGNED, "report_blocker"): TaskState.BLOCKED,
    (TaskState.ASSIGNED, "escalate"): TaskState.ESCALATED,
    (TaskState.ASSIGNED, "abandon"): TaskState.ABANDONED,
    (TaskState.IN_PROGRESS, "complete"): TaskState.IN_REVIEW,
    (TaskState.IN_PROGRESS, "report_blocker"): TaskState.BLOCKED,
    (TaskState.IN_PROGRESS, "escalate"): TaskState.ESCALATED,
    (TaskState.IN_PROGRESS, "abandon"): TaskState.ABANDONED,
    (TaskState.IN_REVIEW, "approve"): TaskState.DONE,
    (TaskState.IN_REVIEW, "request_changes"): TaskState.IN_PROGRESS,
    (TaskState.IN_REVIEW, "reject"): TaskState.ABANDONED,
    (TaskState.ESCALATED, "approve_escalation"): TaskState.IN_PROGRESS,
    (TaskState.ESCALATED, "deny_escalation"): TaskState.BLOCKED,
    (TaskState.ESCALATED, "abandon"): TaskState.ABANDONED,
}


class TaskStateMachine:
    """Wraps a single task node's lifecycle state and enforces the
    transition table above.
    """

    def __init__(self, task_id: str, initial: TaskState = TaskState.PENDING) -> None:
        self.task_id = task_id
        self._state = initial

    @property
    def state(self) -> TaskState:
        return self._state

    def apply(self, event: str) -> TaskState:
        """Apply a named event, returning the new state.

        Raises InvalidTransitionError if the current state has no defined
        edge for this event.
        """
        key = (self._state, event)
        if key not in TRANSITIONS:
            raise InvalidTransitionError(
                f"Task '{self.task_id}': no transition for event "
                f"'{event}' from state {self._state.name}"
            )

        self._state = TRANSITIONS[key]
        return self._state


# Bridges this module's own TaskState to the aecp.common.v1.TaskStatus
# wire enum TaskGraphService persists. Coordinator drives sequencing
# here, then pushes the result to TaskGraph via UpdateTaskStatus — never
# the reverse — so these two enums must always agree.
TASK_STATE_TO_PROTO: dict[TaskState, "common_pb2.TaskStatus"] = {
    TaskState.PENDING: common_pb2.TASK_STATUS_PENDING,
    TaskState.BLOCKED: common_pb2.TASK_STATUS_BLOCKED,
    TaskState.ASSIGNED: common_pb2.TASK_STATUS_ASSIGNED,
    TaskState.IN_PROGRESS: common_pb2.TASK_STATUS_IN_PROGRESS,
    TaskState.IN_REVIEW: common_pb2.TASK_STATUS_IN_REVIEW,
    TaskState.ESCALATED: common_pb2.TASK_STATUS_ESCALATED,
    TaskState.DONE: common_pb2.TASK_STATUS_DONE,
    TaskState.ABANDONED: common_pb2.TASK_STATUS_ABANDONED,
}
TASK_STATE_FROM_PROTO: dict["common_pb2.TaskStatus", TaskState] = {
    value: key for key, value in TASK_STATE_TO_PROTO.items()
}
