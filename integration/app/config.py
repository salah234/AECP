"""Integration layer settings, layered on aecp_platform.config.Loader."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Settings:
    grpc_port: int
    http_port: int
    taskgraph_addr: str
    state_addr: str
    otel_collector_endpoint: str
    mtls_cert_file: str
    mtls_key_file: str
    mtls_ca_file: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Load and validate settings from the environment, failing closed
        on any missing/invalid required value.
        """
        raise NotImplementedError
