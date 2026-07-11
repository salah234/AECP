"""Shared cross-cutting library used by every AECP service.

Subsystems (coordinator, taskgraph, agents, state, integration,
observability, gateway) depend on this package for config loading, secrets
access, service identity / mTLS, tenant isolation, telemetry, and the
shared error taxonomy — so those concerns are implemented once and audited
once, rather than reinvented per service.
"""
