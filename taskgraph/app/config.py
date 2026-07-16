from __future__ import annotations

"""Taskgraph-specific settings, layered on aecp_platform.config.Loader."""
"""TaskGraph handles the execution workflow (store structure of workflow), State is Runtime Data and artifacts"""


from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

@dataclass
class Settings:
    grpc_port: int
    http_port: int
    postgres_dsn: str
    otel_collector_endpoint: str
    mtls_cert_file: str
    mtls_key_file: str
    mtls_ca_file: str
    allowed_callers: tuple[str, ...]

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

        grpc_port = int(require("TASKGRAPH_GRPC_PORT"))
        http_port = int(require("GATEWAY_HTTP_PORT"))

        if not (1 <= grpc_port <= 65535):
            raise ValueError("TASKGRAPH_GRPC_PORT NOT IN BOUNDS")
        if not (1 <= http_port <= 65535):
            raise ValueError("GATEWAY_HTTP_PORT NOT IN BOUNDS")

        allowed_callers = tuple(
            caller.strip()
            for caller in require("ALLOWED_CALLERS").split(",")
            if caller.strip()
        )
        if not allowed_callers:
            raise ValueError("ALLOWED_CALLERS must contain at least one caller")

        return cls(
            grpc_port=grpc_port,
            http_port=http_port,
            postgres_dsn=require("POSTGRES_DSN"),
            otel_collector_endpoint=require("OTEL_COLLECTOR_ENDPOINT"),
            mtls_cert_file=os.getenv("MTLS_CERT_FILE", ""),
            mtls_key_file=os.getenv("MTLS_KEY_FILE", ""),
            mtls_ca_file=os.getenv("MTLS_CA_FILE", ""),
            allowed_callers=allowed_callers,
            )




