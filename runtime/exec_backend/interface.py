"""The ``ExecutionBackend`` seam — generic agent-code execution, isolated.

This is the **lower** of Antiek's two execution seams. Where
``runtime/remote_exec/provider.py`` is the research-fanout seam (streaming
step events, cooperative steering, cost-on-event), this one is the generic
code-execution seam underneath it: a workspace that runs ``argv`` and moves
files, nothing more. There is no streaming, no steering, no event channel —
just ``exec`` + files. The two seams are kept separate on purpose (see the
spec's "kept, not merged" rationale); a future adapter may sit a
``RemoteExecProvider`` *on top of* an ``ExecutionBackend``, but that join is
not built here.

The architectural rule this seam enforces, copied verbatim from the spec's
invariants:

  * **Agents touch the world only via ``exec`` + files.** No graph handle, no
    ingest lock, no event-log writer crosses this boundary. The serialized
    host-side writer stays *outside* every workspace; a workspace exports
    artifacts (``get_file``) and the host's single writer consumes them.
  * **Provider SDK types never cross the interface.** Only the dataclasses and
    builtins defined in this file appear in signatures. A future Docker/E2B
    adapter keeps its SDK import inside its own one file (the same lazy-import
    idiom ``runtime/remote_exec/daytona.py`` uses); missing SDK → loud
    ``BackendUnavailable``, never a silent degradation.

The single-writer discipline is **mechanically provable**, the same way
``runtime/remote_exec/funnel.py`` proves it (its docstring shows the one-file
grep that audit holds it). The equivalent invariant here is the *zero*-file
grep: the three host-side graph-write identifiers — the serialized write
entry point, the ingest lock module, and the append-only event-log module —
appear in **zero** files of this package. That check is encoded as a test in
``tests/test_exec_backend_interface.py`` (it scans the package source for
those identifiers and asserts the hit list is empty), so CI fails the moment
a contributor reaches for the host writer from inside a workspace.

Numbered invariants, each with the mechanical check that keeps it honest:

  * **I1 — mandatory timeout, structured result.** ``exec`` has no default
    ``timeout_s`` (calling without it is a ``TypeError``); no raw
    ``Popen``/stream object ever crosses the seam. ``stdout``/``stderr`` are
    capped (``MAX_OUTPUT_BYTES``) and flagged ``truncated`` beyond. A timeout
    kills the whole process group and returns ``ExecResult(timed_out=True)``,
    never a hang.
  * **I2 — no host writer in workspaces.** The grep proof above; CI-asserted.
  * **I3 — single-writer ingest stays outside.** Workspaces write to their own
    ``out/`` dir; the host copies artifacts out via ``get_file``; only
    host-side consumers that already serialize through the ingest lock ever
    touch the graph. ``--workers 1`` is untouched by any stage of this seam.
  * **I4 — net policy is declared and honestly enforced.** A backend that
    cannot enforce the requested ``NetPolicy`` raises ``NetPolicyUnsupported``
    at ``create()``; it never silently ignores a declared isolation policy (a
    lie about isolation is worse than a refusal). Stage 0 honors
    ``ALLOW_ALL`` only.
  * **I5 — no SDK types in signatures.** Only this module's dataclasses and
    builtins below.
  * **I6 — workspaces are disposable and ID-addressed.** Persistence is
    explicit artifact export only; ``destroy()`` is idempotent and always
    called.
  * **I7 — no shared process pool, ever.** One process per ``exec``, own
    session/group, no reuse — the loky/``parameter_extractor`` external-kill
    lesson encoded as a review rule.

The interface is a ``runtime_checkable`` ``Protocol`` so a fake in the test
suite satisfies it structurally without inheriting — exactly the discipline
``runtime/remote_exec/provider.py`` uses for its provider seam.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

#: Per-stream output cap (I1). ``stdout``/``stderr`` beyond this are truncated
#: and the result's ``truncated`` flag is set, so a runaway child cannot OOM
#: the host by streaming gigabytes back through the seam.
MAX_OUTPUT_BYTES: int = 2 * 1024 * 1024


class NetPolicyKind(enum.StrEnum):
    """What egress a workspace is allowed. A ``StrEnum`` so the value crosses
    logs/JSON as its plain string (mirrors ``RemoteSignal`` in
    ``runtime/remote_exec/provider.py``; ``StrEnum`` is the pyupgrade of that
    file's ``str, enum.Enum`` idiom)."""

    ALLOW_ALL = "allow_all"
    DENY_ALL = "deny_all"
    #: ``allow`` entries are CIDRs and/or hostnames; enforced only by backends
    #: with a real network filter (nftables bridge, Kata/E2B native).
    ALLOWLIST = "allowlist"


@dataclass(frozen=True)
class NetPolicy:
    """A declared egress policy. Declared by every caller (I4) even when the
    backend only honors ``ALLOW_ALL`` — the declaration is the contract, the
    enforcement is the backend's honesty."""

    kind: NetPolicyKind
    #: Only meaningful for ``ALLOWLIST``; ignored (but still carried) otherwise.
    allow: tuple[str, ...] = ()


#: Convenience singletons for the two common policies.
ALLOW_ALL: NetPolicy = NetPolicy(NetPolicyKind.ALLOW_ALL)
DENY_ALL: NetPolicy = NetPolicy(NetPolicyKind.DENY_ALL)


@dataclass(frozen=True)
class ResourceLimits:
    """Best-effort resource envelope for a workspace. Stage 0 enforces these
    advisorially (see each backend's ``probe``); the systemd variant
    (``CPUQuota``/``MemoryMax``) and the Docker backend (``--cpus``/
    ``--memory``) enforce them for real. ``wall_clock_s`` is the workspace
    lifetime ceiling — a caller's ``try/finally`` ``destroy()`` plus an
    external sweep defend it; this seam does not run a timer daemon (YAGNI)."""

    cpu_cores: float = 1.0
    memory_mb: int = 2048
    disk_mb: int = 2048
    wall_clock_s: int = 900


@dataclass(frozen=True)
class WorkspaceProfile:
    """What kind of workspace to provision. ``image`` is a backend-specific
    hint (e.g. a container image), never an SDK type — ``None`` means the
    backend's default. ``env`` is a non-secret baseline environment, frozen as
    a tuple-of-pairs so the profile is hashable and immutable."""

    name: str
    image: str | None = None
    env: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ExecResult:
    """The structured outcome of one ``exec`` — never a raw ``Popen`` or
    stream handle (I1). On timeout the process group is killed and
    ``exit_code`` is set to ``-1`` with ``timed_out=True``; a process that
    exceeds a stream cap is returned with ``truncated=True`` rather than
    dropped."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    truncated: bool = False


# --- Error taxonomy ------------------------------------------------------
#
# Mirrors ``runtime/remote_exec/provider.py``: one ``RuntimeError`` base so
# ``except ExecutionBackendError`` catches every failure this seam raises, and
# concrete subclasses that distinguish *config* vs *provision* vs *policy* vs
# *lost* so a caller can branch informatively. No failure here degrades
# silently — the factory (when it exists) is the one place an intentional
# cross-backend decision is made, and even then it is loud.


class ExecutionBackendError(RuntimeError):
    """Base for every execution-backend failure. Catch this to handle any
    failure this seam surfaces; catch a subclass to branch on the mode."""


class BackendUnavailable(ExecutionBackendError):
    """The backend's dependency is missing (daemon down, SDK not installed,
    capability absent) and was explicitly requested. Loud, not silent — a
    missing daemon is a config error, not a reason to quietly weaken
    isolation. The ``local`` backend never raises this (nothing to be
    missing)."""


class WorkspaceProvisionError(ExecutionBackendError):
    """A workspace could not be allocated (quota, disk, transient spawn
    failure). Distinguished from ``BackendUnavailable`` (a config error) so a
    caller can retry one provision without concluding the backend is down."""


class NetPolicyUnsupported(ExecutionBackendError):
    """The backend cannot *enforce* the declared ``NetPolicy`` (I4). Raised at
    ``create()`` — never a silent ignore. Declaring ``DENY_ALL`` against the
    plain Stage-0 backend (which has no network filter) raises this rather
    than lying that egress is blocked."""


class WorkspaceLost(ExecutionBackendError):
    """A workspace died out of band (its process vanished, its dir was
    removed externally) before ``destroy()`` was called."""


@runtime_checkable
class Workspace(Protocol):
    """One disposable, ID-addressed workspace (I6). A fake in the test suite
    satisfies this structurally; ``_LocalWorkspace`` satisfies it for real.

    All methods are coroutines except the ``workspace_id`` property. Files are
    addressed relative to the workspace root and jailed to it (a ``..`` or
    absolute escape is rejected); the conventional subdirs ``in/``, ``out/``,
    ``work/`` are created at provision time."""

    @property
    def workspace_id(self) -> str: ...

    async def exec(
        self,
        argv: Sequence[str],
        *,
        # MANDATORY and keyword-only by design (I1): there is no safe default
        # for "how long may untrusted code run", so we force the caller to say.
        timeout_s: float,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
        stdin: bytes | None = None,
    ) -> ExecResult: ...

    async def put_file(self, path: str, content: bytes) -> None: ...

    async def get_file(self, path: str) -> bytes: ...

    async def destroy(self) -> None:
        """Tear the workspace down. Idempotent — safe to call twice (the
        runner may call it on cancel after the provider already tore down)."""
        ...


@runtime_checkable
class ExecutionBackend(Protocol):
    """The execution-backend seam. A fake satisfies this structurally; the
    Stage-0 ``LocalProcessBackend`` satisfies it for real; future Docker/E2B
    adapters satisfy it without consumers changing.

    Contract:

      * ``name`` identifies the backend in logs (``"local"`` | ``"docker"`` |
        …). A property, not a method.
      * ``probe`` confirms the backend is usable *now* (daemon reachable,
        runtime registered, SDK importable) and raises ``BackendUnavailable``
        loudly if not. The ``local`` backend's probe never touches the network
        and never raises.
      * ``create`` provisions one workspace for one ``WorkspaceProfile`` under
        a declared ``ResourceLimits`` and ``NetPolicy``. May raise
        ``BackendUnavailable`` (config), ``WorkspaceProvisionError``
        (transient), or ``NetPolicyUnsupported`` (policy the backend will not
        lie about enforcing — I4).
    """

    @property
    def name(self) -> str: ...

    def probe(self) -> None: ...

    async def create(
        self,
        profile: WorkspaceProfile,
        *,
        limits: ResourceLimits,
        # MANDATORY (I4): declared even when only ALLOW_ALL is honored.
        net_policy: NetPolicy,
    ) -> Workspace: ...


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
]
