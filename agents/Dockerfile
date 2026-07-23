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
# file or directory" for /opt/venv/bin/python regardless of which
# service. Using the same python:3.12-slim image for both stages fixes
# the interpreter-copy and ABI mismatch at once, at the cost of
# distroless's smaller attack surface — recovering that requires a
# matching-version distroless image, which Google does not yet publish
# for 3.12.
FROM python:3.12-slim AS runtime
# Real agent execution (app/executor.py) shells out to the `claude` CLI
# against a git checkout of the target codebase — needs Node.js (the
# CLI's runtime) and git, neither of which this image needed before it
# only did session bookkeeping. NodeSource's setup script pins a known
# major (20.x) rather than risking bookworm-slim's inconsistent default
# apt nodejs version. curl/gnupg are purged after install — only needed
# for the NodeSource script itself.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get purge -y curl gnupg && apt-get autoremove -y \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN useradd --no-create-home --uid 65532 nonroot
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY agents/app /app/app
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH="/opt/venv/lib/python3.12/site-packages"
USER nonroot
EXPOSE 8080 50051
ENTRYPOINT ["/opt/venv/bin/python", "-m", "app.main"]
