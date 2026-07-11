"""Gateway settings, layered on aecp_platform.config.Loader."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Settings:
    http_port: int
    session_secret_key: str  # loaded via aecp_platform.secrets, never a literal env default
    oidc_issuer_url: str
    oidc_client_id: str
    oidc_client_secret_key: str  # secrets.Provider key, not the secret itself
    oidc_redirect_url: str
    coordinator_addr: str
    taskgraph_addr: str
    state_addr: str
    integration_addr: str
    observability_addr: str
    rate_limit_requests_per_minute: int
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
