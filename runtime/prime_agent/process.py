"""Hermetic, bounded synchronous execution for Prime Agent one-shot calls."""

from __future__ import annotations

import atexit
import ctypes
import os
import selectors
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from select import select as select_select
from typing import TYPE_CHECKING, BinaryIO, Self, cast

if TYPE_CHECKING:
    from runtime.prime_agent.installation import PrimeAgentInstallation

_READ_SIZE = 16_384
_PROVIDER_CREDENTIAL_KEYS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
    }
)
_STAGE_CACHE_LOCK = threading.RLock()
_STAGE_CACHE_ROOT: Path | None = None
_STAGE_CACHE_PID: int | None = None
_CACHE_GENERATIONS: dict[str, list[_CacheGeneration]] = {}


@dataclass(slots=True)
class _CacheGeneration:
    path: Path
    leases: int = 0
    stale: bool = False


@dataclass(slots=True)
class _GenerationLease:
    generation: _CacheGeneration
    released: bool = False

    def release(self) -> None:
        if self.released:
            return
        self.released = True
        with _STAGE_CACHE_LOCK:
            self.generation.leases -= 1
            if self.generation.stale and self.generation.leases == 0:
                _remove_generation(self.generation)


def _stage_cache_root() -> Path:
    global _STAGE_CACHE_PID, _STAGE_CACHE_ROOT
    current_pid = os.getpid()
    if _STAGE_CACHE_ROOT is None or current_pid != _STAGE_CACHE_PID:
        root = Path(tempfile.mkdtemp(prefix="antiek-prime-cache-"))
        root.chmod(0o700)
        _STAGE_CACHE_ROOT = root
        _STAGE_CACHE_PID = current_pid
    return _STAGE_CACHE_ROOT


def _cleanup_stage_cache() -> None:
    global _STAGE_CACHE_PID, _STAGE_CACHE_ROOT
    root = _STAGE_CACHE_ROOT
    owner_pid = _STAGE_CACHE_PID
    _STAGE_CACHE_ROOT = None
    _STAGE_CACHE_PID = None
    _CACHE_GENERATIONS.clear()
    if root is not None and owner_pid == os.getpid():
        _make_tree_writable(root)
        shutil.rmtree(root, ignore_errors=True)


def _make_tree_writable(root: Path) -> None:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_dir():
            with suppress(OSError):
                path.chmod(0o700)
    with suppress(OSError):
        root.chmod(0o700)


def _remove_generation(generation: _CacheGeneration) -> None:
    _make_tree_writable(generation.path)
    shutil.rmtree(generation.path, ignore_errors=True)
    for generations in _CACHE_GENERATIONS.values():
        if generation in generations:
            generations.remove(generation)
            break


atexit.register(_cleanup_stage_cache)


def _pre_spawn_hook() -> None:
    """Deterministic test seam after verified open and before fd-bound exec."""


def _popen_verified(
    config: PrimeAgentProcessConfig,
    argv: tuple[str, ...],
    *,
    env: Mapping[str, str],
    isolated_root: Path,
) -> tuple[subprocess.Popen[bytes], _GenerationLease]:
    artifact, lease = _cached_verified_artifact(config, isolated_root)
    _pre_spawn_hook()
    try:
        process = subprocess.Popen(
            argv,
            executable=artifact,
            cwd=config.cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except BaseException:
        lease.release()
        raise
    return process, lease


def _cached_verified_artifact(
    config: PrimeAgentProcessConfig, isolated_root: Path
) -> tuple[Path, _GenerationLease]:
    from runtime.prime_agent.installation import (
        prime_agent_artifact_digest,
        revalidate_prime_agent_installation,
        seal_staged_prime_agent,
        stage_verified_prime_agent,
        validate_staged_prime_agent,
    )

    with _STAGE_CACHE_LOCK:
        revalidate_prime_agent_installation(config.installation)
        root = _stage_cache_root()
        key = prime_agent_artifact_digest(config.installation)
        generations = _CACHE_GENERATIONS.setdefault(key, [])
        generation = generations[-1] if generations else None
        artifact = (
            validate_staged_prime_agent(config.installation, generation.path)
            if generation is not None and not generation.stale
            else None
        )
        if artifact is None:
            if generation is not None:
                generation.stale = True
                if generation.leases == 0:
                    _remove_generation(generation)
            destination = root / f"{key}-{uuid.uuid4().hex}"
            building = root / f".{destination.name}.building"
            staged = stage_verified_prime_agent(config.installation, building)
            relative = staged.relative_to(building)
            os.replace(building, destination)
            seal_staged_prime_agent(destination)
            artifact = validate_staged_prime_agent(config.installation, destination)
            if artifact is None or artifact != destination / relative:
                raise RuntimeError("cached Prime Agent artifact failed post-stage validation")
            generation = _CacheGeneration(destination)
            generations.append(generation)
        assert generation is not None
        generation.leases += 1
        lease = _GenerationLease(generation)
        snapshot = isolated_root / "verified-package"
        try:
            shutil.copytree(generation.path, snapshot, copy_function=_clone_or_copy)
        except BaseException:
            lease.release()
            raise
        private_artifact = validate_staged_prime_agent(config.installation, snapshot)
        if private_artifact is None:
            lease.release()
            raise RuntimeError("cached Prime Agent artifact failed post-stage validation")
        return private_artifact, lease


def _clone_or_copy(source: str, destination: str) -> str:
    """Use APFS copy-on-write cloning when available, else a normal private copy."""
    if os.uname().sysname == "Darwin":
        clonefile = ctypes.CDLL(None, use_errno=True).clonefile
        clonefile.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int)
        clonefile.restype = ctypes.c_int
        if clonefile(os.fsencode(source), os.fsencode(destination), 0) == 0:
            return destination
    return shutil.copy2(source, destination)


def _isolated_environment(config: PrimeAgentProcessConfig, root: Path) -> dict[str, str]:
    source = os.environ if config.environ is None else config.environ
    home = root / "home"
    session = root / "session"
    tmp = root / "tmp"
    for directory in (home, session, tmp):
        directory.mkdir(mode=0o700)
    env = {key: source[key] for key in ("PATH", "LANG", "LC_ALL") if source.get(key)}
    env.update(
        {
            "HOME": str(home),
            "TMPDIR": str(tmp),
            "XDG_CONFIG_HOME": str(session / "config"),
            "XDG_CACHE_HOME": str(session / "cache"),
            "XDG_DATA_HOME": str(session / "data"),
            "XDG_STATE_HOME": str(session / "state"),
        }
    )
    credentials = config.provider_environment
    if credentials:
        env.update(credentials)
    return env


@dataclass(frozen=True, slots=True)
class PrimeAgentProcessConfig:
    installation: PrimeAgentInstallation
    cwd: Path
    timeout_seconds: float
    max_stdout_bytes: int
    max_stderr_bytes: int
    terminate_grace_seconds: float = 0.25
    environ: Mapping[str, str] | None = None
    provider_environment: Mapping[str, str] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.installation.binary.is_absolute() or not self.installation.binary.is_file():
            raise ValueError("Prime Agent binary must be an absolute regular file")
        if not self.cwd.is_absolute() or not self.cwd.is_dir():
            raise ValueError("Prime Agent cwd must be an absolute existing directory")
        if self.timeout_seconds <= 0 or self.terminate_grace_seconds < 0:
            raise ValueError("Prime Agent deadlines must be valid")
        if self.max_stdout_bytes <= 0 or self.max_stderr_bytes <= 0:
            raise ValueError("Prime Agent output limits must be positive")
        if self.provider_environment is not None:
            keys = set(self.provider_environment)
            if len(keys) != 1 or not keys <= _PROVIDER_CREDENTIAL_KEYS:
                raise ValueError("Prime Agent requires exactly one recognized provider credential")
            if not next(iter(self.provider_environment.values()), ""):
                raise ValueError("Prime Agent provider credential must not be empty")


@dataclass(frozen=True, slots=True)
class PrimeAgentProcessResult:
    argv: tuple[str, ...]
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    duration_ms: int
    timed_out: bool = False
    stdout_limit_exceeded: bool = False
    stderr_limit_exceeded: bool = False


class PrimeAgentManagedProcess:
    """Hermetic synchronous handle for a bounded JSONL-RPC subprocess."""

    def __init__(
        self,
        config: PrimeAgentProcessConfig,
        process: subprocess.Popen[bytes],
        temporary_home: tempfile.TemporaryDirectory[str],
        session_dir: Path,
        generation_lease: _GenerationLease,
    ) -> None:
        self.config = config
        self.process = process
        self._temporary_home = temporary_home
        self._stdout_buffer = bytearray()
        self._stdout_total = 0
        self._stderr_total = 0
        self._closed = False
        self.session_dir = session_dir
        self._generation_lease = generation_lease
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        for stream in (process.stdin, process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def send_line(self, line: bytes, *, deadline: float) -> None:
        """Write exactly one LF-framed command without an unbounded pipe wait."""
        if b"\n" in line.rstrip(b"\n"):
            raise ValueError("Prime Agent RPC command must be one line")
        payload = line if line.endswith(b"\n") else line + b"\n"
        view = memoryview(payload)
        offset = 0
        assert self.process.stdin is not None
        while offset < len(view):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Prime Agent RPC stdin deadline exceeded")
            _, writable, _ = select_select((), (self.process.stdin,), (), remaining)
            if not writable:
                raise TimeoutError("Prime Agent RPC stdin deadline exceeded")
            try:
                offset += os.write(self.process.stdin.fileno(), view[offset:])
            except BrokenPipeError as exc:
                raise RuntimeError("Prime Agent RPC stdin closed") from exc

    def read_line(self, *, max_bytes: int, deadline: float) -> bytes | None:
        """Read one LF-terminated stdout record while continuously draining stderr."""
        assert self.process.stdout is not None and self.process.stderr is not None
        while True:
            newline = self._stdout_buffer.find(b"\n")
            if newline >= 0:
                record = bytes(self._stdout_buffer[: newline + 1])
                del self._stdout_buffer[: newline + 1]
                return record
            if len(self._stdout_buffer) > max_bytes:
                raise RuntimeError("Prime Agent RPC stdout record exceeded limit")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Prime Agent RPC stdout deadline exceeded")
            readable, _, _ = select_select(
                (self.process.stdout, self.process.stderr), (), (), remaining
            )
            if not readable:
                raise TimeoutError("Prime Agent RPC stdout deadline exceeded")
            for stream in readable:
                chunk = os.read(stream.fileno(), _READ_SIZE)
                if stream is self.process.stderr:
                    self._stderr_total += len(chunk)
                    if self._stderr_total > self.config.max_stderr_bytes:
                        raise RuntimeError("Prime Agent RPC stderr exceeded limit")
                elif chunk:
                    self._stdout_total += len(chunk)
                    if self._stdout_total > self.config.max_stdout_bytes:
                        raise RuntimeError("Prime Agent RPC stdout exceeded total limit")
                    self._stdout_buffer.extend(chunk)
                elif self.process.poll() is not None:
                    if self._stdout_buffer:
                        raise RuntimeError("Prime Agent RPC closed with an unterminated record")
                    return None

    def poll(self) -> int | None:
        return self.process.poll()

    def close_stdin(self) -> None:
        """Deliver EOF after a validated terminal RPC record."""
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()

    def wait_exit(self, *, deadline: float) -> int:
        """Drain stderr and reject trailing stdout until clean process exit."""
        while True:
            line = self.read_line(max_bytes=self.config.max_stdout_bytes, deadline=deadline)
            if line is not None:
                raise RuntimeError("Prime Agent RPC emitted stdout after terminal record")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Prime Agent RPC exit deadline exceeded")
            try:
                return self.process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError("Prime Agent RPC exit deadline exceeded") from exc

    def terminate(self, *, deadline: float) -> None:
        _terminate_group(self.process, deadline, self.config.terminate_grace_seconds)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.process.poll() is None:
            self.terminate(deadline=time.monotonic() + self.config.terminate_grace_seconds)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()
        self._temporary_home.cleanup()
        self._generation_lease.release()


def spawn_prime_agent_managed(
    config: PrimeAgentProcessConfig,
    args: Sequence[str] | Callable[[Path], Sequence[str]],
) -> PrimeAgentManagedProcess:
    """Spawn a verified, isolated process for a caller-managed RPC exchange."""
    temporary_home = tempfile.TemporaryDirectory(prefix="antiek-prime-rpc-")
    root = Path(temporary_home.name)
    env = _isolated_environment(config, root)
    session_dir = root / "session-dir"
    session_dir.mkdir(mode=0o700)
    try:
        if callable(args):
            resolved_args = tuple(args(session_dir))
            try:
                session_index = resolved_args.index("--session-dir")
            except ValueError as exc:
                raise ValueError(
                    "managed Prime Agent argv must include isolated --session-dir"
                ) from exc
            if (
                session_index + 1 >= len(resolved_args)
                or resolved_args[session_index + 1] != str(session_dir)
            ):
                raise ValueError("managed Prime Agent --session-dir must use the isolated path")
        else:
            if "--session-dir" in args:
                raise ValueError("managed Prime Agent session directory is process-owned")
            resolved_args = (*args, "--session-dir", str(session_dir))
        argv = (str(config.installation.binary), *resolved_args)
        process, lease = _popen_verified(config, argv, env=env, isolated_root=root)
    except BaseException:
        temporary_home.cleanup()
        raise
    return PrimeAgentManagedProcess(config, process, temporary_home, session_dir, lease)


def run_prime_agent_process(
    config: PrimeAgentProcessConfig, args: Sequence[str], *, stdin: bytes
) -> PrimeAgentProcessResult:
    """Run with prompt on stdin, isolated state dirs, and a total wall deadline."""
    argv = (str(config.installation.binary), *args)
    started = time.monotonic()
    deadline = started + config.timeout_seconds
    with tempfile.TemporaryDirectory(prefix="antiek-prime-") as root:
        root_path = Path(root)
        env = _isolated_environment(config, root_path)
        try:
            process, lease = _popen_verified(config, argv, env=env, isolated_root=root_path)
        except OSError:
            raise
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        streams = {process.stdout: (bytearray(), config.max_stdout_bytes), process.stderr: (bytearray(), config.max_stderr_bytes)}
        selector = selectors.DefaultSelector()
        for stream in streams:
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
        os.set_blocking(process.stdin.fileno(), False)
        selector.register(process.stdin, selectors.EVENT_WRITE)
        input_view = memoryview(stdin)
        input_offset = 0
        timed_out = stdout_over = stderr_over = False
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                events = selector.select(min(remaining, 0.05))
                for key, _ in events:
                    stream = cast(BinaryIO, key.fileobj)
                    if stream is process.stdin:
                        try:
                            written = os.write(key.fd, input_view[input_offset : input_offset + _READ_SIZE])
                        except (BrokenPipeError, OSError):
                            written = 0
                            input_offset = len(input_view)
                        input_offset += written
                        if input_offset >= len(input_view):
                            selector.unregister(stream)
                            process.stdin.close()
                        continue
                    chunk = os.read(key.fd, _READ_SIZE)
                    if not chunk:
                        selector.unregister(stream)
                        continue
                    target, limit = streams[stream]
                    room = max(0, limit - len(target))
                    target.extend(chunk[:room])
                    if len(chunk) > room:
                        if stream is process.stdout:
                            stdout_over = True
                        else:
                            stderr_over = True
                        break
                if stdout_over or stderr_over:
                    break
            if timed_out or stdout_over or stderr_over or selector.get_map():
                _terminate_group(process, deadline, config.terminate_grace_seconds)
            else:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    _terminate_group(process, deadline, config.terminate_grace_seconds)
                else:
                    try:
                        process.wait(timeout=remaining)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        _terminate_group(process, deadline, config.terminate_grace_seconds)
        except BaseException:
            _terminate_group(process, deadline, config.terminate_grace_seconds)
            raise
        finally:
            selector.close()
            if not process.stdin.closed:
                process.stdin.close()
            process.stdout.close()
            process.stderr.close()
            lease.release()
        stdout = bytes(streams[process.stdout][0])
        stderr = bytes(streams[process.stderr][0])
    return PrimeAgentProcessResult(
        argv=argv,
        exit_code=process.returncode,
        stdout=stdout,
        stderr=stderr,
        duration_ms=max(0, round((time.monotonic() - started) * 1000)),
        timed_out=timed_out,
        stdout_limit_exceeded=stdout_over,
        stderr_limit_exceeded=stderr_over,
    )


def _terminate_group(process: subprocess.Popen[bytes], deadline: float, grace: float) -> None:
    """TERM the entire session, then KILL it without exceeding the total deadline."""
    with suppress(OSError):
        os.killpg(process.pid, signal.SIGTERM)
    if process.poll() is None:
        with suppress(OSError):
            process.terminate()
    wait_for = min(grace, max(0.0, deadline - time.monotonic()))
    if wait_for:
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=wait_for)
    # Kill the group even if its leader exited: hostile grandchildren may remain.
    with suppress(OSError):
        os.killpg(process.pid, signal.SIGKILL)
    if process.poll() is None:
        with suppress(OSError):
            process.kill()
    with suppress(subprocess.TimeoutExpired):
        process.wait(timeout=max(0.01, min(0.1, max(0.0, deadline - time.monotonic()))))
