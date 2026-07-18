"""Thin gRPC client wrapper around aecp.integration.v1.IntegrationService.

/integration's own servicer is not implemented yet (its build_server still
raises NotImplementedError), so calls made through this client will fail
with a transport-level error (UNAVAILABLE) rather than a structured
response until that lands. detect_conflicts() returns None on any RPC
failure instead of raising, so Scheduler can degrade gracefully — proceed
on ownership-boundary checks alone — rather than fail every tick on a
dependency that doesn't exist yet. This is a deliberate, logged
degradation, not a silent one: see scheduler.py's use of this return
value.
"""

from __future__ import annotations

import logging

import grpc

from app.channels import caller_metadata
from app.integration.v1 import integration_pb2, integration_pb2_grpc

logger = logging.getLogger(__name__)


class IntegrationClient:
    def __init__(self, channel: grpc.aio.Channel, caller_id: str = "coordinator") -> None:
        self._stub = integration_pb2_grpc.IntegrationServiceStub(channel)
        self._metadata = caller_metadata(caller_id)

    async def detect_conflicts(
        self, tenant_id: str, candidate_task_ids: list[str]
    ) -> list[integration_pb2.ConflictReport] | None:
        """Return conflict reports for the given candidate task ids, or
        None if the Integration service could not be reached / has not
        been implemented yet.
        """
        try:
            response = await self._stub.DetectConflicts(
                integration_pb2.DetectConflictsRequest(
                    tenant_id=tenant_id, candidate_task_ids=candidate_task_ids
                ),
                metadata=self._metadata,
            )
        except grpc.aio.AioRpcError as exc:
            logger.warning(
                "IntegrationService.DetectConflicts unavailable (%s); "
                "scheduling tick %s candidate(s) on ownership-boundary "
                "checks alone.",
                exc.code(),
                len(candidate_task_ids),
            )
            return None
        return list(response.reports)
