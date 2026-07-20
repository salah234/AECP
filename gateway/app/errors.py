"""Maps internal-service gRPC errors to HTTP responses.

Every router calls through here after an InternalServiceClients call
fails, rather than each router hand-rolling its own grpc.StatusCode ->
HTTP status mapping.
"""

from __future__ import annotations

import grpc
from fastapi import HTTPException

_STATUS_TO_HTTP = {
    grpc.StatusCode.NOT_FOUND: 404,
    grpc.StatusCode.ALREADY_EXISTS: 409,
    grpc.StatusCode.INVALID_ARGUMENT: 400,
    grpc.StatusCode.PERMISSION_DENIED: 403,
    grpc.StatusCode.UNAUTHENTICATED: 401,
    grpc.StatusCode.FAILED_PRECONDITION: 409,
    grpc.StatusCode.RESOURCE_EXHAUSTED: 429,
    grpc.StatusCode.UNAVAILABLE: 503,
    grpc.StatusCode.DEADLINE_EXCEEDED: 504,
}


def grpc_error_to_http(exc: grpc.aio.AioRpcError) -> HTTPException:
    status = _STATUS_TO_HTTP.get(exc.code(), 502)
    return HTTPException(status_code=status, detail=exc.details() or exc.code().name)
