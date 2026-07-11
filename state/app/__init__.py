"""State & Memory Layer: the institutional memory a human team gets for
free through Slack threads, standups, and tribal knowledge.

Owns the decision log, ownership map, interface contracts, and drift
detection. Treated as the source of truth across AECP: the task graph and
agent context are derived views over this layer, not the other way
around.
"""
