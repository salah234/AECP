"""Conflict & Integration Layer.

Handles what happens when parallel agents produce overlapping or
contradictory changes. Static ownership boundaries (owned by the Task
Graph) prevent most conflicts before they happen; this service catches
what slips through — including cases where two changes are individually
valid but jointly incoherent — and applies an explicit, per-risk-tier
merge policy.
"""
