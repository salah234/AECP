"""Gateway: the only AECP component reachable from outside the private
network.

Terminates human OIDC sessions, resolves the authenticated user's tenant
and role, rate-limits, and proxies authorized requests to internal gRPC
services over mTLS. Internal services never accept traffic directly from
the dashboard.
"""
