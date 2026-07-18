from __future__ import annotations

import pytest

from app.statemachine import (
    TASK_STATE_FROM_PROTO,
    TASK_STATE_TO_PROTO,
    InvalidTransitionError,
    TaskState,
    TaskStateMachine,
)


def test_initial_state_defaults_to_pending() -> None:
    sm = TaskStateMachine("task-1")
    assert sm.state is TaskState.PENDING


def test_happy_path_pending_to_done() -> None:
    sm = TaskStateMachine("task-1")
    assert sm.apply("assign") is TaskState.ASSIGNED
    assert sm.apply("start_progress") is TaskState.IN_PROGRESS
    assert sm.apply("complete") is TaskState.IN_REVIEW
    assert sm.apply("approve") is TaskState.DONE


def test_blocked_task_returns_to_pending_and_can_be_reassigned() -> None:
    sm = TaskStateMachine("task-1")
    sm.apply("assign")
    sm.apply("start_progress")
    assert sm.apply("report_blocker") is TaskState.BLOCKED
    assert sm.apply("unblock") is TaskState.PENDING
    assert sm.apply("assign") is TaskState.ASSIGNED


def test_escalation_approved_resumes_in_progress() -> None:
    sm = TaskStateMachine("task-1")
    sm.apply("assign")
    sm.apply("start_progress")
    assert sm.apply("escalate") is TaskState.ESCALATED
    assert sm.apply("approve_escalation") is TaskState.IN_PROGRESS


def test_escalation_denied_blocks_rather_than_silently_proceeding() -> None:
    sm = TaskStateMachine("task-1")
    sm.apply("assign")
    sm.apply("start_progress")
    sm.apply("escalate")
    assert sm.apply("deny_escalation") is TaskState.BLOCKED


def test_review_can_request_changes_back_to_in_progress() -> None:
    sm = TaskStateMachine("task-1")
    sm.apply("assign")
    sm.apply("start_progress")
    sm.apply("complete")
    assert sm.apply("request_changes") is TaskState.IN_PROGRESS


@pytest.mark.parametrize("terminal_state", [TaskState.DONE, TaskState.ABANDONED])
def test_terminal_states_have_no_outgoing_transitions(terminal_state: TaskState) -> None:
    sm = TaskStateMachine("task-1", initial=terminal_state)
    for event in ("assign", "block", "abandon", "complete", "approve"):
        with pytest.raises(InvalidTransitionError):
            sm.apply(event)


def test_undefined_transition_raises_and_does_not_mutate_state() -> None:
    sm = TaskStateMachine("task-1")
    with pytest.raises(InvalidTransitionError):
        sm.apply("complete")
    # State must be unchanged after a rejected transition.
    assert sm.state is TaskState.PENDING


def test_proto_mapping_is_total_and_bijective() -> None:
    assert set(TASK_STATE_TO_PROTO) == set(TaskState)
    assert TASK_STATE_FROM_PROTO == {v: k for k, v in TASK_STATE_TO_PROTO.items()}
    for state, proto_value in TASK_STATE_TO_PROTO.items():
        assert TASK_STATE_FROM_PROTO[proto_value] is state
