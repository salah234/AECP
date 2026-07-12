"""State layer settings, layered on aecp_platform.config.Loader."""

from __future__ import annotations
import os

from dataclasses import dataclass


@dataclass
class Settings:
    grpc_port: int
    http_port: int
    postgres_dsn: str
    object_storage_bucket: str
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

        grpc_port = int(require("GRPC_PORT"))
        http_port = int(require("HTTP_PORT"))

        if not (1 <= grpc_port <= 65535):
            raise ValueError("GRPC_PORT NOT IN BOUNDS")
        if not (1 <= http_port <= 65535):
            raise ValueError("HTTP_PORT NOT IN BOUNDS")
        
        return cls(
            grpc_port=grpc_port,
            http_port=http_port,
            postgres_dsn=require("POSTGRES_DSN"),
            object_storage_bucket=require("OBJECT_STORAGE_BUCKET"), # NEED TO ADD IN .ENV FILE
            otel_collector_endpoint=require("OTEL_COLLECTOR_ENDPOINT"),
            mtls_cert_file=require("MTLS_CERT_FILE"),
            mtls_key_file=require("MTLS_KEY_FILE"),
            mtls_ca_file=require("MTLS_CA_FILE")
            )





    