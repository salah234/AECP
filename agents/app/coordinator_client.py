"""Thin gRPC client wrapper around aecp.coordinator.v1.CoordinatorService.

Agent Pool only ever calls ReportBlocker today: when LifecycleManager
reaps a session past its TTL (see main.py's reap loop), that is reported
to the Coordinator as a blocked task so it can be rescheduled.
CoordinatorService has no dedicated "session reaped, please reschedule"
RPC — only Schedule, Escalate, and ReportBlocker exist
(proto/coordinator/v1/coordinator.proto). ReportBlocker is the closest
existing semantic fit (an agent-side actor reporting it cannot make
progress on a task) and is reused here rather than unilaterally extending
coordinator.proto, which is owned by /coordinator's own implementation,
not by /agents.
"""

from __future__ import annotations

import grpc

from app.channels import caller_metadata
from app.coordinator.v1 import coordinator_pb2, coordinator_pb2_grpc


class CoordinatorClient:
    def __init__(self, channel: grpc.aio.Channel, caller_id: str = "agents") -> None:
        self._stub = coordinator_pb2_grpc.CoordinatorServiceStub(channel)
        self._metadata = caller_metadata(caller_id)

    async def report_blocker(
        self, *, task_id: str, agent_id: str, description: str
    ) -> bool:
        response = await self._stub.ReportBlocker(
            coordinator_pb2.ReportBlockerRequest(
                task_id=task_id, agent_id=agent_id, description=description
            ),
            metadata=self._metadata,
        )
        return response.acknowledged
