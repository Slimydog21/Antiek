"""Deterministic fake ``ExecutionBackend`` / ``Workspace`` for the seam tests.

No network, no subprocess, no daemon — every interface/conformance test that
does not need a *real* process runs against ``FakeBackend`` so the suite is
reproducible and fast. The fakes satisfy the ``Workspace`` and
``ExecutionBackend`` protocols structurally (no inheritance), mirroring how a
real backend would and mirroring ``tests/remote_exec_fakes.py``.

``FakeBackend`` is the structural stand-in: it proves the *interface*, not any
one backend, is what consumers depend on — the same test logic exercised
against ``LocalProcessBackend`` (real subprocesses) passes against the fake.
Genuinely process-level behavior (a real timeout kill, real exit codes) lives
in ``tests/test_exec_backend_local.py``; the conformance suite here holds only
the contract that every conformant backend must share.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence

from runtime.exec_backend.interface import (
    ExecResult,
    ExecutionBackend,
    NetPolicy,
    NetPolicyKind,
    NetPolicyUnsupported,
    ResourceLimits,
    Workspace,
    WorkspaceProfile,
)


class FakeWorkspace:
    """In-memory workspace. ``exec`` scripts the few commands the conformance
    suite needs (``echo`` / ``false``); files live in a dict. ``timeout_s`` is
    mandatory and keyword-only — exactly the contract a real backend keeps
    (invariant I1) — so a caller forgetting it gets a ``TypeError`` here too."""

    def __init__(self, workspace_id: str) -> None:
        self._id = workspace_id
        self._files: dict[str, bytes] = {}
        self.destroyed = 0

    @property
    def workspace_id(self) -> str:
        return self._id

    def _jailed_key(self, path: str) -> str:
        # Mirror the local jail: reject absolute and ``..`` escapes so the
        # conformance assertions are identical across backends.
        if not path or os.path.isabs(path):
            raise ValueError(f"path escapes workspace root: {path!r}")
        parts = path.replace("\\", "/").split("/")
        if any(part == ".." for part in parts):
            raise ValueError(f"path escapes workspace root: {path!r}")
        return path

    async def exec(
        self,
        argv: Sequence[str],
        *,
        timeout_s: float,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
        stdin: bytes | None = None,
    ) -> ExecResult:
        if len(argv) == 0:
            raise ValueError("argv must be non-empty")
        head = argv[0]
        if head == "echo":
            return ExecResult(
                exit_code=0,
                stdout=" ".join(argv[1:]) + "\n",
                stderr="",
                duration_ms=1,
            )
        if head == "false":
            return ExecResult(exit_code=1, stdout="", stderr="", duration_ms=1)
        return ExecResult(exit_code=0, stdout="", stderr="", duration_ms=1)

    async def put_file(self, path: str, content: bytes) -> None:
        self._files[self._jailed_key(path)] = content

    async def get_file(self, path: str) -> bytes:
        key = self._jailed_key(path)
        if key not in self._files:
            raise FileNotFoundError(f"not in workspace {self._id}: {path!r}")
        return self._files[key]

    async def destroy(self) -> None:
        # Idempotent (I6): a second call is a no-op.
        self.destroyed += 1


class FakeBackend:
    """Structural ``ExecutionBackend``. ``reject_policy=True`` makes ``create``
    refuse non-``ALLOW_ALL`` policies (invariant I4) so the honest-enforcement
    contract is testable without a real network filter."""

    def __init__(self, *, reject_policy: bool = True) -> None:
        self._reject_policy = reject_policy
        self.created: list[str] = []

    @property
    def name(self) -> str:
        return "fake"

    def probe(self) -> None:
        return None

    async def create(
        self,
        profile: WorkspaceProfile,  # noqa: ARG002 — accepted for protocol parity
        *,
        limits: ResourceLimits,  # noqa: ARG002
        net_policy: NetPolicy,
    ) -> FakeWorkspace:
        if self._reject_policy and net_policy.kind is not NetPolicyKind.ALLOW_ALL:
            raise NetPolicyUnsupported(
                f"fake cannot enforce {net_policy.kind.value}"
            )
        wid = f"fake-{len(self.created)}"
        self.created.append(wid)
        return FakeWorkspace(workspace_id=wid)


# Prove at import time that the fakes satisfy the protocols structurally —
# if a contributor changes a signature, this fires immediately.
assert isinstance(FakeBackend(), ExecutionBackend)
assert isinstance(FakeWorkspace(workspace_id="x"), Workspace)
