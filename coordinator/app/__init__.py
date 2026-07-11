"""Coordinator: the engineering manager.

Owns the task graph's runtime scheduling, assigns work to agents, decides
sequencing, and is the only component allowed to make cross-agent
tradeoffs. Agent workers never talk to each other directly — everything
routes through this service.
"""
