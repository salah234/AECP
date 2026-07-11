# syntax=docker/dockerfile:1.7
#
# NOTE: this image runs the Agent Pool *manager*, not the untrusted agent
# workloads it spawns. Agent workloads themselves run in the sandbox image
# referenced by Settings.sandbox_image (see app/sandbox.py) with tighter
# isolation (no outbound egress beyond declared dependencies, ephemeral
# filesystem, per-session network namespace).

FROM python:3.12-slim AS builder
WORKDIR /build
RUN pip install --no-cache-dir uv
COPY platform/ /build/platform/
COPY agents/pyproject.toml agents/
WORKDIR /build/agents
RUN uv venv /opt/venv && uv pip install --python /opt/venv/bin/python .

FROM gcr.io/distroless/python3-debian12:nonroot AS runtime
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY agents/app /app/app
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH="/opt/venv/lib/python3.12/site-packages"
USER nonroot
EXPOSE 8080 50051
ENTRYPOINT ["/opt/venv/bin/python", "-m", "app.main"]
