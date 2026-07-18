from __future__ import annotations

import datetime
import ssl

import grpc
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from aecp_platform.errors import UnauthenticatedError
from aecp_platform.identity import AllowList, MTLSConfig, ServiceID, peer_identity


def _write_self_signed_cert(tmp_path, *, name: str, uri_san: str | None = None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.datetime.now(datetime.timezone.utc)

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
    )
    if uri_san:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(uri_san)]),
            critical=False,
        )
    cert = builder.sign(key, hashes.SHA256())

    cert_file = tmp_path / f"{name}.crt"
    key_file = tmp_path / f"{name}.key"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return cert_file, key_file, cert


class TestServiceID:
    def test_service_name_extracts_trailing_segment(self) -> None:
        assert ServiceID("spiffe://aecp/prod/coordinator").service_name() == "coordinator"

    def test_service_name_raises_on_malformed_identity(self) -> None:
        with pytest.raises(ValueError):
            ServiceID("spiffe://").service_name()


class TestMTLSConfig:
    def test_server_and_client_ssl_contexts_build_from_real_certs(self, tmp_path) -> None:
        ca_cert_file, ca_key_file, ca_cert = _write_self_signed_cert(tmp_path, name="ca")
        leaf_cert_file, leaf_key_file, _ = _write_self_signed_cert(
            tmp_path, name="coordinator", uri_san="spiffe://aecp/dev/coordinator"
        )
        ca_file = tmp_path / "ca_bundle.pem"
        ca_file.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))

        config = MTLSConfig(
            self_id=ServiceID("spiffe://aecp/dev/coordinator"),
            cert_file=str(leaf_cert_file),
            key_file=str(leaf_key_file),
            ca_file=str(ca_file),
        )

        server_ctx = config.server_ssl_context()
        assert isinstance(server_ctx, ssl.SSLContext)
        assert server_ctx.verify_mode == ssl.CERT_REQUIRED

        client_ctx = config.client_ssl_context()
        assert isinstance(client_ctx, ssl.SSLContext)
        assert client_ctx.verify_mode == ssl.CERT_REQUIRED
        assert client_ctx.check_hostname is False


class _FakeGrpcContext:
    def __init__(self, auth_context: dict) -> None:
        self._auth_context = auth_context

    def auth_context(self) -> dict:
        return self._auth_context


class TestPeerIdentity:
    def test_extracts_spiffe_uri_from_authenticated_context(self) -> None:
        context = _FakeGrpcContext(
            {
                "transport_security_type": [b"ssl"],
                "x509_subject_alternative_name": [b"spiffe://aecp/dev/agents"],
            }
        )
        assert peer_identity(context) == "spiffe://aecp/dev/agents"

    def test_raises_when_not_ssl(self) -> None:
        context = _FakeGrpcContext({"transport_security_type": [b"tcp"]})
        with pytest.raises(UnauthenticatedError):
            peer_identity(context)

    def test_raises_when_no_transport_security_type(self) -> None:
        context = _FakeGrpcContext({})
        with pytest.raises(UnauthenticatedError):
            peer_identity(context)

    def test_raises_when_ssl_but_no_spiffe_san(self) -> None:
        context = _FakeGrpcContext(
            {
                "transport_security_type": [b"ssl"],
                "x509_subject_alternative_name": [b"not-a-spiffe-uri"],
            }
        )
        with pytest.raises(UnauthenticatedError):
            peer_identity(context)


class TestAllowList:
    def test_contains_bare_names(self) -> None:
        allow_list = AllowList("agents", "gateway")
        assert "agents" in allow_list
        assert "other" not in allow_list

    def test_contains_normalizes_full_spiffe_uris(self) -> None:
        allow_list = AllowList(ServiceID("spiffe://aecp/prod/agents"))
        assert "agents" in allow_list


class _FakeAbortError(Exception):
    def __init__(self, code, details) -> None:
        super().__init__(details)
        self.code = code
        self.details = details


class _FakeInterceptorContext:
    def __init__(self, auth_context: dict, metadata: tuple = ()) -> None:
        self._auth_context = auth_context
        self._metadata = metadata
        self.aborted_with = None

    def auth_context(self) -> dict:
        return self._auth_context

    def invocation_metadata(self):
        return self._metadata

    async def abort(self, code, details=""):
        self.aborted_with = (code, details)
        raise _FakeAbortError(code, details)


class _FakeHandlerCallDetails:
    def __init__(self, method: str) -> None:
        self.method = method


def _fake_handler():
    async def unary_unary(request, context):
        return "ok"

    return grpc.unary_unary_rpc_method_handler(unary_unary)


@pytest.mark.asyncio
class TestAllowListInterceptor:
    async def test_allows_verified_mtls_caller_in_allow_list(self) -> None:
        allow_list = AllowList("agents")
        interceptor = allow_list.grpc_interceptor()

        async def continuation(details):
            return _fake_handler()

        handler = await interceptor.intercept_service(
            continuation, _FakeHandlerCallDetails("/aecp.coordinator.v1.CoordinatorService/Schedule")
        )
        context = _FakeInterceptorContext(
            {
                "transport_security_type": [b"ssl"],
                "x509_subject_alternative_name": [b"spiffe://aecp/dev/agents"],
            }
        )
        result = await handler.unary_unary("request", context)
        assert result == "ok"

    async def test_rejects_verified_mtls_caller_not_in_allow_list(self) -> None:
        allow_list = AllowList("gateway")
        interceptor = allow_list.grpc_interceptor()

        async def continuation(details):
            return _fake_handler()

        handler = await interceptor.intercept_service(
            continuation, _FakeHandlerCallDetails("/aecp.coordinator.v1.CoordinatorService/Schedule")
        )
        context = _FakeInterceptorContext(
            {
                "transport_security_type": [b"ssl"],
                "x509_subject_alternative_name": [b"spiffe://aecp/dev/agents"],
            }
        )
        with pytest.raises(_FakeAbortError) as exc_info:
            await handler.unary_unary("request", context)
        assert exc_info.value.code == grpc.StatusCode.PERMISSION_DENIED

    async def test_falls_back_to_caller_id_metadata_without_mtls(self) -> None:
        allow_list = AllowList("agents")
        interceptor = allow_list.grpc_interceptor()

        async def continuation(details):
            return _fake_handler()

        handler = await interceptor.intercept_service(
            continuation, _FakeHandlerCallDetails("/aecp.coordinator.v1.CoordinatorService/Schedule")
        )
        context = _FakeInterceptorContext({}, metadata=(("caller-id", "agents"),))
        result = await handler.unary_unary("request", context)
        assert result == "ok"

    async def test_reflection_service_is_exempt(self) -> None:
        allow_list = AllowList("agents")
        interceptor = allow_list.grpc_interceptor()

        called = False

        async def continuation(details):
            nonlocal called
            called = True
            return _fake_handler()

        await interceptor.intercept_service(
            continuation, _FakeHandlerCallDetails("/grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo")
        )
        assert called is True
