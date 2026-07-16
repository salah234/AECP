from app.ownership import (
    boundaries_overlap,
    path_within_boundary,
    violating_paths,
)
from app.schema import OwnershipBoundary


def test_path_within_boundary_matches_allowed_glob() -> None:
    boundary = OwnershipBoundary(path_globs=["taskgraph/app/*.py"])

    assert path_within_boundary("taskgraph/app/ownership.py", boundary)


def test_path_within_boundary_rejects_paths_outside_allowed_glob() -> None:
    boundary = OwnershipBoundary(path_globs=["taskgraph/app/*.py"])

    assert not path_within_boundary("taskgraph/app/nested/ownership.py", boundary)


def test_path_within_boundary_rejects_forbidden_glob() -> None:
    boundary = OwnershipBoundary(
        path_globs=["taskgraph/**"],
        forbidden_globs=["taskgraph/tests/**"],
    )

    assert not path_within_boundary("taskgraph/tests/test_ownership.py", boundary)


def test_path_within_boundary_normalizes_common_path_spellings() -> None:
    boundary = OwnershipBoundary(path_globs=["taskgraph/app/*.py"])

    assert path_within_boundary("./taskgraph\\app\\ownership.py", boundary)


def test_violating_paths_preserves_input_order() -> None:
    boundary = OwnershipBoundary(
        path_globs=["taskgraph/app/**"],
        forbidden_globs=["taskgraph/app/private/**"],
    )

    assert violating_paths(
        [
            "taskgraph/app/ownership.py",
            "taskgraph/tests/test_ownership.py",
            "taskgraph/app/private/secret.py",
        ],
        boundary,
    ) == [
        "taskgraph/tests/test_ownership.py",
        "taskgraph/app/private/secret.py",
    ]


def test_boundaries_overlap_for_shared_recursive_subtree() -> None:
    assert boundaries_overlap(
        OwnershipBoundary(path_globs=["taskgraph/**"]),
        OwnershipBoundary(path_globs=["taskgraph/app/*.py"]),
    )


def test_boundaries_overlap_for_literal_path_inside_glob() -> None:
    assert boundaries_overlap(
        OwnershipBoundary(path_globs=["taskgraph/app/ownership.py"]),
        OwnershipBoundary(path_globs=["taskgraph/app/*.py"]),
    )


def test_boundaries_do_not_overlap_for_disjoint_directories() -> None:
    assert not boundaries_overlap(
        OwnershipBoundary(path_globs=["taskgraph/**"]),
        OwnershipBoundary(path_globs=["gateway/**"]),
    )


def test_boundaries_do_not_overlap_when_forbidden_excludes_shared_subtree() -> None:
    assert not boundaries_overlap(
        OwnershipBoundary(
            path_globs=["taskgraph/**"],
            forbidden_globs=["taskgraph/tests/**"],
        ),
        OwnershipBoundary(path_globs=["taskgraph/tests/**"]),
    )


def test_boundaries_overlap_when_forbidden_subtree_leaves_other_shared_paths() -> None:
    assert boundaries_overlap(
        OwnershipBoundary(
            path_globs=["taskgraph/**"],
            forbidden_globs=["taskgraph/tests/**"],
        ),
        OwnershipBoundary(path_globs=["taskgraph/app/**"]),
    )
