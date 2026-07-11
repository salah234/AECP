"""Task Graph: decomposition, dependency, and ownership model.

Work is never a flat queue. Every unit of work is a node with explicit
dependencies, an ownership boundary, a definition of done, and a risk
tier. This service owns the DAG's structure and validity; the Coordinator
owns runtime scheduling over it.
"""
