"""Canonical account/investigation authority and pre-migration stream leases."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import stat
import tempfile
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

TENANCY_VERSION = 1
_KEY_ENV = "ANTIEK_INVESTIGATION_TENANCY_KEY_SECRET"


class InvestigationOwnershipConflict(RuntimeError):
    pass


def default_tenancy_root() -> Path:
    return Path(
        os.environ.get(
            "ANTIEK_RESEARCH_EVENTS_DIR",
            str(
                Path(os.environ.get("ANTIEK_HOME", "~/.antiek")).expanduser()
                / "research_events"
            ),
        )
    )


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise RuntimeError("investigation tenancy directory is unsafe")
    os.chmod(path, 0o700)


def _read_regular(path: Path) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise RuntimeError("investigation tenancy file is unsafe") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError("investigation tenancy file is unsafe")
        return os.read(fd, 1024 * 1024)
    finally:
        os.close(fd)


def _atomic_write(path: Path, data: bytes) -> None:
    _private_dir(path.parent)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _key(root: Path) -> bytes:
    configured = os.environ.get(_KEY_ENV, "")
    configured_key = hashlib.sha256(configured.encode()).digest() if configured else None
    path = root / ".tenancy" / "authority-key-v1"
    _private_dir(path.parent)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raw = _read_regular(path)
    else:
        raw = configured_key or os.urandom(32)
        try:
            os.write(fd, raw)
            os.fsync(fd)
        finally:
            os.close(fd)
    if len(raw) != 32:
        raise RuntimeError("investigation tenancy key is invalid")
    if configured_key is not None and not hmac.compare_digest(raw, configured_key):
        raise RuntimeError("investigation tenancy key rotation requires migration")
    return raw


def _validated(value: str, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\x00" in value
        or any(unicodedata.category(character).startswith("C") for character in value)
        or (field_name == "investigation_id" and ("/" in value or "\\" in value))
    ):
        raise ValueError(f"{field_name} is invalid")
    if len(value.encode("utf-8")) > 512:
        raise ValueError(f"{field_name} is invalid")
    return value


def _digest(root: Path, kind: str, value: str) -> str:
    message = f"antiek-investigation-tenancy-v1\0{kind}\0{value}".encode()
    return hmac.new(_key(root), message, hashlib.sha256).hexdigest()


def tenancy_key_id(root: Path | None = None) -> str:
    """Opaque fingerprint used to fail closed if a tenancy root's key changes."""
    resolved = (root or default_tenancy_root()).expanduser().resolve(strict=False)
    return _digest(resolved, "key-generation", "v1")


@dataclass(frozen=True)
class InvestigationAuthority:
    account_id: str
    investigation_id: str
    root: Path = field(default_factory=default_tenancy_root, repr=False)
    account_digest: str = field(init=False)
    investigation_digest: str = field(init=False)
    stream_key: str = field(init=False)
    key_id: str = field(init=False)
    root_device: int = field(init=False, repr=False)
    root_inode: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        account_id = _validated(self.account_id, "account_id")
        investigation_id = _validated(self.investigation_id, "investigation_id")
        root = self.root.expanduser().resolve(strict=False)
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(self, "investigation_id", investigation_id)
        object.__setattr__(self, "root", root)
        account_digest = _digest(root, "account", account_id)
        investigation_digest = _digest(root, "investigation", investigation_id)
        object.__setattr__(self, "account_digest", account_digest)
        object.__setattr__(self, "investigation_digest", investigation_digest)
        object.__setattr__(
            self,
            "stream_key",
            _digest(root, "stream", f"{account_digest}:{investigation_digest}"),
        )
        object.__setattr__(self, "key_id", tenancy_key_id(root))
        root_info = root.stat()
        object.__setattr__(self, "root_device", root_info.st_dev)
        object.__setattr__(self, "root_inode", root_info.st_ino)


@contextmanager
def _registry_lock(root: Path) -> Iterator[None]:
    directory = root / ".tenancy"
    _private_dir(directory)
    path = directory / "registry.lock"
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError as exc:
        raise RuntimeError("investigation tenancy lock is unsafe") from exc
    with os.fdopen(fd, "a+b") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError("investigation tenancy lock is unsafe")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _bind_legacy_stream_lease(
    authority: InvestigationAuthority, *, provenance: str, allow_historic: bool
) -> Path:
    """Bind the still-global raw event stream to one account until W3 migration."""
    leases = authority.root / ".tenancy" / "legacy-stream-leases"
    path = leases / f"{authority.investigation_digest}.json"
    record = {
        "version": TENANCY_VERSION,
        "account_digest": authority.account_digest,
        "investigation_digest": authority.investigation_digest,
        "future_stream_key": authority.stream_key,
        "storage_state": "legacy",
        "provenance": provenance,
        "created_at": _now(),
    }
    with _registry_lock(authority.root):
        if path.exists() or path.is_symlink():
            existing = json.loads(_read_regular(path).decode("utf-8"))
            identity = {
                key: existing.get(key)
                for key in ("version", "account_digest", "investigation_digest", "future_stream_key")
            }
            expected = {key: record[key] for key in identity}
            if identity != expected:
                raise InvestigationOwnershipConflict(
                    "display investigation ID is leased to another account"
                )
            return path
        if not allow_historic and any(
            (authority.root / f"{authority.investigation_id}{suffix}").exists()
            for suffix in (".jsonl", ".parquet")
        ):
            raise InvestigationOwnershipConflict(
                "unbound historic investigation requires explicit operator migration"
            )
        _atomic_write(path, json.dumps(record, sort_keys=True, separators=(",", ":")).encode())
    return path


def bind_legacy_stream_lease(
    authority: InvestigationAuthority, *, provenance: str = "created"
) -> Path:
    """Bind a new global stream before its first event write."""
    return _bind_legacy_stream_lease(
        authority, provenance=provenance, allow_historic=False
    )


def bind_historic_operator_stream_lease(authority: InvestigationAuthority) -> Path:
    """Explicit migration-only bridge for pre-tenancy operator streams."""
    if authority.account_id != "__operator__":
        raise InvestigationOwnershipConflict(
            "historic investigations may bind only to the canonical operator"
        )
    return _bind_legacy_stream_lease(
        authority,
        provenance="historic_operator_migration",
        allow_historic=True,
    )


def bind_child_stream_lease(
    parent_investigation_id: str,
    child_investigation_id: str,
    *,
    root: Path | None = None,
    expected_account_digest: str,
) -> Path:
    """Inherit opaque ownership for a background-spawned child stream."""
    root = (root or default_tenancy_root()).expanduser().absolute()
    parent_id = _validated(parent_investigation_id, "investigation_id")
    child_id = _validated(child_investigation_id, "investigation_id")
    parent_digest = _digest(root, "investigation", parent_id)
    child_digest = _digest(root, "investigation", child_id)
    leases = root / ".tenancy" / "legacy-stream-leases"
    parent_path = leases / f"{parent_digest}.json"
    child_path = leases / f"{child_digest}.json"
    with _registry_lock(root):
        try:
            parent = json.loads(_read_regular(parent_path).decode("utf-8"))
            account_digest = parent["account_digest"]
        except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
            raise InvestigationOwnershipConflict(
                "parent investigation ownership binding is invalid"
            ) from exc
        if (
            parent.get("version") != TENANCY_VERSION
            or parent.get("investigation_digest") != parent_digest
            or not isinstance(account_digest, str)
            or len(account_digest) != 64
        ):
            raise InvestigationOwnershipConflict(
                "parent investigation ownership binding is invalid"
            )
        if account_digest != expected_account_digest:
            raise InvestigationOwnershipConflict(
                "parent investigation ownership binding is invalid"
            )
        record = {
            "version": TENANCY_VERSION,
            "account_digest": account_digest,
            "investigation_digest": child_digest,
            "future_stream_key": _digest(
                root, "stream", f"{account_digest}:{child_digest}"
            ),
            "provenance": "parent_lease_inheritance",
            "created_at": _now(),
        }
        if child_path.exists() or child_path.is_symlink():
            try:
                existing = json.loads(_read_regular(child_path).decode("utf-8"))
            except (RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise InvestigationOwnershipConflict(
                    "child investigation ownership binding is invalid"
                ) from exc
            identity_keys = (
                "version",
                "account_digest",
                "investigation_digest",
                "future_stream_key",
            )
            if any(existing.get(key) != record[key] for key in identity_keys):
                raise InvestigationOwnershipConflict(
                    "child investigation is leased to another account"
                )
            return child_path
        if any((root / f"{child_id}{suffix}").exists() for suffix in (".jsonl", ".parquet")):
            raise InvestigationOwnershipConflict(
                "unbound child investigation stream already exists"
            )
        _atomic_write(
            child_path,
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode(),
        )
    return child_path


def legacy_stream_account_digest(
    investigation_id: str, *, root: Path | None = None
) -> str:
    """Read the validated opaque owner digest for internal child orchestration."""
    root = (root or default_tenancy_root()).expanduser().absolute()
    investigation_id = _validated(investigation_id, "investigation_id")
    investigation_digest = _digest(root, "investigation", investigation_id)
    path = root / ".tenancy" / "legacy-stream-leases" / f"{investigation_digest}.json"
    with _registry_lock(root):
        try:
            record = json.loads(_read_regular(path).decode("utf-8"))
        except (RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvestigationOwnershipConflict(
                "investigation ownership binding is invalid"
            ) from exc
        account_digest = record.get("account_digest")
        if (
            record.get("version") != TENANCY_VERSION
            or record.get("investigation_digest") != investigation_digest
            or not isinstance(account_digest, str)
            or len(account_digest) != 64
        ):
            raise InvestigationOwnershipConflict(
                "investigation ownership binding is invalid"
            )
        return account_digest


def assert_legacy_stream_owner(authority: InvestigationAuthority) -> None:
    path = (
        authority.root
        / ".tenancy"
        / "legacy-stream-leases"
        / f"{authority.investigation_digest}.json"
    )
    expected = {
        "version": TENANCY_VERSION,
        "account_digest": authority.account_digest,
        "investigation_digest": authority.investigation_digest,
        "future_stream_key": authority.stream_key,
    }
    with _registry_lock(authority.root):
        if not path.exists() and not path.is_symlink():
            raise InvestigationOwnershipConflict(
                "investigation has no account ownership binding"
            )
        try:
            existing = json.loads(_read_regular(path).decode("utf-8"))
            identity = {key: existing.get(key) for key in expected}
        except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
            raise InvestigationOwnershipConflict(
                "investigation ownership binding is invalid"
            ) from exc
        if identity != expected:
            raise InvestigationOwnershipConflict(
                "investigation belongs to another account or has an invalid binding"
            )


def legacy_lease_storage_state(authority: InvestigationAuthority) -> str:
    """Return the explicit compatibility state; pre-W3 leases imply legacy."""
    path = (
        authority.root
        / ".tenancy"
        / "legacy-stream-leases"
        / f"{authority.investigation_digest}.json"
    )
    assert_legacy_stream_owner(authority)
    with _registry_lock(authority.root):
        try:
            record = json.loads(_read_regular(path).decode("utf-8"))
        except (RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvestigationOwnershipConflict(
                "investigation ownership binding is invalid"
            ) from exc
        state = record.get("storage_state", "legacy")
        if state not in {"legacy", "composite"}:
            raise InvestigationOwnershipConflict(
                "investigation ownership binding is invalid"
            )
        return state


def transition_legacy_lease_storage_state(
    authority: InvestigationAuthority, *, expected: str, desired: str
) -> None:
    """Compare-and-swap the leased stream authority after verified publication."""
    with _registry_lock(authority.root):
        _transition_legacy_lease_storage_state_unlocked(
            authority,
            expected=expected,
            desired=desired,
        )


def _transition_legacy_lease_storage_state_unlocked(
    authority: InvestigationAuthority, *, expected: str, desired: str
) -> None:
    """Perform the lease CAS while the caller holds ``registry.lock``."""
    if expected not in {"legacy", "composite"} or desired not in {
        "legacy",
        "composite",
    }:
        raise ValueError("unsupported legacy lease storage transition")
    if expected == desired:
        raise ValueError("legacy lease storage transition must change state")
    path = (
        authority.root
        / ".tenancy"
        / "legacy-stream-leases"
        / f"{authority.investigation_digest}.json"
    )
    try:
        record = json.loads(_read_regular(path).decode("utf-8"))
    except (RuntimeError, UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
        raise InvestigationOwnershipConflict(
            "investigation ownership binding is invalid"
        ) from exc
    identity = {
        "version": TENANCY_VERSION,
        "account_digest": authority.account_digest,
        "investigation_digest": authority.investigation_digest,
        "future_stream_key": authority.stream_key,
    }
    if not isinstance(record, dict) or any(
        record.get(key) != value for key, value in identity.items()
    ):
        raise InvestigationOwnershipConflict(
            "investigation belongs to another account or has an invalid binding"
        )
    current = record.get("storage_state", "legacy")
    if current != expected:
        raise InvestigationOwnershipConflict(
            "investigation storage state changed during migration"
        )
    record["storage_state"] = desired
    _atomic_write(
        path,
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode(),
    )


def mark_legacy_lease_composite(authority: InvestigationAuthority) -> None:
    """Migration-only compatibility wrapper for the verified final flip."""
    transition_legacy_lease_storage_state(
        authority,
        expected="legacy",
        desired="composite",
    )
