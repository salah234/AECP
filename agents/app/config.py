"""Agent pool settings, layered on aecp_platform.config.Loader."""

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
    state_addr: str
    coordinator_addr: str
    session_ttl_seconds: int
    sandbox_image: str
    otel_collector_endpoint: str
    mtls_cert_file: str
    mtls_key_file: str
    mtls_ca_file: str
    allowed_callers: tuple[str, ...]
    # Real agent execution (agents/app/executor.py). All optional/secret-shaped
    # (never require()'d): unset means SpawnSession bookkeeping still works,
    # but AgentExecutor reports a blocker instead of running claude — see
    # executor.py's _run. anthropic_api_key mirrors gateway/app/config.py's
    # session_secret_key precedent: read directly via os.getenv pending
    # docs/adr/0006-secrets-management.md, never a required value.
    anthropic_api_key: str
    agent_model: str
    agent_permission_mode: str
    agent_allowed_tools: str
    agent_execution_timeout_seconds: int
    claude_binary: str
    target_repo_path: str
    target_repo_url: str
    # Which ExecutionBackend main.py wires into AgentExecutor (see
    # agents/app/execution_backends/) — "claude_cli" (default) or "cohere".
    # cohere_api_key mirrors anthropic_api_key's convention: optional,
    # secret-shaped, never require()'d.
    agent_execution_backend: str
    cohere_api_key: str
    cohere_model: str
    cohere_max_tool_iterations: int

    # Deliberately no taskgraph_addr: Agent Pool has no network or client
    # edge to TaskGraphService (deploy/k8s/networkpolicy/agents-edges.yaml
    # permits only Coordinator and State). See
    # docs/adr/0007-agent-pool-has-no-taskgraph-edge.md.

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

        grpc_port = int(require("AGENTS_GRPC_PORT"))
        http_port = int(require("AGENTS_HTTP_PORT"))
        session_ttl_seconds = int(require("SESSION_TTL_SECONDS"))

        if not (1 <= grpc_port <= 65535):
            raise ValueError("AGENTS_GRPC_PORT NOT IN BOUNDS")
        if not (1 <= http_port <= 65535):
            raise ValueError("AGENTS_HTTP_PORT NOT IN BOUNDS")
        if session_ttl_seconds <= 0:
            raise ValueError("SESSION_TTL_SECONDS must be positive")

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
            state_addr=require("STATE_ADDR"),
            coordinator_addr=require("COORDINATOR_ADDR"),
            session_ttl_seconds=session_ttl_seconds,
            sandbox_image=require("SANDBOX_IMAGE"),
            otel_collector_endpoint=require("OTEL_COLLECTOR_ENDPOINT"),
            mtls_cert_file=os.getenv("MTLS_CERT_FILE", ""),
            mtls_key_file=os.getenv("MTLS_KEY_FILE", ""),
            mtls_ca_file=os.getenv("MTLS_CA_FILE", ""),
            allowed_callers=allowed_callers,
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            agent_model=os.getenv("AGENT_MODEL", "sonnet"),
            agent_permission_mode=os.getenv("AGENT_PERMISSION_MODE", "acceptEdits"),
            agent_allowed_tools=os.getenv("AGENT_ALLOWED_TOOLS", "Read Edit Write Bash(git *)"),
            agent_execution_timeout_seconds=int(
                os.getenv("AGENT_EXECUTION_TIMEOUT_SECONDS", "1800")
            ),
            claude_binary=os.getenv("CLAUDE_BINARY", "claude"),
            target_repo_path=os.getenv("TARGET_REPO_PATH", ""),
            target_repo_url=os.getenv("TARGET_REPO_URL", ""),
            agent_execution_backend=os.getenv("AGENT_EXECUTION_BACKEND", "claude_cli"),
            cohere_api_key=os.getenv("COHERE_API_KEY", ""),
            cohere_model=os.getenv("COHERE_MODEL", "command-a-03-2025"),
            cohere_max_tool_iterations=int(os.getenv("COHERE_MAX_TOOL_ITERATIONS", "20")),
        )
