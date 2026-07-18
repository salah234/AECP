"""Coordinator-specific settings, layered on aecp_platform.config.Loader."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


@dataclass
class Settings:
    grpc_port: int
    http_port: int
    postgres_dsn: str
    taskgraph_addr: str
    state_addr: str
    agents_addr: str
    integration_addr: str
    observability_addr: str
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

        grpc_port = int(require("COORDINATOR_GRPC_PORT"))
        http_port = int(require("COORDINATOR_HTTP_PORT"))

        if not (1 <= grpc_port <= 65535):
            raise ValueError("COORDINATOR_GRPC_PORT NOT IN BOUNDS")
        if not (1 <= http_port <= 65535):
            raise ValueError("COORDINATOR_HTTP_PORT NOT IN BOUNDS")

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
            taskgraph_addr=require("TASKGRAPH_ADDR"),
            state_addr=require("STATE_ADDR"),
            agents_addr=require("AGENTS_ADDR"),
            # integration_addr/observability_addr are required even though
            # /integration's own logic is still all NotImplementedError —
            # Coordinator's IntegrationClient must degrade gracefully at
            # call time (see integration_client.py), not at startup, since
            # the network edge and address are both real
            # (deploy/k8s/networkpolicy/coordinator-edges.yaml).
            integration_addr=require("INTEGRATION_ADDR"),
            observability_addr=require("OBSERVABILITY_ADDR"),
            otel_collector_endpoint=require("OTEL_COLLECTOR_ENDPOINT"),
            mtls_cert_file=os.getenv("MTLS_CERT_FILE", ""),
            mtls_key_file=os.getenv("MTLS_KEY_FILE", ""),
            mtls_ca_file=os.getenv("MTLS_CA_FILE", ""),
            allowed_callers=allowed_callers,
        )
