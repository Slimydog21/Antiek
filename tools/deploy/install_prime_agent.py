"""Install or verify the pinned Prime bundle as data in an unpublished release.

Ansible owns transport, the release receipt, freeze and cutover. This module
never executes vendor code, downloads anything, or enables model calls.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, cast

MAX_MEMBERS = 4096
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_PIN_BYTES = 256 * 1024
CHUNK_BYTES = 128 * 1024
BUNDLE = ".prime-agent"
ENVIRONMENT = ".prime-agent.env"
_READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
_DIRECTORY_FLAGS = _READ_FLAGS | os.O_DIRECTORY


class InstallRefused(ValueError):
    """Data or release state does not match the committed artifact contract."""


@dataclass(frozen=True)
class MemberPin:
    path: str
    kind: Literal["directory", "regular"]
    size: int
    archive_mode: int
    sha256: str | None

    @property
    def installed_mode(self) -> int:
        return self.archive_mode & ~0o222


@dataclass(frozen=True)
class ArtifactPin:
    version: str
    url: str
    archive_bytes: int
    archive_sha256: str
    expanded_tar_bytes: int
    manifest_sha256: str
    members: tuple[MemberPin, ...]


def _identity(value: os.stat_result) -> tuple[int, ...]:
    # Reading changes atime; it is not a content/ownership mutation witness.
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(type(k) is not str for k in value):
        raise InstallRefused("invalid manifest object")
    return cast(dict[str, object], value)


def _text(value: object) -> str:
    if type(value) is not str:
        raise InstallRefused("invalid manifest string")
    return value


def _number(value: object) -> int:
    if type(value) is not int or value < 0:
        raise InstallRefused("invalid manifest integer")
    return value


def _digest(value: object) -> str:
    text = _text(value)
    if re.fullmatch(r"[0-9a-f]{64}", text) is None:
        raise InstallRefused("invalid manifest digest")
    return text


def _relative(path: str) -> str:
    parts = path.split("/")
    if (
        not path
        or len(path.encode("utf-8")) > 1024
        or "\\" in path
        or "\x00" in path
        or any(p in {"", ".", ".."} for p in parts)
        or len(parts) > 32
    ):
        raise InstallRefused("noncanonical member path")
    return path


def load_pin(path: Path | None = None) -> ArtifactPin:
    source = path or Path(__file__).with_name("prime_agent_release.json")
    with _file(source, MAX_PIN_BYTES) as fd:
        metadata = os.fstat(fd)
        body = os.read(fd, MAX_PIN_BYTES + 1)
        if len(body) != metadata.st_size or _identity(os.fstat(fd)) != _identity(metadata):
            raise InstallRefused("manifest changed during read")
    data = _object(json.loads(body))
    if (
        type(data.get("schema")) is not int
        or data.get("schema") != 1
        or data.get("platform") != "linux-x86_64-glibc"
    ):
        raise InstallRefused("unsupported manifest schema or platform")
    raw_members = data.get("members")
    if not isinstance(raw_members, list) or not 1 <= len(raw_members) <= MAX_MEMBERS:
        raise InstallRefused("manifest member bound")
    members: list[MemberPin] = []
    for raw in raw_members:
        row = _object(raw)
        kind = row.get("kind")
        if type(kind) is not str or kind not in {"regular", "directory"}:
            raise InstallRefused("unsupported member kind")
        mode = _number(row.get("archive_mode"))
        size = _number(row.get("bytes"))
        if mode not in {0o644, 0o755} or size > MAX_EXPANDED_BYTES:
            raise InstallRefused("unsafe member mode or size")
        if kind == "directory" and (mode != 0o755 or size != 0):
            raise InstallRefused("invalid directory pin")
        members.append(
            MemberPin(
                _relative(_text(row.get("path"))),
                cast(Literal["regular", "directory"], kind),
                size,
                mode,
                _digest(row.get("sha256")) if kind == "regular" else None,
            )
        )
    by_path = {m.path: m for m in members}
    if len(by_path) != len(members) or sum(m.size for m in members) > MAX_EXPANDED_BYTES:
        raise InstallRefused("duplicate or oversized member inventory")
    for member in members:
        parent = str(PurePosixPath(member.path).parent)
        if parent != "." and (parent not in by_path or by_path[parent].kind != "directory"):
            raise InstallRefused("missing pinned parent directory")
    for required in ("prime-agent", "package.json"):
        if required not in by_path or by_path[required].kind != "regular":
            raise InstallRefused("missing executable or package pin")
    expanded = _number(data.get("expanded_tar_bytes"))
    if not 0 < expanded < MAX_EXPANDED_BYTES:
        raise InstallRefused("expanded archive bound")
    url = _text(data.get("url"))
    if not url.startswith("https://pub-728493de92a943e2a9b2d17b4719f318.r2.dev/releases/"):
        raise InstallRefused("unexpected publisher URL")
    compressed = _number(data.get("archive_bytes"))
    if not 0 < compressed <= 64 * 1024 * 1024:
        raise InstallRefused("compressed archive bound")
    return ArtifactPin(
        _text(data.get("version")),
        url,
        compressed,
        _digest(data.get("archive_sha256")),
        expanded,
        hashlib.sha256(body).hexdigest(),
        tuple(members),
    )


def require_supported_platform() -> None:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise InstallRefused("only the reviewed Linux x86_64 bundle is supported")
    if not (os.confstr("CS_GNU_LIBC_VERSION") or "").startswith("glibc "):
        raise InstallRefused("the reviewed bundle requires glibc")


@contextmanager
def _file(path: Path, limit: int) -> Iterator[int]:
    fd = os.open(path, _READ_FLAGS)
    try:
        current = os.fstat(fd)
        if not stat.S_ISREG(current.st_mode) or current.st_size > limit:
            raise InstallRefused("not a bounded regular file")
        yield fd
    finally:
        os.close(fd)


@contextmanager
def _directory(path: Path) -> Iterator[int]:
    fd = os.open(path, _DIRECTORY_FLAGS)
    try:
        current = os.fstat(fd)
        if current.st_uid != os.geteuid() or stat.S_IMODE(current.st_mode) & 0o022:
            raise InstallRefused(
                "directory must be owned by the installer and not group/world writable"
            )
        yield fd
    finally:
        os.close(fd)


@contextmanager
def _member_fd(root: int, relative: str, directory: bool = False) -> Iterator[int]:
    parts = _relative(relative).split("/")
    parent = os.dup(root)
    try:
        for component in parts[:-1]:
            child = os.open(component, _DIRECTORY_FLAGS, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(parts[-1], _DIRECTORY_FLAGS if directory else _READ_FLAGS, dir_fd=parent)
        try:
            yield fd
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def _hash_fd(fd: int, expected_size: int) -> str:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size or before.st_nlink != 1:
        raise InstallRefused("file type, size or link count differs")
    result = hashlib.sha256()
    remaining = expected_size
    while remaining:
        chunk = os.read(fd, min(CHUNK_BYTES, remaining))
        if not chunk:
            raise InstallRefused("file ended early")
        result.update(chunk)
        remaining -= len(chunk)
    if _identity(os.fstat(fd)) != _identity(before):
        raise InstallRefused("file changed while hashing")
    return result.hexdigest()


def _environment(public: Path) -> bytes:
    value = str(public)
    if (
        not public.is_absolute()
        or ".." in public.parts
        or re.fullmatch(r"/[A-Za-z0-9_./-]+", value) is None
    ):
        raise InstallRefused("unsafe public release path")
    return f"ANTIEK_PRIME_AGENT_BIN={value}/{BUNDLE}/prime-agent\n".encode()


def _verify_bundle(pin: ArtifactPin, root: Path) -> None:
    with _directory(root) as fd:
        identity = os.fstat(fd)
        if stat.S_IMODE(identity.st_mode) != 0o555:
            raise InstallRefused("bundle root must be readonly")
        expected = {m.path: m for m in pin.members}
        seen: set[str] = set()
        pending = [""]
        while pending:
            relative = pending.pop()
            with _member_fd(fd, relative, True) if relative else _directory(root) as current:
                with os.scandir(current) as children:
                    for child in children:
                        name = _relative(f"{relative}/{child.name}" if relative else child.name)
                        if name not in expected or name in seen:
                            raise InstallRefused("unexpected installed member")
                        seen.add(name)
                        member = expected[name]
                        with _member_fd(fd, name, member.kind == "directory") as entry_fd:
                            before = os.fstat(entry_fd)
                            if (
                                before.st_uid != os.geteuid()
                                or stat.S_IMODE(before.st_mode) != member.installed_mode
                            ):
                                raise InstallRefused("installed owner or mode differs")
                            if member.kind == "directory":
                                if not stat.S_ISDIR(before.st_mode):
                                    raise InstallRefused("directory type differs")
                                pending.append(name)
                            elif _hash_fd(entry_fd, member.size) != member.sha256:
                                raise InstallRefused("installed content differs")
                if relative and _identity(os.fstat(current)) != _identity(
                    os.stat(relative, dir_fd=fd, follow_symlinks=False)
                ):
                    raise InstallRefused("installed directory changed")
        if (
            seen != set(expected)
            or _identity(os.fstat(fd)) != _identity(identity)
            or _identity(os.lstat(root)) != _identity(identity)
        ):
            raise InstallRefused("installed inventory or root changed")


def _verify_payload(pin: ArtifactPin, release: Path, public: Path) -> None:
    _verify_bundle(pin, release / BUNDLE)
    expected = _environment(public)
    with _file(release / ENVIRONMENT, 4096) as fd:
        before = os.fstat(fd)
        if before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != 0o444:
            raise InstallRefused("environment owner or mode differs")
        if os.read(fd, 4097) != expected or _identity(os.fstat(fd)) != _identity(before):
            raise InstallRefused("release environment differs")


def _extract(pin: ArtifactPin, archive_fd: int, stage: Path) -> None:
    expanded = stage / "archive.tar"
    os.lseek(archive_fd, 0, os.SEEK_SET)
    with (
        os.fdopen(os.dup(archive_fd), "rb") as source,
        gzip.GzipFile(fileobj=source) as zipped,
        expanded.open("xb") as out,
    ):
        total = 0
        while True:
            chunk = zipped.read(min(CHUNK_BYTES, pin.expanded_tar_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > pin.expanded_tar_bytes:
                raise InstallRefused("expanded archive exceeds pinned size")
            out.write(chunk)
        if total != pin.expanded_tar_bytes:
            raise InstallRefused("expanded archive size differs")
    payload = stage / "payload"
    payload.mkdir(mode=0o700)
    expected = {m.path: m for m in pin.members}
    seen: set[str] = set()
    with tarfile.open(expanded, "r:") as tar:
        for item in tar:
            name = _relative(item.name)
            if name not in expected or name in seen or len(seen) >= MAX_MEMBERS:
                raise InstallRefused("unexpected or duplicate archive member")
            seen.add(name)
            member = expected[name]
            if item.pax_headers or item.sparse or not (item.isfile() or item.isdir()):
                raise InstallRefused("archive extensions, links or special members refused")
            if (
                ("directory" if item.isdir() else "regular") != member.kind
                or item.mode != member.archive_mode
                or item.size != member.size
            ):
                raise InstallRefused("archive member metadata differs")
            target = payload / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if member.kind == "directory":
                target.mkdir(exist_ok=True, mode=0o700)
                continue
            member_source = tar.extractfile(item)
            if member_source is None:
                raise InstallRefused("missing archive body")
            digest = hashlib.sha256()
            with member_source, target.open("xb") as out:
                remaining = member.size
                while remaining:
                    chunk = member_source.read(min(CHUNK_BYTES, remaining))
                    if not chunk:
                        raise InstallRefused("archive member ended early")
                    digest.update(chunk)
                    out.write(chunk)
                    remaining -= len(chunk)
                out.flush()
                os.fsync(out.fileno())
            if digest.hexdigest() != member.sha256:
                raise InstallRefused("archive member hash differs")
            target.chmod(member.installed_mode)
    if seen != set(expected):
        raise InstallRefused("archive inventory differs")
    for member in sorted(pin.members, key=lambda m: m.path.count("/"), reverse=True):
        if member.kind == "directory":
            (payload / member.path).chmod(member.installed_mode)
    payload.chmod(0o555)
    _verify_bundle(pin, payload)


def install_release(pin: ArtifactPin, release: Path, archive: Path, public: Path) -> None:
    """Prepare bytes only. Partial installs refuse; the release builder rebuilds."""
    with _directory(release) as directory:
        if (release / ".release-receipt").exists() or not os.fstat(
            directory
        ).st_mode & stat.S_IWUSR:
            raise InstallRefused("refusing to alter a receipted or frozen release")
        if os.path.lexists(release / BUNDLE) or os.path.lexists(release / ENVIRONMENT):
            _verify_payload(pin, release, public)
            return
        environment = _environment(public)
        with _file(archive, pin.archive_bytes) as fd:
            identity = os.fstat(fd)
            if _hash_fd(fd, pin.archive_bytes) != pin.archive_sha256:
                raise InstallRefused("archive hash differs")
            stage = Path(tempfile.mkdtemp(prefix=".prime-agent-stage-", dir=release))
            try:
                _extract(pin, fd, stage)
                if _identity(os.fstat(fd)) != _identity(identity):
                    raise InstallRefused("archive changed during extraction")
                staged_env = stage / "environment"
                with staged_env.open("xb") as out:
                    out.write(environment)
                    out.flush()
                    os.fsync(out.fileno())
                staged_env.chmod(0o444)
                # macOS requires the moved directory itself to be writable.
                # No receipt or public pointer can reference this candidate yet.
                (stage / "payload").chmod(0o755)
                os.rename(stage / "payload", release / BUNDLE)
                (release / BUNDLE).chmod(0o555)
                os.rename(staged_env, release / ENVIRONMENT)
                os.fsync(directory)
                _verify_payload(pin, release, public)
            finally:
                # The stage is never a published release. Make only it writable.
                primary = sys.exception()
                try:
                    for parent, dirs, _files in os.walk(stage):
                        os.chmod(parent, 0o700)
                        for name in dirs:
                            os.chmod(Path(parent) / name, 0o700)
                    shutil.rmtree(stage)
                except OSError as cleanup:
                    if primary is None:
                        raise
                    primary.add_note(f"stage cleanup also failed: {type(cleanup).__name__}")


def receipt_text(pin: ArtifactPin, target: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", target) is None:
        raise InstallRefused("release identity must be an exact SHA")
    return (
        f"source_sha={target}\nlock_check=pass\nexact_sync=pass\n"
        "bootstrap_uv_removed=pass\nfrontend_index_present=pass\n"
        f"prime_agent_archive_sha256={pin.archive_sha256}\n"
        f"prime_agent_manifest_sha256={pin.manifest_sha256}\n"
    )


def verify_release(pin: ArtifactPin, release: Path, public: Path) -> None:
    """Read-only complete verification, required even when a receipt skips build."""
    with _directory(release) as directory:
        if stat.S_IMODE(os.fstat(directory).st_mode) != 0o555:
            raise InstallRefused("release freeze did not complete")
        _verify_payload(pin, release, public)
        with _file(release / ".release-receipt", 4096) as fd:
            before = os.fstat(fd)
            if before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != 0o444:
                raise InstallRefused("release receipt owner or mode differs")
            if os.read(fd, 4097) != receipt_text(pin, release.name).encode() or _identity(
                os.fstat(fd)
            ) != _identity(before):
                raise InstallRefused("release receipt differs from pinned artifact")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("describe", "install", "verify"))
    parser.add_argument("--release", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--public", type=Path, default=Path("/opt/antiek"))
    args = parser.parse_args()
    try:
        require_supported_platform()
        if os.geteuid() != 0:
            raise InstallRefused("deployment must run as root")
        pin = load_pin()
        if args.action == "describe":
            print(
                json.dumps(
                    {
                        "url": pin.url,
                        "archive_bytes": pin.archive_bytes,
                        "archive_sha256": pin.archive_sha256,
                        "manifest_sha256": pin.manifest_sha256,
                        "version": pin.version,
                    },
                    sort_keys=True,
                )
            )
        else:
            if args.release is None or not args.release.is_absolute():
                raise InstallRefused("absolute release directory required")
            if args.action == "install":
                if args.archive is None:
                    raise InstallRefused("downloaded archive required")
                install_release(pin, args.release, args.archive, args.public)
            else:
                verify_release(pin, args.release, args.public)
            print(
                json.dumps({"action": args.action, "version": pin.version, "data_verified": True})
            )
    except (InstallRefused, OSError, tarfile.TarError, EOFError, json.JSONDecodeError) as exc:
        # No archive body, environment contents or incidental native paths.
        print(json.dumps({"refused": type(exc).__name__}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
