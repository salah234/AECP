"""Tests for AllowListInterceptor.

No existing interceptor test file exists elsewhere in the repo to mirror
(taskgraph and agents implement the same interceptor but don't yet test it
directly either), so this constructs a minimal handler_call_details-shaped
stand-in directly, matching the two attributes AllowListInterceptor.
intercept_service actually reads: .method and .invocation_metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import grpc
import pytest

from app.interceptors import AllowListInterceptor

from .fakes import AbortedRPC, FakeContext


@dataclass
class _FakeHandlerCallDetails:
    method: str
    invocation_metadata: tuple[tuple[str, str], ...] = field(default_factory=tuple)


async def _continuation(_handler_call_details):
    return "REAL_HANDLER"


async def test_allows_caller_in_allow_list() -> None:
    interceptor = AllowListInterceptor(["agent-pool"])
    details = _FakeHandlerCallDetails(
        method="/aecp.state.v1.StateService/GetOwnership",
        invocation_metadata=(("caller-id", "agent-pool"),),
    )

    result = await interceptor.intercept_service(_continuation, details)

    assert result == "REAL_HANDLER"


async def test_rejects_caller_not_in_allow_list() -> None:
    interceptor = AllowListInterceptor(["agent-pool"])
    details = _FakeHandlerCallDetails(
        method="/aecp.state.v1.StateService/GetOwnership",
        invocation_metadata=(("caller-id", "some-other-caller"),),
    )

    handler = await interceptor.intercept_service(_continuation, details)

    assert handler != "REAL_HANDLER"

    context = FakeContext()
    with pytest.raises(AbortedRPC) as exc_info:
        await handler.unary_unary(request=None, context=context)

    assert exc_info.value.code == grpc.StatusCode.PERMISSION_DENIED


async def test_rejects_caller_with_no_caller_id_metadata_at_all() -> None:
    interceptor = AllowListInterceptor(["agent-pool"])
    details = _FakeHandlerCallDetails(
        method="/aecp.state.v1.StateService/GetOwnership",
        invocation_metadata=(),
    )

    handler = await interceptor.intercept_service(_continuation, details)

    context = FakeContext()
    with pytest.raises(AbortedRPC) as exc_info:
        await handler.unary_unary(request=None, context=context)

    assert exc_info.value.code == grpc.StatusCode.PERMISSION_DENIED


async def test_exempts_grpc_reflection_v1alpha_service_path() -> None:
    interceptor = AllowListInterceptor(["agent-pool"])
    details = _FakeHandlerCallDetails(
        method="/grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo",
        invocation_metadata=(),  # no caller-id at all
    )

    result = await interceptor.intercept_service(_continuation, details)

    assert result == "REAL_HANDLER"


async def test_exempts_grpc_reflection_v1_service_path() -> None:
    interceptor = AllowListInterceptor(["agent-pool"])
    details = _FakeHandlerCallDetails(
        method="/grpc.reflection.v1.ServerReflection/ServerReflectionInfo",
        invocation_metadata=(),
    )

    result = await interceptor.intercept_service(_continuation, details)

    assert result == "REAL_HANDLER"
