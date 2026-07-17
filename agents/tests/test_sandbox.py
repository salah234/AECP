"""Tests for the dev-placeholder Sandbox: scratch directory allocation
and cleanup, ownership_globs recording. Does not test isolation, since
this implementation deliberately provides none (see sandbox.py's
module docstring).
"""

from __future__ import annotations

from pathlib import Path

from app.sandbox import Sandbox


async def test_create_allocates_scratch_dir_with_ownership_globs() -> None:
    sandbox = Sandbox(image="unused-in-dev-placeholder")

    handle = await sandbox.create(
        session_id="session-1",
        tenant_id="tenant-1",
        ownership_globs=["agents/app/**", "!agents/app/secrets/**"],
    )

    scratch_dir = Path(handle.scratch_dir)
    assert scratch_dir.is_dir()
    globs_file = scratch_dir / "OWNERSHIP_GLOBS"
    assert globs_file.read_text() == "agents/app/**\n!agents/app/secrets/**"


async def test_destroy_removes_scratch_dir() -> None:
    sandbox = Sandbox(image="unused-in-dev-placeholder")
    handle = await sandbox.create(
        session_id="session-1", tenant_id="tenant-1", ownership_globs=[]
    )

    await sandbox.destroy(handle)

    assert not Path(handle.scratch_dir).exists()


async def test_destroy_is_idempotent_on_missing_dir() -> None:
    sandbox = Sandbox(image="unused-in-dev-placeholder")
    handle = await sandbox.create(
        session_id="session-1", tenant_id="tenant-1", ownership_globs=[]
    )

    await sandbox.destroy(handle)
    await sandbox.destroy(handle)  # must not raise
