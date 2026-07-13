"""Quarantined encrypted storage for owner-private source bundles.

The store is deliberately single-owner and has no production composition,
creation/head signer, generic decrypt/get/list API, provider execution,
checkpoint, or sink authority.
"""

from __future__ import annotations

import ast
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, closing
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Never, Protocol, SupportsIndex

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_source_authority import (
    OwnerPrivateEncryptedSourceBundleV1,
    build_owner_private_source_vault_contract_v1,
    validate_owner_private_encrypted_source_bundle_v1,
)
from .private_source_head_store import (
    _CURRENT_DDL,
    _HEADS_DDL,
    MAX_OWNER_PRIVATE_SOURCE_HEAD_AGE_MS,
    PRIVATE_SOURCE_HEAD_STORE_MODULE_SOURCE_SHA256,
    OwnerPrivateSourceAuthorityHeadV1,
    _SourceHeadRepositoryV1,
)

MAX_PENDING_SELECTORS = 64
PENDING_SELECTOR_TTL_MS = 300_000
SELECTOR_COLLISION_RETRIES = 8
NONCE_COLLISION_RETRIES = 8
MAX_SOURCE_BUNDLE_PLAINTEXT_BYTES = 67_108_864
MAX_SOURCE_BUNDLE_CIPHERTEXT_BYTES = 67_108_880
MAX_SOURCE_RECEIPT_PAIRS = 8
SOURCE_WITNESS_TTL_MS = 30_000
MAX_SOURCE_KEY_VERSION_BYTES = 71
MAX_SOURCE_STORE_DB_BYTES = 4_294_967_296

_SOURCE_AEAD_DOMAIN = b"antiek.midnight-oil.owner-private-source-aead.v1\x00"
_PENDING_DOMAIN = b"antiek.midnight-oil.owner-private-source-pending-selector.v1\x00"
_WITNESS_DOMAIN = b"antiek.midnight-oil.owner-private-source-resolution-witness.v1\x00"
_RESOLVER_CONTRACT_DOMAIN = (
    b"antiek.midnight-oil.owner-private-source-exact-current-resolver.v1\x00"
)
_RESOLVER_CONTRACT_MATERIAL = {
    "schema_version": 1,
    "operation": "resolve_exact_current",
    "inputs": [
        "owner_path_authority",
        "opaque_source_bundle_id",
        "expected_current_head_sha256",
        "expected_row_revision",
        "expected_receipt_pairs",
        "now_ms",
        "required_until_ms",
    ],
    "current_head_read": "full_chain_to_external_floor_then_final_reread",
    "lookup": "exact_selector_head_revision_and_bounded_receipt_pairs",
    "max_receipt_pairs": MAX_SOURCE_RECEIPT_PAIRS,
    "witness_ttl_ms": SOURCE_WITNESS_TTL_MS,
    "head_store_semantic_source_sha256": PRIVATE_SOURCE_HEAD_STORE_MODULE_SOURCE_SHA256,
    "vault_contract_sha256": build_owner_private_source_vault_contract_v1().contract_sha256,
    "witness_mac_domain": _WITNESS_DOMAIN.decode("ascii"),
    "bundle_semantic_source_binding": "external_nonrecursive_module_attestation",
    "witness_fields": [
        "witness_handle",
        "opaque_source_bundle_id",
        "row_revision",
        "registry_id",
        "current_head_sha256",
        "current_epoch",
        "checked_at_ms",
        "expires_at_ms",
        "resolver_contract_sha256",
        "exact_match",
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ],
    "process_local_nonportable": True,
    "confers_execution_authority": False,
    "confers_checkpoint_authority": False,
    "confers_sink_authority": False,
    "confers_transition_authority": False,
    "production_consumer_enabled": False,
}
OWNER_PRIVATE_SOURCE_EXACT_CURRENT_RESOLVER_CONTRACT_SHA256 = hashlib.sha256(
    _RESOLVER_CONTRACT_DOMAIN
    + json.dumps(
        _RESOLVER_CONTRACT_MATERIAL,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
).hexdigest()
_HEX64 = re.compile(r"[0-9a-f]{64}")
_OWNER_PATH = re.compile(r"opspd1_[0-9a-f]{64}")
_REGISTRY_ID = re.compile(r"opsreg1_[0-9a-f]{64}")
_SELECTOR = re.compile(r"opsbs1_[0-9a-f]{64}")
_KEY_VERSION = re.compile(r"opskv1_[A-Za-z0-9._-]{1,64}")

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS owner_private_source_schema (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1)
)
"""
_BUNDLES_DDL = """
CREATE TABLE IF NOT EXISTS owner_private_encrypted_source_bundles (
    opaque_source_bundle_id TEXT PRIMARY KEY,
    owner_path_discriminator TEXT NOT NULL,
    categorical_state TEXT NOT NULL CHECK (categorical_state = 'sealed'),
    aead_suite TEXT NOT NULL CHECK (aead_suite = 'aes-256-gcm'),
    key_version TEXT NOT NULL,
    nonce_length INTEGER NOT NULL CHECK (nonce_length = 12),
    nonce BLOB NOT NULL CHECK (length(nonce) = 12),
    ciphertext_schema TEXT NOT NULL
        CHECK (ciphertext_schema = 'owner_private_encrypted_source_bundle_v1_json'),
    ciphertext_type TEXT NOT NULL CHECK (ciphertext_type = 'application/json'),
    ciphertext_length INTEGER NOT NULL
        CHECK (ciphertext_length >= 16 AND ciphertext_length <= 67108880),
    row_revision INTEGER NOT NULL CHECK (row_revision = 1),
    ciphertext BLOB NOT NULL,
    CHECK (ciphertext_length = length(ciphertext)),
    UNIQUE (owner_path_discriminator, key_version, nonce)
)
"""

_EXPECTED_TABLES = {
    "owner_private_source_schema",
    "owner_private_encrypted_source_bundles",
    "owner_private_source_authority_heads",
    "owner_private_source_authority_current",
}


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]


class OwnerPrivateSourceStoreRejected(ValueError):
    def __init__(self) -> None:
        super().__init__("owner-private source store operation rejected")

    def __repr__(self) -> str:
        return "OwnerPrivateSourceStoreRejected()"


class SourceHeadAdmissionResultV1(_Closed):
    applied: bool
    registry_id: str = Field(pattern=r"^opsreg1_[0-9a-f]{64}$")
    current_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_epoch: int = Field(ge=0)
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class SourceBundleAdmissionResultV1(_Closed):
    applied: bool
    replayed: bool
    opaque_source_bundle_id: str = Field(pattern=r"^opsbs1_[0-9a-f]{64}$")
    row_revision: Literal[1] = 1
    current_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_epoch: int = Field(ge=0)
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _categorical(self) -> SourceBundleAdmissionResultV1:
        if self.applied == self.replayed:
            raise ValueError("source bundle admission result conflicts")
        return self


class OwnerPrivateSourceKeyProviderV1(Protocol):
    def open_aes256gcm_key(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        key_version: str,
    ) -> AbstractContextManager[bytearray]: ...


_PRIVATE_CONSTRUCTOR = object()


class PendingOpaqueSourceSelectorV1:
    __slots__ = (
        "_authority_identity",
        "_authority_object",
        "_base_epoch",
        "_base_head",
        "_boot_nonce",
        "_created_at_ms",
        "_expires_at_ms",
        "_handle_id",
        "_mac",
        "_owner_path",
        "_pid",
        "_selector",
        "_sealed",
    )

    def __init__(
        self,
        token: object,
        *,
        handle_id: str,
        selector: str,
        owner_path: str,
        base_head: str,
        base_epoch: int,
        created_at_ms: int,
        expires_at_ms: int,
        pid: int,
        boot_nonce: bytes,
        authority_identity: int,
        authority_object: object,
        mac: bytes,
    ) -> None:
        if token is not _PRIVATE_CONSTRUCTOR:
            raise TypeError("pending source selector is store-created")
        object.__setattr__(self, "_sealed", False)
        self._handle_id = handle_id
        self._selector = selector
        self._owner_path = owner_path
        self._base_head = base_head
        self._base_epoch = base_epoch
        self._created_at_ms = created_at_ms
        self._expires_at_ms = expires_at_ms
        self._pid = pid
        self._boot_nonce = boot_nonce
        self._authority_identity = authority_identity
        self._authority_object = authority_object
        self._mac = mac

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("pending source selector is immutable")
        object.__setattr__(self, name, value)

    @property
    def opaque_source_bundle_id(self) -> str:
        return self._selector

    @property
    def expected_current_head_sha256(self) -> str:
        return self._base_head

    @property
    def expected_current_epoch(self) -> int:
        return self._base_epoch

    @property
    def expires_at_ms(self) -> int:
        return self._expires_at_ms

    def __repr__(self) -> str:
        return "PendingOpaqueSourceSelectorV1(redacted=True)"

    def __reduce__(self) -> Never:
        raise TypeError("pending source selector is process-local")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        raise TypeError("pending source selector is process-local")

    def __copy__(self) -> Never:
        raise TypeError("pending source selector is process-local")

    def __deepcopy__(self, memo: object) -> Never:
        raise TypeError("pending source selector is process-local")


class OwnerPrivateSourceResolutionWitnessV1:
    __slots__ = (
        "_checked_at_ms",
        "_current_epoch",
        "_current_head",
        "_expires_at_ms",
        "_handle",
        "_mac",
        "_registry_id",
        "_revision",
        "_selector",
        "_sealed",
    )

    def __init__(
        self,
        token: object,
        *,
        handle: str,
        selector: str,
        revision: int,
        registry_id: str,
        current_head: str,
        current_epoch: int,
        checked_at_ms: int,
        expires_at_ms: int,
        mac: bytes,
    ) -> None:
        if token is not _PRIVATE_CONSTRUCTOR:
            raise TypeError("source witness is store-created")
        object.__setattr__(self, "_sealed", False)
        self._handle = handle
        self._selector = selector
        self._revision = revision
        self._registry_id = registry_id
        self._current_head = current_head
        self._current_epoch = current_epoch
        self._checked_at_ms = checked_at_ms
        self._expires_at_ms = expires_at_ms
        self._mac = mac
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("source witness is immutable")
        object.__setattr__(self, name, value)

    @property
    def witness_handle(self) -> str:
        return self._handle

    @property
    def opaque_source_bundle_id(self) -> str:
        return self._selector

    @property
    def row_revision(self) -> int:
        return self._revision

    @property
    def registry_id(self) -> str:
        return self._registry_id

    @property
    def current_head_sha256(self) -> str:
        return self._current_head

    @property
    def current_epoch(self) -> int:
        return self._current_epoch

    @property
    def checked_at_ms(self) -> int:
        return self._checked_at_ms

    @property
    def expires_at_ms(self) -> int:
        return self._expires_at_ms

    @property
    def resolver_contract_sha256(self) -> str:
        return OWNER_PRIVATE_SOURCE_EXACT_CURRENT_RESOLVER_CONTRACT_SHA256

    @property
    def exact_match(self) -> Literal[True]:
        return True

    @property
    def confers_execution_authority(self) -> Literal[False]:
        return False

    @property
    def confers_checkpoint_authority(self) -> Literal[False]:
        return False

    @property
    def confers_sink_authority(self) -> Literal[False]:
        return False

    @property
    def confers_transition_authority(self) -> Literal[False]:
        return False

    @property
    def production_consumer_enabled(self) -> Literal[False]:
        return False

    def __repr__(self) -> str:
        return "OwnerPrivateSourceResolutionWitnessV1(redacted=True)"

    def __reduce__(self) -> Never:
        raise TypeError("source witness is process-local")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        raise TypeError("source witness is process-local")

    def __copy__(self) -> Never:
        raise TypeError("source witness is process-local")

    def __deepcopy__(self, memo: object) -> Never:
        raise TypeError("source witness is process-local")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _compact_sql(value: str) -> str:
    return "".join(value.lower().split()).replace("ifnotexists", "")


def _valid_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool) and value >= 0


def _pending_material(pending: PendingOpaqueSourceSelectorV1) -> bytes:
    return _canonical_json(
        {
            "authority_identity": pending._authority_identity,
            "base_epoch": pending._base_epoch,
            "base_head": pending._base_head,
            "boot_nonce": pending._boot_nonce.hex(),
            "created_at_ms": pending._created_at_ms,
            "expires_at_ms": pending._expires_at_ms,
            "handle_id": pending._handle_id,
            "owner_path": pending._owner_path,
            "pid": pending._pid,
            "selector": pending._selector,
        }
    )


def _bundle_plaintext(bundle: OwnerPrivateEncryptedSourceBundleV1) -> bytes:
    raw = bundle.model_dump_json().encode("utf-8")
    if not raw or len(raw) > MAX_SOURCE_BUNDLE_PLAINTEXT_BYTES:
        raise ValueError
    return raw


def _parse_bundle_plaintext(value: bytes) -> OwnerPrivateEncryptedSourceBundleV1:
    if type(value) is not bytes or not value or len(value) > MAX_SOURCE_BUNDLE_PLAINTEXT_BYTES:
        raise ValueError

    def reject_duplicates(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in items:
            if key in result:
                raise ValueError
            result[key] = item
        return result

    json.loads(value.decode("utf-8"), object_pairs_hook=reject_duplicates)
    bundle = OwnerPrivateEncryptedSourceBundleV1.model_validate_json(value)
    if not hmac.compare_digest(bundle.model_dump_json().encode("utf-8"), value):
        raise ValueError
    return bundle


def _aad(metadata: Mapping[str, object]) -> bytes:
    contract = build_owner_private_source_vault_contract_v1()
    if tuple(metadata) != contract.aad_fields:
        raise ValueError
    return _SOURCE_AEAD_DOMAIN + _canonical_json(dict(metadata))


def _row_metadata(
    *,
    selector: str,
    owner_path: str,
    key_version: str,
    ciphertext_length: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "opaque_source_bundle_id": selector,
        "owner_path_discriminator": owner_path,
        "categorical_state": "sealed",
        "aead_suite": "aes-256-gcm",
        "key_version": key_version,
        "nonce_length": 12,
        "ciphertext_schema": "owner_private_encrypted_source_bundle_v1_json",
        "ciphertext_type": "application/json",
        "ciphertext_length": ciphertext_length,
        "row_revision": 1,
    }


_ROW_SELECT = (
    "SELECT opaque_source_bundle_id, owner_path_discriminator, categorical_state, "
    "aead_suite, key_version, nonce_length, nonce, ciphertext_schema, "
    "ciphertext_type, ciphertext_length, row_revision, ciphertext "
    "FROM owner_private_encrypted_source_bundles WHERE opaque_source_bundle_id = ?"
)


class OwnerPrivateEncryptedSourceBundleStoreV1:
    """One owner-scoped SQLite authority root; no production consumer imports it."""

    __slots__ = (
        "_anchor_keys",
        "_boot_nonce",
        "_head_repository",
        "_key_provider",
        "_pending",
        "_pending_key",
        "_pending_lock",
        "_pid",
        "_sealed",
        "_witness_key",
        "owner_path_discriminator",
        "path",
        "registry_id",
        "trusted_floor_sha256",
    )

    def __init__(
        self,
        path: str | Path,
        *,
        owner_path_discriminator: str,
        registry_id: str,
        trusted_floor_sha256: str,
        creation_anchor_verification_keys: Mapping[str, bytes],
        source_head_verification_keys: Mapping[str, bytes],
        key_provider: OwnerPrivateSourceKeyProviderV1,
    ) -> None:
        object.__setattr__(self, "_sealed", False)
        try:
            if (
                type(owner_path_discriminator) is not str
                or _OWNER_PATH.fullmatch(owner_path_discriminator) is None
                or type(registry_id) is not str
                or _REGISTRY_ID.fullmatch(registry_id) is None
                or type(trusted_floor_sha256) is not str
                or _HEX64.fullmatch(trusted_floor_sha256) is None
            ):
                raise ValueError
            anchor_keys = MappingProxyType(
                self._copy_keyring(creation_anchor_verification_keys)
            )
            head_repository = _SourceHeadRepositoryV1(
                owner_path_discriminator=owner_path_discriminator,
                registry_id=registry_id,
                verification_keys=source_head_verification_keys,
                trusted_floor_sha256=trusted_floor_sha256,
            )
            if set(anchor_keys).intersection(
                head_repository.verification_keys
            ) or set(anchor_keys.values()).intersection(
                head_repository.verification_keys.values()
            ):
                raise ValueError
            self.owner_path_discriminator = owner_path_discriminator
            self.registry_id = registry_id
            self.trusted_floor_sha256 = trusted_floor_sha256
            self._anchor_keys = anchor_keys
            self._head_repository = head_repository
            self._key_provider = key_provider
            self._pending_key = secrets.token_bytes(32)
            self._witness_key = secrets.token_bytes(32)
            self._boot_nonce = secrets.token_bytes(32)
            self._pid = os.getpid()
            self._pending: dict[str, PendingOpaqueSourceSelectorV1] = {}
            self._pending_lock = threading.RLock()
            self._configure_path(path)
            self._initialize_schema()
            object.__setattr__(self, "_sealed", True)
        except Exception:
            raise OwnerPrivateSourceStoreRejected() from None

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("source bundle store is immutable")
        object.__setattr__(self, name, value)

    @staticmethod
    def _copy_keyring(value: Mapping[str, bytes]) -> dict[str, bytes]:
        copied: dict[str, bytes] = {}
        try:
            for index, (key_id, key) in enumerate(value.items()):
                if (
                    index >= 64
                    or type(key_id) is not str
                    or re.fullmatch(r"[A-Za-z0-9._-]{1,128}", key_id) is None
                    or type(key) is not bytes
                    or len(key) != 32
                    or key_id in copied
                    or key in copied.values()
                ):
                    raise ValueError
                copied[key_id] = bytes(key)
        except Exception:
            raise OwnerPrivateSourceStoreRejected() from None
        return copied

    def _configure_path(self, path: str | Path) -> None:
        if type(path) not in {str, type(Path())}:
            raise OwnerPrivateSourceStoreRejected() from None
        raw = os.fspath(path)
        if not raw.strip() or raw == ":memory:":
            raise OwnerPrivateSourceStoreRejected() from None
        supplied = Path(raw).absolute()
        for component in (supplied, *supplied.parents):
            if component.is_symlink():
                raise OwnerPrivateSourceStoreRejected() from None
        canonical = supplied.resolve(strict=False)
        canonical.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if canonical.parent.is_symlink() or canonical.parent.stat().st_mode & 0o077:
            raise OwnerPrivateSourceStoreRejected() from None
        if canonical.exists() and canonical.stat().st_nlink != 1:
            raise OwnerPrivateSourceStoreRejected() from None
        self.path = canonical

    def _connect(self, *, validate_schema: bool = True) -> sqlite3.Connection:
        self._validate_durable_path(require_exists=validate_schema)
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute("PRAGMA page_size=4096")
            connection.execute("PRAGMA max_page_count=1048576")
            self._chmod_sidecars()
            if validate_schema:
                self._validate_schema(connection)
            return connection
        except Exception:
            connection.close()
            raise

    def _validate_durable_path(self, *, require_exists: bool) -> None:
        symlinked_component = any(
            component.is_symlink() for component in (self.path, *self.path.parents)
        )
        if (
            (require_exists and not self.path.is_file())
            or symlinked_component
            or self.path.parent.stat().st_mode & 0o077
            or (self.path.exists() and self.path.stat().st_mode & 0o077)
            or (self.path.exists() and self.path.stat().st_nlink != 1)
        ):
            raise OwnerPrivateSourceStoreRejected() from None

    def _chmod_sidecars(self) -> None:
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(self.path) + suffix)
            if sidecar.exists():
                os.chmod(sidecar, 0o600)

    def _initialize_schema(self) -> None:
        existing = self.path.exists() and self.path.stat().st_size > 0
        with closing(self._connect(validate_schema=False)) as connection:
            if existing:
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                }
                if tables != _EXPECTED_TABLES:
                    raise OwnerPrivateSourceStoreRejected() from None
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(_SCHEMA_DDL)
                connection.execute(_BUNDLES_DDL)
                connection.execute(_HEADS_DDL)
                connection.execute(_CURRENT_DDL)
                connection.execute(
                    "INSERT OR IGNORE INTO owner_private_source_schema "
                    "(singleton, schema_version) VALUES (1, 1)"
                )
                self._validate_schema(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        os.chmod(self.path, 0o600)
        self._chmod_sidecars()

    def _validate_schema(self, connection: sqlite3.Connection) -> None:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        views = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('view','trigger')"
        ).fetchone()
        singleton = connection.execute(
            "SELECT singleton, schema_version FROM owner_private_source_schema"
        ).fetchall()
        if tables != _EXPECTED_TABLES or views != (0,) or singleton != [(1, 1)]:
            raise OwnerPrivateSourceStoreRejected() from None
        expected_columns = {
            "owner_private_source_schema": (
                ("singleton", "INTEGER", 0, 1),
                ("schema_version", "INTEGER", 1, 0),
            ),
            "owner_private_encrypted_source_bundles": (
                ("opaque_source_bundle_id", "TEXT", 0, 1),
                ("owner_path_discriminator", "TEXT", 1, 0),
                ("categorical_state", "TEXT", 1, 0),
                ("aead_suite", "TEXT", 1, 0),
                ("key_version", "TEXT", 1, 0),
                ("nonce_length", "INTEGER", 1, 0),
                ("nonce", "BLOB", 1, 0),
                ("ciphertext_schema", "TEXT", 1, 0),
                ("ciphertext_type", "TEXT", 1, 0),
                ("ciphertext_length", "INTEGER", 1, 0),
                ("row_revision", "INTEGER", 1, 0),
                ("ciphertext", "BLOB", 1, 0),
            ),
            "owner_private_source_authority_heads": (
                ("head_sha256", "TEXT", 0, 1),
                ("registry_id", "TEXT", 1, 0),
                ("owner_path_discriminator", "TEXT", 1, 0),
                ("epoch", "INTEGER", 1, 0),
                ("previous_head_sha256", "TEXT", 1, 0),
                ("issued_at_ms", "INTEGER", 1, 0),
                ("document_json", "TEXT", 1, 0),
            ),
            "owner_private_source_authority_current": (
                ("registry_id", "TEXT", 0, 1),
                ("owner_path_discriminator", "TEXT", 1, 0),
                ("head_sha256", "TEXT", 1, 0),
            ),
        }
        for table, expected_column_rows in expected_columns.items():
            actual_columns = tuple(
                (str(row[1]), str(row[2]).upper(), int(row[3]), int(row[5]))
                for row in connection.execute(f"PRAGMA table_info('{table}')").fetchall()
            )
            if actual_columns != expected_column_rows:
                raise OwnerPrivateSourceStoreRejected() from None
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list('owner_private_source_authority_current')"
        ).fetchall()
        if len(foreign_keys) != 1 or (
            str(foreign_keys[0][2]),
            str(foreign_keys[0][3]),
            str(foreign_keys[0][4]),
        ) != (
            "owner_private_source_authority_heads",
            "head_sha256",
            "head_sha256",
        ):
            raise OwnerPrivateSourceStoreRejected() from None
        expected_unique = {
            "owner_private_encrypted_source_bundles": {
                ("opaque_source_bundle_id",),
                ("owner_path_discriminator", "key_version", "nonce"),
            },
            "owner_private_source_authority_heads": {
                ("head_sha256",),
                ("epoch",),
            },
            "owner_private_source_authority_current": {
                ("registry_id",),
                ("owner_path_discriminator",),
            },
        }
        for table, expected_indexes in expected_unique.items():
            actual_unique = {
                tuple(
                    str(column[2])
                    for column in connection.execute(
                        f"PRAGMA index_info('{str(index[1])}')"
                    ).fetchall()
                )
                for index in connection.execute(f"PRAGMA index_list('{table}')").fetchall()
                if int(index[2]) == 1
            }
            if actual_unique != expected_indexes:
                raise OwnerPrivateSourceStoreRejected() from None
        custom_indexes = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
        ).fetchone()
        if custom_indexes != (0,):
            raise OwnerPrivateSourceStoreRejected() from None
        expected_sql = {
            "owner_private_source_schema": _SCHEMA_DDL,
            "owner_private_encrypted_source_bundles": _BUNDLES_DDL,
            "owner_private_source_authority_heads": _HEADS_DDL,
            "owner_private_source_authority_current": _CURRENT_DDL,
        }
        for table, ddl in expected_sql.items():
            stored = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if (
                stored is None
                or type(stored[0]) is not str
                or _compact_sql(stored[0]) != _compact_sql(ddl)
            ):
                raise OwnerPrivateSourceStoreRejected() from None
        settings = {
            "busy_timeout": int(connection.execute("PRAGMA busy_timeout").fetchone()[0]),
            "foreign_keys": int(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
            "journal_mode_wal": int(
                str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
            ),
            "page_size": int(connection.execute("PRAGMA page_size").fetchone()[0]),
            "max_page_count": int(connection.execute("PRAGMA max_page_count").fetchone()[0]),
            "synchronous": int(connection.execute("PRAGMA synchronous").fetchone()[0]),
            "temp_store": int(connection.execute("PRAGMA temp_store").fetchone()[0]),
        }
        if settings != {
            "busy_timeout": 30_000,
            "foreign_keys": 1,
            "journal_mode_wal": 1,
            "page_size": 4096,
            "max_page_count": 1_048_576,
            "synchronous": 2,
            "temp_store": 2,
        }:
            raise OwnerPrivateSourceStoreRejected() from None

    def admit_trusted_floor(
        self, *, head: OwnerPrivateSourceAuthorityHeadV1, now_ms: int
    ) -> SourceHeadAdmissionResultV1:
        try:
            if not _valid_int(now_ms):
                raise ValueError
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    before = connection.execute(
                        "SELECT COUNT(*) FROM owner_private_source_authority_current"
                    ).fetchone()
                    bundle_count = connection.execute(
                        "SELECT COUNT(*) FROM owner_private_encrypted_source_bundles"
                    ).fetchone()
                    if before == (0,) and bundle_count != (0,):
                        raise ValueError
                    self._head_repository.admit_trusted_floor(connection, head)
                    current = self._head_repository.load_current_to_floor(
                        connection, now_ms=now_ms
                    )[0]
                    if not hmac.compare_digest(current.head_sha256, head.head_sha256):
                        raise ValueError
                    self._require_rows_match_head(connection, current)
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            return SourceHeadAdmissionResultV1(
                applied=before == (0,),
                registry_id=self.registry_id,
                current_head_sha256=current.head_sha256,
                current_epoch=current.epoch,
            )
        except Exception:
            raise OwnerPrivateSourceStoreRejected() from None

    def mint_pending_selector(
        self,
        *,
        owner_path_authority: object,
        expected_current_head_sha256: str,
        expected_current_epoch: int,
        now_ms: int,
    ) -> PendingOpaqueSourceSelectorV1:
        try:
            if (
                type(expected_current_head_sha256) is not str
                or _HEX64.fullmatch(expected_current_head_sha256) is None
                or not _valid_int(expected_current_epoch)
                or not _valid_int(now_ms)
            ):
                raise ValueError
            with closing(self._connect()) as connection:
                connection.execute("BEGIN")
                try:
                    current = self._head_repository.load_current_to_floor(
                        connection, now_ms=now_ms
                    )[0]
                    self._require_rows_match_head(connection, current)
                    if (
                        not hmac.compare_digest(current.head_sha256, expected_current_head_sha256)
                        or current.epoch != expected_current_epoch
                    ):
                        raise ValueError
                    stored = {
                        str(row[0])
                        for row in connection.execute(
                            "SELECT opaque_source_bundle_id "
                            "FROM owner_private_encrypted_source_bundles"
                        ).fetchall()
                    }
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            with self._pending_lock:
                self._purge_pending(now_ms)
                if len(self._pending) >= MAX_PENDING_SELECTORS:
                    raise ValueError
                for _ in range(SELECTOR_COLLISION_RETRIES):
                    handle = "opsph1_" + secrets.token_hex(32)
                    selector = "opsbs1_" + secrets.token_hex(32)
                    pending_selectors = {item._selector for item in self._pending.values()}
                    if (
                        handle not in self._pending
                        and selector not in pending_selectors
                        and selector not in stored
                    ):
                        break
                else:
                    raise ValueError
                pending = PendingOpaqueSourceSelectorV1(
                    _PRIVATE_CONSTRUCTOR,
                    handle_id=handle,
                    selector=selector,
                    owner_path=self.owner_path_discriminator,
                    base_head=current.head_sha256,
                    base_epoch=current.epoch,
                    created_at_ms=now_ms,
                    expires_at_ms=now_ms + PENDING_SELECTOR_TTL_MS,
                    pid=self._pid,
                    boot_nonce=self._boot_nonce,
                    authority_identity=id(owner_path_authority),
                    authority_object=owner_path_authority,
                    mac=b"",
                )
                pending._mac = hmac.digest(
                    self._pending_key,
                    _PENDING_DOMAIN + _pending_material(pending),
                    "sha256",
                )
                object.__setattr__(pending, "_sealed", True)
                self._pending[handle] = pending
                return pending
        except Exception:
            raise OwnerPrivateSourceStoreRejected() from None

    def _purge_pending(self, now_ms: int) -> None:
        expired = [
            key for key, pending in self._pending.items() if pending._expires_at_ms <= now_ms
        ]
        for key in expired:
            del self._pending[key]

    def _consume_pending(
        self,
        pending: PendingOpaqueSourceSelectorV1,
        *,
        owner_path_authority: object,
        expected_head_sha256: str,
        now_ms: int,
    ) -> None:
        with self._pending_lock:
            self._purge_pending(now_ms)
            if type(pending) is not PendingOpaqueSourceSelectorV1:
                raise ValueError
            stored = self._pending.get(pending._handle_id)
            expected_mac = hmac.digest(
                self._pending_key,
                _PENDING_DOMAIN + _pending_material(pending),
                "sha256",
            )
            if (
                stored is not pending
                or pending._pid != os.getpid()
                or pending._pid != self._pid
                or pending._boot_nonce != self._boot_nonce
                or pending._owner_path != self.owner_path_discriminator
                or pending._authority_identity != id(owner_path_authority)
                or pending._authority_object is not owner_path_authority
                or pending._expires_at_ms <= now_ms
                or not hmac.compare_digest(pending._base_head, expected_head_sha256)
                or not hmac.compare_digest(pending._mac, expected_mac)
            ):
                raise ValueError
            del self._pending[pending._handle_id]

    def _open_key(
        self, *, owner_path_authority: object, key_version: str
    ) -> AbstractContextManager[bytearray]:
        if (
            type(key_version) is not str
            or _KEY_VERSION.fullmatch(key_version) is None
            or len(key_version.encode("ascii")) > MAX_SOURCE_KEY_VERSION_BYTES
        ):
            raise ValueError
        return self._key_provider.open_aes256gcm_key(
            owner_path_authority=owner_path_authority,
            owner_path_discriminator=self.owner_path_discriminator,
            key_version=key_version,
        )

    def _nonce_candidates(self) -> tuple[bytes, ...]:
        return tuple(secrets.token_bytes(12) for _ in range(NONCE_COLLISION_RETRIES))

    def seal_bundle_current(
        self,
        *,
        owner_path_authority: object,
        pending_selector: PendingOpaqueSourceSelectorV1,
        bundle: OwnerPrivateEncryptedSourceBundleV1,
        expected_current_head_sha256: str,
        expected_absent_row_revision: int,
        next_head: OwnerPrivateSourceAuthorityHeadV1,
        key_version: str,
        now_ms: int,
    ) -> SourceBundleAdmissionResultV1:
        try:
            if (
                type(expected_absent_row_revision) is not int
                or isinstance(expected_absent_row_revision, bool)
                or expected_absent_row_revision != 0
                or not _valid_int(now_ms)
            ):
                raise ValueError
            self._consume_pending(
                pending_selector,
                owner_path_authority=owner_path_authority,
                expected_head_sha256=expected_current_head_sha256,
                now_ms=now_ms,
            )
            validate_owner_private_encrypted_source_bundle_v1(
                bundle, anchor_verification_keys=self._anchor_keys
            )
            selector = pending_selector.opaque_source_bundle_id
            if next_head.epoch != pending_selector.expected_current_epoch + 1 or not any(
                row.opaque_source_bundle_id == selector
                for row in next_head.snapshot.active_bundle_revisions
            ):
                raise ValueError
            plaintext = _bundle_plaintext(bundle)
            ciphertext_length = len(plaintext) + 16
            if ciphertext_length > MAX_SOURCE_BUNDLE_CIPHERTEXT_BYTES:
                raise ValueError
            metadata = _row_metadata(
                selector=selector,
                owner_path=self.owner_path_discriminator,
                key_version=key_version,
                ciphertext_length=ciphertext_length,
            )
            aad = _aad(metadata)
            candidates = self._nonce_candidates()
            with self._open_key(
                owner_path_authority=owner_path_authority, key_version=key_version
            ) as key:
                if type(key) is not bytearray or len(key) != 32:
                    raise ValueError
                with closing(self._connect()) as preflight:
                    used = {
                        bytes(row[0])
                        for row in preflight.execute(
                            "SELECT nonce FROM owner_private_encrypted_source_bundles "
                            "WHERE owner_path_discriminator=? AND key_version=?",
                            (self.owner_path_discriminator, key_version),
                        ).fetchall()
                    }
                nonce = next((candidate for candidate in candidates if candidate not in used), None)
                if nonce is None:
                    raise ValueError
                try:
                    ciphertext = AESGCM(bytes(key)).encrypt(nonce, plaintext, aad)
                finally:
                    key[:] = b"\x00" * len(key)
            if len(ciphertext) != ciphertext_length:
                raise ValueError
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    current = self._head_repository.load_current_to_floor(
                        connection, now_ms=now_ms
                    )[0]
                    if not hmac.compare_digest(current.head_sha256, expected_current_head_sha256):
                        raise ValueError
                    exists = connection.execute(
                        "SELECT 1 FROM owner_private_encrypted_source_bundles "
                        "WHERE opaque_source_bundle_id=?",
                        (selector,),
                    ).fetchone()
                    if exists is not None:
                        raise ValueError
                    connection.execute(
                        "INSERT INTO owner_private_encrypted_source_bundles "
                        "(opaque_source_bundle_id,owner_path_discriminator,categorical_state,"
                        "aead_suite,key_version,nonce_length,nonce,ciphertext_schema,"
                        "ciphertext_type,ciphertext_length,row_revision,ciphertext) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            selector,
                            self.owner_path_discriminator,
                            "sealed",
                            "aes-256-gcm",
                            key_version,
                            12,
                            nonce,
                            "owner_private_encrypted_source_bundle_v1_json",
                            "application/json",
                            ciphertext_length,
                            1,
                            ciphertext,
                        ),
                    )
                    advanced = self._head_repository.insert_and_advance(
                        connection,
                        expected_head_sha256=expected_current_head_sha256,
                        next_head=next_head,
                        now_ms=now_ms,
                    )
                    if not advanced.applied:
                        raise ValueError
                    self._require_rows_match_head(connection, advanced.current)
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            return SourceBundleAdmissionResultV1(
                applied=True,
                replayed=False,
                opaque_source_bundle_id=selector,
                current_head_sha256=next_head.head_sha256,
                current_epoch=next_head.epoch,
            )
        except Exception:
            raise OwnerPrivateSourceStoreRejected() from None

    def _require_rows_match_head(
        self,
        connection: sqlite3.Connection,
        head: OwnerPrivateSourceAuthorityHeadV1,
    ) -> None:
        rows = connection.execute(
            "SELECT opaque_source_bundle_id,row_revision "
            "FROM owner_private_encrypted_source_bundles "
            "ORDER BY opaque_source_bundle_id"
        ).fetchall()
        expected = [
            (item.opaque_source_bundle_id, item.row_revision)
            for item in head.snapshot.active_bundle_revisions
        ]
        if rows != expected:
            raise ValueError

    def _read_row_and_head(
        self,
        *,
        selector: str,
        expected_head_sha256: str,
        expected_row_revision: int,
        now_ms: int,
    ) -> tuple[Sequence[object], OwnerPrivateSourceAuthorityHeadV1]:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            try:
                head = self._head_repository.load_current_to_floor(connection, now_ms=now_ms)[0]
                if not hmac.compare_digest(head.head_sha256, expected_head_sha256):
                    raise ValueError
                row = connection.execute(_ROW_SELECT, (selector,)).fetchone()
                if row is None or row[10] != expected_row_revision:
                    raise ValueError
                self._require_rows_match_head(connection, head)
                connection.execute("COMMIT")
                return row, head
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _open_row(
        self,
        row: Sequence[object],
        *,
        owner_path_authority: object,
    ) -> OwnerPrivateEncryptedSourceBundleV1:
        if len(row) != 12:
            raise ValueError
        selector = str(row[0])
        owner_path = str(row[1])
        key_version = str(row[4])
        nonce_value = row[6]
        length_value = row[9]
        ciphertext_value = row[11]
        if (
            type(nonce_value) is not bytes
            or type(length_value) is not int
            or isinstance(length_value, bool)
            or type(ciphertext_value) is not bytes
        ):
            raise ValueError
        nonce = nonce_value
        ciphertext_length = length_value
        ciphertext = ciphertext_value
        metadata = {
            "schema_version": 1,
            "opaque_source_bundle_id": selector,
            "owner_path_discriminator": owner_path,
            "categorical_state": row[2],
            "aead_suite": row[3],
            "key_version": key_version,
            "nonce_length": row[5],
            "ciphertext_schema": row[7],
            "ciphertext_type": row[8],
            "ciphertext_length": ciphertext_length,
            "row_revision": row[10],
        }
        if (
            owner_path != self.owner_path_discriminator
            or _SELECTOR.fullmatch(selector) is None
            or _KEY_VERSION.fullmatch(key_version) is None
            or len(nonce) != 12
            or len(ciphertext) != ciphertext_length
            or ciphertext_length > MAX_SOURCE_BUNDLE_CIPHERTEXT_BYTES
        ):
            raise ValueError
        with self._open_key(
            owner_path_authority=owner_path_authority, key_version=key_version
        ) as key:
            if type(key) is not bytearray or len(key) != 32:
                raise ValueError
            try:
                plaintext = AESGCM(bytes(key)).decrypt(nonce, ciphertext, _aad(metadata))
            finally:
                key[:] = b"\x00" * len(key)
        bundle = _parse_bundle_plaintext(plaintext)
        validate_owner_private_encrypted_source_bundle_v1(
            bundle, anchor_verification_keys=self._anchor_keys
        )
        return bundle

    def replay_bundle_current(
        self,
        *,
        owner_path_authority: object,
        opaque_source_bundle_id: str,
        bundle: OwnerPrivateEncryptedSourceBundleV1,
        expected_current_head_sha256: str,
        expected_row_revision: int,
        now_ms: int,
    ) -> SourceBundleAdmissionResultV1:
        try:
            validate_owner_private_encrypted_source_bundle_v1(
                bundle, anchor_verification_keys=self._anchor_keys
            )
            self._validate_lookup_shape(
                opaque_source_bundle_id,
                expected_current_head_sha256,
                expected_row_revision,
                now_ms,
            )
            row, head = self._read_row_and_head(
                selector=opaque_source_bundle_id,
                expected_head_sha256=expected_current_head_sha256,
                expected_row_revision=expected_row_revision,
                now_ms=now_ms,
            )
            stored = self._open_row(row, owner_path_authority=owner_path_authority)
            if not hmac.compare_digest(_bundle_plaintext(stored), _bundle_plaintext(bundle)):
                raise ValueError
            final_row, final_head = self._read_row_and_head(
                selector=opaque_source_bundle_id,
                expected_head_sha256=expected_current_head_sha256,
                expected_row_revision=expected_row_revision,
                now_ms=now_ms,
            )
            if final_row[6] != row[6] or final_row[11] != row[11]:
                raise ValueError
            return SourceBundleAdmissionResultV1(
                applied=False,
                replayed=True,
                opaque_source_bundle_id=opaque_source_bundle_id,
                current_head_sha256=final_head.head_sha256,
                current_epoch=final_head.epoch,
            )
        except Exception:
            raise OwnerPrivateSourceStoreRejected() from None

    @staticmethod
    def _validate_lookup_shape(
        selector: object, head_sha256: object, revision: object, now_ms: object
    ) -> None:
        if (
            type(selector) is not str
            or _SELECTOR.fullmatch(selector) is None
            or type(head_sha256) is not str
            or _HEX64.fullmatch(head_sha256) is None
            or revision != 1
            or type(revision) is not int
            or isinstance(revision, bool)
            or not _valid_int(now_ms)
        ):
            raise ValueError

    def resolve_exact_current(
        self,
        *,
        owner_path_authority: object,
        opaque_source_bundle_id: str,
        expected_current_head_sha256: str,
        expected_row_revision: int,
        expected_receipt_pairs: tuple[tuple[str, str], ...],
        now_ms: int,
        required_until_ms: int,
    ) -> OwnerPrivateSourceResolutionWitnessV1:
        try:
            self._validate_lookup_shape(
                opaque_source_bundle_id,
                expected_current_head_sha256,
                expected_row_revision,
                now_ms,
            )
            if not _valid_int(required_until_ms) or required_until_ms < now_ms:
                raise ValueError
            if (
                type(expected_receipt_pairs) is not tuple
                or len(expected_receipt_pairs) > MAX_SOURCE_RECEIPT_PAIRS
            ):
                raise ValueError
            pairs = expected_receipt_pairs
            for pair in pairs:
                if (
                    type(pair) is not tuple
                    or len(pair) != 2
                    or type(pair[0]) is not str
                    or type(pair[1]) is not str
                    or re.fullmatch(r"opsr5_[0-9a-f]{24}", pair[0]) is None
                    or _HEX64.fullmatch(pair[1]) is None
                ):
                    raise ValueError
            row, head = self._read_row_and_head(
                selector=opaque_source_bundle_id,
                expected_head_sha256=expected_current_head_sha256,
                expected_row_revision=expected_row_revision,
                now_ms=now_ms,
            )
            bundle = self._open_row(row, owner_path_authority=owner_path_authority)
            actual_pairs = tuple(
                (receipt.receipt_id, receipt.receipt_sha256) for receipt in bundle.receipt_v5_roster
            )
            if len(actual_pairs) != len(pairs) or any(
                not hmac.compare_digest(actual_id, expected_id)
                or not hmac.compare_digest(actual_hash, expected_hash)
                for (actual_id, actual_hash), (expected_id, expected_hash) in zip(
                    actual_pairs, pairs, strict=True
                )
            ):
                raise ValueError
            if required_until_ms > bundle.required_until_ms:
                raise ValueError
            _, final_head = self._read_row_and_head(
                selector=opaque_source_bundle_id,
                expected_head_sha256=expected_current_head_sha256,
                expected_row_revision=expected_row_revision,
                now_ms=now_ms,
            )
            expiry = min(
                now_ms + SOURCE_WITNESS_TTL_MS,
                bundle.required_until_ms,
                final_head.issued_at_ms + MAX_OWNER_PRIVATE_SOURCE_HEAD_AGE_MS,
            )
            if expiry <= now_ms:
                raise ValueError
            handle = "opsw1_" + secrets.token_hex(32)
            material = _canonical_json(
                {
                    "checked_at_ms": now_ms,
                    "current_epoch": final_head.epoch,
                    "current_head_sha256": final_head.head_sha256,
                    "expires_at_ms": expiry,
                    "handle": handle,
                    "pid": os.getpid(),
                    "boot_nonce": self._boot_nonce.hex(),
                    "registry_id": self.registry_id,
                    "resolver_contract_sha256": (
                        OWNER_PRIVATE_SOURCE_EXACT_CURRENT_RESOLVER_CONTRACT_SHA256
                    ),
                    "row_revision": 1,
                    "selector": opaque_source_bundle_id,
                }
            )
            mac = hmac.digest(self._witness_key, _WITNESS_DOMAIN + material, "sha256")
            return OwnerPrivateSourceResolutionWitnessV1(
                _PRIVATE_CONSTRUCTOR,
                handle=handle,
                selector=opaque_source_bundle_id,
                revision=1,
                registry_id=self.registry_id,
                current_head=final_head.head_sha256,
                current_epoch=final_head.epoch,
                checked_at_ms=now_ms,
                expires_at_ms=expiry,
                mac=mac,
            )
        except Exception:
            raise OwnerPrivateSourceStoreRejected() from None


def private_source_bundle_store_module_source_sha256() -> str:
    """Attest this module AST while excluding only its self identity literal."""
    tree = ast.parse(Path(__file__).read_bytes(), filename=__file__)
    name = "PRIVATE_SOURCE_BUNDLE_STORE_MODULE_SOURCE_SHA256"
    assignments = 0
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == name
        ):
            value = statement.value
            if (
                not isinstance(value, ast.Constant)
                or type(value.value) is not str
                or len(value.value) != 64
                or any(character not in "0123456789abcdef" for character in value.value)
            ):
                raise RuntimeError("private source bundle source identity conflicts")
            assignments += 1
            statement.value = ast.Constant(value="<self-semantic-module-source-sha256>")
    stores = sum(
        isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == name
        for node in ast.walk(tree)
    )
    if assignments != 1 or stores != 1:
        raise RuntimeError("private source bundle source assignment conflicts")
    material = ast.dump(tree, annotate_fields=True, include_attributes=False).encode()
    return hashlib.sha256(
        b"antiek.midnight-oil.owner-private-source-bundle-semantic-source.v1\x00" + material
    ).hexdigest()


PRIVATE_SOURCE_BUNDLE_STORE_MODULE_SOURCE_SHA256 = (
    "54409180c7ebac048027ecb3788711c7fc3fadcc940ec01663b363dbd2217c43"
)


def require_private_source_bundle_store_module_source() -> None:
    if not hmac.compare_digest(
        private_source_bundle_store_module_source_sha256(),
        PRIVATE_SOURCE_BUNDLE_STORE_MODULE_SOURCE_SHA256,
    ):
        raise RuntimeError("private source bundle implementation conflicts")


__all__ = [
    "MAX_PENDING_SELECTORS",
    "MAX_SOURCE_BUNDLE_CIPHERTEXT_BYTES",
    "MAX_SOURCE_BUNDLE_PLAINTEXT_BYTES",
    "MAX_SOURCE_RECEIPT_PAIRS",
    "NONCE_COLLISION_RETRIES",
    "OWNER_PRIVATE_SOURCE_EXACT_CURRENT_RESOLVER_CONTRACT_SHA256",
    "PRIVATE_SOURCE_BUNDLE_STORE_MODULE_SOURCE_SHA256",
    "OwnerPrivateEncryptedSourceBundleStoreV1",
    "OwnerPrivateSourceKeyProviderV1",
    "OwnerPrivateSourceResolutionWitnessV1",
    "OwnerPrivateSourceStoreRejected",
    "PENDING_SELECTOR_TTL_MS",
    "PendingOpaqueSourceSelectorV1",
    "SELECTOR_COLLISION_RETRIES",
    "SOURCE_WITNESS_TTL_MS",
    "SourceBundleAdmissionResultV1",
    "SourceHeadAdmissionResultV1",
    "private_source_bundle_store_module_source_sha256",
    "require_private_source_bundle_store_module_source",
]
