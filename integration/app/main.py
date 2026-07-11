"""Integration service entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="aecp-integration")


@app.get("/healthz")
async def healthz() -> dict:
    raise NotImplementedError


@app.get("/readyz")
async def readyz() -> dict:
    raise NotImplementedError


async def serve_grpc() -> None:
    raise NotImplementedError


def main() -> None:
    """Load Settings, init telemetry, and run the HTTP health server and
    gRPC server concurrently.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
