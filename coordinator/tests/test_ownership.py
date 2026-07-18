from __future__ import annotations

from app import ownership
from app.common.v1 import common_pb2


def _boundary(path_globs: list[str], forbidden_globs: list[str] | None = None):
    return common_pb2.OwnershipBoundary(
        path_globs=path_globs, forbidden_globs=forbidden_globs or []
    )


def test_disjoint_boundaries_do_not_overlap() -> None:
    a = _boundary(["coordinator/app/scheduler.py"])
    b = _boundary(["taskgraph/app/graph.py"])
    assert ownership.boundaries_overlap(a, b) is False


def test_identical_globs_overlap() -> None:
    a = _boundary(["coordinator/app/**"])
    b = _boundary(["coordinator/app/**"])
    assert ownership.boundaries_overlap(a, b) is True


def test_overlapping_wildcard_directories_overlap() -> None:
    a = _boundary(["coordinator/app/*.py"])
    b = _boundary(["coordinator/app/scheduler.py"])
    assert ownership.boundaries_overlap(a, b) is True


def test_forbidden_glob_excludes_from_overlap() -> None:
    a = _boundary(["coordinator/**"], forbidden_globs=["coordinator/tests/**"])
    b = _boundary(["coordinator/tests/test_scheduler.py"])
    assert ownership.boundaries_overlap(a, b) is False


def test_path_within_boundary_respects_forbidden_globs() -> None:
    boundary = _boundary(["coordinator/**"], forbidden_globs=["coordinator/tests/**"])
    assert ownership.path_within_boundary("coordinator/app/scheduler.py", boundary) is True
    assert ownership.path_within_boundary("coordinator/tests/test_scheduler.py", boundary) is False


def test_violating_paths_returns_only_out_of_boundary_paths() -> None:
    boundary = _boundary(["coordinator/app/**"])
    paths = ["coordinator/app/scheduler.py", "taskgraph/app/graph.py"]
    assert ownership.violating_paths(paths, boundary) == ["taskgraph/app/graph.py"]
