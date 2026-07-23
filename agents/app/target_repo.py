"""Checks out the single target codebase AECP is coordinating agents on.

AECP's own schema (aecp.common.v1.OwnershipBoundary) has no repo URL or
clone target anywhere on it — only relative path_globs/forbidden_globs.
Per CLAUDE.md's own framing ("coordinating multiple autonomous engineers
... on a single real codebase"), this repo takes a single configured
target repo (env var) rather than a per-task/per-tenant repo registry,
which is explicitly out of scope for a first working version of real
execution.

Known, deliberately deferred gap: a `git worktree add` against
TARGET_REPO_PATH leaves a `.git/worktrees/<branch>` metadata entry behind
after the scratch dir it points at is later rmtree'd by Sandbox.destroy()
— no cleanup hook exists yet. A periodic `git worktree prune` (or an
explicit `git worktree remove` wired into session teardown) is real
fast-follow work, not silently dropped.
"""

from __future__ import annotations

import asyncio
from pathlib import Path


class TargetRepoCheckout:
    def __init__(self, *, repo_path: str = "", repo_url: str = "", git_binary: str = "git") -> None:
        self._repo_path = repo_path
        self._repo_url = repo_url
        self._git_binary = git_binary

    async def checkout(self, scratch_dir: str, session_id: str) -> str:
        """Materialize the target repo into scratch_dir/repo, on a fresh
        branch scoped to this session, and return its path.

        Raises RuntimeError if neither TARGET_REPO_PATH nor
        TARGET_REPO_URL is configured — callers (AgentExecutor) treat
        that as a reason to report a blocker, not crash the session.
        """
        dest = str(Path(scratch_dir) / "repo")

        if self._repo_path:
            branch = f"aecp-session-{session_id}"
            await self._run_git(["-C", self._repo_path, "worktree", "add", "-b", branch, dest])
        elif self._repo_url:
            await self._run_git(["clone", "--depth", "1", self._repo_url, dest])
        else:
            raise RuntimeError(
                "No TARGET_REPO_PATH or TARGET_REPO_URL configured; cannot check "
                "out a codebase for the agent to work on."
            )

        # A commit made by the agent needs *some* identity — this is a
        # local, session-scoped config, not a claim about who authored
        # the resulting change (that's KIND_AGENT in the decision log).
        await self._run_git(["-C", dest, "config", "user.email", "agent@aecp.local"])
        await self._run_git(["-C", dest, "config", "user.name", "AECP Agent"])

        return dest

    async def _run_git(self, args: list[str]) -> None:
        proc = await asyncio.create_subprocess_exec(
            self._git_binary,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed ({proc.returncode}): {stderr.decode(errors='replace')}"
            )
