"""Thin gRPC client wrapper around aecp.agents.v1.AgentPoolService.

Coordinator is the only caller that can populate SpawnSessionRequest's
ownership/task_node_snapshot fields, since it is the only service with a
TaskGraph edge (see docs/adr/0007-agent-pool-has-no-taskgraph-edge.md).
AssignmentEngine.assign() is the sole caller of spawn_session; it must
always pass both fields — Agent Pool has no fallback path to fetch them
itself.
"""

from __future__ import annotations

import grpc

from app.agents.v1 import agents_pb2, agents_pb2_grpc
from app.channels import caller_metadata
from app.common.v1 import common_pb2


class AgentPoolClient:
    def __init__(self, channel: grpc.aio.Channel, caller_id: str = "coordinator") -> None:
        self._stub = agents_pb2_grpc.AgentPoolServiceStub(channel)
        self._metadata = caller_metadata(caller_id)

    async def spawn_session(
        self,
        *,
        tenant_id: str,
        task_id: str,
        granted_risk_tier: "common_pb2.RiskTier",
        ownership: "common_pb2.OwnershipBoundary",
        task_node_snapshot: bytes,
    ) -> agents_pb2.AgentSession:
        response = await self._stub.SpawnSession(
            agents_pb2.SpawnSessionRequest(
                tenant_id=tenant_id,
                task_id=task_id,
                granted_risk_tier=granted_risk_tier,
                ownership=ownership,
                task_node_snapshot=task_node_snapshot,
            ),
            metadata=self._metadata,
        )
        return response.session

    async def terminate_session(self, session_id: str, reason: str) -> bool:
        response = await self._stub.TerminateSession(
            agents_pb2.TerminateSessionRequest(session_id=session_id, reason=reason),
            metadata=self._metadata,
        )
        return response.terminated
