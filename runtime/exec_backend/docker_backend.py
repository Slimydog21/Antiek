"""Stage-1 backend: one disposable Docker container per workspace.

``DockerBackend`` is the second rung of the ``ExecutionBackend`` ladder
(spec ``sandbox-execution-seam.md`` §5.4): where ``LocalProcessBackend``
runs agent code as ordinary children of the host, this backend runs it
inside a container — non-root, read-only rootfs, tmpfs scratch — and pays
for that with a real isolation story the plain-process mode honestly does
not have. It satisfies the same frozen ``ExecutionBackend`` /
``Workspace`` protocols, so a consumer swapping ``local`` → ``docker``
changes exactly one construction site and nothing else.

How it is built:

  * **The ``docker`` CLI, not an SDK.** ``pyproject.toml`` carries no
    docker Python dependency, so every operation shells out through a
    small client seam (``DockerClient``) whose real implementation
    (``_SubprocessDockerClient``) runs ``docker <args>`` as an asyncio
    subprocess. The seam is **injectable**: tests hand the backend a fake
    client that records invocations and scripts results, so the entire
    lifecycle — ``run`` / ``exec`` / ``kill`` / ``rm`` — is
    assertable without a daemon.
  * **One container per workspace.** ``create`` provisions a detached
    container ``antiek-ws-<hex>`` from ``profile.image`` (or the default
    ``alpine:latest``), running ``sleep infinity`` as its no-op keeper
    command, then ``mkdir``s the conventional ``in/`` / ``out/`` /
    ``work/`` subdirs inside it. The workspace is ID-addressed and
    disposable (I6); persistence is explicit ``get_file`` export only —
    a destroyed container is the workspace, gone.
  * **Isolation shape:** ``--user 65534:65534`` (nobody), ``--read-only``
    rootfs, ``--tmpfs /tmp`` and ``--tmpfs /workspace``, ``--cpus`` /
    ``--memory`` from the declared ``ResourceLimits``, ``--pids-limit``
    256, ``--security-opt no-new-privileges``. One deliberate departure
    from the spec's literal flags: the spec writes ``--tmpfs
    /workspace/work``, but with a read-only rootfs the sibling ``in/``
    and ``out/`` dirs could never be provisioned on an arbitrary image —
    so the whole job dir ``/workspace`` is the tmpfs scratch, and all
    three conventional subdirs live on it. The read-only rootfs claim is
    otherwise unchanged: nothing on the image itself is mutable.
  * **No host mounts, period.** The job dir travels as bytes, never as a
    bind mount — a bind mount would hand agent code a handle on host
    filesystem state, which this seam's rule (agents touch the world only
    via ``exec`` + files) forbids. ``put_file`` streams the bytes into
    the container via ``docker exec -i tee <path>`` — pure argv, no shell
    interpolation (the path is attacker-shaped), binary-safe, and the
    file lands owned by the workspace user (``nobody``), so agent code
    can read *and* write its inputs without mode gymnastics.
    ``get_file`` reads via ``docker exec cat <path>`` raw stdout. Why not
    ``docker cp``: on Docker ≥ 29 the daemon refuses ``docker cp`` on
    ``--read-only`` containers in both directions — writes fail with
    "container rootfs is marked read-only" and reads cannot see tmpfs
    contents ("Could not find the file"), verified 2026-08-07 against
    Docker 29.2.1 even with registered ``type=tmpfs`` mounts — so this
    adapter does not depend on it. The workspace image must ship
    ``mkdir`` / ``tee`` / ``cat`` (busybox and coreutils both do).
  * **Net policy, honestly enforced (I4).** ``DENY_ALL`` → ``--network
    none`` at ``create``; ``ALLOW_ALL`` → the default bridge (no flag).
    ``ALLOWLIST`` is refused with ``NetPolicyUnsupported`` — the plain
    bridge has no hostname/CIDR filter, and a policy the backend cannot
    enforce is refused loudly, never ignored.
  * **Mandatory timeout, structured result (I1).** ``exec`` runs
    ``docker exec`` through the client with the caller's ``timeout_s``
    (no default); on expiry the workspace issues ``docker kill`` against
    the container and returns ``ExecResult(timed_out=True,
    exit_code=-1)`` — killing the container is airtight, no process tree
    survives it.
  * **Idempotent destroy (I6).** ``destroy()`` issues ``docker rm -f``
    once and is a no-op thereafter; a container already removed out of
    band ("no such container") is tolerated, mirroring
    ``LocalProcessBackend``'s ``rmtree(ignore_errors=True)``.

gVisor rung: ``ANTIEK_EXEC_DOCKER_RUNTIME=runsc`` (or the ``runtime=``
constructor arg) adds ``--runtime runsc`` to ``create``; probe logs which
runtime the backend will use. The interface does not change — that is the
point of the seam.

Honesty notes: ``probe`` is synchronous and drives the async client via
``asyncio.run`` — call it from a sync context (the conformance suite
does). ``get_file`` raises on an artifact that exceeds the seam's output
cap rather than returning a silently truncated file — a corrupted
artifact is worse than a loud failure.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .interface import (
    MAX_OUTPUT_BYTES,
    BackendUnavailable,
    ExecResult,
    ExecutionBackendError,
    NetPolicy,
    NetPolicyKind,
    NetPolicyUnsupported,
    ResourceLimits,
    WorkspaceProfile,
    WorkspaceProvisionError,
)
from .local_process import _drain_capped

#: Image used when ``WorkspaceProfile.image`` is None. Alpine is a few MB,
#: ships busybox ``sh``/``sleep``/``cat``, and runs as ``nobody`` without
#: drama — the smallest keeper that satisfies the seam's default needs.
_DEFAULT_IMAGE: str = "alpine:latest"

#: Container-name prefix; ``create`` makes ``antiek-ws-<uuid4-hex>``.
_CONTAINER_PREFIX: str = "antiek-ws-"

#: How long provisioning calls (``run``, the provision ``mkdir``) may take
#: before the client kills them. Pulling an image the first time is the slow
#: case; 120s is generous without hanging a caller forever.
_PROVISION_TIMEOUT_S: float = 120.0

#: How long a file operation (``mkdir`` / ``tee`` / ``cat``) may take.
_FILE_OP_TIMEOUT_S: float = 60.0

#: How long ``kill`` / ``rm -f`` may take during teardown and timeout
#: escalation.
_KILL_TIMEOUT_S: float = 15.0

#: How long ``probe`` waits for ``docker version`` against the daemon.
_PROBE_TIMEOUT_S: float = 10.0


@dataclass(frozen=True)
class DockerClientResult:
    """The structured outcome of one ``docker <args>`` invocation. Bytes, not
    str — stdout may carry raw file bytes (``get_file``); the caller decodes
    where text is expected. On a client-side timeout the process is killed and
    ``exit_code`` is ``-1`` with ``timed_out=True``."""

    exit_code: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    truncated: bool = False


@runtime_checkable
class DockerClient(Protocol):
    """The injectable ``docker`` CLI seam. A fake in the test suite satisfies
    this structurally — every backend operation (``run``, ``exec``, ``kill``,
    ``rm``, ``version``) is a single async ``run``, which is what makes the
    whole lifecycle mockable without a daemon. ``timeout_s`` is optional here
    (some operations are fire-and-forget-ish); ``stdin`` is streamed to the
    CLI process when given (``put_file``'s ``tee``, ``exec -i``)."""

    async def run(
        self,
        args: Sequence[str],
        *,
        timeout_s: float | None = None,
        stdin: bytes | None = None,
    ) -> DockerClientResult: ...


class _SubprocessDockerClient:
    """The real ``DockerClient``: runs ``docker <args>`` as an asyncio
    subprocess, draining both streams concurrently (so a chatty daemon reply
    cannot deadlock the pipe) and capping each at ``MAX_OUTPUT_BYTES``. A
    missing CLI binary is reported as the shell's ``command not found``
    convention (exit 127) in a structured result — the same honest signal
    ``LocalProcessBackend.exec`` uses — so ``probe`` and ``create`` can tell
    "CLI missing" apart from "daemon down" by reading the message, not the
    exception."""

    def __init__(self, *, binary: str = "docker") -> None:
        self._binary = binary

    async def run(
        self,
        args: Sequence[str],
        *,
        timeout_s: float | None = None,
        stdin: bytes | None = None,
    ) -> DockerClientResult:
        if not args:
            raise ValueError("docker args must be non-empty")
        stdin_arg = (
            asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                self._binary,
                *args,
                stdin=stdin_arg,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return DockerClientResult(
                exit_code=127,
                stdout=b"",
                stderr=f"executable not found on PATH: {self._binary}".encode(),
            )

        if stdin is not None and proc.stdin is not None:
            with contextlib.suppress(BrokenPipeError, ConnectionResetError, OSError):
                proc.stdin.write(stdin)
                await proc.stdin.drain()
            proc.stdin.close()
            with contextlib.suppress(BrokenPipeError, OSError):
                await proc.stdin.wait_closed()

        # Drain both streams concurrently with the wait — the same load-bearing
        # pattern as local_process: without a concurrent reader a child
        # emitting more than a pipe buffer's worth of output blocks on write.
        stdout_task = asyncio.ensure_future(_drain_capped(proc.stdout))
        stderr_task = asyncio.ensure_future(_drain_capped(proc.stderr))

        timed_out = False
        if timeout_s is not None:
            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout_s)
            except TimeoutError:
                timed_out = True
                proc.kill()
                await proc.wait()
        else:
            await proc.wait()

        out_b, out_trunc = await stdout_task
        err_b, err_trunc = await stderr_task
        rc = proc.returncode
        exit_code = -1 if timed_out else (rc if rc is not None else -1)
        return DockerClientResult(
            exit_code=exit_code,
            stdout=out_b,
            stderr=err_b,
            timed_out=timed_out,
            truncated=out_trunc or err_trunc,
        )


class _DockerWorkspace:
    """One disposable workspace backed by one container (``antiek-ws-<hex>``).

    Satisfies the ``Workspace`` protocol structurally. Files are addressed
    relative to the container job dir ``/workspace`` and jailed to it (an
    absolute path or any ``..`` component is rejected, mirroring
    ``_LocalWorkspace._jailed``); they travel in and out as raw bytes over
    ``docker exec`` (``tee`` in, ``cat`` out) — no host-side directory
    exists for this backend, so a workspace's files *are* its container's
    ``/workspace`` tmpfs.
    """

    def __init__(
        self,
        *,
        workspace_id: str,
        container_name: str,
        client: DockerClient,
        profile: WorkspaceProfile,
        limits: ResourceLimits,
        log: logging.Logger,
    ) -> None:
        self._id = workspace_id
        self._name = container_name
        self._client = client
        self._profile = profile
        self._limits = limits
        self._log = log
        self._destroyed = False

    @property
    def workspace_id(self) -> str:
        return self._id

    @property
    def container_name(self) -> str:
        """The docker container backing this workspace (ops/teardown)."""
        return self._name

    def _jailed(self, path: str) -> str:
        """Resolve ``path`` against the workspace root and reject any escape.
        Container paths are relative to ``/workspace``: an absolute path, a
        ``..`` component, or an empty component is refused; the remainder is
        normalized (``out//x`` → ``out/x``) for a clean container path."""
        if not path or os.path.isabs(path):
            raise ValueError(f"path escapes workspace root: {path!r}")
        parts = path.replace("\\", "/").split("/")
        if any(part in ("", "..") for part in parts):
            raise ValueError(f"path escapes workspace root: {path!r}")
        return "/".join(parts)

    def _container_path(self, path: str) -> str:
        return f"/workspace/{self._jailed(path)}"

    async def _kill_container(self) -> None:
        """Force-kill the backing container. Best-effort: the container may
        already be gone (the caller's timeout race or an out-of-band teardown);
        a genuine failure is logged, never raised, so the timeout path always
        returns its structured result."""
        result = await self._client.run(["kill", self._name], timeout_s=_KILL_TIMEOUT_S)
        if result.exit_code != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            if "no such container" not in err.lower():
                self._log.warning(
                    "docker kill %s failed (exit %s): %s",
                    self._name,
                    result.exit_code,
                    err,
                )

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
        args: list[str] = ["exec"]
        if env:
            for key, value in env.items():
                args += ["-e", f"{key}={value}"]
        work_cwd = "/workspace/work" if cwd is None else self._container_path(cwd)
        args += ["-w", work_cwd]
        if stdin is not None:
            args.append("-i")
        args += [self._name, *argv]

        start = time.monotonic()
        result = await self._client.run(args, timeout_s=timeout_s, stdin=stdin)
        duration_ms = int((time.monotonic() - start) * 1000)
        out_s = result.stdout.decode("utf-8", errors="replace")
        err_s = result.stderr.decode("utf-8", errors="replace")
        if result.timed_out:
            # The docker exec client was killed at timeout_s; the exec'd
            # process inside the container would otherwise keep running, so
            # kill the whole container — airtight, no tree survives.
            await self._kill_container()
            return ExecResult(
                exit_code=-1,
                stdout=out_s,
                stderr=err_s,
                duration_ms=duration_ms,
                timed_out=True,
                truncated=result.truncated,
            )
        return ExecResult(
            exit_code=result.exit_code,
            stdout=out_s,
            stderr=err_s,
            duration_ms=duration_ms,
            truncated=result.truncated,
        )

    async def put_file(self, path: str, content: bytes) -> None:
        """Stream ``content`` into ``/workspace/<path>`` via
        ``docker exec -i tee`` — pure argv, no shell interpolation, so a
        path with spaces or metacharacters is just a path; binary-safe;
        and the file lands owned by the workspace user (``nobody``), so
        agent code can read and write its own inputs. The parent dir is
        created first (``mkdir -p``); docker's own ``cp`` is unusable on
        ``--read-only`` containers (see the module docstring)."""
        jailed = self._jailed(path)
        parent, _, _ = jailed.rpartition("/")
        container_dir = f"/workspace/{parent}" if parent else "/workspace"
        mkdir = await self._client.run(
            ["exec", self._name, "mkdir", "-p", container_dir],
            timeout_s=_FILE_OP_TIMEOUT_S,
        )
        if mkdir.exit_code != 0:
            err = mkdir.stderr.decode("utf-8", errors="replace").strip()
            raise ExecutionBackendError(
                f"mkdir in workspace {self._id} failed "
                f"(exit {mkdir.exit_code}): {err}"
            )
        result = await self._client.run(
            ["exec", "-i", self._name, "tee", f"/workspace/{jailed}"],
            stdin=content,
            timeout_s=_FILE_OP_TIMEOUT_S,
        )
        if result.exit_code != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            raise ExecutionBackendError(
                f"put_file into workspace {self._id} failed "
                f"(exit {result.exit_code}): {err}"
            )

    async def get_file(self, path: str) -> bytes:
        """Pull ``/workspace/<path>`` out of the container via
        ``docker exec cat`` raw stdout and return its content — a missing
        file surfaces as ``FileNotFoundError`` (the same contract the local
        backend keeps), and an artifact past the seam's output cap raises
        rather than coming back silently truncated."""
        container_path = self._container_path(path)
        result = await self._client.run(
            ["exec", self._name, "cat", container_path],
            timeout_s=_FILE_OP_TIMEOUT_S,
        )
        if result.exit_code != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            if "No such file or directory" in err or "Is a directory" in err:
                raise FileNotFoundError(f"not in workspace {self._id}: {path!r}")
            raise ExecutionBackendError(
                f"get_file from workspace {self._id} failed "
                f"(exit {result.exit_code}): {err}"
            )
        if result.truncated:
            raise ExecutionBackendError(
                f"get_file from workspace {self._id} exceeded the "
                f"{MAX_OUTPUT_BYTES}-byte output cap; raise the cap or "
                "export smaller artifacts"
            )
        return result.stdout

    async def destroy(self) -> None:
        """Remove the backing container (``docker rm -f``). Idempotent (I6):
        one rm, then a no-op; a container already removed out of band is
        tolerated. Never raises — mirroring ``LocalProcessBackend``'s
        ``rmtree(ignore_errors=True)`` — but a genuine rm failure is logged
        loudly so a leaked container is not silent."""
        if self._destroyed:
            return
        self._destroyed = True
        result = await self._client.run(["rm", "-f", self._name], timeout_s=_KILL_TIMEOUT_S)
        if result.exit_code != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            if "no such container" not in err.lower():
                self._log.warning(
                    "docker rm -f %s failed (exit %s): %s — container may "
                    "leak; remove manually",
                    self._name,
                    result.exit_code,
                    err,
                )


class DockerBackend:
    """The Stage-1 ``ExecutionBackend``: one container per workspace.

    Satisfies the ``ExecutionBackend`` protocol structurally. Construct with
    an injected ``client`` in tests; in production the default client shells
    the ``docker`` CLI. ``runtime`` (defaulting to
    ``$ANTIEK_EXEC_DOCKER_RUNTIME``) selects the container runtime
    (e.g. ``runsc`` for the gVisor rung) via ``--runtime`` on ``create``.
    """

    def __init__(
        self,
        *,
        client: DockerClient | None = None,
        runtime: str | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        self._client = client if client is not None else _SubprocessDockerClient()
        resolved_runtime = runtime if runtime is not None else os.environ.get(
            "ANTIEK_EXEC_DOCKER_RUNTIME"
        )
        self._runtime = resolved_runtime if resolved_runtime else None
        self._log = log or logging.getLogger("antiek.exec_backend.docker")

    @property
    def name(self) -> str:
        return "docker"

    def probe(self) -> None:
        """Confirm the backend is usable *now*: the CLI answers and the daemon
        is reachable (``docker version`` server section). Any failure — CLI
        missing (exit 127) or daemon unreachable — raises
        ``BackendUnavailable`` loudly; there is no silent degradation to
        ``local``, because downgrading would silently weaken an isolation
        guarantee the caller declared. Synchronous by contract; call from a
        sync context (as the conformance suite does)."""
        result = asyncio.run(
            self._client.run(
                ["version", "--format", "{{.Server.Version}}"],
                timeout_s=_PROBE_TIMEOUT_S,
            )
        )
        if result.exit_code != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            raise BackendUnavailable(
                f"docker unavailable (exit {result.exit_code}): {err}"
            )
        version = result.stdout.decode("utf-8", errors="replace").strip()
        self._log.info(
            "DockerBackend ready; server version %s; runtime=%s",
            version,
            self._runtime or "default",
        )

    async def create(
        self,
        profile: WorkspaceProfile,
        *,
        limits: ResourceLimits,
        net_policy: NetPolicy,
    ) -> _DockerWorkspace:
        if net_policy.kind is NetPolicyKind.ALLOWLIST:
            # I4 — honest enforcement: the plain bridge has no hostname/CIDR
            # filter, so an allowlist is refused loudly, never approximated.
            raise NetPolicyUnsupported(
                f"DockerBackend cannot enforce {net_policy.kind.value}: the "
                "default bridge has no allowlist filter. Use ALLOW_ALL or "
                "DENY_ALL (--network none)."
            )
        wid = uuid.uuid4().hex
        name = f"{_CONTAINER_PREFIX}{wid}"
        run_argv: list[str] = [
            "run",
            "-d",
            "--name",
            name,
            "--user",
            "65534:65534",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/workspace",
            "--cpus",
            f"{limits.cpu_cores}",
            "--memory",
            f"{limits.memory_mb}m",
            "--pids-limit",
            "256",
            "--security-opt",
            "no-new-privileges",
        ]
        if net_policy.kind is NetPolicyKind.DENY_ALL:
            run_argv += ["--network", "none"]
        if self._runtime:
            run_argv += ["--runtime", self._runtime]
        for key, value in profile.env:
            run_argv += ["-e", f"{key}={value}"]
        image = profile.image or _DEFAULT_IMAGE
        run_argv += [image, "sleep", "infinity"]

        result = await self._client.run(run_argv, timeout_s=_PROVISION_TIMEOUT_S)
        if result.exit_code != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            raise WorkspaceProvisionError(
                f"docker run for {name} failed (exit {result.exit_code}): {err}"
            )

        workspace = _DockerWorkspace(
            workspace_id=wid,
            container_name=name,
            client=self._client,
            profile=profile,
            limits=limits,
            log=self._log,
        )
        mkdir = await self._client.run(
            [
                "exec",
                name,
                "mkdir",
                "-p",
                "/workspace/in",
                "/workspace/out",
                "/workspace/work",
            ],
            timeout_s=_PROVISION_TIMEOUT_S,
        )
        if mkdir.exit_code != 0:
            # Provision failed after the container was created — roll the
            # container back so a half-baked workspace cannot leak.
            with contextlib.suppress(Exception):
                await self._client.run(["rm", "-f", name], timeout_s=_KILL_TIMEOUT_S)
            err = mkdir.stderr.decode("utf-8", errors="replace").strip()
            raise WorkspaceProvisionError(
                f"workspace {name} provision incomplete (mkdir failed, "
                f"exit {mkdir.exit_code}): {err}"
            )
        self._log.info(
            "DockerBackend created workspace %s (container %s, network=%s, "
            "runtime=%s)",
            wid,
            name,
            net_policy.kind.value,
            self._runtime or "default",
        )
        return workspace


__all__ = ["DockerBackend"]
