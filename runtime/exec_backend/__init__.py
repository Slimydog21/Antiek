"""``runtime.exec_backend`` — the generic agent-code execution seam.

The **lower** of Antiek's two execution seams: a workspace that runs ``argv``
and moves files, nothing more. Where ``runtime.remote_exec`` is the research-
fanout seam (streaming step events, cooperative steering, cost-on-event),
this is the generic code-execution seam underneath it — no streaming, no
steering, just ``exec`` + files. The two are kept separate on purpose; a
future adapter may sit a ``RemoteExecProvider`` on top of an
``ExecutionBackend``, but that join is not built here.

The one architectural rule this seam enforces: **agents touch the world only
via ``exec`` + files.** No graph handle, no ingest lock, no event-log writer
crosses this boundary — the serialized host-side writer stays *outside* every
workspace; a workspace exports artifacts (``get_file``) and the host's single
writer consumes them. The ``--workers 1`` invariant is untouched by every
stage of this seam.

This package ships exactly the Stage-0 floor:

  * ``interface`` — the frozen seam: frozen dataclasses
    (``NetPolicy`` / ``ResourceLimits`` / ``WorkspaceProfile`` /
    ``ExecResult``), the error taxonomy, and the ``Workspace`` +
    ``ExecutionBackend`` ``runtime_checkable`` protocols. Provider SDK types
    never appear in it.
  * ``local_process`` — ``LocalProcessBackend``, the zero-dependency default
    that runs agent code as plain subprocesses on the host the operator
    already owns. Every later backend (Docker, gVisor, microVM, managed E2B)
    is a mechanical adapter on top of this interface, never a rework.

Importing this package touches no network and loads no provider SDK.
"""

from __future__ import annotations

from .interface import (
    ALLOW_ALL,
    DENY_ALL,
    MAX_OUTPUT_BYTES,
    BackendUnavailable,
    ExecResult,
    ExecutionBackend,
    ExecutionBackendError,
    NetPolicy,
    NetPolicyKind,
    NetPolicyUnsupported,
    ResourceLimits,
    Workspace,
    WorkspaceLost,
    WorkspaceProfile,
    WorkspaceProvisionError,
)
from .local_process import LocalProcessBackend

__all__ = [
    # dataclasses crossing the seam
    "NetPolicy",
    "NetPolicyKind",
    "ResourceLimits",
    "WorkspaceProfile",
    "ExecResult",
    "ALLOW_ALL",
    "DENY_ALL",
    "MAX_OUTPUT_BYTES",
    # error taxonomy
    "ExecutionBackendError",
    "BackendUnavailable",
    "WorkspaceProvisionError",
    "NetPolicyUnsupported",
    "WorkspaceLost",
    # protocols
    "Workspace",
    "ExecutionBackend",
    # stage-0 backend
    "LocalProcessBackend",
]
