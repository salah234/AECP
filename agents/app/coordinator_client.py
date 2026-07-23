"""Thin gRPC client wrapper around aecp.coordinator.v1.CoordinatorService.

Agent Pool calls ReportBlocker when LifecycleManager reaps a session past
its TTL (see main.py's reap loop) or when AgentExecutor's real `claude`
run fails/times out, so the task can be rescheduled. It calls
ReportCompletion when AgentExecutor's run succeeds, so Coordinator can
move the task to TASK_STATUS_IN_REVIEW (see coordinator/app/tradeoff.py's
report_completion for why not straight to DONE) and record the agent's
summary/rationale to the decision log.
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
        self, *, task_id: str, tenant_id: str, agent_id: str, description: str
    ) -> bool:
        response = await self._stub.ReportBlocker(
            coordinator_pb2.ReportBlockerRequest(
                task_id=task_id,
                tenant_id=tenant_id,
                agent_id=agent_id,
                description=description,
            ),
            metadata=self._metadata,
        )
        return response.acknowledged

    async def report_completion(
        self, *, task_id: str, tenant_id: str, agent_id: str, summary: str, rationale: str
    ) -> bool:
        response = await self._stub.ReportCompletion(
            coordinator_pb2.ReportCompletionRequest(
                task_id=task_id,
                tenant_id=tenant_id,
                agent_id=agent_id,
                summary=summary,
                rationale=rationale,
            ),
            metadata=self._metadata,
        )
        return response.acknowledged
