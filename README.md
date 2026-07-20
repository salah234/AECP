# Autonomous Engineering Coordination Platform (AECP)

> **An operating system that manages AI software engineers like a real engineering manager.**

---

## Overview

The **Autonomous Engineering Coordination Platform (AECP)** is an operating system for autonomous software development.

While modern AI models have become remarkably good at writing code, they still struggle to build and maintain large software systems over weeks or months without human intervention.

The bottleneck is no longer **code generation**.

The bottleneck is **engineering coordination**.

AECP treats AI agents as software engineers rather than autocomplete tools. Instead of asking a single model to build an application, AECP manages an entire engineering organization composed of specialized autonomous engineers.

It assigns work, tracks progress, enforces engineering standards, reviews code, resolves dependencies, and continuously monitors project health—just like an experienced engineering manager.

---

# Quickstart

**Prerequisites:** Docker + Docker Compose, [`uv`](https://docs.astral.sh/uv/) (Python package/venv manager), Node.js 22+, and [`buf`](https://buf.build) if you need to regenerate proto stubs.

```bash
cp .env.example .env    # fill in OIDC_* if you're testing the gateway login flow;
                         # every other value already has a working local-dev default
make install             # installs every service's deps (Python venvs + platform) and dashboard's npm deps
make dev-up               # boots the full local topology: postgres, otel-collector, jaeger,
                          # all 7 backend services, gateway, and the dashboard (deploy/docker/docker-compose.yml)
```

Then apply migrations once against the running Postgres container (`taskgraph`, `state`, and `observability` each own one table set):

```bash
for svc in taskgraph state observability; do
  docker compose -f deploy/docker/docker-compose.yml exec -T postgres \
    psql -U aecp -d aecp < $svc/migrations/0001_*.sql
done
```

Dashboard: http://localhost:3000 · Gateway: http://localhost:8080 · Jaeger UI: http://localhost:16686

**Run a single service's tests directly** (each service is an independent `uv`-managed Python project):

```bash
cd coordinator && uv venv .venv && uv pip install -e . --group dev
.venv/bin/pytest -q
```

**Run everything** (every backend service + dashboard):

```bash
make test        # loops pytest across every Python service
cd dashboard && npm test && npm run typecheck && npm run lint
```

**Real, multi-container system tests** (boots every service as a real Docker container and drives full task lifecycles over real gRPC — no fakes): see the module docstring in `coordinator/tests/integration/test_e2e_docker_compose.py` and `test_full_system_e2e.py` for exact steps; summary:

```bash
docker compose -f coordinator/tests/integration/docker-compose.test.yml up -d --build
python -c "from coordinator.tests.integration.test_e2e_docker_compose import apply_migrations as f; f()"
AECP_RUN_DOCKER_INTEGRATION_TESTS=1 pytest coordinator/tests/integration -q
docker compose -f coordinator/tests/integration/docker-compose.test.yml down -v
```

**Repository layout:** see `CLAUDE.md`'s "Repository Structure" section — it's the authoritative, binding description of what lives where and why. `docs/adr/` has the reasoning behind every major technical decision; `security/THREAT_MODEL.md` has the trust-boundary model and a running list of open security decisions.

---

# The Problem

Today's coding agents are excellent at solving isolated tasks.

However, real software engineering involves much more than writing code.

Large projects require:

* Long-term planning
* Dependency management
* Parallel execution
* Context preservation
* Code ownership
* Architecture consistency
* Quality assurance
* Documentation
* Testing
* Continuous integration
* Risk management

Current AI coding tools lose context, duplicate work, overwrite each other's changes, and lack the organizational structure necessary to scale.

The result is an AI workforce without management.

---

# Our Vision

AECP transforms autonomous coding agents into an organized engineering organization.

Instead of:

```
Human
   │
   ▼
One AI Agent
   │
Writes Code
```

AECP creates:

```
                    Human
                      │
                      ▼
      Autonomous Engineering Coordinator
                      │
      ┌───────────────┼───────────────┐
      ▼               ▼               ▼
Backend Engineer  Frontend Engineer  DevOps Engineer
      │               │               │
      └───────────────┼───────────────┘
                      ▼
              QA & Code Review
                      │
                      ▼
             Documentation Agent
                      │
                      ▼
               Production Ready Code
```

Every AI agent has a defined role, responsibilities, objectives, and communication pathways.

---

# Core Philosophy

Software engineering is fundamentally a coordination problem.

Writing code is only one responsibility.

Professional engineering organizations spend most of their effort on:

* planning
* communication
* architecture
* reviews
* testing
* deployment
* documentation

AECP automates those responsibilities.

---

# Key Features

## Engineering Manager

The central orchestrator responsible for:

* Breaking large goals into milestones
* Creating engineering tickets
* Assigning work
* Prioritizing tasks
* Monitoring progress
* Detecting blockers
* Resolving conflicts
* Measuring productivity

---

## Autonomous Sprint Planning

The platform automatically:

* Creates project roadmaps
* Generates engineering tasks
* Estimates complexity
* Organizes work into sprints
* Tracks completion

---

## Multi-Agent Coordination

Agents specialize in different engineering disciplines.

Examples include:

* Backend Engineer
* Frontend Engineer
* Infrastructure Engineer
* DevOps Engineer
* QA Engineer
* Security Engineer
* Documentation Engineer
* Database Engineer
* API Engineer
* Performance Engineer

Agents collaborate instead of competing.

---

## Persistent Project Memory

Every engineering decision is stored.

Examples:

* architecture decisions
* design documents
* technical debt
* completed tasks
* discussions
* implementation history
* code ownership

No more context loss after long conversations.

---

## Dependency Graph

AECP understands relationships between work.

Example:

```
Database Schema
      │
      ▼
REST API
      │
      ▼
Frontend Components
      │
      ▼
Integration Tests
```

Tasks automatically wait for dependencies before execution.

---

## Intelligent Code Review

Dedicated reviewer agents examine:

* Architecture
* Security
* Performance
* Maintainability
* Test coverage
* Style consistency

Code is merged only after passing quality gates.

---

## Continuous Project Awareness

Unlike isolated chat sessions, AECP continuously understands:

* current sprint
* active tickets
* blocked work
* project goals
* technical debt
* documentation
* architecture evolution

---

## Autonomous Debugging

If builds fail:

1. Detect failure
2. Assign debugging agent
3. Reproduce issue
4. Generate fix
5. Validate tests
6. Re-run pipeline
7. Continue project

No human intervention required.

---

## Engineering Metrics

Monitor:

* Sprint velocity
* Agent utilization
* Task completion
* Build success rate
* Test coverage
* Cycle time
* Review latency
* Technical debt

---

# Example Workflow

```
Human:
"Build a SaaS CRM."

↓

Engineering Manager

↓

Break into Epics

↓

Create 240 Engineering Tasks

↓

Assign Tasks

↓

Agents Work in Parallel

↓

Peer Review

↓

Testing

↓

Deployment

↓

Next Sprint

↓

Repeat Until Complete
```

---

# Example Agent Organization

```
CEO / Founder
        │
        ▼
Engineering Manager (Coordinator)
        │
 ┌──────┼──────────────┐
 │      │              │
 ▼      ▼              ▼
Backend Frontend   Infrastructure
 │      │              │
 ▼      ▼              ▼
Database UI      DevOps
 │
 ▼
Testing
 │
 ▼
Documentation
```

Each agent has:

* Role
* Responsibilities
* Long-term memory
* Context window
* Assigned tickets
* Deadlines
* Communication channels

---

# Potential Architecture

```
┌─────────────────────────────────────┐
│               Dashboard             │
└─────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│     Engineering Coordination Core   │
└─────────────────────────────────────┘
                 │
     ┌───────────┼────────────┐
     ▼           ▼            ▼
 Task Engine  Memory Engine  Planner
     │           │            │
     └───────┬───┴────────────┘
             ▼
      Agent Orchestrator
             │
 ┌───────────┼────────────────────┐
 ▼           ▼                    ▼
Claude     GPT               Local Models
             │
             ▼
Git • GitHub • CI/CD • Tests • IDE
```

---

# Tech Stack

See `CLAUDE.md` ("Tech Stack & Conventions" and "Security & Multi-Tenancy") for the authoritative, binding version. Summary:

### Frontend

* Next.js / React / TypeScript
* Talks only to `/gateway`, never to an internal service directly

### Backend

* Python (FastAPI + grpcio) across every subsystem: `/coordinator`, `/taskgraph`, `/agents`, `/state`, `/integration`, `/observability`, `/gateway`
* PostgreSQL (Row-Level Security for multi-tenancy) + object storage for large context artifacts
* `/proto` as the single source of truth for internal gRPC contracts
* `/platform` shared library for config, secrets, service identity (mTLS), tenancy, telemetry

### Infrastructure

* Docker (distroless, non-root images)
* Kubernetes with explicit NetworkPolicies enforcing the no-agent-to-agent invariant
* GitHub Actions (lint, typecheck, test, dependency audit, secret scan, proto lint, container scan)
* Terraform (network, KMS, managed Postgres, cluster)

### Observability

* Grafana + Prometheus + OpenTelemetry
* Append-only audit trail (`observability/app/audit.py`) distinct from application logs

See `docs/adr/` for the reasoning behind these choices and `security/THREAT_MODEL.md` for the trust-boundary model.

---

# Long-Term Roadmap

### Phase 1

* Multi-agent orchestration
* Task management
* Memory system
* Git integration

### Phase 2

* Autonomous planning
* Code review agents
* QA automation
* Documentation generation

### Phase 3

* Self-improving engineering organization
* Automatic architecture evolution
* Cross-repository coordination
* Enterprise collaboration

### Phase 4

* Fully autonomous software organizations capable of managing large-scale engineering projects with minimal human oversight.

---

# Why AECP?

The future of software engineering will not be powered by a single super-intelligent coding model.

It will be powered by coordinated teams of specialized AI engineers working together under structured management.

AECP is designed to provide that management layer.

Rather than replacing software engineers, it aims to augment engineering organizations by automating coordination, planning, execution, and quality control—allowing humans to focus on strategy, product direction, and high-impact technical decisions.

---

# Status

🚧 **Development Phase — core coordination loop implemented and tested, security hardening in progress**

Every subsystem in the architecture below is real, running code, not a design sketch: `/coordinator`, `/taskgraph`, `/agents`, `/state`, `/integration`, `/observability`, `/gateway`, and the `/dashboard` all have working implementations with unit test coverage, and the full system has been verified end-to-end as real Docker containers talking real gRPC (`coordinator/tests/integration/test_full_system_e2e.py`) — task creation → scheduling → agent assignment → conflict detection → decision logging → audit trail → REST access all round-trip through the real services, not fakes.

What's deliberately still open, tracked as ADRs rather than silently defaulted: the production secrets backend (`docs/adr/0006`), real per-service mTLS certificate issuance (`docs/adr/0008` — every service today authenticates internal callers via a documented interim scheme, not yet a cryptographically verified one), and the agent sandbox isolation technology (`docs/adr/0009` — `agents/app/sandbox.py`'s current implementation provides no real isolation and must not be pointed at real tenant code). See `security/THREAT_MODEL.md`'s "Open items" for the full list. Per `CLAUDE.md`'s Escalation Policy, all three are Tier 3 (security boundary) decisions requiring explicit human sign-off before implementation — not something either an agent or this document can unilaterally resolve.
