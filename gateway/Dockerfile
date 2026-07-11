# syntax=docker/dockerfile:1.7
#
# The gateway is the only backend image exposed via an Ingress/LoadBalancer
# (see deploy/k8s). Every other service's Dockerfile should never be
# reachable from outside the cluster network — enforced by
# deploy/k8s/networkpolicy, not by this file alone.

FROM python:3.12-slim AS builder
WORKDIR /build
RUN pip install --no-cache-dir uv
COPY platform/ /build/platform/
COPY gateway/pyproject.toml gateway/
WORKDIR /build/gateway
RUN uv venv /opt/venv && uv pip install --python /opt/venv/bin/python .

FROM gcr.io/distroless/python3-debian12:nonroot AS runtime
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY gateway/app /app/app
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH="/opt/venv/lib/python3.12/site-packages"
USER nonroot
EXPOSE 8080
ENTRYPOINT ["/opt/venv/bin/python", "-m", "app.main"]
