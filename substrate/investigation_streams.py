"""Opaque account-scoped event stream codec and W3 storage-state resolver."""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import stat
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from substrate.investigation_tenancy import (
    TENANCY_VERSION,
    InvestigationAuthority,
    InvestigationOwnershipConflict,
    default_tenancy_root,
)

STREAM_LAYOUT_VERSION = 1
_MAX_MARKER_BYTES = 64 * 1024


class StreamStorageState(StrEnum):
    LEGACY = "legacy"
    COPYING = "copying"
    COMPOSITE = "composite"
    QUARANTINED = "quarantined"


class InvestigationStreamUnbound(InvestigationOwnershipConflict):
    """No legacy lease or composite allocation exists for this authority."""


@dataclass(frozen=True)
class ResolvedInvestigationStream:
    authority: InvestigationAuthority
    state: StreamStorageState
    jsonl_path: Path
    parquet_path: Path
    state_path: Path
    allocation_path: Path


@dataclass(frozen=True)
class OpenedInvestigationStream:
    """Pinned stream namespace; ``directory_fd`` is valid only in its context."""

    authority: InvestigationAuthority
    state: StreamStorageState
    directory_fd: int
    jsonl_name: str
    parquet_name: str


def _key(authority: InvestigationAuthority) -> str:
    key = authority.stream_key
    if len(key) != 64 or any(ch not in "0123456789abcdef" for ch in key):
        raise RuntimeError("investigation stream key is invalid")
    return key


def _relative_paths(authority: InvestigationAuthority) -> dict[str, tuple[str, ...]]:
    key = _key(authority)
    return {
        "stream_dir": ("streams", f"v{STREAM_LAYOUT_VERSION}", key[:2]),
        "state_dir": (".tenancy", "stream-state"),
        "allocation_dir": (".tenancy", "stream-allocations"),
        "index_dir": (
            ".tenancy",
            "account-stream-index",
            authority.account_digest[:2],
            authority.account_digest,
        ),
        "key_dir": (".tenancy",),
    }


def _paths(authority: InvestigationAuthority) -> tuple[Path, Path, Path, Path]:
    key = _key(authority)
    stream_dir = authority.root.joinpath(*_relative_paths(authority)["stream_dir"])
    return (
        stream_dir / f"{key}.jsonl",
        stream_dir / f"{key}.parquet",
        authority.root / ".tenancy" / "stream-state" / f"{key}.json",
        authority.root / ".tenancy" / "stream-allocations" / f"{key}.json",
    )


def composite_stream_is_allocated(authority: InvestigationAuthority) -> bool:
    """Probe allocation without the resolver's recovery bookkeeping writes."""
    try:
        _paths(authority)[3].lstat()
    except FileNotFoundError:
        return False
    return True


def _root_fd(root: Path) -> int:
    root = root.expanduser().absolute()
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    current = os.open(root.anchor or "/", flags)
    try:
        for part in root.parts[1:]:
            if not part or part in {".", ".."}:
                raise RuntimeError("investigation stream root is unsafe")
            created = False
            try:
                os.mkdir(part, mode=0o700, dir_fd=current)
                created = True
            except FileExistsError:
                pass
            try:
                child = os.open(part, flags, dir_fd=current)
            except OSError as exc:
                raise RuntimeError("investigation stream root is unsafe") from exc
            try:
                if created:
                    os.fsync(current)
                    os.fsync(child)
            except Exception:
                os.close(child)
                raise
            try:
                os.close(current)
            except Exception:
                os.close(child)
                raise
            current = child
        return current
    except Exception:
        os.close(current)
        raise


def _authority_root_fd(authority: InvestigationAuthority) -> int:
    fd = _root_fd(authority.root)
    info = os.fstat(fd)
    if (info.st_dev, info.st_ino) != (
        authority.root_device,
        authority.root_inode,
    ):
        os.close(fd)
        raise RuntimeError("investigation stream root identity changed")
    return fd


def _directory_fd(root_fd: int, parts: tuple[str, ...], *, create: bool) -> int:
    current = os.dup(root_fd)
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    try:
        for part in parts:
            if not part or part in {".", ".."} or "/" in part or "\\" in part:
                raise RuntimeError("investigation stream directory is unsafe")
            created = False
            if create:
                with suppress(FileExistsError):
                    os.mkdir(part, mode=0o700, dir_fd=current)
                    created = True
            try:
                child = os.open(part, flags, dir_fd=current)
            except OSError as exc:
                raise RuntimeError("investigation stream directory is unsafe") from exc
            try:
                if created:
                    os.fsync(current)
                    os.fsync(child)
            except Exception:
                os.close(child)
                raise
            try:
                os.close(current)
            except Exception:
                os.close(child)
                raise
            current = child
        return current
    except Exception:
        os.close(current)
        raise


def _read_at_unlocked(directory_fd: int, name: str) -> bytes | None:
    try:
        fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeError("investigation stream marker is unsafe") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError("investigation stream marker is unsafe")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(fd, 16 * 1024):
            total += len(chunk)
            if total > _MAX_MARKER_BYTES:
                raise RuntimeError("investigation stream marker is oversized")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _recover_publish_at(directory_fd: int, name: str) -> None:
    """Remove only crash remnants that are provably the published inode."""
    prefix = f".{name}."
    temp_names = sorted(
        entry
        for entry in os.listdir(directory_fd)
        if entry.startswith(prefix) and entry.endswith(".tmp")
    )
    if not temp_names:
        return
    try:
        final = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        final = None
    changed = False
    for temp_name in temp_names:
        try:
            temp = os.stat(temp_name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(temp.st_mode):
            raise RuntimeError("investigation stream publish remnant is unsafe")
        if final is None:
            if temp.st_nlink != 1:
                raise RuntimeError("investigation stream publish remnant is unsafe")
        elif (
            (temp.st_dev, temp.st_ino) != (final.st_dev, final.st_ino)
            or temp.st_nlink != 2
            or final.st_nlink != 2
        ):
            raise RuntimeError("investigation stream publish remnant is unsafe")
        os.unlink(temp_name, dir_fd=directory_fd)
        changed = True
    if changed:
        os.fsync(directory_fd)


def _read_at(directory_fd: int, name: str) -> bytes | None:
    # Recovery mutates the directory, so readers briefly take the exclusive lock.
    # The marker is small and reads are infrequent control-plane operations.
    fcntl.flock(directory_fd, fcntl.LOCK_EX)
    try:
        _recover_publish_at(directory_fd, name)
        return _read_at_unlocked(directory_fd, name)
    finally:
        fcntl.flock(directory_fd, fcntl.LOCK_UN)


def _atomic_create_at(directory_fd: int, name: str, payload: bytes) -> bool:
    temp_name = f".{name}.{secrets.token_hex(12)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fcntl.flock(directory_fd, fcntl.LOCK_EX)
    fd: int | None = None
    try:
        _recover_publish_at(directory_fd, name)
        if _read_at_unlocked(directory_fd, name) is not None:
            return False
        fd = os.open(temp_name, flags, 0o600, dir_fd=directory_fd)
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(
                temp_name,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            return False
        os.unlink(temp_name, dir_fd=directory_fd)
        os.fsync(directory_fd)
        return True
    finally:
        if fd is not None:
            os.close(fd)
        with suppress(FileNotFoundError):
            os.unlink(temp_name, dir_fd=directory_fd)
        fcntl.flock(directory_fd, fcntl.LOCK_UN)


def _canonical(data: dict[str, object]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _entry_exists_at(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


@contextmanager
def _operation_lock(tenancy_fd: int, *, exclusive: bool) -> Iterator[None]:
    # Darwin can report ENOENT when several threads race O_CREAT|O_NOFOLLOW on
    # the same dirfd-relative name. Publish the inode through our serialized
    # no-overwrite primitive, then open the established file.
    _atomic_create_at(tenancy_fd, "stream-resolution.lock", b"")
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open("stream-resolution.lock", flags, 0o600, dir_fd=tenancy_fd)
    except OSError as exc:
        raise RuntimeError("investigation stream operation lock is unsafe") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError("investigation stream operation lock is unsafe")
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _legacy_lease_state_at(
    authority: InvestigationAuthority, tenancy_fd: int, *, required: bool = True
) -> str | None:
    """Read legacy ownership from the same pinned tenancy namespace."""
    try:
        os.stat("legacy-stream-leases", dir_fd=tenancy_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        if not required:
            return None
        raise InvestigationStreamUnbound(
            "investigation has no account ownership binding"
        ) from exc
    try:
        leases_fd = _directory_fd(tenancy_fd, ("legacy-stream-leases",), create=False)
    except RuntimeError as exc:
        raise InvestigationOwnershipConflict(
            "investigation ownership binding is invalid"
        ) from exc
    try:
        raw = _read_at(leases_fd, f"{authority.investigation_digest}.json")
    finally:
        os.close(leases_fd)
    if raw is None:
        if not required:
            return None
        raise InvestigationStreamUnbound(
            "investigation has no account ownership binding"
        )
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvestigationOwnershipConflict(
            "investigation ownership binding is invalid"
        ) from exc
    expected = {
        "version": TENANCY_VERSION,
        "account_digest": authority.account_digest,
        "investigation_digest": authority.investigation_digest,
        "future_stream_key": authority.stream_key,
    }
    if not isinstance(record, dict) or any(
        record.get(key) != value for key, value in expected.items()
    ):
        raise InvestigationOwnershipConflict(
            "investigation belongs to another account or has an invalid binding"
        )
    state = record.get("storage_state", StreamStorageState.LEGACY.value)
    if state not in {
        StreamStorageState.LEGACY.value,
        StreamStorageState.COMPOSITE.value,
    }:
        raise InvestigationOwnershipConflict(
            "investigation ownership binding is invalid"
        )
    return state


def _legacy_display_lease_allows_parallel_composite(
    authority: InvestigationAuthority, tenancy_fd: int
) -> bool:
    """Allow ID reuse only after the foreign legacy owner fully cut over."""
    try:
        leases_fd = _directory_fd(tenancy_fd, ("legacy-stream-leases",), create=False)
    except RuntimeError:
        return True
    try:
        raw = _read_at(leases_fd, f"{authority.investigation_digest}.json")
    finally:
        os.close(leases_fd)
    if raw is None:
        return True
    try:
        record = json.loads(raw.decode("utf-8"))
        account_digest = record["account_digest"]
        stream_key = record["future_stream_key"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise InvestigationOwnershipConflict(
            "investigation ownership binding is invalid"
        ) from exc
    if (
        not isinstance(record, dict)
        or record.get("version") != TENANCY_VERSION
        or record.get("investigation_digest") != authority.investigation_digest
        or not isinstance(account_digest, str)
        or len(account_digest) != 64
        or any(ch not in "0123456789abcdef" for ch in account_digest)
        or not isinstance(stream_key, str)
        or len(stream_key) != 64
        or any(ch not in "0123456789abcdef" for ch in stream_key)
    ):
        raise InvestigationOwnershipConflict(
            "investigation ownership binding is invalid"
        )
    if account_digest == authority.account_digest:
        return False
    if record.get("storage_state") != StreamStorageState.COMPOSITE.value:
        raise InvestigationOwnershipConflict(
            "display investigation ID is leased to another account"
        )
    allocation_fd = _directory_fd(tenancy_fd, ("stream-allocations",), create=False)
    state_fd = _directory_fd(tenancy_fd, ("stream-state",), create=False)
    index_fd = _directory_fd(
        tenancy_fd,
        ("account-stream-index", account_digest[:2], account_digest),
        create=False,
    )
    try:
        marker_name = f"{stream_key}.json"
        index_raw = _read_at(index_fd, marker_name)
        try:
            index = json.loads((index_raw or b"").decode("utf-8"))
            account_id = index["account_id"]
            investigation_id = index["investigation_id"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise InvestigationOwnershipConflict(
                "migrated investigation ownership binding is invalid"
            ) from exc
        owner = InvestigationAuthority(account_id, investigation_id, authority.root)
        if (
            owner.investigation_id != authority.investigation_id
            or owner.account_digest != account_digest
            or owner.stream_key != stream_key
        ):
            raise InvestigationOwnershipConflict(
                "migrated investigation ownership binding is invalid"
            )
        _parse_exact(
            _read_at(allocation_fd, marker_name),
            _identity_record(owner),
            "migrated investigation stream allocation is invalid",
        )
        _parse_exact(
            _read_at(state_fd, marker_name),
            _state_record(owner),
            "migrated investigation stream state is invalid",
        )
        _parse_exact(
            index_raw,
            _index_record(owner),
            "migrated investigation stream index is invalid",
        )
    finally:
        os.close(index_fd)
        os.close(state_fd)
        os.close(allocation_fd)
    return True


def _lease_state_for_resolution(
    authority: InvestigationAuthority,
    tenancy_fd: int,
    *,
    allocation_present: bool,
) -> str | None:
    try:
        return _legacy_lease_state_at(authority, tenancy_fd, required=False)
    except InvestigationOwnershipConflict:
        if allocation_present and _legacy_display_lease_allows_parallel_composite(
            authority,
            tenancy_fd,
        ):
            return None
        raise


def _identity_record(authority: InvestigationAuthority) -> dict[str, object]:
    return {
        "version": STREAM_LAYOUT_VERSION,
        "key_id": authority.key_id,
        "account_digest": authority.account_digest,
        "investigation_digest": authority.investigation_digest,
        "stream_key": authority.stream_key,
    }


def _state_record(authority: InvestigationAuthority) -> dict[str, object]:
    return {**_identity_record(authority), "state": StreamStorageState.COMPOSITE.value}


def _index_record(authority: InvestigationAuthority) -> dict[str, object]:
    return {
        **_identity_record(authority),
        "account_id": authority.account_id,
        "investigation_id": authority.investigation_id,
    }


def _parse_exact(raw: bytes | None, expected: dict[str, object], message: str) -> None:
    if raw is None:
        raise InvestigationOwnershipConflict(message)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvestigationOwnershipConflict(message) from exc
    if not isinstance(data, dict) or data != expected:
        raise InvestigationOwnershipConflict(message)


def _verify_key_anchor(
    authority: InvestigationAuthority, tenancy_fd: int, *, create: bool
) -> None:
    expected = _canonical(
        {"version": STREAM_LAYOUT_VERSION, "key_id": authority.key_id}
    )
    raw = _read_at(tenancy_fd, "stream-key-generation.json")
    if raw is None and create:
        _atomic_create_at(tenancy_fd, "stream-key-generation.json", expected)
        raw = _read_at(tenancy_fd, "stream-key-generation.json")
    if raw != expected:
        raise InvestigationOwnershipConflict("investigation tenancy key changed")


def _assert_no_incomplete_migration_at(
    authority: InvestigationAuthority, tenancy_fd: int
) -> None:
    try:
        journal_fd = _directory_fd(tenancy_fd, ("stream-migrations",), create=False)
    except RuntimeError:
        return
    try:
        for direction, suffix in (
            ("legacy_to_composite", "forward"),
            ("composite_to_legacy", "rollback"),
        ):
            raw = _read_at(journal_fd, f"{authority.stream_key}.{suffix}.json")
            if raw is None:
                continue
            try:
                record = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise InvestigationOwnershipConflict(
                    "investigation migration journal is invalid"
                ) from exc
            expected = {
                "version": 1,
                "key_id": authority.key_id,
                "account_digest": authority.account_digest,
                "investigation_digest": authority.investigation_digest,
                "stream_key": authority.stream_key,
                "direction": direction,
            }
            if (
                not isinstance(record, dict)
                or any(record.get(key) != value for key, value in expected.items())
                or not isinstance(record.get("operation_digest"), str)
                or len(record["operation_digest"]) != 64
                or any(
                    ch not in "0123456789abcdef"
                    for ch in record["operation_digest"]
                )
            ):
                raise InvestigationOwnershipConflict(
                    "investigation migration journal is invalid"
                )
            if record.get("phase") not in {"flipped", "complete"}:
                raise InvestigationOwnershipConflict(
                    "investigation migration requires operator recovery"
                )
    finally:
        os.close(journal_fd)


def initialize_composite_stream(authority: InvestigationAuthority) -> ResolvedInvestigationStream:
    """Durably allocate and initialize a composite stream before its first write."""
    with ExitStack() as stack:
        root_fd = _authority_root_fd(authority)
        stack.callback(os.close, root_fd)
        tenancy_fd = _directory_fd(root_fd, (".tenancy",), create=True)
        stack.callback(os.close, tenancy_fd)
        paths = _relative_paths(authority)
        allocation_fd = _directory_fd(
            tenancy_fd, paths["allocation_dir"][1:], create=True
        )
        stack.callback(os.close, allocation_fd)
        state_fd = _directory_fd(tenancy_fd, paths["state_dir"][1:], create=True)
        stack.callback(os.close, state_fd)
        index_fd = _directory_fd(tenancy_fd, paths["index_dir"][1:], create=True)
        stack.callback(os.close, index_fd)
        stream_fd = _directory_fd(root_fd, paths["stream_dir"], create=True)
        stack.callback(os.close, stream_fd)
        with _operation_lock(tenancy_fd, exclusive=True):
            if any(
                _entry_exists_at(root_fd, f"{authority.investigation_id}{suffix}")
                for suffix in (".jsonl", ".parquet")
            ):
                raise InvestigationOwnershipConflict(
                    "historic investigation requires explicit composite migration"
                )
            if not _legacy_display_lease_allows_parallel_composite(
                authority,
                tenancy_fd,
            ):
                raise InvestigationOwnershipConflict(
                    "legacy investigation requires explicit composite migration"
                )
            _verify_key_anchor(authority, tenancy_fd, create=True)
            _assert_no_incomplete_migration_at(authority, tenancy_fd)
            name = f"{authority.stream_key}.json"
            allocation = _canonical(_identity_record(authority))
            if not _atomic_create_at(allocation_fd, name, allocation):
                _parse_exact(
                    _read_at(allocation_fd, name),
                    _identity_record(authority),
                    "investigation stream allocation is invalid",
                )
            state = _canonical(_state_record(authority))
            if not _atomic_create_at(state_fd, name, state):
                _parse_exact(
                    _read_at(state_fd, name),
                    _state_record(authority),
                    "investigation stream state is invalid",
                )
            index = _canonical(_index_record(authority))
            if not _atomic_create_at(index_fd, name, index):
                _parse_exact(
                    _read_at(index_fd, name),
                    _index_record(authority),
                    "investigation stream index is invalid",
                )
    jsonl, parquet, state_path, allocation_path = _paths(authority)
    return ResolvedInvestigationStream(
        authority,
        StreamStorageState.COMPOSITE,
        jsonl,
        parquet,
        state_path,
        allocation_path,
    )


def resolve_investigation_stream(
    authority: InvestigationAuthority,
) -> ResolvedInvestigationStream:
    """Resolve exactly one authoritative state; a lost marker never revives legacy."""
    # Existing W2 roots establish their key-generation anchor on first W3
    # resolution; every later key change fails before legacy/composite lookup.
    with ExitStack() as stack:
        root_fd = _authority_root_fd(authority)
        stack.callback(os.close, root_fd)
        tenancy_fd = _directory_fd(root_fd, (".tenancy",), create=True)
        stack.callback(os.close, tenancy_fd)
        paths = _relative_paths(authority)
        allocation_fd = _directory_fd(
            tenancy_fd, paths["allocation_dir"][1:], create=True
        )
        stack.callback(os.close, allocation_fd)
        state_fd = _directory_fd(tenancy_fd, paths["state_dir"][1:], create=True)
        stack.callback(os.close, state_fd)
        with _operation_lock(tenancy_fd, exclusive=False):
            _verify_key_anchor(authority, tenancy_fd, create=True)
            _assert_no_incomplete_migration_at(authority, tenancy_fd)
            name = f"{authority.stream_key}.json"
            allocation = _read_at(allocation_fd, name)
            state = _read_at(state_fd, name)
            lease_state = _lease_state_for_resolution(
                authority,
                tenancy_fd,
                allocation_present=allocation is not None,
            )
            if lease_state == StreamStorageState.LEGACY.value:
                resolved_state = StreamStorageState.LEGACY
            elif (
                lease_state == StreamStorageState.COMPOSITE.value
                or allocation is not None
            ):
                index_fd = _directory_fd(
                    tenancy_fd, paths["index_dir"][1:], create=False
                )
                stack.callback(os.close, index_fd)
                _parse_exact(
                    allocation,
                    _identity_record(authority),
                    "investigation stream allocation is invalid",
                )
                _parse_exact(
                    state,
                    _state_record(authority),
                    "investigation stream state is invalid",
                )
                _parse_exact(
                    _read_at(index_fd, name),
                    _index_record(authority),
                    "investigation stream index is invalid",
                )
                resolved_state = StreamStorageState.COMPOSITE
            elif state is not None:
                raise InvestigationOwnershipConflict(
                    "investigation stream state is orphaned"
                )
            else:
                raise InvestigationStreamUnbound(
                    "investigation has no account ownership binding"
                )
    jsonl, parquet, state_path, allocation_path = _paths(authority)
    if resolved_state is StreamStorageState.COMPOSITE:
        return ResolvedInvestigationStream(
            authority,
            resolved_state,
            jsonl,
            parquet,
            state_path,
            allocation_path,
        )
    return ResolvedInvestigationStream(
        authority,
        StreamStorageState.LEGACY,
        authority.root / f"{authority.investigation_id}.jsonl",
        authority.root / f"{authority.investigation_id}.parquet",
        state_path,
        allocation_path,
    )


def resolve_writable_investigation_stream(
    authority: InvestigationAuthority,
) -> ResolvedInvestigationStream:
    """Resolve an existing stream or allocate a new composite stream exactly once."""
    try:
        return resolve_investigation_stream(authority)
    except InvestigationStreamUnbound:
        return initialize_composite_stream(authority)


@contextmanager
def open_investigation_stream(
    authority: InvestigationAuthority, *, writable: bool
) -> Iterator[OpenedInvestigationStream]:
    """Pin and revalidate one state-selected stream namespace across I/O."""
    if writable:
        resolve_writable_investigation_stream(authority)
    else:
        resolve_investigation_stream(authority)
    with ExitStack() as stack:
        root_fd = _authority_root_fd(authority)
        stack.callback(os.close, root_fd)
        tenancy_fd = _directory_fd(root_fd, (".tenancy",), create=False)
        stack.callback(os.close, tenancy_fd)
        paths = _relative_paths(authority)
        allocation_fd = _directory_fd(
            tenancy_fd, paths["allocation_dir"][1:], create=False
        )
        stack.callback(os.close, allocation_fd)
        state_fd = _directory_fd(tenancy_fd, paths["state_dir"][1:], create=False)
        stack.callback(os.close, state_fd)
        with _operation_lock(tenancy_fd, exclusive=False):
            _verify_key_anchor(authority, tenancy_fd, create=False)
            _assert_no_incomplete_migration_at(authority, tenancy_fd)
            marker_name = f"{authority.stream_key}.json"
            allocation = _read_at(allocation_fd, marker_name)
            state = _read_at(state_fd, marker_name)
            lease_state = _lease_state_for_resolution(
                authority,
                tenancy_fd,
                allocation_present=allocation is not None,
            )
            if lease_state == StreamStorageState.COMPOSITE.value or (
                lease_state is None and allocation is not None
            ):
                index_fd = _directory_fd(
                    tenancy_fd, paths["index_dir"][1:], create=False
                )
                stack.callback(os.close, index_fd)
                _parse_exact(
                    allocation,
                    _identity_record(authority),
                    "investigation stream allocation is invalid",
                )
                _parse_exact(
                    state,
                    _state_record(authority),
                    "investigation stream state is invalid",
                )
                _parse_exact(
                    _read_at(index_fd, marker_name),
                    _index_record(authority),
                    "investigation stream index is invalid",
                )
                directory_fd = _directory_fd(
                    root_fd, paths["stream_dir"], create=writable
                )
                stack.callback(os.close, directory_fd)
                key = authority.stream_key
                yield OpenedInvestigationStream(
                    authority,
                    StreamStorageState.COMPOSITE,
                    directory_fd,
                    f"{key}.jsonl",
                    f"{key}.parquet",
                )
                return
            if lease_state is None and state is not None:
                raise InvestigationOwnershipConflict(
                    "investigation stream state is orphaned"
                )
            if lease_state != StreamStorageState.LEGACY.value:
                raise InvestigationStreamUnbound(
                    "investigation has no account ownership binding"
                )
            directory_fd = os.dup(root_fd)
            stack.callback(os.close, directory_fd)
            display_id = authority.investigation_id
            yield OpenedInvestigationStream(
                authority,
                StreamStorageState.LEGACY,
                directory_fd,
                f"{display_id}.jsonl",
                f"{display_id}.parquet",
            )


def list_composite_investigation_ids(
    account_id: str, *, root: Path | None = None
) -> list[str]:
    """Enumerate validated composite display IDs for exactly one account."""
    probe = InvestigationAuthority(
        account_id,
        "__account_stream_index_probe__",
        root=root or default_tenancy_root(),
    )
    with ExitStack() as stack:
        root_fd = _authority_root_fd(probe)
        stack.callback(os.close, root_fd)
        tenancy_fd = _directory_fd(root_fd, (".tenancy",), create=False)
        stack.callback(os.close, tenancy_fd)
        paths = _relative_paths(probe)
        try:
            index_fd = _directory_fd(
                tenancy_fd, paths["index_dir"][1:], create=False
            )
        except RuntimeError:
            return []
        stack.callback(os.close, index_fd)
        with _operation_lock(tenancy_fd, exclusive=False):
            _verify_key_anchor(probe, tenancy_fd, create=False)
            investigation_ids: list[str] = []
            for name in sorted(os.listdir(index_fd)):
                if not name.endswith(".json") or name.startswith("."):
                    continue
                raw = _read_at(index_fd, name)
                try:
                    record = json.loads((raw or b"").decode("utf-8"))
                    investigation_id = record["investigation_id"]
                except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise InvestigationOwnershipConflict(
                        "investigation stream index is invalid"
                    ) from exc
                authority = InvestigationAuthority(account_id, investigation_id, probe.root)
                if name != f"{authority.stream_key}.json":
                    raise InvestigationOwnershipConflict(
                        "investigation stream index is invalid"
                    )
                _parse_exact(
                    raw,
                    _index_record(authority),
                    "investigation stream index is invalid",
                )
                investigation_ids.append(investigation_id)
            return investigation_ids


def list_authorized_investigation_ids(
    account_id: str, *, root: Path | None = None
) -> list[str]:
    """Enumerate composite and leased legacy streams owned by one account."""
    probe = InvestigationAuthority(
        account_id,
        "__account_stream_enumeration_probe__",
        root=root or default_tenancy_root(),
    )
    investigation_ids = set(
        list_composite_investigation_ids(account_id, root=probe.root)
    )
    with ExitStack() as stack:
        root_fd = _authority_root_fd(probe)
        stack.callback(os.close, root_fd)
        tenancy_fd = _directory_fd(root_fd, (".tenancy",), create=False)
        stack.callback(os.close, tenancy_fd)
        with _operation_lock(tenancy_fd, exclusive=False):
            candidates: set[str] = set()
            for name in os.listdir(root_fd):
                if name.endswith(".jsonl"):
                    candidates.add(name[: -len(".jsonl")])
                elif name.endswith(".parquet"):
                    candidates.add(name[: -len(".parquet")])
            for investigation_id in candidates:
                try:
                    authority = InvestigationAuthority(
                        account_id,
                        investigation_id,
                        probe.root,
                    )
                    if _legacy_lease_state_at(
                        authority,
                        tenancy_fd,
                        required=False,
                    ) == StreamStorageState.LEGACY:
                        investigation_ids.add(investigation_id)
                except (ValueError, InvestigationOwnershipConflict):
                    continue
    return sorted(investigation_ids)


def list_operator_investigation_authorities(
    operator: InvestigationAuthority,
) -> list[InvestigationAuthority]:
    """Enumerate every validated composite stream for an explicit operator."""
    if operator.account_id != "__operator__":
        raise InvestigationOwnershipConflict("global stream enumeration requires operator")
    authorities: list[InvestigationAuthority] = []
    with ExitStack() as stack:
        root_fd = _authority_root_fd(operator)
        stack.callback(os.close, root_fd)
        tenancy_fd = _directory_fd(root_fd, (".tenancy",), create=False)
        stack.callback(os.close, tenancy_fd)
        with _operation_lock(tenancy_fd, exclusive=False):
            raw_investigation_ids = {
                name.removesuffix(".jsonl").removesuffix(".parquet")
                for name in os.listdir(root_fd)
                if name.endswith((".jsonl", ".parquet"))
            }
            try:
                index_root_fd = _directory_fd(
                    tenancy_fd,
                    ("account-stream-index",),
                    create=False,
                )
            except RuntimeError:
                if raw_investigation_ids:
                    raise InvestigationOwnershipConflict(
                        "global stream enumeration requires legacy migration"
                    ) from None
                return []
            stack.callback(os.close, index_root_fd)
            _verify_key_anchor(operator, tenancy_fd, create=False)
            for prefix in sorted(os.listdir(index_root_fd)):
                if len(prefix) != 2 or any(ch not in "0123456789abcdef" for ch in prefix):
                    raise InvestigationOwnershipConflict(
                        "investigation account index is invalid"
                    )
                prefix_fd = _directory_fd(index_root_fd, (prefix,), create=False)
                try:
                    for account_digest in sorted(os.listdir(prefix_fd)):
                        if (
                            len(account_digest) != 64
                            or not account_digest.startswith(prefix)
                            or any(
                                ch not in "0123456789abcdef"
                                for ch in account_digest
                            )
                        ):
                            raise InvestigationOwnershipConflict(
                                "investigation account index is invalid"
                            )
                        account_fd = _directory_fd(
                            prefix_fd,
                            (account_digest,),
                            create=False,
                        )
                        try:
                            for name in sorted(os.listdir(account_fd)):
                                if not name.endswith(".json") or name.startswith("."):
                                    continue
                                raw = _read_at(account_fd, name)
                                try:
                                    record = json.loads((raw or b"").decode("utf-8"))
                                    account_id = record["account_id"]
                                    investigation_id = record["investigation_id"]
                                except (
                                    UnicodeDecodeError,
                                    json.JSONDecodeError,
                                    KeyError,
                                    TypeError,
                                ) as exc:
                                    raise InvestigationOwnershipConflict(
                                        "investigation account index is invalid"
                                    ) from exc
                                authority = InvestigationAuthority(
                                    account_id,
                                    investigation_id,
                                    operator.root,
                                )
                                if (
                                    authority.account_digest != account_digest
                                    or name != f"{authority.stream_key}.json"
                                ):
                                    raise InvestigationOwnershipConflict(
                                        "investigation account index is invalid"
                                    )
                                _parse_exact(
                                    raw,
                                    _index_record(authority),
                                    "investigation account index is invalid",
                                )
                                authorities.append(authority)
                        finally:
                            os.close(account_fd)
                finally:
                    os.close(prefix_fd)
            for investigation_id in raw_investigation_ids:
                migrated_owners = 0
                for authority in authorities:
                    if authority.investigation_id != investigation_id:
                        continue
                    try:
                        lease_state = _legacy_lease_state_at(
                            authority,
                            tenancy_fd,
                            required=False,
                        )
                    except InvestigationOwnershipConflict:
                        continue
                    if lease_state == StreamStorageState.COMPOSITE.value:
                        migrated_owners += 1
                if migrated_owners != 1:
                    raise InvestigationOwnershipConflict(
                        "global stream enumeration requires legacy migration"
                    )
    authorities.sort(key=lambda item: (item.account_id, item.investigation_id))
    return authorities
