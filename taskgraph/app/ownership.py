"""Ownership boundary validation.

Static ownership boundaries prevent most conflicts before they happen.
This module checks whether a set of changed paths falls within (or
outside) a task node's declared OwnershipBoundary, and detects overlap
between two nodes' boundaries for the scheduler.
"""

from __future__ import annotations

import fnmatch
import posixpath
from functools import lru_cache

from .schema import OwnershipBoundary

_GLOB_META = frozenset("*?[")


def path_within_boundary(path: str, boundary: OwnershipBoundary) -> bool:
    """Return whether `path` matches one of boundary.path_globs and none
    of boundary.forbidden_globs.
    """
    normalized_path = _normalize_path(path)

    return (
        any(
            _glob_matches_path(normalized_path, path_glob)
            for path_glob in boundary.path_globs
        )
        and not any(
            _glob_matches_path(normalized_path, forbidden_glob)
            for forbidden_glob in boundary.forbidden_globs
        )
    )


def boundaries_overlap(a: OwnershipBoundary, b: OwnershipBoundary) -> bool:
    """Return whether two ownership boundaries could both match at least
    one common path, i.e. their owning tasks cannot safely run in
    parallel.
    """
    a_path_globs = _effective_path_globs(a)
    b_path_globs = _effective_path_globs(b)

    for a_glob in a_path_globs:
        for b_glob in b_path_globs:
            if not _globs_may_intersect(a_glob, b_glob):
                continue

            if _known_excluded_intersection(a_glob, b_glob, a, b):
                continue

            if _has_matching_overlap_sample(a_glob, b_glob, a, b):
                return True

            # Glob intersection is intentionally conservative. If we know
            # the include globs can intersect but cannot prove their shared
            # region is wholly forbidden, treat them as conflicting.
            return True

    return False


def violating_paths(paths: list[str], boundary: OwnershipBoundary) -> list[str]:
    """Return the subset of `paths` that fall outside `boundary`."""
    return [
        path
        for path in paths
        if not path_within_boundary(path, boundary)
    ]


def _normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")

    while normalized.startswith("./"):
        normalized = normalized[2:]

    return posixpath.normpath(normalized).strip("/")


def _split_glob(path_glob: str) -> tuple[str, ...]:
    normalized = _normalize_path(path_glob)

    if normalized in ("", "."):
        return ()

    return tuple(normalized.split("/"))


def _glob_matches_path(path: str, path_glob: str) -> bool:
    path_segments = _split_glob(path)
    glob_segments = _split_glob(path_glob)

    @lru_cache(maxsize=None)
    def matches(path_index: int, glob_index: int) -> bool:
        if glob_index == len(glob_segments):
            return path_index == len(path_segments)

        segment_glob = glob_segments[glob_index]
        if segment_glob == "**":
            return any(
                matches(next_path_index, glob_index + 1)
                for next_path_index in range(path_index, len(path_segments) + 1)
            )

        return (
            path_index < len(path_segments)
            and fnmatch.fnmatchcase(path_segments[path_index], segment_glob)
            and matches(path_index + 1, glob_index + 1)
        )

    return matches(0, 0)


def _effective_path_globs(boundary: OwnershipBoundary) -> list[str]:
    return [
        path_glob
        for path_glob in boundary.path_globs
        if not any(
            _glob_covers(forbidden_glob, path_glob)
            for forbidden_glob in boundary.forbidden_globs
        )
    ]


def _globs_may_intersect(a_glob: str, b_glob: str) -> bool:
    a_segments = _split_glob(a_glob)
    b_segments = _split_glob(b_glob)

    @lru_cache(maxsize=None)
    def intersects(a_index: int, b_index: int) -> bool:
        if a_index == len(a_segments):
            return all(segment == "**" for segment in b_segments[b_index:])

        if b_index == len(b_segments):
            return all(segment == "**" for segment in a_segments[a_index:])

        a_segment = a_segments[a_index]
        b_segment = b_segments[b_index]

        if a_segment == "**" and b_segment == "**":
            return (
                intersects(a_index + 1, b_index)
                or intersects(a_index, b_index + 1)
                or intersects(a_index + 1, b_index + 1)
            )

        if a_segment == "**":
            return (
                intersects(a_index + 1, b_index)
                or intersects(a_index, b_index + 1)
            )

        if b_segment == "**":
            return (
                intersects(a_index, b_index + 1)
                or intersects(a_index + 1, b_index)
            )

        return (
            _segment_globs_may_intersect(a_segment, b_segment)
            and intersects(a_index + 1, b_index + 1)
        )

    return intersects(0, 0)


def _known_excluded_intersection(
    a_glob: str,
    b_glob: str,
    a: OwnershipBoundary,
    b: OwnershipBoundary,
) -> bool:
    return (
        any(_glob_covers(forbidden_glob, b_glob) for forbidden_glob in a.forbidden_globs)
        or any(_glob_covers(forbidden_glob, a_glob) for forbidden_glob in b.forbidden_globs)
    )


def _has_matching_overlap_sample(
    a_glob: str,
    b_glob: str,
    a: OwnershipBoundary,
    b: OwnershipBoundary,
) -> bool:
    candidate_paths = {
        *_sample_paths_for_glob(a_glob),
        *_sample_paths_for_glob(b_glob),
    }

    return any(
        path_within_boundary(path, a)
        and path_within_boundary(path, b)
        for path in candidate_paths
    )


def _sample_paths_for_glob(path_glob: str) -> set[str]:
    samples = [()]

    for segment_glob in _split_glob(path_glob):
        if segment_glob == "**":
            samples = [
                sample
                for prefix in samples
                for sample in (
                    prefix,
                    (*prefix, "sample"),
                )
            ]
            continue

        segment = _sample_segment_for_glob(segment_glob)
        samples = [
            (*prefix, segment)
            for prefix in samples
        ]

    return {
        "/".join(sample)
        for sample in samples
        if sample
    }


def _sample_segment_for_glob(segment_glob: str) -> str:
    sample = []
    index = 0

    while index < len(segment_glob):
        char = segment_glob[index]

        if char == "*":
            sample.append("sample")
        elif char == "?":
            sample.append("x")
        elif char == "[":
            end_index = segment_glob.find("]", index + 1)
            if end_index == -1:
                sample.append("[")
            else:
                choices = segment_glob[index + 1:end_index]
                if choices.startswith(("!", "^")):
                    sample.append("x")
                else:
                    sample.append(_first_character_class_choice(choices))
                index = end_index
        else:
            sample.append(char)

        index += 1

    candidate = "".join(sample) or "sample"
    if fnmatch.fnmatchcase(candidate, segment_glob):
        return candidate

    return "sample"


def _first_character_class_choice(choices: str) -> str:
    for choice in choices:
        if choice not in ("!", "^", "-"):
            return choice

    return "x"


def _segment_globs_may_intersect(a_segment: str, b_segment: str) -> bool:
    a_has_meta = _has_glob_meta(a_segment)
    b_has_meta = _has_glob_meta(b_segment)

    if not a_has_meta and not b_has_meta:
        return a_segment == b_segment

    if not a_has_meta:
        return fnmatch.fnmatchcase(a_segment, b_segment)

    if not b_has_meta:
        return fnmatch.fnmatchcase(b_segment, a_segment)

    a_sample = _sample_segment_for_glob(a_segment)
    if (
        fnmatch.fnmatchcase(a_sample, a_segment)
        and fnmatch.fnmatchcase(a_sample, b_segment)
    ):
        return True

    b_sample = _sample_segment_for_glob(b_segment)
    if (
        fnmatch.fnmatchcase(b_sample, b_segment)
        and fnmatch.fnmatchcase(b_sample, a_segment)
    ):
        return True

    a_prefix = _literal_prefix(a_segment)
    b_prefix = _literal_prefix(b_segment)
    if (
        a_prefix
        and b_prefix
        and not a_prefix.startswith(b_prefix)
        and not b_prefix.startswith(a_prefix)
    ):
        return False

    a_suffix = _literal_suffix(a_segment)
    b_suffix = _literal_suffix(b_segment)
    if (
        a_suffix
        and b_suffix
        and not a_suffix.endswith(b_suffix)
        and not b_suffix.endswith(a_suffix)
    ):
        return False

    return True


def _glob_covers(covering_glob: str, covered_glob: str) -> bool:
    covering_segments = _split_glob(covering_glob)
    covered_segments = _split_glob(covered_glob)

    if covering_segments == covered_segments:
        return True

    if covering_segments == ("**",):
        return True

    if not any(_has_glob_meta(segment) for segment in covered_segments):
        return _glob_matches_path("/".join(covered_segments), covering_glob)

    if covering_segments and covering_segments[-1] == "**":
        prefix_segments = covering_segments[:-1]
        if len(covered_segments) < len(prefix_segments):
            return False

        return all(
            _segment_glob_covers(covering_segment, covered_segment)
            for covering_segment, covered_segment in zip(
                prefix_segments,
                covered_segments[:len(prefix_segments)],
            )
        )

    return False


def _segment_glob_covers(covering_segment: str, covered_segment: str) -> bool:
    if covering_segment == covered_segment:
        return True

    if covering_segment == "*":
        return True

    if not _has_glob_meta(covered_segment):
        return fnmatch.fnmatchcase(covered_segment, covering_segment)

    return False


def _has_glob_meta(value: str) -> bool:
    return any(char in value for char in _GLOB_META)


def _literal_prefix(value: str) -> str:
    prefix = []

    for char in value:
        if char in _GLOB_META:
            break
        prefix.append(char)

    return "".join(prefix)


def _literal_suffix(value: str) -> str:
    suffix = []

    for char in reversed(value):
        if char in _GLOB_META:
            break
        suffix.append(char)

    return "".join(reversed(suffix))
