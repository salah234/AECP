"""REST surface over CoordinatorService.Schedule, scoped to the caller's
tenant — the "invoke an agent" action.

Per agents.py's own docstring, session spawn is Coordinator-driven only;
the dashboard never calls AgentPoolService directly. Schedule is the
real primitive: it assigns every ready task node for the tenant to an
agent, so a human "invoking an agent" from the dashboard is really
triggering a scheduling pass, not hand-picking a session. The returned
trace_id (see aecp_platform.telemetry.current_trace_id_hex) is this
request's own span id, rooted by main.py's tracing_middleware and
propagated through Coordinator -> Agent Pool -> State by
TracingClientInterceptor/TracingServerInterceptor — the dashboard can
paste it straight into Jaeger to watch the whole assignment land.
"""

from __future__ import annotations

import grpc
from fastapi import APIRouter, Depends

from aecp_platform.telemetry import current_trace_id_hex
from app.coordinator.v1 import coordinator_pb2
from app.deps import RequestContext, get_clients, get_request_context
from app.errors import grpc_error_to_http
from app.schemas import assignment_decision_to_dict

router = APIRouter(prefix="/api/v1/coordinator", tags=["coordinator"])


@router.post("/schedule")
async def schedule(
    ctx: RequestContext = Depends(get_request_context),
    clients=Depends(get_clients),
):
    try:
        response = await clients.coordinator().Schedule(
            coordinator_pb2.ScheduleRequest(tenant_id=ctx.tenant_id),
            metadata=clients.metadata(ctx.tenant_id),
        )
    except grpc.aio.AioRpcError as exc:
        raise grpc_error_to_http(exc) from exc

    return {
        "decisions": [assignment_decision_to_dict(d) for d in response.decisions],
        "traceId": current_trace_id_hex(),
    }
