"""Real agent execution: runs a session's task against the target
codebase via a pluggable ExecutionBackend, and reports the outcome back
to Coordinator.

Before this module existed, Agent Pool only did session bookkeeping
(spawn/hydrate/handoff/terminate) — nothing anywhere actually invoked a
coding agent to do work. AgentExecutor itself is backend-agnostic: it
owns hydration, target-repo checkout, prompt construction, background
task lifecycle, and blocker/completion reporting, and delegates the
actual "make the change" step to whichever ExecutionBackend main.py wires
in (see app/execution_backends/ — ClaudeCliBackend is the default,
CohereBackend is a second, selectable option via AGENT_EXECUTION_BACKEND).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

from app.common.v1 import common_pb2
from app.taskgraph.v1 import taskgraph_pb2

logger = logging.getLogger(__name__)

# A backend's stdout/output may contain task descriptions or model output
# derived from tenant code — truncate before it ever leaves this process
# via a blocker RPC payload (security/THREAT_MODEL.md, threat #4: secret/
# content exposure via logs).
_MAX_REPORTED_OUTPUT_CHARS = 4000


class AgentExecutor:
    """Owns running one session's task as a background asyncio.Task, and
    reporting its outcome to Coordinator — independent of which
    ExecutionBackend actually performs the work.
    """

    def __init__(
        self,
        *,
        hydrator,
        coordinator_client,
        target_repo,
        backend,
        execution_timeout_seconds: float,
        lifecycle_manager=None,
    ) -> None:
        self._hydrator = hydrator
        self._coordinator_client = coordinator_client
        self._target_repo = target_repo
        self._backend = backend
        self._execution_timeout_seconds = execution_timeout_seconds
        # Optional: lets _run tear down its own session once it's reported
        # an outcome (success or blocker), instead of leaving it ACTIVE in
        # Agent Pool's in-memory registry indefinitely (only the TTL reap
        # loop would eventually catch it otherwise — up to
        # SESSION_TTL_SECONDS later). None keeps existing direct _run()
        # callers/tests (which construct AgentExecutor without a full
        # LifecycleManager) working unchanged.
        self._lifecycle_manager = lifecycle_manager
        self._tasks: dict[str, asyncio.Task] = {}
        # Strong references for the fire-and-forget cleanup tasks _on_done
        # schedules — without this, asyncio only holds a weak reference to
        # a bare create_task() result and could garbage-collect it mid-run.
        self._cleanup_tasks: set[asyncio.Task] = set()

    def spawn_background(self, session, scratch_dir: str) -> None:
        """Fire-and-forget: start running `session`'s task in the
        background. Deliberately not awaited by the caller (SpawnSession)
        — RPC latency must stay bounded by sandbox+identity provisioning
        only, not an entire backend run.
        """
        task = asyncio.create_task(self._run(session, scratch_dir))
        self._tasks[session.session_id] = task
        task.add_done_callback(self._make_done_callback(session.session_id))

    def _make_done_callback(self, session_id: str) -> Callable[[asyncio.Task], None]:
        def _on_done(_task: asyncio.Task) -> None:
            self._tasks.pop(session_id, None)
            if self._lifecycle_manager is None:
                return
            # Runs *after* _run has fully returned and this session_id is
            # no longer in self._tasks, so execution_canceller (routed
            # through terminate_and_return) finds nothing to cancel here —
            # this is teardown of an already-finished session, not a live
            # one. If something else (TerminateSession, handoff, reap)
            # already tore this session down first, terminate_and_return's
            # existing pop-and-check-None atomicity makes this a no-op.
            cleanup = asyncio.create_task(
                self._lifecycle_manager.terminate(session_id, reason="execution finished")
            )
            self._cleanup_tasks.add(cleanup)
            cleanup.add_done_callback(self._cleanup_tasks.discard)

        return _on_done

    async def cancel(self, session_id: str) -> None:
        """Cancel a session's in-flight execution, if any, and wait for
        the cancellation to actually land before returning. Intended to
        be wired as LifecycleManager.execution_canceller, called from
        terminate_and_return before the sandbox's scratch dir is deleted
        out from under a still-running backend.
        """
        task = self._tasks.get(session_id)
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def shutdown(self) -> None:
        """Cancel and await every tracked execution — called from
        main.py's shutdown path. Awaited (unlike main.py's existing
        reap_task.cancel(), which doesn't wait for confirmation) since an
        orphaned live execution matters more than an orphaned in-memory
        loop.
        """
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, session, scratch_dir: str) -> None:
        try:
            bundle = await self._hydrator.hydrate(session.session_id)
            repo_dir = await self._target_repo.checkout(scratch_dir, session.session_id)
            prompt = self._build_prompt(bundle)
            outcome = await self._backend.run(
                prompt=prompt,
                repo_dir=repo_dir,
                timeout_seconds=self._execution_timeout_seconds,
            )
        except asyncio.CancelledError:
            # Only reached via execution_canceller, whose call sites
            # (TerminateSession, HandoffCoordinator.handoff,
            # _reap_loop-driven reap_expired) already handle their own
            # bookkeeping. Reporting anything here would double-report.
            raise
        except Exception as exc:  # noqa: BLE001 - any failure here must degrade to a blocker, not crash the session
            await self._report_blocker(session, f"Agent execution failed: {exc}")
            return

        if not outcome.success:
            await self._report_blocker(session, outcome.rationale)
            return

        await self._coordinator_client.report_completion(
            task_id=session.task_id,
            tenant_id=session.tenant_id,
            agent_id=session.session_id,
            summary=outcome.summary,
            rationale=outcome.rationale,
        )

    def _build_prompt(self, bundle) -> str:
        node = taskgraph_pb2.TaskNode()
        # bundle.task_node is opaque, Coordinator-forwarded bytes per
        # hydration.py's documented contract ("does not parse it or
        # depend on taskgraph_pb2") — that convention guards against a
        # *network* edge to TaskGraph (ADR-0007), not against a consumer
        # that finally understands the already-forwarded blob. This is
        # that consumer, so parsing here (for prompt construction only)
        # is a deliberate, narrow exception, not a silent ADR-0007
        # violation.
        node.ParseFromString(bundle.task_node)

        ownership = common_pb2.OwnershipBoundary()
        ownership.ParseFromString(bundle.ownership_boundary)

        path_globs = "\n".join(f"- {g}" for g in ownership.path_globs) or "(none declared)"
        forbidden_globs = "\n".join(f"- {g}" for g in ownership.forbidden_globs) or "(none declared)"
        acceptance_criteria = (
            "\n".join(f"- {c}" for c in node.definition_of_done.acceptance_criteria)
            or "(none declared)"
        )
        required_checks = (
            "\n".join(f"- {c}" for c in node.definition_of_done.required_checks)
            or "(none declared)"
        )
        risk_tier_name = common_pb2.RiskTier.Name(node.risk_tier)

        return (
            "You are an autonomous engineering agent operating within AECP on "
            "exactly one task node. Do not act outside your ownership boundary, "
            "and do not ask for interactive clarification — make the most "
            "reasonable judgment call and note any assumptions in your final "
            "summary.\n\n"
            f"Task: {node.title}\n"
            f"Description: {node.description}\n\n"
            "Ownership boundary (you may ONLY create/edit files matching these "
            f"globs):\n{path_globs}\n\n"
            f"Forbidden globs (never touch, even if related):\n{forbidden_globs}\n\n"
            f"Definition of done:\nAcceptance criteria:\n{acceptance_criteria}\n"
            f"Required checks:\n{required_checks}\n\n"
            f"Granted risk tier: {risk_tier_name} — do not perform any change "
            "beyond what this tier allows. If the task turns out to need a "
            "higher tier, stop and explain why in your final summary rather "
            "than proceeding.\n\n"
            "When finished, commit your changes on this worktree branch "
            "(git add -A && git commit) and give a concise final summary of "
            "exactly what you changed and why — this becomes the task's "
            "completion record."
        )

    async def _report_blocker(self, session, description: str) -> None:
        logger.warning(
            "Agent session %s execution blocked: %s", session.session_id, description
        )
        try:
            await self._coordinator_client.report_blocker(
                task_id=session.task_id,
                tenant_id=session.tenant_id,
                agent_id=session.session_id,
                description=_truncate(description),
            )
        except Exception:
            logger.exception(
                "Failed to report blocker for session %s to Coordinator", session.session_id
            )


def _truncate(text: str) -> str:
    if len(text) <= _MAX_REPORTED_OUTPUT_CHARS:
        return text
    return text[:_MAX_REPORTED_OUTPUT_CHARS] + "... [truncated]"
