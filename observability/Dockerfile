# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder
WORKDIR /build
RUN pip install --no-cache-dir uv
COPY platform/ /build/platform/
COPY observability/pyproject.toml observability/
WORKDIR /build/observability
RUN uv venv /opt/venv && uv pip install --python /opt/venv/bin/python .

FROM gcr.io/distroless/python3-debian12:nonroot AS runtime
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY observability/app /app/app
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH="/opt/venv/lib/python3.12/site-packages"
USER nonroot
EXPOSE 8080 50051
ENTRYPOINT ["/opt/venv/bin/python", "-m", "app.main"]
