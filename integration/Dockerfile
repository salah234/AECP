# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder
WORKDIR /build
RUN pip install --no-cache-dir uv
COPY platform/ /build/platform/
COPY integration/pyproject.toml integration/
WORKDIR /build/integration
# --no-editable: pyproject.toml's [tool.uv.sources] pins aecp-platform to
# an editable local path (../platform) for host-side dev convenience, but
# an editable install only links back to that source tree rather than
# copying it into site-packages — and only /opt/venv (not /build) is
# copied into the runtime stage below, so the link would dangle there.
RUN uv venv /opt/venv && uv pip install --no-editable --python /opt/venv/bin/python .

# Runtime was gcr.io/distroless/python3-debian12:nonroot, but that image
# only ships Python 3.11 while every service here declares
# requires-python>=3.12 — the builder's venv/python symlink pointed at
# python:3.12-slim's system interpreter (outside /opt/venv), which never
# got copied across, so the container failed at startup with "no such
# file or directory" for /opt/venv/bin/python. Using the same
# python:3.12-slim image for both stages fixes the interpreter-copy and
# ABI mismatch at once — mirrors the identical fix already applied to
# taskgraph/Dockerfile, state/Dockerfile, coordinator/Dockerfile, and
# agents/Dockerfile.
FROM python:3.12-slim AS runtime
RUN useradd --no-create-home --uid 65532 nonroot
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY integration/app /app/app
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH="/opt/venv/lib/python3.12/site-packages"
USER nonroot
EXPOSE 8080 50055
ENTRYPOINT ["/opt/venv/bin/python", "-m", "app.main"]
