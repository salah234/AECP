"""Ownership boundary validation.

Static ownership boundaries prevent most conflicts before they happen.
This module checks whether a set of changed paths falls within (or
outside) a task node's declared OwnershipBoundary, and detects overlap
between two nodes' boundaries for the scheduler.
"""

from __future__ import annotations

from .schema import OwnershipBoundary


def path_within_boundary(path: str, boundary: OwnershipBoundary) -> bool:
    """Return whether `path` matches one of boundary.path_globs and none
    of boundary.forbidden_globs.
    """
    raise NotImplementedError


def boundaries_overlap(a: OwnershipBoundary, b: OwnershipBoundary) -> bool:
    """Return whether two ownership boundaries could both match at least
    one common path, i.e. their owning tasks cannot safely run in
    parallel.
    """
    raise NotImplementedError


def violating_paths(paths: list[str], boundary: OwnershipBoundary) -> list[str]:
    """Return the subset of `paths` that fall outside `boundary`."""
    raise NotImplementedError
