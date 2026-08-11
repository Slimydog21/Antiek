"""Owner-scoped durable registry for BYO data-tool connections.

The sidecar contains no plaintext credentials.  A registry row is only a
binding to an owner-bound v3 record in :mod:`runtime.byok.store`; every list
and resolve revalidates that metadata and its fingerprint without decrypting.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from runtime.byok.store import (
    CredentialMetadata,
    delete_credential,
    list_credentials,
    store_credential_with_metadata,
)
from runtime.connectors.base import (
    ConnectorDescriptor,
    KeyShape,
    RateSpec,
    validate_key_shape,
)

ToolVendor = Literal["youtube", "polygon", "fmp", "edgar"]
CredentialKind = Literal["api_key", "contact"]
ConnectionStatus = Literal["unconfigured", "configured_unverified", "degraded"]

_ENV_PATH = "ANTIEK_TOOL_CONNECTIONS_PATH"
_ENV_HOME = "ANTIEK_HOME"
_MODE = 0o600
_MAX_REGISTRY_BYTES = 1_048_576
_LOCK = threading.RLock()
_EMAIL_SHAPE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_CRED_ID = re.compile(r"^cred-x-[0-9a-f]{16}$")
_RECORD_FIELDS = frozenset(
    {"record_version", "owner_user_id", "vendor", "credential_kind", "cred_id",
     "credential_fingerprint", "account_handle", "updated_at"}
)
_PENDING_KEY = "__pending_deletions__"
_PENDING_FIELDS = frozenset(
    {"cred_id", "owner_user_id", "vendor", "pipeline_kind", "account_handle", "credential_fingerprint"}
)


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    vendor: ToolVendor
    display_name: str
    credential_kind: CredentialKind
    descriptor: ConnectorDescriptor
    quota_kind: Literal["youtube_units", "rate_ceiling", "unavailable"]


@dataclass(frozen=True, slots=True)
class ToolConnectionRecord:
    record_version: int
    owner_user_id: str
    vendor: ToolVendor
    credential_kind: CredentialKind
    cred_id: str
    credential_fingerprint: str
    account_handle: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class PendingDeletion:
    cred_id: str
    owner_user_id: str
    vendor: ToolVendor
    pipeline_kind: str
    account_handle: str
    credential_fingerprint: str


@dataclass(frozen=True, slots=True)
class ToolConnectionSnapshot:
    vendor: ToolVendor
    display_name: str
    credential_kind: CredentialKind
    auth: str
    docs_url: str
    status: ConnectionStatus
    credential_present: bool
    status_note: str | None
    quota_kind: str


class ToolConnectionError(RuntimeError):
    """Value-free base error for registry and resolution failures."""


class ToolConnectionIntegrityError(ToolConnectionError):
    pass


class ToolConnectionUnavailable(ToolConnectionError):
    pass


_CATALOG: dict[ToolVendor, ToolDefinition] = {
    "youtube": ToolDefinition(
        vendor="youtube",
        display_name="YouTube Data API",
        credential_kind="api_key",
        descriptor=ConnectorDescriptor(
            vendor="youtube",
            chassis="paste_key",
            auth="api_key_query",
            key_shape=KeyShape(min_len=20, prefix="AIza"),
            rate=None,
            docs_url="https://console.cloud.google.com/apis/credentials",
        ),
        quota_kind="youtube_units",
    ),
    "polygon": ToolDefinition(
        vendor="polygon",
        display_name="Polygon.io",
        credential_kind="api_key",
        descriptor=ConnectorDescriptor(
            vendor="polygon",
            chassis="paste_key",
            auth="api_key_query",
            key_shape=KeyShape(min_len=10),
            rate=None,
            docs_url="https://polygon.io/docs",
        ),
        quota_kind="unavailable",
    ),
    "fmp": ToolDefinition(
        vendor="fmp",
        display_name="Financial Modeling Prep",
        credential_kind="api_key",
        descriptor=ConnectorDescriptor(
            vendor="fmp",
            chassis="paste_key",
            auth="api_key_query",
            key_shape=KeyShape(min_len=10),
            rate=None,
            docs_url="https://site.financialmodelingprep.com/developer/docs",
        ),
        quota_kind="unavailable",
    ),
    "edgar": ToolDefinition(
        vendor="edgar",
        display_name="SEC EDGAR",
        credential_kind="contact",
        descriptor=ConnectorDescriptor(
            vendor="edgar",
            chassis="paste_key",
            auth="none",
            key_shape=None,
            rate=RateSpec(max_calls=8, window_s=1.0),
            docs_url="https://www.sec.gov/search-filings",
        ),
        quota_kind="rate_ceiling",
    ),
}
_VENDOR_ORDER: tuple[ToolVendor, ...] = ("youtube", "polygon", "fmp", "edgar")


def tool_catalog() -> tuple[ToolDefinition, ...]:
    return tuple(_CATALOG[vendor] for vendor in _VENDOR_ORDER)


def _definition(vendor: str) -> ToolDefinition:
    try:
        return _CATALOG[vendor]  # type: ignore[index]
    except KeyError as exc:
        raise ToolConnectionUnavailable("unsupported tool vendor") from exc


def _path() -> Path:
    configured = os.environ.get(_ENV_PATH)
    if configured:
        return Path(os.path.expanduser(configured))
    home = Path(os.environ.get(_ENV_HOME, os.path.expanduser("~/.antiek")))
    return home / "settings" / "tool_connections.json"


def _fsync_directory(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _ensure_directory(path: Path) -> None:
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for item in reversed(missing):
        item.mkdir(exist_ok=True)
        _fsync_directory(item)
        _fsync_directory(item.parent)


def _secure_fd(fd: int, *, label: str) -> None:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise ToolConnectionIntegrityError(f"{label} must be a regular file")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise ToolConnectionIntegrityError(f"{label} has the wrong owner")
    if stat.S_IMODE(info.st_mode) != _MODE:
        os.fchmod(fd, _MODE)


@contextmanager
def _guard(*, exclusive: bool) -> Iterator[None]:
    lock_path = Path(f"{_path()}.lock")
    _ensure_directory(lock_path.parent)
    with _LOCK:
        fd = os.open(
            str(lock_path),
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            _MODE,
        )
        try:
            _secure_fd(fd, label="tool connection registry lock")
            fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _record_key(owner_user_id: str, vendor: ToolVendor) -> str:
    owner_hash = hashlib.blake2b(owner_user_id.encode(), digest_size=16).hexdigest()
    return f"{owner_hash}:{vendor}"


def _parse_record(key: str, value: object) -> ToolConnectionRecord:
    if not isinstance(value, dict) or set(value) != _RECORD_FIELDS:
        raise ToolConnectionIntegrityError("tool connection registry entry is invalid")
    if type(value["record_version"]) is not int or any(
        not isinstance(value[name], str) for name in _RECORD_FIELDS - {"record_version"}
    ):
        raise ToolConnectionIntegrityError("tool connection registry entry has invalid types")
    record = ToolConnectionRecord(**value)
    definition = _definition(record.vendor)
    try:
        updated = datetime.fromisoformat(record.updated_at)
    except ValueError as exc:
        raise ToolConnectionIntegrityError("tool connection registry timestamp is invalid") from exc
    if (
        record.record_version != 1
        or record.credential_kind != definition.credential_kind
        or key != _record_key(record.owner_user_id, record.vendor)
        or not (1 <= len(record.owner_user_id) <= 256)
        or _CRED_ID.fullmatch(record.cred_id) is None
        or _FINGERPRINT.fullmatch(record.credential_fingerprint) is None
        or not (1 <= len(record.account_handle) <= 256)
        or updated.tzinfo is None
    ):
        raise ToolConnectionIntegrityError("tool connection registry identity is invalid")
    return record


def _parse_pending(value: object) -> PendingDeletion:
    if not isinstance(value, dict) or set(value) != _PENDING_FIELDS or any(
        not isinstance(value[name], str) for name in _PENDING_FIELDS
    ):
        raise ToolConnectionIntegrityError("tool connection pending deletion is invalid")
    item = PendingDeletion(**value)
    _definition(item.vendor)
    if (
        _CRED_ID.fullmatch(item.cred_id) is None
        or not (1 <= len(item.owner_user_id) <= 256)
        or item.pipeline_kind != f"connector_{item.vendor}"
        or not (1 <= len(item.account_handle) <= 256)
        or _FINGERPRINT.fullmatch(item.credential_fingerprint) is None
    ):
        raise ToolConnectionIntegrityError("tool connection pending deletion authority is invalid")
    return item


def _load_unlocked() -> tuple[dict[str, ToolConnectionRecord], list[PendingDeletion]]:
    path = _path()
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return {}, []
    try:
        _secure_fd(fd, label="tool connection registry")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            payload = handle.read(_MAX_REGISTRY_BYTES + 1)
        if len(payload) > _MAX_REGISTRY_BYTES:
            raise ToolConnectionIntegrityError("tool connection registry is too large")
        raw = json.loads(payload)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise ToolConnectionIntegrityError("tool connection registry is unreadable") from exc
    finally:
        os.close(fd)
    if not isinstance(raw, dict):
        raise ToolConnectionIntegrityError("tool connection registry root is invalid")
    pending_raw = raw.pop(_PENDING_KEY, [])
    if not isinstance(pending_raw, list):
        raise ToolConnectionIntegrityError("tool connection pending deletions are invalid")
    pending = [_parse_pending(item) for item in pending_raw]
    if len({item.cred_id for item in pending}) != len(pending):
        raise ToolConnectionIntegrityError("tool connection pending deletions are duplicated")
    return ({str(key): _parse_record(str(key), value) for key, value in raw.items()}, pending)


def _write_unlocked(records: dict[str, ToolConnectionRecord], pending: list[PendingDeletion]) -> None:
    path = _path()
    _ensure_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, _MODE)
    try:
        payload = json.dumps(
            {**{key: asdict(record) for key, record in records.items()},
             _PENDING_KEY: [asdict(item) for item in pending]},
            sort_keys=True,
            indent=2,
        ).encode()
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, _MODE)
        _fsync_directory(path.parent)
    finally:
        os.close(fd)
        with suppress(FileNotFoundError):
            temporary.unlink()


def _recover_pending_unlocked(
    records: dict[str, ToolConnectionRecord], pending: list[PendingDeletion], *, artifact_path: str | None
) -> list[PendingDeletion]:
    if not pending:
        return []
    active_ids = {record.cred_id for record in records.values()}
    metadata = _metadata_by_id(artifact_path=artifact_path)
    remaining: list[PendingDeletion] = []
    for item in pending:
        if item.cred_id in active_ids:
            raise ToolConnectionIntegrityError("pending deletion references an active credential")
        meta = metadata.get(item.cred_id)
        if meta is None:
            continue
        if not _pending_matches(item, meta):
            raise ToolConnectionIntegrityError("pending deletion credential authority changed")
        delete_credential(item.cred_id, artifact_path=artifact_path)
    if pending:
        _write_unlocked(records, remaining)
    return remaining


def _metadata_by_id(*, artifact_path: str | None = None) -> dict[str, CredentialMetadata]:
    return {item.cred_id: item for item in list_credentials(artifact_path=artifact_path)}


def _metadata_matches(record: ToolConnectionRecord, metadata: CredentialMetadata | None) -> bool:
    return bool(
        metadata is not None
        and metadata.binding_version == 3
        and metadata.owner_user_id == record.owner_user_id
        and metadata.pipeline_kind == f"connector_{record.vendor}"
        and metadata.account_handle == record.account_handle
        and metadata.artifact_fingerprint == record.credential_fingerprint
    )


def _pending_for(record: ToolConnectionRecord) -> PendingDeletion:
    return PendingDeletion(
        cred_id=record.cred_id, owner_user_id=record.owner_user_id, vendor=record.vendor,
        pipeline_kind=f"connector_{record.vendor}", account_handle=record.account_handle,
        credential_fingerprint=record.credential_fingerprint,
    )


def _pending_matches(item: PendingDeletion, metadata: CredentialMetadata) -> bool:
    return bool(
        metadata.binding_version == 3 and metadata.cred_id == item.cred_id
        and metadata.owner_user_id == item.owner_user_id
        and metadata.pipeline_kind == item.pipeline_kind
        and metadata.account_handle == item.account_handle
        and metadata.artifact_fingerprint == item.credential_fingerprint
    )


def _validate_value(definition: ToolDefinition, value: str) -> None:
    if definition.credential_kind == "api_key":
        validate_key_shape(definition.descriptor, value)
        return
    if not isinstance(value, str) or len(value) > 320 or not _EMAIL_SHAPE.fullmatch(value):
        raise ValueError("SEC contact must be an email address")


def connect_tool(
    owner_user_id: str,
    vendor: str,
    value: str,
    *,
    artifact_path: str | None = None,
    key_bytes: bytes | None = None,
    key_file: str | None = None,
) -> ToolConnectionSnapshot:
    if not owner_user_id or len(owner_user_id) > 256:
        raise ToolConnectionUnavailable("authenticated owner is required")
    definition = _definition(vendor)
    _validate_value(definition, value)
    account_handle = f"tool-{_record_key(owner_user_id, definition.vendor)}"
    metadata = store_credential_with_metadata(
        account_handle,
        value,
        pipeline_kind=f"connector_{definition.vendor}",
        owner_user_id=owner_user_id,
        artifact_path=artifact_path,
        key_bytes=key_bytes,
        key_file=key_file,
    )
    cred_id = metadata.cred_id
    record = ToolConnectionRecord(
        record_version=1,
        owner_user_id=owner_user_id,
        vendor=definition.vendor,
        credential_kind=definition.credential_kind,
        cred_id=cred_id,
        credential_fingerprint=metadata.artifact_fingerprint,
        account_handle=account_handle,
        updated_at=datetime.now(UTC).isoformat(),
    )
    key = _record_key(owner_user_id, definition.vendor)
    old: ToolConnectionRecord | None = None
    cleanup_old = False
    try:
        with _guard(exclusive=True):
            records, pending = _load_unlocked()
            _recover_pending_unlocked(records, pending, artifact_path=artifact_path)
            old = records.get(key)
            cleanup_old = bool(
                old is not None
                and _metadata_matches(
                    old, _metadata_by_id(artifact_path=artifact_path).get(old.cred_id)
                )
            )
            records[key] = record
            pending = [_pending_for(old)] if old is not None and cleanup_old else []
            _write_unlocked(records, pending)
    except Exception:
        delete_credential(cred_id, artifact_path=artifact_path)
        raise
    if old is not None and cleanup_old:
        delete_credential(old.cred_id, artifact_path=artifact_path)
        with _guard(exclusive=True):
            records, pending = _load_unlocked()
            before = len(pending)
            pending = [item for item in pending if item.cred_id != old.cred_id]
            if len(pending) != before:
                _write_unlocked(records, pending)
    return _snapshot(record, metadata)


def disconnect_tool(
    owner_user_id: str,
    vendor: str,
    *,
    artifact_path: str | None = None,
) -> bool:
    definition = _definition(vendor)
    key = _record_key(owner_user_id, definition.vendor)
    removed: ToolConnectionRecord | None = None
    with _guard(exclusive=True):
        records, pending = _load_unlocked()
        _recover_pending_unlocked(records, pending, artifact_path=artifact_path)
        removed = records.pop(key, None)
        if removed is not None:
            removed_meta = _metadata_by_id(artifact_path=artifact_path).get(removed.cred_id)
            if _metadata_matches(removed, removed_meta):
                pending.append(_pending_for(removed))
            _write_unlocked(records, pending)
    if removed is None:
        return False
    metadata = _metadata_by_id(artifact_path=artifact_path).get(removed.cred_id)
    cleanup_removed = _metadata_matches(removed, metadata)
    if cleanup_removed:
        delete_credential(removed.cred_id, artifact_path=artifact_path)
    with _guard(exclusive=True):
        records, pending = _load_unlocked()
        before = len(pending)
        pending = [item for item in pending if item.cred_id != removed.cred_id]
        if len(pending) != before:
            _write_unlocked(records, pending)
    return True


def _snapshot(
    record: ToolConnectionRecord | None,
    metadata: CredentialMetadata | None,
    *,
    definition: ToolDefinition | None = None,
) -> ToolConnectionSnapshot:
    item = definition or _definition(record.vendor if record else "")
    present = record is not None and _metadata_matches(record, metadata)
    return ToolConnectionSnapshot(
        vendor=item.vendor,
        display_name=item.display_name,
        credential_kind=item.credential_kind,
        auth=item.descriptor.auth,
        docs_url=item.descriptor.docs_url,
        status="configured_unverified" if present else ("degraded" if record else "unconfigured"),
        credential_present=present,
        status_note=(
            None
            if present
            else "Stored credential metadata is unavailable" if record else None
        ),
        quota_kind=item.quota_kind,
    )


def list_tool_connections(
    owner_user_id: str,
    *,
    artifact_path: str | None = None,
) -> tuple[ToolConnectionSnapshot, ...]:
    with _guard(exclusive=True):
        records, pending = _load_unlocked()
        _recover_pending_unlocked(records, pending, artifact_path=artifact_path)
    metadata = _metadata_by_id(artifact_path=artifact_path)
    out: list[ToolConnectionSnapshot] = []
    for definition in tool_catalog():
        record = records.get(_record_key(owner_user_id, definition.vendor))
        out.append(
            _snapshot(
                record,
                metadata.get(record.cred_id) if record else None,
                definition=definition,
            )
        )
    return tuple(out)


def resolve_tool_connection(
    owner_user_id: str,
    vendor: str,
    *,
    artifact_path: str | None = None,
    key_bytes: bytes | None = None,
    key_file: str | None = None,
    **connector_kwargs: Any,
) -> Any:
    definition = _definition(vendor)
    with _guard(exclusive=False):
        records, _pending = _load_unlocked()
        record = records.get(_record_key(owner_user_id, definition.vendor))
    if record is None:
        raise ToolConnectionUnavailable("tool is not configured")
    metadata = _metadata_by_id(artifact_path=artifact_path).get(record.cred_id)
    if not _metadata_matches(record, metadata):
        raise ToolConnectionUnavailable("tool credential binding is unavailable")
    if definition.vendor == "edgar":
        from acquisition.edgar.client import EdgarConnector

        return EdgarConnector(
            contact_cred_id=record.cred_id,
            artifact_path=artifact_path,
            key_bytes=key_bytes,
            key_file=key_file,
            **connector_kwargs,
        )
    connector_types: dict[str, tuple[str, str]] = {
        "youtube": ("acquisition.youtube.data_api", "YouTubeConnector"),
        "polygon": ("acquisition.polygon.client", "PolygonConnector"),
        "fmp": ("acquisition.fmp.client", "FmpConnector"),
    }
    module_name, class_name = connector_types[definition.vendor]
    from importlib import import_module

    connector_type = getattr(import_module(module_name), class_name)
    return connector_type(
        cred_id=record.cred_id,
        artifact_path=artifact_path,
        key_bytes=key_bytes,
        key_file=key_file,
        **connector_kwargs,
    )


__all__ = [
    "ConnectionStatus",
    "CredentialKind",
    "ToolConnectionError",
    "ToolConnectionIntegrityError",
    "ToolConnectionSnapshot",
    "ToolConnectionUnavailable",
    "ToolDefinition",
    "ToolVendor",
    "connect_tool",
    "disconnect_tool",
    "list_tool_connections",
    "resolve_tool_connection",
    "tool_catalog",
]
