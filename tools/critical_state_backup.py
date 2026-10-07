"""Private critical-state snapshots alongside the existing DuckDB export.

SQLite's online backup includes committed WAL data. The BYOK pair shares its
actual store's key/artifact flocks and is checked with the existing credential
verifier. Individual stores have independent snapshot times: this is not a
cross-store transaction. Only an offline recovery directory is produced here.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

MAX_FILES = 32768
MAX_FILE_BYTES = 8 * 1024**3
MAX_TOTAL_BYTES = 16 * 1024**3
LOCK_TIMEOUT_SECONDS = 30.0
SQLITE_TIMEOUT_SECONDS = 30.0
_FILE_BYTES = 16 * 1024**2


class SnapshotError(ValueError):
    """A value-free snapshot failure; never a successful backup receipt."""


@dataclass(frozen=True)
class SnapshotSources:
    state: Path
    byok_key: Path
    byok_artifact: Path
    accounts: Path
    passkeys: Path
    settings: tuple[Path, ...]
    turbopuffer: Path
    system_files: dict[str, Path]
    extra_sqlite: tuple[Path, ...] = ()


@dataclass
class _Inventory:
    uids: set[int]
    gids: set[int]
    records: list[dict[str, object]] = field(default_factory=list)
    total: int = 0
    entries: int = 0
    escrow_created: bool = False

    def charge(self, size: int) -> None:
        self.total += size
        if size > MAX_FILE_BYTES or self.total > MAX_TOTAL_BYTES:
            raise SnapshotError("critical snapshot exceeds its storage limit")

    def visit(self) -> None:
        self.entries += 1
        if self.entries > MAX_FILES:
            raise SnapshotError("critical snapshot exceeds its namespace limit")


def _parents(path: Path, inventory: _Inventory) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise SnapshotError("critical source path must be absolute without traversal")
    for parent in reversed(path.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in inventory.uids:
            raise SnapshotError("critical source parent is unsafe")
        if info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX:
            raise SnapshotError("critical source parent is writable by others")


def _regular(path: Path, inventory: _Inventory) -> os.stat_result:
    _parents(path, inventory)
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
        or info.st_uid not in inventory.uids or info.st_gid not in inventory.gids
        or info.st_mode & 0o027  # root/Antiek group read is permitted; other access is not.
    ):
        raise SnapshotError("critical source is not a protected regular file")
    return info


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_size, info.st_mtime_ns)


def _read(path: Path, inventory: _Inventory, limit: int = _FILE_BYTES) -> bytes:
    before = _regular(path, inventory)
    if before.st_size > limit:
        raise SnapshotError("critical file exceeds its size limit")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise SnapshotError("critical source changed while opening")
        body = stream.read(limit + 1)
        if len(body) > limit or _identity(os.fstat(stream.fileno())) != _identity(before):
            raise SnapshotError("critical source changed while reading")
    if _identity(path.lstat()) != _identity(before):
        raise SnapshotError("critical source was replaced while reading")
    return body


def _write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    info = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        current = path.lstat()
        if (info.st_dev, info.st_ino) == (current.st_dev, current.st_ino):
            path.unlink()
        raise


def _record(inventory: _Inventory, path: Path, target: Path, kind: str, root: Path) -> None:
    size = target.stat().st_size
    inventory.charge(size)
    digest = hashlib.sha256()
    with target.open("rb") as stream:
        while chunk := stream.read(65536):
            digest.update(chunk)
    inventory.records.append({
        "source": str(path), "path": target.relative_to(root).as_posix(), "kind": kind, "bytes": size,
        "sha256": digest.hexdigest(),
    })


@contextmanager
def _pair_locks(sources: SnapshotSources, inventory: _Inventory) -> Iterator[None]:
    """Keep the original lock inodes and order; never create or rotate a key."""
    descriptors: list[int] = []
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    try:
        for path in (sources.byok_key, sources.byok_artifact):
            lock = Path(str(path) + ".lock")
            _parents(lock, inventory)
            try:
                descriptor = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except FileNotFoundError:
                raise SnapshotError("required original BYOK lock is missing") from None
            descriptors.append(descriptor)
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid not in inventory.uids or info.st_gid not in inventory.gids
                or info.st_mode & 0o077):
                raise SnapshotError("BYOK lock is unsafe")
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise SnapshotError("BYOK snapshot lock deadline exceeded") from None
                    time.sleep(0.05)
        yield
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _byok(sources: SnapshotSources, destination: Path, escrow: Path, inventory: _Inventory) -> None:
    with _pair_locks(sources, inventory):
        key = _read(sources.byok_key, inventory, 32)
        artifact = _read(sources.byok_artifact, inventory)
        if len(key) != 32:
            raise SnapshotError("BYOK master key size is invalid")
        try:
            from runtime.byok.store import _credential_from_record

            records = json.loads(artifact)
            if not isinstance(records, dict):
                raise ValueError
            for credential_id, row in records.items():
                _credential_from_record(credential_id, row, key)
        except Exception:
            raise SnapshotError("BYOK key and ciphertext do not authenticate together") from None
        ciphertext = destination / "state/byok/credentials.enc"
        _write(ciphertext, artifact)
        _write(escrow, key)  # This file is encrypted into a separate object, never the data archive.
        inventory.escrow_created = True
        _record(inventory, sources.byok_artifact, ciphertext, "byok-ciphertext", destination)


def _sqlite_native(path: Path, target: Path, inventory: _Inventory, root: Path, timeout: float) -> None:
    before = _regular(path, inventory)
    if before.st_uid != os.geteuid():
        raise SnapshotError("SQLite must be read by its actual file owner")
    if before.st_size > MAX_FILE_BYTES:
        raise SnapshotError("SQLite source exceeds its size limit")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(descriptor)
    deadline = time.monotonic() + timeout

    def progress(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() >= deadline or target.stat().st_size > MAX_FILE_BYTES:
            raise SnapshotError("SQLite online backup exceeded its bound")

    source = sqlite3.connect("file:" + quote(str(path), safe="/") + "?mode=ro", uri=True, timeout=1)
    try:
        restored = sqlite3.connect(target, timeout=1)
        try:
            source.backup(restored, pages=256, progress=progress, sleep=0.05)
            # The live store may use WAL. Make the owned snapshot a standalone
            # rollback-journal DB without changing the live store's mode.
            if restored.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
                raise SnapshotError("SQLite snapshot could not become a standalone database")
            if restored.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise SnapshotError("SQLite online backup integrity check failed")
        finally:
            restored.close()
    finally:
        source.close()
    after = _regular(path, inventory)
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise SnapshotError("SQLite source was replaced during backup")
    with target.open("rb") as stream:
        os.fsync(stream.fileno())
    _record(inventory, path, target, "sqlite-online-backup", root)


def _retire_sqlite_worker(child: subprocess.Popen[bytes]) -> None:
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=7)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=3)


def _sqlite(path: Path, target: Path, inventory: _Inventory, root: Path) -> None:
    """Keep any native WAL/SHM creation under the live database's Unix owner.

    A readonly SQLite connection may create live sidecars. The root collector
    must not leave those files root-owned and block the application writer.
    Only a newly owned staging directory is chowned, never a live source.
    """
    before = _regular(path, inventory)
    if before.st_size > MAX_FILE_BYTES:
        raise SnapshotError("SQLite source exceeds its size limit")
    if os.geteuid() != 0 and before.st_uid != os.geteuid():
        raise SnapshotError("SQLite snapshot requires the actual source-owner worker")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".sqlite-owned-", dir=target.parent) as temporary:
        worker = Path(temporary)
        worker_uid: int | None = None
        worker_gid: int | None = None
        worker_groups: list[int] | None = None
        if os.geteuid() == 0:
            os.chown(worker, before.st_uid, before.st_gid)
            worker_uid, worker_gid, worker_groups = before.st_uid, before.st_gid, []
        environment = {name: os.environ[name] for name in ("PATH", "LANG", "LC_ALL") if name in os.environ}
        environment.update(HOME=".", TMPDIR=".", ANTIEK_HOME=".")
        command = [sys.executable, "-I", str(Path(__file__).resolve()), "_sqlite-worker",
                   "--source", str(path), "--timeout", str(SQLITE_TIMEOUT_SECONDS)]
        child = subprocess.Popen(command, cwd=worker, env=environment, close_fds=True,
                                 stdin=subprocess.DEVNULL, umask=0o077,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 user=worker_uid, group=worker_gid, extra_groups=worker_groups)
        try:
            code = child.wait(timeout=SQLITE_TIMEOUT_SECONDS + 5)
        except BaseException as primary:
            try:
                _retire_sqlite_worker(child)
            except BaseException:
                raise SnapshotError("SQLite snapshot failed; worker retirement is unknown") from primary
            raise SnapshotError("SQLite snapshot worker did not complete") from primary
        if code != 0:
            raise SnapshotError("SQLite source-owner worker refused")
        after = _regular(path, inventory)
        if (before.st_dev, before.st_ino, before.st_uid, before.st_gid, before.st_mode) != (
            after.st_dev, after.st_ino, after.st_uid, after.st_gid, after.st_mode,
        ):
            raise SnapshotError("SQLite source identity changed during backup")
        completed = worker / "snapshot.sqlite3"
        info = _regular(completed, inventory)
        if info.st_size > MAX_FILE_BYTES:
            raise SnapshotError("SQLite snapshot exceeds its size limit")
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as output, completed.open("rb") as source:
            if _identity(os.fstat(source.fileno())) != _identity(info):
                raise SnapshotError("SQLite worker output changed while opening")
            remaining = info.st_size
            while remaining:
                chunk = source.read(min(65536, remaining))
                if not chunk:
                    raise SnapshotError("SQLite worker output is truncated")
                output.write(chunk)
                remaining -= len(chunk)
            if (source.read(1) or _identity(os.fstat(source.fileno())) != _identity(info)
                or _identity(completed.lstat()) != _identity(info)):
                raise SnapshotError("SQLite worker output changed during publication")
            output.flush()
            os.fsync(output.fileno())
        _record(inventory, path, target, "sqlite-online-backup", root)


def _tree(root: Path, inventory: _Inventory) -> Iterator[Path]:
    """Bounded metadata traversal; links/errors refuse rather than omit state."""
    _parents(root, inventory)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid not in inventory.uids or info.st_mode & 0o022:
        raise SnapshotError("critical directory is unsafe")
    with os.scandir(root) as directory:
        for entry in directory:
            inventory.visit()
            path = Path(entry.path)
            if entry.is_symlink():
                raise SnapshotError("critical directory contains a symlink")
            if entry.is_dir(follow_symlinks=False):
                yield from _tree(path, inventory)
            elif entry.is_file(follow_symlinks=False):
                yield path
            else:
                raise SnapshotError("critical directory contains a special file")


def snapshot(sources: SnapshotSources, destination: Path, escrow: Path) -> dict[str, object]:
    """Snapshot required durable state into two newly owned private locations.

    Source path configuration is operational custody, not inferred from an
    email/account claim. Missing required sources refuse. Pending auth claims,
    cookies, challenges, jobs and lock sidecars are never copied as authority.
    """
    state_info = sources.state.lstat()
    inventory = _Inventory({0, os.getuid(), state_info.st_uid}, {0, os.getgid(), state_info.st_gid})
    if set(sources.system_files) != {"secrets.env", "rclone.conf", "tunnel.json"}:
        raise SnapshotError("required recovery configuration is incomplete")
    required_paths = (sources.byok_key, sources.byok_artifact, sources.accounts, sources.passkeys,
                      *sources.system_files.values())
    if len(set(required_paths)) != len(required_paths):
        raise SnapshotError("required critical sources must have distinct paths")
    _parents(destination, inventory)
    _parents(escrow, inventory)
    if (destination.is_relative_to(sources.state) or escrow.is_relative_to(sources.state)
        or escrow.is_relative_to(destination)):
        raise SnapshotError("critical staging must be outside the live state tree")
    try:
        escrow.lstat()
    except FileNotFoundError:
        pass
    else:
        raise SnapshotError("BYOK escrow destination already exists")
    destination.mkdir(mode=0o700)
    try:
        _byok(sources, destination, escrow, inventory)
        copied: set[Path] = {sources.byok_artifact}

        def copy(path: Path, target: Path, kind: str) -> None:
            if path == sources.byok_key:
                raise SnapshotError("BYOK master key cannot enter the data archive")
            if path in copied:
                return
            copied.add(path)
            if path.suffix in {".sqlite", ".sqlite3", ".db"}:
                _sqlite(path, target, inventory, destination)
            else:
                _write(target, _read(path, inventory))
                _record(inventory, path, target, kind, destination)

        for label, path in sources.system_files.items():
            copy(path, destination / "system" / label, "system-recovery")
        copy(sources.accounts, destination / "state/auth/accounts.json", "account-registry")
        copy(sources.passkeys, destination / "state/auth/passkeys.json", "passkey-state")
        if not sources.settings:
            raise SnapshotError("required settings directory is not configured")
        for index, root in enumerate((*sources.settings, sources.turbopuffer)):
            for path in _tree(root, inventory):
                copy(path, destination / "trees" / str(index) / path.relative_to(root), "settings-or-pointer")
        for path in _tree(sources.state, inventory):
            if path.suffix in {".sqlite", ".sqlite3", ".db"}:
                copy(path, destination / "state" / path.relative_to(sources.state), "sqlite-online-backup")
        for index, path in enumerate(sources.extra_sqlite):
            if path == sources.byok_key:
                raise SnapshotError("BYOK master key cannot enter the data archive")
            if path not in copied:
                _sqlite(path, destination / "external-sqlite" / str(index) / path.name, inventory, destination)
                copied.add(path)
        manifest: dict[str, object] = {
            "critical_state_contract_version": 1,
            "snapshot_consistency": "per-store; BYOK pair coordinated; SQLite online backup; no cross-store atomicity",
            "files": inventory.records,
            "bytes": inventory.total,
            "namespace_entries_inspected": inventory.entries,
            "ephemeral_authority_restored": False,
            "byok_key_storage": "separate-encrypted-object",
        }
        _write(destination / "manifest.json", json.dumps(manifest, sort_keys=True).encode())
        return manifest
    except BaseException as exc:
        cleanup_failed = False
        for cleanup in (lambda: shutil.rmtree(destination),
                        lambda: escrow.unlink(missing_ok=True) if inventory.escrow_created else None):
            try:
                cleanup()
            except OSError:
                cleanup_failed = True
        if cleanup_failed:
            raise SnapshotError("critical-state snapshot failed; owned cleanup is incomplete") from None
        if not isinstance(exc, Exception) or isinstance(exc, SnapshotError):
            raise
        raise SnapshotError("critical-state snapshot failed") from None


def load_sources(configuration: Path, expected_state: Path) -> SnapshotSources:
    """Read one protected operational path inventory, never secret env contents."""
    info = expected_state.lstat()
    inventory = _Inventory({0, os.getuid(), info.st_uid}, {0, os.getgid(), info.st_gid})
    try:
        raw = json.loads(_read(configuration, inventory, 65536))
        required = {"version", "state", "byok_key", "byok_artifact", "accounts", "passkeys",
                    "settings", "turbopuffer", "system_files", "extra_sqlite"}
        if (not isinstance(raw, dict) or set(raw) != required
            or type(raw["version"]) is not int or raw["version"] != 1):
            raise SnapshotError("critical source inventory schema is invalid")

        def path(value: object) -> Path:
            if not isinstance(value, str) or not value or "\x00" in value:
                raise SnapshotError("critical source path type is invalid")
            result = Path(value)
            if not result.is_absolute() or ".." in result.parts:
                raise SnapshotError("critical source path must be absolute without traversal")
            return result

        def paths(value: object) -> tuple[Path, ...]:
            if not isinstance(value, list) or len(value) > 256:
                raise SnapshotError("critical source inventory exceeds its list limit")
            result = tuple(path(item) for item in value)
            if len(set(result)) != len(result):
                raise SnapshotError("critical source inventory repeats a path")
            return result

        system = raw["system_files"]
        if not isinstance(system, dict) or set(system) != {"secrets.env", "rclone.conf", "tunnel.json"}:
            raise SnapshotError("required recovery configuration is incomplete")
        state = path(raw["state"])
        if state != expected_state:
            raise SnapshotError("critical source inventory does not match the deployed state directory")
        return SnapshotSources(state, path(raw["byok_key"]), path(raw["byok_artifact"]),
                               path(raw["accounts"]), path(raw["passkeys"]), paths(raw["settings"]),
                               path(raw["turbopuffer"]), {key: path(value) for key, value in system.items()},
                               paths(raw["extra_sqlite"]))
    except (OSError, ValueError, TypeError, KeyError):
        raise SnapshotError("critical source inventory is missing or invalid") from None


def prepare(sources: SnapshotSources, destination: Path, escrow: Path, recipient: Path) -> None:
    """Prepare critical state and seal its separate key before tar creation."""
    from tools.critical_backup_crypto import encrypt_file

    encrypted_key = Path(str(escrow) + ".enc")
    try:
        encrypted_key.lstat()
    except FileNotFoundError:
        pass
    else:
        raise SnapshotError("encrypted BYOK escrow destination already exists")
    manifest = snapshot(sources, destination, escrow)
    try:
        encrypted = encrypt_file(escrow, encrypted_key, recipient)
        escrow.unlink()
        manifest["encrypted_byok_key"] = {
            "sha256": encrypted.sha256, "bytes": encrypted.bytes,
            "recipient_sha256": encrypted.recipient_sha256,
        }
        # The snapshot is private and owned by this job; publish its complete
        # pairing record before the enclosing encrypted archive is constructed.
        temporary = destination / "manifest-complete.json"
        _write(temporary, json.dumps(manifest, sort_keys=True).encode())
        temporary.replace(destination / "manifest.json")
    except BaseException as exc:
        cleanup_failed = False
        for cleanup in (lambda: shutil.rmtree(destination),
                        lambda: escrow.unlink(missing_ok=True), lambda: encrypted_key.unlink(missing_ok=True)):
            try:
                cleanup()
            except OSError:
                cleanup_failed = True
        if cleanup_failed:
            raise SnapshotError("critical preparation failed; owned cleanup is incomplete") from None
        if not isinstance(exc, Exception):
            raise
        raise SnapshotError("critical preparation failed; no complete encrypted snapshot") from None


def _extract(archive: Path, destination: Path) -> None:
    """Extract only bounded regular files/directories into a fresh private tree."""
    seen: set[str] = set()
    total = 0
    root: str | None = None
    with tarfile.open(archive, mode="r|gz") as bundle:
        for member in bundle:
            name = member.name.rstrip("/") if member.isdir() else member.name
            parts = name.split("/")
            if (not parts or any(part in {"", ".", ".."} for part in parts)
                or member.name.startswith("/") or len(member.name) > 4096):
                raise SnapshotError("restore archive path is invalid")
            if root is None:
                root = parts[0]
            if parts[0] != root or not root.startswith("antiek-backup."):
                raise SnapshotError("restore archive has an unexpected root")
            if name in seen or len(seen) >= MAX_FILES:
                raise SnapshotError("restore archive repeats or exceeds its namespace")
            seen.add(name)
            target = destination.joinpath(*parts[1:])
            if not (member.isdir() or member.isfile()) or member.size < 0:
                raise SnapshotError("restore archive contains a link or special file")
            total += member.size
            if member.size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES * 4:
                raise SnapshotError("restore archive exceeds its storage limit")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
                continue
            if target == destination:
                raise SnapshotError("restore archive root is not a directory")
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            source = bundle.extractfile(member)
            if source is None:
                raise SnapshotError("restore archive file is unreadable")
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with source, os.fdopen(descriptor, "wb") as output:
                remaining = member.size
                while remaining:
                    chunk = source.read(min(65536, remaining))
                    if not chunk:
                        raise SnapshotError("restore archive file is truncated")
                    output.write(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())
    if root is None:
        raise SnapshotError("restore archive is empty")


def _verify_restored(root: Path, key: Path, encrypted_key: Path) -> None:
    """Verify the exact critical payload and key pairing, without activating it."""
    from runtime.byok.store import _credential_from_record

    info = root.stat()
    inventory = _Inventory({0, os.getuid()}, {0, os.getgid(), info.st_gid})
    critical = root / "critical-state"
    manifest = json.loads(_read(critical / "manifest.json", inventory))
    if (not isinstance(manifest, dict) or type(manifest.get("critical_state_contract_version")) is not int
        or manifest.get("critical_state_contract_version") != 1
        or manifest.get("ephemeral_authority_restored") is not False
        or manifest.get("byok_key_storage") != "separate-encrypted-object"):
        raise SnapshotError("restore critical manifest is invalid")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) > MAX_FILES:
        raise SnapshotError("restore critical file inventory is invalid")
    expected = {"manifest.json"}
    kinds: set[str] = set()
    total = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"source", "path", "kind", "bytes", "sha256"}:
            raise SnapshotError("restore critical file schema is invalid")
        name, size, digest, kind = row["path"], row["bytes"], row["sha256"], row["kind"]
        if (not isinstance(row["source"], str) or not Path(row["source"]).is_absolute()
            or ".." in Path(row["source"]).parts or "\x00" in row["source"]
            or not isinstance(name, str) or Path(name).is_absolute()
            or any(part in {"", ".", ".."} for part in name.split("/"))
            or name in expected or type(size) is not int or size < 0 or size > MAX_FILE_BYTES
            or not isinstance(digest, str) or len(digest) != 64 or not isinstance(kind, str)):
            raise SnapshotError("restore critical file identity is invalid")
        expected.add(name)
        kinds.add(kind)
        target = critical / name
        info = _regular(target, inventory)
        actual = hashlib.sha256()
        with target.open("rb") as stream:
            while chunk := stream.read(65536):
                actual.update(chunk)
        if info.st_size != size or actual.hexdigest() != digest:
            raise SnapshotError("restore critical file hash does not match")
        total += size
    if (type(manifest.get("bytes")) is not int or total != manifest.get("bytes") or total > MAX_TOTAL_BYTES
        or not {"byok-ciphertext", "account-registry", "passkey-state", "system-recovery"}.issubset(kinds)
        or {path.relative_to(critical).as_posix() for path in _tree(critical, inventory)} != expected):
        raise SnapshotError("restore critical coverage does not match")
    for required in ("state/byok/credentials.enc", "state/auth/accounts.json", "state/auth/passkeys.json",
                     "system/secrets.env", "system/rclone.conf", "system/tunnel.json"):
        if required not in expected:
            raise SnapshotError("restore required critical file is missing")
    encrypted_info = _regular(encrypted_key, inventory)
    pairing = manifest.get("encrypted_byok_key")
    if (not isinstance(pairing, dict) or set(pairing) != {"sha256", "bytes", "recipient_sha256"}
        or type(pairing["bytes"]) is not int or pairing["bytes"] != encrypted_info.st_size
        or not isinstance(pairing["sha256"], str) or len(pairing["sha256"]) != 64
        or not isinstance(pairing["recipient_sha256"], str) or len(pairing["recipient_sha256"]) != 64
        or hashlib.sha256(_read(encrypted_key, inventory, 4096)).hexdigest() != pairing["sha256"]):
        raise SnapshotError("restore separate key object does not match this archive")
    master = _read(key, inventory, 32)
    if len(master) != 32:
        raise SnapshotError("restore BYOK master key size is invalid")
    records = json.loads(_read(critical / "state/byok/credentials.enc", inventory))
    if not isinstance(records, dict):
        raise SnapshotError("restore BYOK artifact is invalid")
    for credential_id, row in records.items():
        _credential_from_record(credential_id, row, master)


def restore(encrypted_data: Path, encrypted_key: Path, identity: Path, destination: Path) -> None:
    """Recover into a new offline directory only, never into live user stores."""
    from tools.critical_backup_crypto import decrypt_file

    inventory = _Inventory({0, os.getuid()}, {0, os.getgid()})
    _parents(destination, inventory)
    destination.mkdir(mode=0o700)
    phase = "data authentication"
    try:
        with tempfile.TemporaryDirectory(prefix=".critical-restore-", dir=destination.parent) as temporary:
            archive = Path(temporary) / "data.tar.gz"
            key = Path(temporary) / "byok-master.key"
            decrypt_file(encrypted_data, archive, identity)
            phase = "separate key authentication"
            decrypt_file(encrypted_key, key, identity)
            phase = "archive extraction"
            _extract(archive, destination)
            phase = "critical inventory verification"
            _verify_restored(destination, key, encrypted_key)
            phase = "separate key publication"
            _write(destination / "separate-byok-key/byok_master.key", key.read_bytes())
    except BaseException as exc:
        try:
            shutil.rmtree(destination)
        except OSError:
            raise SnapshotError("offline restore failed; owned cleanup is incomplete") from None
        if not isinstance(exc, Exception):
            raise
        # Our own refusal messages are fixed/value-free. Native or dependency
        # error text may contain file contents, so expose only its class.
        reason = str(exc) if isinstance(exc, SnapshotError) else type(exc).__name__
        raise SnapshotError(f"offline restore refused during {phase} ({reason}); no recovered state published") from None


def main() -> int:
    parser = argparse.ArgumentParser(description="Encrypted critical-state backup and offline recovery")
    commands = parser.add_subparsers(dest="command", required=True)
    preparing = commands.add_parser("prepare")
    for name in ("sources", "state", "destination", "escrow", "recipient"):
        preparing.add_argument("--" + name, required=True, type=Path)
    sealing = commands.add_parser("encrypt")
    for name in ("source", "destination", "recipient"):
        sealing.add_argument("--" + name, required=True, type=Path)
    recovering = commands.add_parser("restore")
    for name in ("data", "key", "identity", "destination"):
        recovering.add_argument("--" + name, required=True, type=Path)
    sqlite_worker = commands.add_parser("_sqlite-worker", help=argparse.SUPPRESS)
    sqlite_worker.add_argument("--source", required=True, type=Path)
    sqlite_worker.add_argument("--timeout", required=True, type=float)
    arguments = parser.parse_args()
    from tools.critical_backup_crypto import BackupCryptoError, encrypt_file

    try:
        if arguments.command == "_sqlite-worker":
            if not 0 < arguments.timeout <= SQLITE_TIMEOUT_SECONDS:
                raise SnapshotError("SQLite worker deadline is invalid")
            inventory = _Inventory({0, os.geteuid()}, {0, os.getegid()})
            _sqlite_native(arguments.source, Path("snapshot.sqlite3"), inventory, Path("."), arguments.timeout)
        elif arguments.command == "prepare":
            prepare(load_sources(arguments.sources, arguments.state), arguments.destination,
                    arguments.escrow, arguments.recipient)
        elif arguments.command == "encrypt":
            encrypt_file(arguments.source, arguments.destination, arguments.recipient)
        else:
            restore(arguments.data, arguments.key, arguments.identity, arguments.destination)
    except (SnapshotError, BackupCryptoError, OSError, ValueError):
        print("ERROR: critical backup/restore refused; no successful receipt", file=sys.stderr)
        return 11
    return 0


if __name__ == "__main__":
    # Direct deployed-script invocation needs the repository root, not only tools/.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())
