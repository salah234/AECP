"""Conflict detection across candidate task changes.

Three kinds, per CLAUDE.md: textual (overlapping diff hunks), ownership
(touched files outside declared boundary — should be rare if taskgraph
scheduling worked, but checked again here as defense in depth), and
semantic (individually valid, jointly incoherent — e.g. two agents both
"fix" the same invariant in incompatible ways).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from app import ownership
from app.taskgraph.v1 import taskgraph_pb2


class ConflictKind(Enum):
    TEXTUAL = "textual"
    SEMANTIC = "semantic"
    OWNERSHIP = "ownership"


@dataclass
class ConflictReport:
    report_id: str
    tenant_id: str
    kind: ConflictKind
    task_ids: list[str]
    description: str
    auto_resolvable: bool
    detected_at: datetime


class ConflictDetector:
    """Runs every conflict check across all pairs of a tenant's candidate
    task ids and collects whatever reports come back.

    taskgraph_client is used to fetch each candidate's TaskNode (for the
    ownership check); semantic_diff is a SemanticDiffer used for the
    semantic check. Each candidate's TaskNode is fetched exactly once per
    detect() call and threaded through to the pairwise ownership check as
    an explicit argument rather than cached on self — detect() may be
    called concurrently (e.g. two DetectConflicts RPCs for different
    tenants arriving at once, since IntegrationServicer holds a single
    shared ConflictDetector instance), and instance-level mutable state
    would race across those concurrent calls at each await point. Boring
    explicit data-passing over shared mutable state, per CLAUDE.md.
    """

    def __init__(self, taskgraph_client, semantic_diff) -> None:
        self.taskgraph_client = taskgraph_client
        self.semantic_diff = semantic_diff

    async def detect(self, tenant_id: str, candidate_task_ids: list[str]) -> list[ConflictReport]:
        """Run textual, ownership, and semantic conflict checks across all
        pairs of candidate task ids and return every report found.
        """
        nodes: dict[str, taskgraph_pb2.TaskNode] = {}
        for task_id in candidate_task_ids:
            node = await self.taskgraph_client.get_task_node(task_id, tenant_id)
            if node is not None:
                nodes[task_id] = node

        reports: list[ConflictReport] = []

        for task_id_a, task_id_b in itertools.combinations(candidate_task_ids, 2):
            textual_report = await self._detect_textual(task_id_a, task_id_b)
            if textual_report is not None:
                reports.append(textual_report)

            node_a = nodes.get(task_id_a)
            node_b = nodes.get(task_id_b)
            if node_a is not None and node_b is not None:
                ownership_report = await self._detect_ownership(
                    task_id_a, task_id_b, node_a=node_a, node_b=node_b
                )
                if ownership_report is not None:
                    reports.append(ownership_report)

            diff_result = await self.semantic_diff.compare(tenant_id, task_id_a, task_id_b)
            if not diff_result.jointly_coherent:
                reports.append(
                    ConflictReport(
                        report_id=str(uuid4()),
                        tenant_id=tenant_id,
                        kind=ConflictKind.SEMANTIC,
                        task_ids=[task_id_a, task_id_b],
                        description=diff_result.explanation,
                        auto_resolvable=False,
                        detected_at=datetime.now(timezone.utc),
                    )
                )

        return reports

    async def _detect_textual(self, task_id_a: str, task_id_b: str) -> ConflictReport | None:
        """Always returns None. This is a documented, flagged data-model
        gap, not a bug.

        A real textual conflict check needs the actual diff/patch hunks
        for each task's change so it can compare overlapping line
        ranges. No service or proto in this repo exposes that data:
        TaskGraph stores task *metadata* (title, description, ownership
        globs, definition of done — never a diff); State stores
        decision/contract metadata plus opaque object-storage URIs
        (platform/aecp_platform/storage never parses what it stores, so
        Integration has no client-side way to interpret those bytes as a
        diff even if it fetched them); and Agent Pool has no gRPC edge to
        Integration at all.

        This mirrors this codebase's existing pattern of clearly-flagged
        MVP gaps rather than a fabricated answer: see
        state/app/repository.py's get_decisions_for_module docstring and
        agents/app/hydration.py's documented-empty contract lists. Do
        not turn this into a silent "no conflict" default without first
        wiring an actual diff data source (a proto field, a repository
        query, something) — the whole point of always returning `None`
        here (never `False`/"no conflict") is that a future reader can
        grep for this docstring and understand why textual conflicts are
        never reported today, rather than assuming this path was tested
        and found conflict-free.
        """
        return None

    async def _detect_ownership(
        self,
        task_id_a: str,
        task_id_b: str,
        *,
        node_a: taskgraph_pb2.TaskNode,
        node_b: taskgraph_pb2.TaskNode,
    ) -> ConflictReport | None:
        """Two tasks conflict on ownership if their OwnershipBoundary
        path_globs could both match at least one common path — see
        app/ownership.py for the conservative overlap check used here
        (a simpler, more false-positive-prone cousin of taskgraph's own
        precise glob-intersection algorithm, which lives in a different
        deployable and can't be imported from this service).

        node_a/node_b are passed in explicitly by detect() (already
        fetched once per candidate) rather than re-fetched here by
        task_id, both to avoid a redundant RPC per pair and to avoid any
        shared per-instance node cache that could race under concurrent
        detect() calls (see ConflictDetector's own docstring).
        """
        if not ownership.boundaries_may_overlap(
            list(node_a.ownership.path_globs), list(node_b.ownership.path_globs)
        ):
            return None

        return ConflictReport(
            report_id=str(uuid4()),
            tenant_id=node_a.tenant_id,
            kind=ConflictKind.OWNERSHIP,
            task_ids=[task_id_a, task_id_b],
            description=(
                f"Task '{task_id_a}' and task '{task_id_b}' declare ownership "
                f"boundaries whose path globs may overlap "
                f"({list(node_a.ownership.path_globs)} vs. "
                f"{list(node_b.ownership.path_globs)})."
            ),
            auto_resolvable=False,
            detected_at=datetime.now(timezone.utc),
        )
