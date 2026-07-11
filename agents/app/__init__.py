"""Agent Pool: agent lifecycle management.

Spin-up, context hydration, handoff, and teardown for agent worker
sessions. Every session is disposable and stateless — an agent that dies
or times out mid-task must be resumable by a different instance with no
loss of continuity, because all durable knowledge lives in the State
Layer, never in a session's own scratch context.
"""
