"""Resolve and capability-check the one supported Prime Agent CLI line."""

from __future__ import annotations

import os
import re
import shutil
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

PRIME_AGENT_BINARY_ENV = "ANTIEK_PRIME_AGENT_BIN"
DEFAULT_PRIME_AGENT_BINARY = "prime-agent"
MINIMUM_VERSION = (0, 7, 0)
MAXIMUM_VERSION = (0, 8, 0)
_MAX_BUNDLE_FILES = 4096
_MAX_BUNDLE_BYTES = 256 * 1024 * 1024
_BUNDLED_RUNTIME_PACKAGES = (
    "@silvia-odwyer/photon-node",
    "bufferutil",
    "cmake-ts",
    "google-auth-library",
    "node-addon-api",
    "typebox",
    "undici",
    "utf-8-validate",
    "zeromq",
)
_VERSION_RE = re.compile(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)")
_PRINT_FLAGS = frozenset(
    {
        "-p",
        "--cwd",
        "--offline",
        "--no-session",
        "--no-tools",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--no-themes",
        "--no-context-files",
    }
)
_RPC_FLAGS = frozenset({"--mode", "rpc"})
_PROBE_TIMEOUT_SECONDS = 5.0
_PROBE_OUTPUT_BYTES = 128_000


class PrimeAgentUnavailable(RuntimeError):
    """The configured executable cannot satisfy Antiek's pinned contract."""


@dataclass(frozen=True, slots=True)
class PrimeAgentBinaryIdentity:
    """Immutable executable metadata and content identity."""

    device: int
    inode: int
    size: int
    mtime_ns: int
    mode: int
    owner_uid: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PrimeAgentBundleEntry:
    relative_path: str
    identity: PrimeAgentBinaryIdentity


@dataclass(frozen=True, slots=True)
class PrimeAgentInstallation:
    """Verified executable identity and semantic version."""

    binary: Path
    version: tuple[int, int, int]
    identity: PrimeAgentBinaryIdentity
    bundle_root: Path | None = None
    bundle: tuple[PrimeAgentBundleEntry, ...] = ()


def resolve_prime_agent_binary(
    environ: Mapping[str, str] | None = None, *, binary: str | os.PathLike[str] | None = None
) -> Path:
    """Resolve the configured command to an absolute, executable regular file."""
    values = os.environ if environ is None else environ
    candidate = os.fspath(binary) if binary is not None else values.get(
        PRIME_AGENT_BINARY_ENV, DEFAULT_PRIME_AGENT_BINARY
    )
    if not candidate.strip():
        raise PrimeAgentUnavailable(f"{PRIME_AGENT_BINARY_ENV} must not be empty")
    found = shutil.which(candidate, path=values.get("PATH"))
    if found is None:
        raise PrimeAgentUnavailable("prime-agent executable not found")
    try:
        resolved = Path(found).resolve(strict=True)
    except OSError as exc:
        raise PrimeAgentUnavailable("prime-agent executable could not be resolved") from exc
    _snapshot_binary(resolved)
    return resolved


def verify_prime_agent_installation(
    binary: Path, *, environ: Mapping[str, str] | None = None
) -> PrimeAgentInstallation:
    """Reject version drift and CLIs missing print or JSONL-RPC capabilities."""
    identity = _snapshot_binary(binary)
    bundle_root, bundle = _snapshot_bundle(binary)
    provisional = PrimeAgentInstallation(
        binary=binary,
        version=(0, 0, 0),
        identity=identity,
        bundle_root=bundle_root,
        bundle=bundle,
    )
    version_text = _probe(provisional, ("--version",), environ=environ)
    match = _VERSION_RE.search(version_text)
    if match is None:
        raise PrimeAgentUnavailable("prime-agent returned an unparseable version")
    version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    if not MINIMUM_VERSION <= version < MAXIMUM_VERSION:
        raise PrimeAgentUnavailable(
            f"prime-agent version {'.'.join(map(str, version))} is outside >=0.7.0,<0.8.0"
        )
    help_tokens = frozenset(
        _HELP_TOKEN_RE.findall(_probe(provisional, ("--help",), environ=environ))
    )
    missing_print = sorted(_PRINT_FLAGS - help_tokens)
    missing_rpc = sorted(_RPC_FLAGS - help_tokens)
    if missing_print or missing_rpc:
        missing = ", ".join((*missing_print, *missing_rpc))
        raise PrimeAgentUnavailable(f"prime-agent is missing required CLI capabilities: {missing}")
    revalidate_prime_agent_installation(provisional)
    return PrimeAgentInstallation(
        binary=binary,
        version=version,
        identity=identity,
        bundle_root=bundle_root,
        bundle=bundle,
    )


_HELP_TOKEN_RE = re.compile(r"(?<![\w-])(?:--[a-z][a-z0-9-]*|-[A-Za-z]|[A-Za-z][A-Za-z0-9_-]*)(?![\w-])")


def revalidate_prime_agent_installation(installation: PrimeAgentInstallation) -> None:
    """Refuse an executable changed or atomically replaced since verification."""
    if _snapshot_binary(installation.binary) != installation.identity:
        raise PrimeAgentUnavailable("verified prime-agent executable changed before spawn")
    if installation.bundle_root is not None:
        root, entries = _snapshot_bundle(installation.binary)
        if root != installation.bundle_root or entries != installation.bundle:
            raise PrimeAgentUnavailable("verified prime-agent bundle changed before spawn")


def _snapshot_bundle(binary: Path) -> tuple[Path | None, tuple[PrimeAgentBundleEntry, ...]]:
    if binary.suffix != ".js":
        return None, ()
    bundle_dir = binary.parent
    package_root = bundle_dir.parent.parent
    package_json = package_root / "package.json"
    root = package_root if package_json.is_file() else bundle_dir
    paths = [*bundle_dir.rglob("*")]
    if package_json.is_file():
        paths.append(package_json)
        for package_name in _BUNDLED_RUNTIME_PACKAGES:
            dependency = package_root / "node_modules" / package_name
            if dependency.is_dir():
                paths.extend(dependency.rglob("*"))
    entries: list[PrimeAgentBundleEntry] = []
    total = 0
    for path in sorted(paths):
        if path.is_symlink() or not path.is_file():
            continue
        identity = _snapshot_binary(path, require_executable=path == binary)
        total += identity.size
        entries.append(PrimeAgentBundleEntry(str(path.relative_to(root)), identity))
        if len(entries) > _MAX_BUNDLE_FILES or total > _MAX_BUNDLE_BYTES:
            raise PrimeAgentUnavailable("prime-agent bundle exceeds verification bounds")
    if not entries:
        raise PrimeAgentUnavailable("prime-agent JavaScript bundle is empty")
    return root, tuple(entries)


@contextmanager
def open_verified_prime_agent(installation: PrimeAgentInstallation) -> Iterator[int]:
    """Yield an open descriptor bound to the exact verified executable bytes."""
    try:
        fd = os.open(installation.binary, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    except OSError as exc:
        raise PrimeAgentUnavailable("verified prime-agent executable could not be opened") from exc
    try:
        if _identity_from_fd(fd) != installation.identity:
            raise PrimeAgentUnavailable("verified prime-agent executable changed before spawn")
        yield fd
    finally:
        os.close(fd)


def stage_verified_prime_agent(installation: PrimeAgentInstallation, destination: Path) -> Path:
    """Copy only verified open descriptors into a private executable bundle."""
    destination.mkdir(mode=0o700)
    if installation.bundle_root is None:
        target = destination / installation.binary.name
        _copy_verified_file(installation.binary, installation.identity, target, executable=True)
        return target
    for entry in installation.bundle:
        source = installation.bundle_root / entry.relative_path
        target = destination / entry.relative_path
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _copy_verified_file(
            source,
            entry.identity,
            target,
            executable=source == installation.binary,
        )
    return destination / installation.binary.relative_to(installation.bundle_root)


def seal_staged_prime_agent(destination: Path) -> None:
    """Remove directory write bits only after atomic cache publication."""
    for directory in sorted(
        (path for path in destination.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.chmod(0o500)
    destination.chmod(0o500)


def prime_agent_artifact_digest(installation: PrimeAgentInstallation) -> str:
    """Return the canonical content/shape digest used for process-private caching."""
    digest = sha256()
    entries = installation.bundle or (
        PrimeAgentBundleEntry(installation.binary.name, installation.identity),
    )
    for entry in entries:
        digest.update(entry.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(entry.identity.size).encode("ascii"))
        digest.update(b"\0")
        digest.update(entry.identity.sha256.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def validate_staged_prime_agent(
    installation: PrimeAgentInstallation, destination: Path
) -> Path | None:
    """Return the staged entrypoint only when the private tree is exact and readonly."""
    if destination.is_symlink() or not destination.is_dir() or destination.stat().st_mode & (
        stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    ):
        return None
    entries = installation.bundle or (
        PrimeAgentBundleEntry(installation.binary.name, installation.identity),
    )
    expected_paths = {entry.relative_path for entry in entries}
    staged_paths = list(destination.rglob("*"))
    if any(path.is_symlink() for path in staged_paths):
        return None
    actual_paths = {
        str(path.relative_to(destination))
        for path in staged_paths
        if path.is_file()
    }
    if actual_paths != expected_paths:
        return None
    expected_directories = {
        str(parent)
        for relative in expected_paths
        for parent in Path(relative).parents
        if str(parent) != "."
    }
    actual_directories = {
        str(path.relative_to(destination)) for path in staged_paths if path.is_dir()
    }
    if actual_directories != expected_directories:
        return None
    for entry in entries:
        path = destination / entry.relative_path
        try:
            opened = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
        except OSError:
            return None
        try:
            actual = _identity_from_fd(opened)
        finally:
            os.close(opened)
        if actual.size != entry.identity.size or actual.sha256 != entry.identity.sha256:
            return None
        if actual.owner_uid != os.geteuid():
            return None
        if actual.mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            return None
    relative = (
        installation.binary.relative_to(installation.bundle_root)
        if installation.bundle_root is not None
        else Path(installation.binary.name)
    )
    entrypoint = destination / relative
    if not entrypoint.is_file() or not entrypoint.stat().st_mode & stat.S_IXUSR:
        return None
    return entrypoint


def _copy_verified_file(
    source: Path,
    expected: PrimeAgentBinaryIdentity,
    target: Path,
    *,
    executable: bool,
) -> None:
    try:
        source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    except OSError as exc:
        raise PrimeAgentUnavailable("verified prime-agent bundle file could not be opened") from exc
    try:
        if _identity_from_fd(source_fd) != expected:
            raise PrimeAgentUnavailable("verified prime-agent bundle changed before spawn")
        target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o500 if executable else 0o400)
        try:
            while chunk := os.read(source_fd, 128 * 1024):
                view = memoryview(chunk)
                offset = 0
                while offset < len(view):
                    offset += os.write(target_fd, view[offset:])
            os.fsync(target_fd)
        finally:
            os.close(target_fd)
    finally:
        os.close(source_fd)


def _snapshot_binary(binary: Path, *, require_executable: bool = True) -> PrimeAgentBinaryIdentity:
    """Open once, compare lstat/fstat, enforce ownership/mode, and hash that fd."""
    try:
        path_stat = binary.lstat()
        fd = os.open(binary, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    except OSError as exc:
        raise PrimeAgentUnavailable("prime-agent executable could not be inspected") from exc
    try:
        opened_stat = os.fstat(fd)
        if not stat.S_ISREG(path_stat.st_mode) or not stat.S_ISREG(opened_stat.st_mode):
            raise PrimeAgentUnavailable("prime-agent executable is not a regular file")
        if (path_stat.st_dev, path_stat.st_ino) != (opened_stat.st_dev, opened_stat.st_ino):
            raise PrimeAgentUnavailable("prime-agent executable changed while being inspected")
        if opened_stat.st_uid not in {0, os.geteuid()}:
            raise PrimeAgentUnavailable(
                "prime-agent executable must be owned by root or the current user"
            )
        if opened_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise PrimeAgentUnavailable("prime-agent executable must not be group/world writable")
        if require_executable and not opened_stat.st_mode & (
            stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        ):
            raise PrimeAgentUnavailable("prime-agent executable is not executable")
        return _identity_from_fd(fd)
    finally:
        os.close(fd)


def _identity_from_fd(fd: int) -> PrimeAgentBinaryIdentity:
    opened_stat = os.fstat(fd)
    if not stat.S_ISREG(opened_stat.st_mode):
        raise PrimeAgentUnavailable("prime-agent executable is not a regular file")
    os.lseek(fd, 0, os.SEEK_SET)
    digest = sha256()
    while chunk := os.read(fd, 128 * 1024):
        digest.update(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return PrimeAgentBinaryIdentity(
        device=opened_stat.st_dev,
        inode=opened_stat.st_ino,
        size=opened_stat.st_size,
        mtime_ns=opened_stat.st_mtime_ns,
        mode=opened_stat.st_mode,
        owner_uid=opened_stat.st_uid,
        sha256=digest.hexdigest(),
    )


def _probe(
    installation: PrimeAgentInstallation,
    args: tuple[str, ...],
    *,
    environ: Mapping[str, str] | None,
) -> str:
    # Local import avoids an import cycle while keeping probes on the exact
    # same bounded, isolated process primitive as real turns.
    from runtime.prime_agent.process import PrimeAgentProcessConfig, run_prime_agent_process

    try:
        result = run_prime_agent_process(
            PrimeAgentProcessConfig(
                installation=installation,
                cwd=installation.binary.parent,
                timeout_seconds=_PROBE_TIMEOUT_SECONDS,
                max_stdout_bytes=_PROBE_OUTPUT_BYTES,
                max_stderr_bytes=_PROBE_OUTPUT_BYTES,
                environ=environ,
            ),
            args,
            stdin=b"",
        )
    except OSError as exc:
        raise PrimeAgentUnavailable(f"prime-agent capability probe failed: {type(exc).__name__}") from exc
    output = result.stdout + result.stderr
    if (
        result.exit_code != 0
        or result.timed_out
        or result.stdout_limit_exceeded
        or result.stderr_limit_exceeded
    ):
        raise PrimeAgentUnavailable("prime-agent capability probe failed")
    try:
        return output.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PrimeAgentUnavailable("prime-agent capability probe was not UTF-8") from exc
