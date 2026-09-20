"""Stage-0 backend: a plain-subprocess workspace (the one box, today).

``LocalProcessBackend`` is the default ``ExecutionBackend`` — it runs agent
code as ordinary child processes on the host the operator already owns. No
daemon, no SDK, no container runtime, no network call: it is the zero-
dependency floor that every later backend (Docker, gVisor, microVM, managed
E2B) is a mechanical adapter *on top of* this seam for, never a rework of it.

What this mode buys cheaply and what it honestly does not:

  * **Bought cheaply** — a disposable, ID-addressed workspace dir per
    ``create``; agent code that touches the world only through ``exec`` +
    files; a parent environment that is **never inherited** (children get a
    minimal allowlist — ``PATH``, ``LANG``, ``HOME`` → the workspace — plus
    the profile/exec overrides), so agent code cannot read the host's keys
    that live in the parent env; a mandatory process-group-scoped timeout
    that kills the whole tree and returns a structured result, never a hang;
    a best-effort address-space ceiling on Linux.
  * **Honestly not bought here** — CPU/disk limits (advisory; enforced by the
    systemd ``CPUQuota``/``MemoryMax`` rung or Docker ``--cpus``/``--memory``)
    and any egress filter. Because plain subprocess has no network filter,
    ``create`` with anything other than ``ALLOW_ALL`` raises
    ``NetPolicyUnsupported`` (invariant I4) rather than pretending egress is
    blocked — a lie about isolation is worse than a refusal.

No shared process pool, ever (I7): one process per ``exec``, its own session
and group (``start_new_session=True``), no worker reuse, no cross-workspace
semaphores. This is the deliberate "disposable dissolves the failure class"
argument: a dead process is a dead workspace, not a poisoned pool — the
loky / ``parameter_extractor`` external-kill lesson encoded here directly.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import signal
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from .interface import (
    MAX_OUTPUT_BYTES,
    ExecResult,
    ExecutionBackendError,
    NetPolicy,
    NetPolicyKind,
    NetPolicyUnsupported,
    ResourceLimits,
    WorkspaceProfile,
)

#: Grace window between SIGTERM and SIGKILL when a timeout fires. The group
#: gets a chance to clean up (flush, unlock, remove its own tmpfiles); if it
#: ignores SIGTERM it is unconditionally killed. Kept short — the caller
#: already declared ``timeout_s`` and the process blew past it.
_KILL_GRACE_S: float = 5.0

try:
    import resource as _resource
except ImportError:  # Windows — not a supported backend host.
    _resource = None  # type: ignore[assignment]


def _resolve_workdir_base(workdir_base: str | os.PathLike[str] | None) -> Path:
    """Where workspace dirs live. Resolution order, mirroring the spec's
    ``${ANTIEK_EXEC_WORKDIR:-$ANTIEK_STATE_DIR/exec_workspaces}``:

      1. the explicit ``workdir_base`` arg (tests pass a tmp_path here);
      2. ``$ANTIEK_EXEC_WORKDIR``;
      3. ``$ANTIEK_STATE_DIR/exec_workspaces``;
      4. a self-contained dir under the system temp (kept tidy by
         ``destroy()`` and the documented wall-clock sweep).
    """
    if workdir_base is not None:
        return Path(workdir_base)
    env_dir = os.environ.get("ANTIEK_EXEC_WORKDIR")
    if env_dir:
        return Path(env_dir)
    state_dir = os.environ.get("ANTIEK_STATE_DIR")
    if state_dir:
        return Path(state_dir) / "exec_workspaces"
    return Path(tempfile.gettempdir()) / "antiek-exec-workspaces"


def _child_apply_rlimit_as(memory_bytes: int) -> None:
    """``preexec_fn`` body: runs in the forked child before ``exec``. Applies a
    coarse ``RLIMIT_AS`` ceiling. Best-effort and defensive — the real memory
    cap is the systemd ``MemoryMax`` rung or Docker ``--memory``; a failure to
    set the limit (unsupported value, no privilege) never aborts the spawn."""
    if _resource is None:
        return
    with contextlib.suppress(ValueError, OSError):
        _resource.setrlimit(_resource.RLIMIT_AS, (memory_bytes, memory_bytes))


def _make_preexec(memory_mb: int) -> Callable[[], None] | None:
    """Build the ``preexec_fn`` for a workspace, or ``None`` when the platform
    does not get rlimits. Only Linux gets ``RLIMIT_AS``; macOS dev boxes skip
    it (the limit is documented advisory there — see ``probe``)."""
    if sys.platform != "linux":
        return None
    memory_bytes = memory_mb * 1024 * 1024

    def _preexec() -> None:
        _child_apply_rlimit_as(memory_bytes)

    return _preexec


async def _kill_process_group(proc: asyncio.subprocess.Process, grace_s: float) -> None:
    """Tear down a whole process group: SIGTERM, wait ``grace_s``, then
    SIGKILL. Covers double-forked children because ``start_new_session=True``
    made the child a session/group leader. Leaves the process reaped."""
    if proc.returncode is not None:
        return
    pid = proc.pid
    if pid is None:
        return
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace_s)
        return
    except TimeoutError:
        pass
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    await proc.wait()


#: Chunk size for draining a child stream. Kept at the OS pipe-buffer order of
#: magnitude so each read frees the pipe promptly and the child never blocks.
_READ_CHUNK_BYTES: int = 64 * 1024


async def _drain_capped(stream: asyncio.StreamReader | None) -> tuple[bytes, bool]:
    """Continuously drain one child stream to EOF, keeping at most
    ``MAX_OUTPUT_BYTES`` and flagging ``truncated`` if there was more.

    This MUST run concurrently with ``proc.wait()``: an ``asyncio`` subprocess
    ``StreamReader`` pauses its transport once its buffer passes the high-water
    mark, after which the OS pipe fills and the child **blocks on write** — the
    documented ``proc.wait()``+``PIPE`` deadlock. Reading here as the process
    runs keeps the pipe empty so a child emitting more than a pipe-buffer's
    worth of output completes instead of being falsely killed as a timeout.
    Bytes past the cap are read and discarded (not buffered) so a runaway child
    can neither deadlock the seam nor OOM the host."""
    if stream is None:
        return b"", False
    buf = bytearray()
    truncated = False
    while True:
        chunk = await stream.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        remaining = MAX_OUTPUT_BYTES - len(buf)
        if remaining > 0:
            buf.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
        else:
            truncated = True
        # keep looping to EOF even past the cap — draining, not buffering
    return bytes(buf), truncated


class _LocalWorkspace:
    """One disposable workspace backed by a real directory. Satisfies the
    ``Workspace`` protocol structurally — no inheritance."""

    def __init__(
        self,
        *,
        workspace_id: str,
        root: Path,
        profile: WorkspaceProfile,
        limits: ResourceLimits,
        log: logging.Logger,
    ) -> None:
        self._id = workspace_id
        self._root = root
        self._profile = profile
        self._limits = limits
        self._log = log
        self._work_dir = root / "work"
        self._preexec_fn = _make_preexec(limits.memory_mb)

    @property
    def workspace_id(self) -> str:
        return self._id

    @property
    def root(self) -> Path:
        """The workspace's on-disk root (host-side callers use ``get_file``;
        this is exposed for host-side artifact collection, not for workspace
        code)."""
        return self._root

    def _jailed(self, path: str) -> Path:
        """Resolve ``path`` against the workspace root and reject any escape.
        An absolute path replaces the root (``Path(root) / "/etc" == "/etc"``)
        and a ``..`` chain walks out of it; ``relative_to`` raises for both."""
        root = self._root.resolve()
        candidate = (self._root / path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            msg = f"path escapes workspace root: {path!r}"
            raise ValueError(msg) from exc
        return candidate

    def _build_env(self, exec_env: Mapping[str, str] | None) -> dict[str, str]:
        """Minimal allowlist env. The parent's environment — which on prod
        carries the host's secrets — is never inherited. Only ``PATH`` (to find
        the binary), ``LANG``, and ``HOME`` (the workspace) seed the child;
        profile baseline and the per-exec override layer on top."""
        env: dict[str, str] = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "HOME": str(self._root),
        }
        for key, value in self._profile.env:
            env[key] = value
        if exec_env:
            env.update(exec_env)
        return env

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
        child_env = self._build_env(env)
        work_cwd = self._work_dir if cwd is None else self._jailed(cwd)
        stdin_arg = (
            asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL
        )
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(work_cwd),
                env=child_env,
                start_new_session=True,
                preexec_fn=self._preexec_fn,
                stdin=stdin_arg,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            # Binary missing — structured result using the shell's "command
            # not found" convention (127) rather than an unhandled exception.
            return ExecResult(
                exit_code=127,
                stdout="",
                stderr=str(exc),
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except OSError as exc:
            # Spawn failed for another reason (e.g. permission/EAGAIN) — raise
            # loudly; this is not the "command not found" happy path.
            raise ExecutionBackendError(
                f"failed to spawn {list(argv)!r}: {exc}"
            ) from exc

        # Drain both output streams CONCURRENTLY with the wait below. This is
        # load-bearing: without a concurrent reader a child emitting more than
        # a pipe buffer's worth of output blocks on write and never exits (the
        # documented proc.wait()+PIPE deadlock), so it would be falsely killed
        # as a timeout. See ``_drain_capped``.
        stdout_task = asyncio.ensure_future(_drain_capped(proc.stdout))
        stderr_task = asyncio.ensure_future(_drain_capped(proc.stderr))

        if stdin is not None and proc.stdin is not None:
            with contextlib.suppress(BrokenPipeError, ConnectionResetError, OSError):
                proc.stdin.write(stdin)
                await proc.stdin.drain()
            proc.stdin.close()
            with contextlib.suppress(BrokenPipeError, OSError):
                await proc.stdin.wait_closed()

        timed_out = False
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout_s)
        except TimeoutError:
            timed_out = True
            await _kill_process_group(proc, grace_s=_KILL_GRACE_S)

        # The process (and its group) has now exited — on its own or by our
        # kill. Both drain tasks see EOF on the closed pipes and complete with
        # whatever was captured up to the cap.
        out_b, out_trunc = await stdout_task
        err_b, err_trunc = await stderr_task
        out_s = out_b.decode("utf-8", errors="replace")
        err_s = err_b.decode("utf-8", errors="replace")
        if timed_out:
            exit_code = -1
        else:
            rc = proc.returncode
            exit_code = rc if rc is not None else -1
        return ExecResult(
            exit_code=exit_code,
            stdout=out_s,
            stderr=err_s,
            duration_ms=int((time.monotonic() - start) * 1000),
            timed_out=timed_out,
            truncated=out_trunc or err_trunc,
        )

    async def put_file(self, path: str, content: bytes) -> None:
        target = self._jailed(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    async def get_file(self, path: str) -> bytes:
        target = self._jailed(path)
        if not target.exists():
            raise FileNotFoundError(f"not in workspace {self._id}: {path!r}")
        return target.read_bytes()

    async def destroy(self) -> None:
        # Idempotent (I6): ignore_errors makes a second call a no-op, and a
        # crashed-and-already-removed dir is fine too.
        shutil.rmtree(self._root, ignore_errors=True)


class LocalProcessBackend:
    """The Stage-0 ``ExecutionBackend``: plain subprocesses on this host.

    Satisfies the ``ExecutionBackend`` protocol structurally. Construct with an
    explicit ``workdir_base`` in tests; in production it resolves from
    ``$ANTIEK_EXEC_WORKDIR`` / ``$ANTIEK_STATE_DIR`` (see
    ``_resolve_workdir_base``).
    """

    def __init__(
        self,
        *,
        workdir_base: str | os.PathLike[str] | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        self._base = _resolve_workdir_base(workdir_base)
        self._log = log or logging.getLogger("antiek.exec_backend.local")

    @property
    def name(self) -> str:
        return "local"

    @property
    def base_dir(self) -> Path:
        """The parent under which workspace dirs are created (host-side
        accounting, e.g. the orphan sweep; not for workspace code)."""
        return self._base

    def probe(self) -> None:
        """Confirm the backend is usable. ``local`` has no daemon, SDK, or
        capability to be missing — so this never raises and never touches the
        network. It logs one honesty line documenting which ``ResourceLimits``
        fields this mode actually enforces, because silently accepting a limit
        it does not keep would be a lie."""
        if sys.platform == "linux":
            enforced = "memory_mb=advisory (RLIMIT_AS, best-effort)"
        else:
            enforced = "none (RLIMIT_AS skipped on non-Linux dev boxes)"
        self._log.info(
            "LocalProcessBackend ready; limits enforced=[%s]; "
            "advisory=[cpu_cores, disk_mb — use the systemd/Docker rungs]",
            enforced,
        )

    async def create(
        self,
        profile: WorkspaceProfile,
        *,
        limits: ResourceLimits,
        net_policy: NetPolicy,
    ) -> _LocalWorkspace:
        if net_policy.kind is not NetPolicyKind.ALLOW_ALL:
            # I4 — honest enforcement. Plain subprocess has no egress filter,
            # so anything but ALLOW_ALL is refused loudly, never silently.
            raise NetPolicyUnsupported(
                f"LocalProcessBackend (plain mode) cannot enforce "
                f"{net_policy.kind.value}: it has no network filter. Use "
                "ALLOW_ALL, or a backend with a real egress filter (the "
                "systemd IPAddressDeny variant, Docker --network none, ...)."
            )
        self._base.mkdir(parents=True, exist_ok=True)
        wid = uuid.uuid4().hex
        root = self._base / wid
        for sub in ("in", "out", "work"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        return _LocalWorkspace(
            workspace_id=wid,
            root=root,
            profile=profile,
            limits=limits,
            log=self._log,
        )


__all__ = ["LocalProcessBackend"]
