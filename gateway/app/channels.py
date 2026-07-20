"""mTLS client channel construction for calling internal services.

Mirrors coordinator/app/channels.py (every service duplicates this rather
than sharing it — see that file's own docstring), falling back to an
insecure channel when no mTLS files are configured (dev/local). Every
outbound call attaches a caller-id metadata entry so the allow-list on the
far end can authorize gateway even when no verified mTLS peer identity is
available (see aecp_platform.identity.AllowList's interim metadata
fallback).
"""

from __future__ import annotations

from pathlib import Path

import grpc

CALLER_ID_METADATA_KEY = "caller-id"


def build_client_channel(
    target: str,
    *,
    mtls_cert_file: str,
    mtls_key_file: str,
    mtls_ca_file: str,
) -> grpc.aio.Channel:
    if mtls_cert_file and mtls_key_file and mtls_ca_file:
        credentials = grpc.ssl_channel_credentials(
            root_certificates=Path(mtls_ca_file).read_bytes(),
            private_key=Path(mtls_key_file).read_bytes(),
            certificate_chain=Path(mtls_cert_file).read_bytes(),
        )
        return grpc.aio.secure_channel(target, credentials)

    return grpc.aio.insecure_channel(target)


def caller_metadata(caller_id: str) -> tuple[tuple[str, str], ...]:
    return ((CALLER_ID_METADATA_KEY, caller_id),)
