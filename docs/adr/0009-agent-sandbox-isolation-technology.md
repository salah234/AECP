# 0009 — Agent sandbox isolation technology (OPEN — PROPOSAL, human decision required)

## Context
`agents/app/sandbox.py`'s `Sandbox` class is, by its own module
docstring, explicitly **not a security boundary**: `create()` allocates a
scratch directory and writes the session's declared ownership globs into
a file for inspection, and nothing else — no process isolation, no
filesystem isolation, no network namespace isolation, no resource limits.
This exists so the rest of Agent Pool (spawn, handoff, teardown, capacity
accounting in `lifecycle.py`/`pool.py`) could be implemented and
integration-tested end to end without blocking on this decision — those
modules are real and well-tested (`agents/tests/test_lifecycle.py`,
`test_pool.py`, `test_concurrent_sessions.py`), they just call into a
`Sandbox` that isn't actually a sandbox yet.

This matters because of what an agent session actually is, per
`CLAUDE.md`: a process executing **untrusted, model-generated actions**
(shell commands, file edits, network calls) against real tenant code,
with write access. A compromised or simply misbehaving agent session must
not be able to reach another tenant's data, another agent's sandbox
(`CLAUDE.md`'s key invariant: no agent-to-agent communication, ever — the
network-layer half of that is enforced by
`deploy/k8s/networkpolicy/agents-edges.yaml`; the sandbox is the other
half, since two agent processes sharing a node's kernel/filesystem could
still interfere with each other even with no network path between them),
or infrastructure outside its declared ownership boundary.

`security/THREAT_MODEL.md`'s "Open items" lists this exact decision as
blocking real production use of Agent Pool.

## Decision
Not yet made. This ADR exists so the decision is tracked and
`Sandbox.create()`'s complete lack of isolation stays a visible, flagged
gap rather than something that quietly becomes "how it's always worked"
as more of the system is built out around it.

## Options under consideration

- **gVisor.** A user-space kernel intercepting syscalls (runs as a
  runsc OCI runtime, so it slots into the same container-image /
  `SANDBOX_IMAGE` config `agents/app/config.py` already has a field for).
  Strong-ish isolation (a compromised sandbox reaches gVisor's
  restricted syscall surface, not the host kernel) at container-like
  startup latency, which matters for an interactive-feeling agent-spawn
  path (`LifecycleManager.spawn` is on Coordinator's `Schedule` critical
  path today). Weaker isolation guarantee than a real VM boundary — a
  gVisor escape is a known, if rare, class of vulnerability.
- **Firecracker microVMs.** Real hardware-virtualized VM boundary per
  session — the strongest isolation of the three options, and the same
  technology AWS Lambda/Fargate build on. Meaningfully more operational
  surface: needs a Firecracker-aware orchestration layer (`firecracker-
  containerd` or a hand-rolled control plane), kernel/rootfs image
  management per sandbox, and won't run inside an environment that is
  itself already virtualized without nested-virtualization support
  (relevant if AECP's own control plane runs on a VM-based cloud
  instance type without that enabled).
- **Plain containers + seccomp/AppArmor + a dedicated low-trust node
  pool.** Lowest new-infrastructure cost — reuses whatever container
  runtime the rest of `deploy/k8s` already runs on, adds a restrictive
  seccomp profile (narrower than every other Deployment's
  `RuntimeDefault` — see `deploy/k8s/base/*.yaml`'s existing
  `securityContext` blocks, which currently assume normal AECP service
  containers, not sandboxes for untrusted code) and schedules agent
  sandboxes onto nodes that run nothing else sensitive, via a taint/
  toleration. Real, meaningfully better than today's no-op, but shares
  the host kernel — a container-escape vulnerability is a full sandbox
  break, unlike gVisor or Firecracker.

**Recommendation, not a decision:** gVisor is the reasonable default to
propose for a first real implementation — it directly replaces
`Sandbox.create()`'s current "container-shaped" call site with another
container-shaped one (same `SANDBOX_IMAGE` field, same lifecycle calls),
giving a real isolation boundary without introducing a second
orchestration system the way Firecracker would. Revisit toward
Firecracker if/when agent sessions start running workloads where a
gVisor-class boundary stops being sufficient for the threat model (e.g.
executing genuinely adversarial, not just occasionally-buggy, model
output).

## Consequences of leaving this open
`Sandbox.create()`/`destroy()`'s signatures (`session_id, tenant_id,
ownership_globs -> SandboxHandle`) are already shaped to swap in a real
backend without changing `LifecycleManager`'s call sites — whichever
technology is chosen, it should be implementable as a drop-in
replacement for this class, not a `LifecycleManager` rewrite. Until then,
Agent Pool must not be pointed at real tenant code in any environment
that matters — `agents/tests/test_sandbox.py`'s own docstring already
says as much explicitly.

## Explicitly out of scope for this ADR (and for whoever implements it)
Per `CLAUDE.md`'s Escalation Policy, this is a Tier 3 change (security
boundary) — agents may propose (this document) but never merge a
real sandbox implementation unilaterally. Provisioning gVisor/Firecracker
node pools, writing the actual isolation-enforcing code, and removing the
"THIS IMPLEMENTATION IS NOT A SECURITY BOUNDARY" warning from
`sandbox.py` all require human sign-off on this ADR's Decision section
first.
