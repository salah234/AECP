"""Ownership boundary overlap check for the Integration service.

This is a conservative, structural check — not a full glob-intersection
engine. taskgraph/app/ownership.py already implements a rigorous
glob-intersection algorithm (with proper "**" handling, forbidden-glob
carve-outs, sample-path generation, etc.) for the Task Graph's own
scheduling-time boundary enforcement, but that module lives in a
different deployable/package (`taskgraph`, not `integration`) and cannot
be imported from here — per CLAUDE.md, services never share code across
package boundaries, only gRPC/proto contracts.

Design tradeoff (documented per this fix's instructions): normalize each
glob down to its leading run of literal (non-wildcard) path segments —
the part before the first segment containing "*", "?", or "[" — and treat
two globs as possibly overlapping whenever one literal-prefix is a prefix
of the other, OR either glob has no literal prefix at all (i.e. it is a
wildcard from its very first segment, such as "**" or "*.py", which could
in principle match anything).

This is deliberately conservative: it will flag glob pairs that share no
real file in common (false positive) more often than taskgraph's own
precise algorithm would — e.g. "coordinator/app/*.py" and
"coordinator/app/foo_test.py" are flagged as overlapping even though the
second could describe a forbidden test-only path the first never
touches. That's an acceptable tradeoff here: per conflict.py's own
docstring, ownership conflicts detected by *this* service are "defense
in depth" on top of taskgraph's own boundary enforcement at task-creation
time, so a false positive here just costs one extra human glance at a
MergePolicyDecision. A false negative — silently letting two agents
stomp on the same files — is not an acceptable tradeoff, so when in
doubt this module reports overlap.
"""

from __future__ import annotations

_GLOB_META = frozenset("*?[")


def _literal_prefix_segments(path_glob: str) -> tuple[str, ...]:
    """Return the leading path segments of `path_glob` up to (not
    including) the first segment that contains a wildcard character.
    """
    normalized = path_glob.replace("\\", "/").strip("/")
    if not normalized:
        return ()

    segments = normalized.split("/")
    literal_segments: list[str] = []
    for segment in segments:
        if any(char in segment for char in _GLOB_META):
            break
        literal_segments.append(segment)

    return tuple(literal_segments)


def globs_may_overlap(glob_a: str, glob_b: str) -> bool:
    """Return whether two path globs could plausibly match a common
    path, using the conservative literal-prefix check documented above.
    """
    prefix_a = _literal_prefix_segments(glob_a)
    prefix_b = _literal_prefix_segments(glob_b)

    # A glob with no literal prefix (wildcard in its first segment, e.g.
    # "**" or "*.py") could in principle cover anything the other glob
    # covers — conservatively treat that as a possible overlap.
    if not prefix_a or not prefix_b:
        return True

    shorter, longer = (
        (prefix_a, prefix_b) if len(prefix_a) <= len(prefix_b) else (prefix_b, prefix_a)
    )
    return longer[: len(shorter)] == shorter


def boundaries_may_overlap(
    path_globs_a: list[str] | tuple[str, ...],
    path_globs_b: list[str] | tuple[str, ...],
) -> bool:
    """Return whether any glob in `path_globs_a` could plausibly overlap
    any glob in `path_globs_b`.

    Note: unlike taskgraph/app/ownership.py's boundaries_overlap, this
    does not consider forbidden_globs carve-outs — that refinement would
    require the same intersection machinery this module deliberately
    avoids reimplementing. Omitting it only makes this check *more*
    conservative (more false positives, never fewer), which is the safe
    direction per this module's documented tradeoff.
    """
    return any(
        globs_may_overlap(glob_a, glob_b) for glob_a in path_globs_a for glob_b in path_globs_b
    )


def shared_literal_paths(
    path_globs_a: list[str] | tuple[str, ...],
    path_globs_b: list[str] | tuple[str, ...],
) -> list[str]:
    """Return candidate concrete path strings implied by each overlapping
    glob pair's shared literal prefix.

    This is for informational lookups only (e.g. semantic_diff.py's
    State-ownership-map enrichment, which needs *some* concrete path to
    query GetOwnership with) — it is not a substitute for
    boundaries_may_overlap's conflict-detection judgment, and a glob pair
    can be flagged by boundaries_may_overlap (e.g. because one side has
    no literal prefix at all, like "**") without producing any candidate
    path here.
    """
    candidates: list[str] = []
    for glob_a in path_globs_a:
        for glob_b in path_globs_b:
            if not globs_may_overlap(glob_a, glob_b):
                continue

            prefix_a = _literal_prefix_segments(glob_a)
            prefix_b = _literal_prefix_segments(glob_b)
            shorter = prefix_a if len(prefix_a) <= len(prefix_b) else prefix_b
            if shorter:
                candidates.append("/".join(shorter))

    return candidates
