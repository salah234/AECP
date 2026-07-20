"""Gateway settings.

Follows the same hand-rolled Settings.from_env() pattern every other
service uses (see coordinator/app/config.py) rather than
aecp_platform.config.Loader, which has no working implementation or
precedent anywhere in this repo yet. session_secret_key/
oidc_client_secret_key are read from the environment the same way every
other "secret-shaped" setting in the codebase is today
(aecp_platform.secrets has no working SecretProvider either) — see
docs/adr/0006-secrets-management.md for why this is provisional, not a
production-ready secrets story.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


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

        def require(name: str) -> str:
            value = os.getenv(name)
            if value is None or value.strip() == "":
                raise ValueError(f"Missing required environment variable: {name}")
            return value

        http_port = int(require("GATEWAY_HTTP_PORT"))
        if not (1 <= http_port <= 65535):
            raise ValueError("GATEWAY_HTTP_PORT NOT IN BOUNDS")

        rate_limit_requests_per_minute = int(require("RATE_LIMIT_REQUESTS_PER_MINUTE"))
        if rate_limit_requests_per_minute <= 0:
            raise ValueError("RATE_LIMIT_REQUESTS_PER_MINUTE must be positive")

        return cls(
            http_port=http_port,
            session_secret_key=require("GATEWAY_SESSION_SECRET_KEY"),
            oidc_issuer_url=require("OIDC_ISSUER_URL"),
            oidc_client_id=require("OIDC_CLIENT_ID"),
            oidc_client_secret_key=require("OIDC_CLIENT_SECRET"),
            oidc_redirect_url=require("OIDC_REDIRECT_URL"),
            coordinator_addr=require("COORDINATOR_ADDR"),
            taskgraph_addr=require("TASKGRAPH_ADDR"),
            state_addr=require("STATE_ADDR"),
            integration_addr=require("INTEGRATION_ADDR"),
            observability_addr=require("OBSERVABILITY_ADDR"),
            rate_limit_requests_per_minute=rate_limit_requests_per_minute,
            otel_collector_endpoint=require("OTEL_COLLECTOR_ENDPOINT"),
            mtls_cert_file=os.getenv("MTLS_CERT_FILE", ""),
            mtls_key_file=os.getenv("MTLS_KEY_FILE", ""),
            mtls_ca_file=os.getenv("MTLS_CA_FILE", ""),
        )
