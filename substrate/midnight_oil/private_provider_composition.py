"""Durable, non-executable composition for private-provider authority.

This module authenticates capability files and a rollback-floored revocation
chain for both API and worker composition roots.  It deliberately exposes no
prepare, consent, dispatch, acquisition, or output-sink integration.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_provider_policy import (
    MAX_PRIVATE_PROVIDER_CAPABILITIES,
    MAX_PRIVATE_PROVIDER_CAPABILITY_BYTES,
    MAX_PRIVATE_PROVIDER_REVOCATION_REFERENCE_AGE_MS,
    PrivateProviderCapabilityReferenceRegistry,
    PrivateProviderProcessingCapabilityV1,
    PrivateProviderRevocationSnapshotV1,
    parse_private_provider_capability_json,
    verify_private_provider_revocation_snapshot,
)

PRIVATE_PROVIDER_CAPABILITY_KEYRING_ENVS_ENV = (
    "ANTIEK_PRIVATE_PROVIDER_CAPABILITY_PUBLIC_KEY_ENVS_JSON"
)
PRIVATE_PROVIDER_REVOCATION_KEYRING_ENVS_ENV = (
    "ANTIEK_PRIVATE_PROVIDER_REVOCATION_PUBLIC_KEY_ENVS_JSON"
)
PRIVATE_PROVIDER_CAPABILITY_PATHS_ENV = (
    "ANTIEK_PRIVATE_PROVIDER_CAPABILITY_PATHS_JSON"
)
PRIVATE_PROVIDER_TRUSTED_FLOOR_PATH_ENV = (
    "ANTIEK_PRIVATE_PROVIDER_TRUSTED_FLOOR_PATH"
)
PRIVATE_PROVIDER_TRUSTED_FLOOR_SHA256_ENV = (
    "ANTIEK_PRIVATE_PROVIDER_TRUSTED_FLOOR_SHA256"
)
PRIVATE_PROVIDER_EXPECTED_CURRENT_PATH_ENV = (
    "ANTIEK_PRIVATE_PROVIDER_EXPECTED_CURRENT_HEAD_PATH"
)
PRIVATE_PROVIDER_EXPECTED_CURRENT_SHA256_ENV = (
    "ANTIEK_PRIVATE_PROVIDER_EXPECTED_CURRENT_HEAD_SHA256"
)
PRIVATE_PROVIDER_EXPECTED_COMPOSITION_SHA256_ENV = (
    "ANTIEK_PRIVATE_PROVIDER_EXPECTED_COMPOSITION_SHA256"
)
MAX_PRIVATE_PROVIDER_HEAD_BYTES = 128_000
MAX_PRIVATE_PROVIDER_HEAD_CHAIN = 1_024
ZERO_SHA256 = "0" * 64

_HEAD_DOMAIN = b"antiek.midnight-oil.private-provider-revocation-head.v1\x00"
_HEAD_SIGNATURE_DOMAIN = (
    b"antiek.midnight-oil.private-provider-revocation-head-signature.v1\x00"
)
_COMPOSITION_DOMAIN = b"antiek.midnight-oil.private-provider-composition.v1\x00"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_KEY_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")
_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{2,127}")

_HEADS_DDL = """
CREATE TABLE IF NOT EXISTS private_provider_revocation_heads (
    head_sha256 TEXT PRIMARY KEY,
    epoch BIGINT NOT NULL UNIQUE,
    previous_head_sha256 TEXT NOT NULL,
    issued_at_ms BIGINT NOT NULL,
    document_json TEXT NOT NULL
)
"""
_CURRENT_DDL = """
CREATE TABLE IF NOT EXISTS private_provider_revocation_current (
    registry_id TEXT PRIMARY KEY,
    head_sha256 TEXT NOT NULL,
    FOREIGN KEY (head_sha256) REFERENCES private_provider_revocation_heads(head_sha256)
)
"""
_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS private_provider_revocation_schema (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1)
)
"""


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PrivateProviderRevocationHeadV1(_Closed):
    """Signed transition; current-head truth still comes from the durable store."""

    schema_version: Literal[1] = 1
    registry_id: Literal["antiek-private-provider-revocations-v1"] = (
        "antiek-private-provider-revocations-v1"
    )
    epoch: int = Field(ge=0)
    issued_at_ms: int = Field(ge=0)
    previous_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot: PrivateProviderRevocationSnapshotV1
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    issuer_role: Literal["private_provider_revocation_issuer"] = (
        "private_provider_revocation_issuer"
    )
    signature_scheme: Literal["ed25519"] = "ed25519"
    head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_ed25519: str = Field(pattern=r"^[0-9a-f]{128}$")
    confers_execution_authority: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> PrivateProviderRevocationHeadV1:
        if (
            self.snapshot.registry_id != self.registry_id
            or self.snapshot.epoch != self.epoch
            or self.snapshot.issued_at_ms != self.issued_at_ms
        ):
            raise ValueError("private provider head conflicts with its snapshot")
        if (self.epoch == 0) != (self.previous_head_sha256 == ZERO_SHA256):
            raise ValueError("private provider head predecessor conflicts with epoch")
        if self.head_sha256 != private_provider_revocation_head_sha256(self):
            raise ValueError("private provider head identity conflicts")
        return self


def _canonical_material(
    value: BaseModel | Mapping[str, object], omitted: frozenset[str]
) -> bytes:
    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    material = {key: item for key, item in raw.items() if key not in omitted}
    return json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def private_provider_revocation_head_sha256(
    head: PrivateProviderRevocationHeadV1 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _HEAD_DOMAIN
        + _canonical_material(head, frozenset({"head_sha256", "signature_ed25519"}))
    ).hexdigest()


def private_provider_revocation_head_signature(
    head_sha256: str, *, signing_key: bytes
) -> str:
    if len(signing_key) != 32:
        raise ValueError("private provider head Ed25519 signing key must be 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(signing_key).sign(
        _HEAD_SIGNATURE_DOMAIN + head_sha256.encode("ascii")
    ).hex()


def signed_private_provider_revocation_head(
    *,
    snapshot: PrivateProviderRevocationSnapshotV1,
    previous_head_sha256: str,
    key_id: str,
    signing_key: bytes,
) -> PrivateProviderRevocationHeadV1:
    material: dict[str, object] = {
        "schema_version": 1,
        "registry_id": snapshot.registry_id,
        "epoch": snapshot.epoch,
        "issued_at_ms": snapshot.issued_at_ms,
        "previous_head_sha256": previous_head_sha256,
        "snapshot": snapshot.model_dump(mode="python"),
        "key_id": key_id,
        "issuer_role": "private_provider_revocation_issuer",
        "signature_scheme": "ed25519",
        "confers_execution_authority": False,
    }
    digest = private_provider_revocation_head_sha256(material)
    return PrivateProviderRevocationHeadV1.model_validate(
        {
            **material,
            "head_sha256": digest,
            "signature_ed25519": private_provider_revocation_head_signature(
                digest, signing_key=signing_key
            ),
        }
    )


def verify_private_provider_revocation_head(
    head: PrivateProviderRevocationHeadV1,
    *,
    verification_keys: Mapping[str, bytes],
) -> None:
    digest = private_provider_revocation_head_sha256(head)
    if not hmac.compare_digest(digest, head.head_sha256):
        raise ValueError("private provider revocation head is unavailable")
    public_key = verification_keys.get(head.key_id)
    if public_key is None or len(public_key) != 32:
        raise ValueError("private provider revocation head is unavailable")
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            bytes.fromhex(head.signature_ed25519),
            _HEAD_SIGNATURE_DOMAIN + digest.encode("ascii"),
        )
    except (InvalidSignature, ValueError):
        raise ValueError("private provider revocation head is unavailable") from None
    verify_private_provider_revocation_snapshot(
        head.snapshot, verification_keys=verification_keys
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("private provider JSON contains duplicate keys")
        result[key] = value
    return result


def parse_private_provider_revocation_head_json(
    raw: str,
) -> PrivateProviderRevocationHeadV1:
    if type(raw) is not str or not raw or len(raw.encode()) > MAX_PRIVATE_PROVIDER_HEAD_BYTES:
        raise ValueError("private provider revocation head JSON is invalid")
    try:
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("private provider revocation head JSON is invalid") from exc
    if type(payload) is not dict:
        raise ValueError("private provider revocation head JSON is invalid")
    snapshot = payload.get("snapshot")
    if type(snapshot) is dict and type(snapshot.get("revoked_capability_sha256s")) is list:
        payload = {
            **payload,
            "snapshot": {
                **snapshot,
                "revoked_capability_sha256s": tuple(
                    snapshot["revoked_capability_sha256s"]
                ),
            },
        }
    return PrivateProviderRevocationHeadV1.model_validate(payload)


@dataclass(frozen=True)
class RevocationHeadCasResult:
    applied: bool
    current: PrivateProviderRevocationHeadV1


class InvalidPrivateProviderRevocationStore(RuntimeError):
    """Persisted revocation authority is malformed, forked, or rolled back."""


class DurablePrivateProviderRevocationHeadStore:
    """Append-only trusted-floor chain with cross-process exact-head CAS."""

    def __init__(
        self,
        path: str | Path,
        *,
        verification_keys: Mapping[str, bytes],
        trusted_floor_sha256: str,
    ) -> None:
        raw_path = os.fspath(path)
        if not raw_path.strip() or raw_path == ":memory:":
            raise ValueError("a durable private provider revocation path is required")
        if _HEX64.fullmatch(trusted_floor_sha256) is None:
            raise ValueError("private provider trusted floor is invalid")
        supplied = Path(raw_path)
        if supplied.exists() and supplied.is_symlink():
            raise ValueError("private provider revocation path must not be a symlink")
        existing_nonempty = supplied.exists() and supplied.stat().st_size > 0
        self.path = supplied.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.verification_keys = dict(verification_keys)
        self.trusted_floor_sha256 = trusted_floor_sha256
        with closing(self._connect()) as connection:
            if existing_nonempty:
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' "
                        "AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                }
                expected_tables = {
                    "private_provider_revocation_schema",
                    "private_provider_revocation_heads",
                    "private_provider_revocation_current",
                }
                if tables != expected_tables:
                    raise InvalidPrivateProviderRevocationStore(
                        "private provider revocation schema is invalid"
                    )
            connection.execute(_SCHEMA_DDL)
            connection.execute(_HEADS_DDL)
            connection.execute(_CURRENT_DDL)
            connection.execute(
                "INSERT OR IGNORE INTO private_provider_revocation_schema "
                "(singleton, schema_version) VALUES (1, 1)"
            )
            self._validate_schema(connection)
        os.chmod(self.path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _validate_schema(self, connection: sqlite3.Connection) -> None:
        schema_rows = connection.execute(
            "SELECT singleton, schema_version "
            "FROM private_provider_revocation_schema"
        ).fetchall()
        if schema_rows != [(1, 1)]:
            raise InvalidPrivateProviderRevocationStore(
                "private provider revocation schema is invalid"
            )
        expected_columns = {
            "private_provider_revocation_schema": (
                ("singleton", "INTEGER", 0, 1),
                ("schema_version", "INTEGER", 1, 0),
            ),
            "private_provider_revocation_heads": (
                ("head_sha256", "TEXT", 0, 1),
                ("epoch", "BIGINT", 1, 0),
                ("previous_head_sha256", "TEXT", 1, 0),
                ("issued_at_ms", "BIGINT", 1, 0),
                ("document_json", "TEXT", 1, 0),
            ),
            "private_provider_revocation_current": (
                ("registry_id", "TEXT", 0, 1),
                ("head_sha256", "TEXT", 1, 0),
            ),
        }
        for table, columns in expected_columns.items():
            rows = connection.execute(f"PRAGMA table_info('{table}')").fetchall()
            actual = tuple(
                (str(row[1]), str(row[2]).upper(), int(row[3]), int(row[5]))
                for row in rows
            )
            if actual != columns:
                raise InvalidPrivateProviderRevocationStore(
                    "private provider revocation schema is invalid"
                )
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list('private_provider_revocation_current')"
        ).fetchall()
        if len(foreign_keys) != 1 or (
            str(foreign_keys[0][2]),
            str(foreign_keys[0][3]),
            str(foreign_keys[0][4]),
        ) != (
            "private_provider_revocation_heads",
            "head_sha256",
            "head_sha256",
        ):
            raise InvalidPrivateProviderRevocationStore(
                "private provider revocation schema is invalid"
            )
        unique_indexes = connection.execute(
            "PRAGMA index_list('private_provider_revocation_heads')"
        ).fetchall()
        unique_columns = {
            tuple(
                str(column[2])
                for column in connection.execute(
                    f"PRAGMA index_info('{str(index[1])}')"
                ).fetchall()
            )
            for index in unique_indexes
            if int(index[2]) == 1
        }
        if unique_columns != {("head_sha256",), ("epoch",)}:
            raise InvalidPrivateProviderRevocationStore(
                "private provider revocation schema is invalid"
            )
        schema_sql_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' "
            "AND name = 'private_provider_revocation_schema'"
        ).fetchone()
        schema_sql = "" if schema_sql_row is None else str(schema_sql_row[0]).lower()
        compact_schema_sql = "".join(schema_sql.split())
        if (
            "check(singleton=1)" not in compact_schema_sql
            or "check(schema_version=1)" not in compact_schema_sql
        ):
            raise InvalidPrivateProviderRevocationStore(
                "private provider revocation schema is invalid"
            )

    def admit_trusted_floor(self, head: PrivateProviderRevocationHeadV1) -> None:
        verify_private_provider_revocation_head(
            head, verification_keys=self.verification_keys
        )
        if head.head_sha256 != self.trusted_floor_sha256:
            raise ValueError("private provider trusted floor conflicts")
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = connection.execute(
                    "SELECT head_sha256 FROM private_provider_revocation_current "
                    "WHERE registry_id = ?",
                    [head.registry_id],
                ).fetchone()
                if current is None:
                    counts = connection.execute(
                        "SELECT "
                        "(SELECT COUNT(*) FROM private_provider_revocation_heads), "
                        "(SELECT COUNT(*) FROM private_provider_revocation_current)"
                    ).fetchone()
                    if counts != (0, 0):
                        raise InvalidPrivateProviderRevocationStore(
                            "private provider revocation store is partially initialized"
                        )
                    self._insert_head(connection, head)
                    connection.execute(
                        "INSERT INTO private_provider_revocation_current "
                        "(registry_id, head_sha256) VALUES (?, ?)",
                        [head.registry_id, head.head_sha256],
                    )
                else:
                    stored_chain = self._load_stored_chain(connection)
                    matching = next(
                        (
                            index
                            for index, stored in enumerate(stored_chain)
                            if stored.head_sha256 == head.head_sha256
                        ),
                        None,
                    )
                    if matching is None or stored_chain[matching] != head:
                        raise InvalidPrivateProviderRevocationStore(
                            "private provider trusted floor is not in current history"
                        )
                    older_hashes = tuple(
                        stored.head_sha256 for stored in stored_chain[matching + 1 :]
                    )
                    if older_hashes:
                        connection.executemany(
                            "DELETE FROM private_provider_revocation_heads "
                            "WHERE head_sha256 = ?",
                            ((digest,) for digest in older_hashes),
                        )
                self._load_chain(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def current(self, *, now_ms: int) -> PrivateProviderRevocationHeadV1:
        _valid_now(now_ms)
        head = self.current_verified()
        _require_fresh(head, now_ms=now_ms)
        return head

    def current_verified(self) -> PrivateProviderRevocationHeadV1:
        """Return the fully audited head without claiming freshness."""

        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            try:
                head = self._load_chain(connection)[0]
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return head

    def compare_and_set(
        self,
        *,
        expected_head_sha256: str,
        next_head: PrivateProviderRevocationHeadV1,
        now_ms: int,
    ) -> RevocationHeadCasResult:
        _valid_now(now_ms)
        verify_private_provider_revocation_head(
            next_head, verification_keys=self.verification_keys
        )
        _require_fresh(next_head, now_ms=now_ms)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = self._load_chain(connection)[0]
                if current.head_sha256 != expected_head_sha256:
                    connection.execute("COMMIT")
                    return RevocationHeadCasResult(applied=False, current=current)
                if next_head.head_sha256 == current.head_sha256:
                    connection.execute("COMMIT")
                    return RevocationHeadCasResult(applied=False, current=current)
                retained = connection.execute(
                    "SELECT COUNT(*) FROM private_provider_revocation_heads"
                ).fetchone()
                if retained is None or int(retained[0]) >= MAX_PRIVATE_PROVIDER_HEAD_CHAIN:
                    raise InvalidPrivateProviderRevocationStore(
                        "private provider revocation chain requires re-anchoring"
                    )
                _validate_successor(current, next_head)
                self._insert_head(connection, next_head)
                changed = connection.execute(
                    "UPDATE private_provider_revocation_current SET head_sha256 = ? "
                    "WHERE registry_id = ? AND head_sha256 = ? RETURNING head_sha256",
                    [
                        next_head.head_sha256,
                        next_head.registry_id,
                        expected_head_sha256,
                    ],
                ).fetchone()
                if changed is None:
                    raise InvalidPrivateProviderRevocationStore(
                        "private provider current-head CAS was lost inside its lock"
                    )
                connection.execute("COMMIT")
                return RevocationHeadCasResult(applied=True, current=next_head)
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _insert_head(
        self, connection: sqlite3.Connection, head: PrivateProviderRevocationHeadV1
    ) -> None:
        connection.execute(
            "INSERT INTO private_provider_revocation_heads "
            "(head_sha256, epoch, previous_head_sha256, issued_at_ms, document_json) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                head.head_sha256,
                head.epoch,
                head.previous_head_sha256,
                head.issued_at_ms,
                head.model_dump_json(),
            ],
        )

    def _load_chain(
        self, connection: sqlite3.Connection
    ) -> tuple[PrivateProviderRevocationHeadV1, ...]:
        stored_chain = self._load_stored_chain(connection)
        for index, head in enumerate(stored_chain):
            if head.head_sha256 == self.trusted_floor_sha256:
                return stored_chain[: index + 1]
        raise InvalidPrivateProviderRevocationStore(
            "private provider revocation chain lost its trusted floor"
        )

    def _load_stored_chain(
        self, connection: sqlite3.Connection
    ) -> tuple[PrivateProviderRevocationHeadV1, ...]:
        current_rows = connection.execute(
            "SELECT h.head_sha256, h.epoch, h.previous_head_sha256, "
            "h.issued_at_ms, h.document_json "
            "FROM private_provider_revocation_current c "
            "JOIN private_provider_revocation_heads h ON h.head_sha256 = c.head_sha256 "
            "WHERE c.registry_id = ?",
            ["antiek-private-provider-revocations-v1"],
        ).fetchall()
        pointer_count = connection.execute(
            "SELECT COUNT(*) FROM private_provider_revocation_current"
        ).fetchone()
        if len(current_rows) != 1 or pointer_count != (1,):
            raise InvalidPrivateProviderRevocationStore(
                "private provider trusted floor is not initialized"
            )
        chain: list[PrivateProviderRevocationHeadV1] = []
        seen: set[str] = set()
        row = current_rows[0]
        try:
            while True:
                head = self._decode_stored_head(row)
                if head.head_sha256 in seen:
                    raise InvalidPrivateProviderRevocationStore(
                        "private provider revocation chain contains a cycle"
                    )
                seen.add(head.head_sha256)
                chain.append(head)
                if len(chain) > MAX_PRIVATE_PROVIDER_HEAD_CHAIN:
                    raise InvalidPrivateProviderRevocationStore(
                        "private provider revocation chain exceeds its bound"
                    )
                parent_row = connection.execute(
                    "SELECT head_sha256, epoch, previous_head_sha256, "
                    "issued_at_ms, document_json "
                    "FROM private_provider_revocation_heads "
                    "WHERE head_sha256 = ?",
                    [head.previous_head_sha256],
                ).fetchone()
                if parent_row is None:
                    break
                row = parent_row
            for child, parent in zip(chain, chain[1:], strict=False):
                _validate_successor(parent, child)
            total = connection.execute(
                "SELECT COUNT(*) FROM private_provider_revocation_heads"
            ).fetchone()
            if total is None or int(total[0]) != len(chain):
                raise InvalidPrivateProviderRevocationStore(
                    "private provider revocation store contains a fork"
                )
            return tuple(chain)
        except InvalidPrivateProviderRevocationStore:
            raise
        except Exception as exc:
            raise InvalidPrivateProviderRevocationStore(
                "private provider revocation chain is invalid"
            ) from exc

    def _decode_stored_head(
        self, row: Sequence[object]
    ) -> PrivateProviderRevocationHeadV1:
        if len(row) != 5:
            raise InvalidPrivateProviderRevocationStore(
                "private provider revocation row is invalid"
            )
        head = parse_private_provider_revocation_head_json(str(row[4]))
        verify_private_provider_revocation_head(
            head, verification_keys=self.verification_keys
        )
        if (
            head.head_sha256 != str(row[0])
            or head.epoch != row[1]
            or head.previous_head_sha256 != str(row[2])
            or head.issued_at_ms != row[3]
        ):
            raise InvalidPrivateProviderRevocationStore(
                "private provider signed document conflicts with its durable row"
            )
        return head


def _validate_successor(
    current: PrivateProviderRevocationHeadV1,
    successor: PrivateProviderRevocationHeadV1,
) -> None:
    if (
        successor.registry_id != current.registry_id
        or successor.previous_head_sha256 != current.head_sha256
        or successor.epoch != current.epoch + 1
        or successor.issued_at_ms <= current.issued_at_ms
        or not set(current.snapshot.revoked_capability_sha256s).issubset(
            successor.snapshot.revoked_capability_sha256s
        )
    ):
        raise ValueError("private provider revocation successor conflicts")


def _valid_now(now_ms: int) -> None:
    if type(now_ms) is not int or isinstance(now_ms, bool) or now_ms < 0:
        raise ValueError("private provider current time is invalid")


def _require_fresh(head: PrivateProviderRevocationHeadV1, *, now_ms: int) -> None:
    if (
        head.issued_at_ms > now_ms
        or now_ms - head.issued_at_ms
        > MAX_PRIVATE_PROVIDER_REVOCATION_REFERENCE_AGE_MS
    ):
        raise ValueError("private provider revocation head is stale")


@dataclass(frozen=True)
class PrivateProviderComposition:
    """Identical API/worker proof bundle; no method confers execution authority."""

    capability_key_ids: tuple[str, ...]
    revocation_key_ids: tuple[str, ...]
    verification_key_envs: frozenset[str]
    public_verification_keys: tuple[bytes, ...] = field(repr=False)
    capability_verification_keys: tuple[tuple[str, bytes], ...] = field(repr=False)
    revocation_verification_keys: tuple[tuple[str, bytes], ...] = field(repr=False)
    capabilities: tuple[PrivateProviderProcessingCapabilityV1, ...] = field(repr=False)
    revocation_store: DurablePrivateProviderRevocationHeadStore = field(repr=False)
    current_head: PrivateProviderRevocationHeadV1
    reference_registry: PrivateProviderCapabilityReferenceRegistry = field(repr=False)
    composition_sha256: str
    confers_execution_authority: Literal[False] = False

    @property
    def capability_hashes(self) -> tuple[str, ...]:
        return tuple(sorted(row.capability_sha256 for row in self.capabilities))

    def live_reference_registry(
        self, *, now_ms: int
    ) -> PrivateProviderCapabilityReferenceRegistry:
        """Re-audit durable current revocation state for one transition."""

        current = self.revocation_store.current(now_ms=now_ms)
        return PrivateProviderCapabilityReferenceRegistry(
            self.capabilities,
            capability_verification_keys=dict(self.capability_verification_keys),
            revocation_verification_keys=dict(self.revocation_verification_keys),
            revocation_snapshot=current.snapshot,
        )


def private_provider_composition_sha256(
    *,
    capabilities: Sequence[PrivateProviderProcessingCapabilityV1],
    capability_keys: Mapping[str, bytes],
    revocation_keys: Mapping[str, bytes],
    floor: PrivateProviderRevocationHeadV1,
    current: PrivateProviderRevocationHeadV1,
    state_path: str | Path,
) -> str:
    """Derive the exact deployment pin without reading or mutating runtime state."""

    material = {
        "schema_version": 1,
        "capability_hashes": tuple(
            sorted(row.capability_sha256 for row in capabilities)
        ),
        "capability_key_fingerprints": tuple(
            sorted(hashlib.sha256(value).hexdigest() for value in capability_keys.values())
        ),
        "revocation_key_fingerprints": tuple(
            sorted(hashlib.sha256(value).hexdigest() for value in revocation_keys.values())
        ),
        "trusted_floor_sha256": floor.head_sha256,
        "current_head_sha256": current.head_sha256,
        "current_epoch": current.epoch,
        "current_snapshot_sha256": current.snapshot.snapshot_sha256,
        "expected_current_sha256": current.head_sha256,
        "state_path_sha256": hashlib.sha256(
            str(Path(state_path).resolve()).encode()
        ).hexdigest(),
        "reference_only": True,
        "confers_execution_authority": False,
    }
    return hashlib.sha256(
        _COMPOSITION_DOMAIN
        + json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_private_provider_composition(
    *,
    state_dir: str | Path,
    environ: Mapping[str, str],
    now_ms: int,
    forbidden_key_envs: frozenset[str] = frozenset(),
    forbidden_keys: Sequence[bytes] = (),
    forbidden_key_values: Sequence[str] = (),
) -> PrivateProviderComposition | None:
    """Load a purpose-specific closed bundle; absent is closed, partial is fatal."""

    names = (
        PRIVATE_PROVIDER_CAPABILITY_KEYRING_ENVS_ENV,
        PRIVATE_PROVIDER_REVOCATION_KEYRING_ENVS_ENV,
        PRIVATE_PROVIDER_CAPABILITY_PATHS_ENV,
        PRIVATE_PROVIDER_TRUSTED_FLOOR_PATH_ENV,
        PRIVATE_PROVIDER_TRUSTED_FLOOR_SHA256_ENV,
        PRIVATE_PROVIDER_EXPECTED_CURRENT_PATH_ENV,
        PRIVATE_PROVIDER_EXPECTED_CURRENT_SHA256_ENV,
        PRIVATE_PROVIDER_EXPECTED_COMPOSITION_SHA256_ENV,
    )
    values = tuple(environ.get(name, "").strip() for name in names)
    if not any(values):
        return None
    if not all(values):
        raise ValueError("private provider composition is incomplete")
    capability_key_envs = _parse_keyring_envs(values[0])
    revocation_key_envs = _parse_keyring_envs(values[1])
    all_key_envs = set(capability_key_envs.values()) | set(
        revocation_key_envs.values()
    )
    private_raw_values = tuple(
        environ.get(name, "").strip() for name in sorted(all_key_envs)
    )
    substack_envs, substack_keys = _substack_authority_inventory(environ)
    forbidden_key_envs = forbidden_key_envs | substack_envs
    forbidden_keys = tuple(forbidden_keys) + substack_keys
    if (
        set(capability_key_envs) & set(revocation_key_envs)
        or set(capability_key_envs.values()) & set(revocation_key_envs.values())
        or all_key_envs & forbidden_key_envs
    ):
        raise ValueError("private provider keys reuse another authority purpose")
    capability_keys = {
        key_id: _decode_public_key(environ.get(env_name, ""))
        for key_id, env_name in capability_key_envs.items()
    }
    revocation_keys = {
        key_id: _decode_public_key(environ.get(env_name, ""))
        for key_id, env_name in revocation_key_envs.items()
    }
    normalized_forbidden_keys = list(forbidden_keys)
    for value in forbidden_key_values:
        with suppress(ValueError):
            normalized_forbidden_keys.append(_decode_public_key(value))
    all_public_keys = tuple(capability_keys.values()) + tuple(revocation_keys.values())
    if any(
        hmac.compare_digest(private_key, forbidden_key)
        for private_key in all_public_keys
        for forbidden_key in normalized_forbidden_keys
    ) or any(
        raw and forbidden and hmac.compare_digest(raw, forbidden)
        for raw in private_raw_values
        for forbidden in forbidden_key_values
    ) or len(set(all_public_keys)) != len(all_public_keys):
        raise ValueError("private provider keys reuse another authority purpose")
    capability_paths = _parse_paths(values[2], maximum=MAX_PRIVATE_PROVIDER_CAPABILITIES)
    capabilities = tuple(
        parse_private_provider_capability_json(_read_bounded(path, MAX_PRIVATE_PROVIDER_CAPABILITY_BYTES))
        for path in capability_paths
    )
    floor_path = _absolute_file(values[3])
    floor = parse_private_provider_revocation_head_json(
        _read_bounded(floor_path, MAX_PRIVATE_PROVIDER_HEAD_BYTES)
    )
    if floor.head_sha256 != values[4]:
        raise ValueError("private provider trusted floor hash conflicts")
    verify_private_provider_revocation_head(
        floor, verification_keys=revocation_keys
    )
    expected_path = _absolute_file(values[5])
    expected = parse_private_provider_revocation_head_json(
        _read_bounded(expected_path, MAX_PRIVATE_PROVIDER_HEAD_BYTES)
    )
    if expected.head_sha256 != values[6]:
        raise ValueError("private provider expected current-head hash conflicts")
    verify_private_provider_revocation_head(
        expected, verification_keys=revocation_keys
    )
    state_path = Path(state_dir) / "private-provider-revocations.sqlite3"
    anticipated_composition_sha256 = private_provider_composition_sha256(
        capabilities=capabilities,
        capability_keys=capability_keys,
        revocation_keys=revocation_keys,
        floor=floor,
        current=expected,
        state_path=state_path,
    )
    if anticipated_composition_sha256 != values[7]:
        raise ValueError("private provider composition fingerprint conflicts")
    store = DurablePrivateProviderRevocationHeadStore(
        state_path,
        verification_keys=revocation_keys,
        trusted_floor_sha256=floor.head_sha256,
    )
    store.admit_trusted_floor(floor)
    persisted = store.current_verified()
    if persisted.head_sha256 != expected.head_sha256:
        updated = store.compare_and_set(
            expected_head_sha256=persisted.head_sha256,
            next_head=expected,
            now_ms=now_ms,
        )
        if not updated.applied and updated.current.head_sha256 != expected.head_sha256:
            raise ValueError("private provider expected current head is unavailable")
    current = store.current(now_ms=now_ms)
    if current.head_sha256 != expected.head_sha256:
        raise ValueError("private provider expected current head is unavailable")
    registry = PrivateProviderCapabilityReferenceRegistry(
        capabilities,
        capability_verification_keys=capability_keys,
        revocation_verification_keys=revocation_keys,
        revocation_snapshot=current.snapshot,
    )
    composition_sha256 = private_provider_composition_sha256(
        capabilities=capabilities,
        capability_keys=capability_keys,
        revocation_keys=revocation_keys,
        floor=floor,
        current=current,
        state_path=store.path,
    )
    if composition_sha256 != anticipated_composition_sha256:
        raise InvalidPrivateProviderRevocationStore(
            "private provider composition changed during admission"
        )
    return PrivateProviderComposition(
        capability_key_ids=tuple(sorted(capability_keys)),
        revocation_key_ids=tuple(sorted(revocation_keys)),
        verification_key_envs=frozenset(all_key_envs),
        public_verification_keys=tuple(sorted(all_public_keys)),
        capability_verification_keys=tuple(sorted(capability_keys.items())),
        revocation_verification_keys=tuple(sorted(revocation_keys.items())),
        capabilities=capabilities,
        revocation_store=store,
        current_head=current,
        reference_registry=registry,
        composition_sha256=composition_sha256,
    )


def _parse_keyring_envs(raw: str) -> dict[str, str]:
    payload = _json_value(raw, maximum_bytes=16_000)
    if type(payload) is not dict or not 1 <= len(payload) <= 16:
        raise ValueError("private provider verification keyring is invalid")
    result: dict[str, str] = {}
    for key_id, env_name in payload.items():
        if (
            type(key_id) is not str
            or _KEY_ID.fullmatch(key_id) is None
            or type(env_name) is not str
            or _ENV_NAME.fullmatch(env_name) is None
        ):
            raise ValueError("private provider verification keyring is invalid")
        result[key_id] = env_name
    return result


def _substack_authority_inventory(
    environ: Mapping[str, str],
) -> tuple[frozenset[str], tuple[bytes, ...]]:
    active = environ.get("ANTIEK_SUBSTACK_AUTH_ACTIVE_KEY_ID", "").strip()
    signing_env = environ.get("ANTIEK_SUBSTACK_AUTH_SIGNING_KEY_ENV", "").strip()
    keyring_raw = environ.get(
        "ANTIEK_SUBSTACK_AUTH_VERIFICATION_KEY_ENVS_JSON", ""
    ).strip()
    if not any((active, signing_env, keyring_raw)):
        return frozenset(), ()
    if not all((active, signing_env, keyring_raw)):
        raise ValueError("Substack authority composition is incomplete")
    keyring = _parse_keyring_envs(keyring_raw)
    if keyring.get(active) != signing_env:
        raise ValueError("Substack authority composition is invalid")
    keys = tuple(_decode_authority_key(environ.get(name, "")) for name in keyring.values())
    return frozenset(keyring.values()), keys


def _parse_paths(raw: str, *, maximum: int) -> tuple[Path, ...]:
    payload = _json_value(raw, maximum_bytes=64_000)
    if type(payload) is not list or not 1 <= len(payload) <= maximum:
        raise ValueError("private provider capability paths are invalid")
    if any(type(value) is not str for value in payload):
        raise ValueError("private provider capability paths are invalid")
    paths = tuple(_absolute_file(value) for value in payload)
    if len(set(paths)) != len(paths):
        raise ValueError("private provider capability paths contain duplicates")
    return paths


def _json_value(raw: str, *, maximum_bytes: int) -> object:
    if not raw or len(raw.encode()) > maximum_bytes:
        raise ValueError("private provider environment JSON is invalid")
    try:
        return json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ValueError("private provider environment JSON is invalid") from exc


def _absolute_file(value: str) -> Path:
    if not value or len(value) > 4_096:
        raise ValueError("private provider artifact path is invalid")
    path = Path(value)
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("private provider artifact path is invalid")
    return path.resolve()


def _read_bounded(path: Path, maximum: int) -> str:
    try:
        if path.stat().st_size > maximum:
            raise ValueError("private provider artifact exceeds its bound")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("private provider artifact is unreadable") from exc


def _decode_public_key(raw: str) -> bytes:
    if not raw or len(raw) > 4_096:
        raise ValueError("private provider public key has an invalid encoded length")
    try:
        key = base64.b64decode(
            raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, TypeError, binascii.Error) as exc:
        raise ValueError("private provider public key is not base64url") from exc
    if len(key) != 32:
        raise ValueError("private provider Ed25519 public key must be 32 bytes")
    return key


def _decode_authority_key(raw: str) -> bytes:
    if not raw or len(raw) > 4_096:
        raise ValueError("authority key has an invalid encoded length")
    try:
        key = base64.b64decode(
            raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, TypeError, binascii.Error) as exc:
        raise ValueError("authority key is not base64url") from exc
    if len(key) < 32:
        raise ValueError("authority key must be at least 256 bits")
    return key


__all__ = [
    "MAX_PRIVATE_PROVIDER_HEAD_BYTES",
    "MAX_PRIVATE_PROVIDER_HEAD_CHAIN",
    "PRIVATE_PROVIDER_CAPABILITY_PATHS_ENV",
    "PRIVATE_PROVIDER_EXPECTED_CURRENT_PATH_ENV",
    "PRIVATE_PROVIDER_EXPECTED_CURRENT_SHA256_ENV",
    "PRIVATE_PROVIDER_EXPECTED_COMPOSITION_SHA256_ENV",
    "PRIVATE_PROVIDER_CAPABILITY_KEYRING_ENVS_ENV",
    "PRIVATE_PROVIDER_REVOCATION_KEYRING_ENVS_ENV",
    "PRIVATE_PROVIDER_TRUSTED_FLOOR_PATH_ENV",
    "PRIVATE_PROVIDER_TRUSTED_FLOOR_SHA256_ENV",
    "DurablePrivateProviderRevocationHeadStore",
    "InvalidPrivateProviderRevocationStore",
    "PrivateProviderComposition",
    "PrivateProviderRevocationHeadV1",
    "RevocationHeadCasResult",
    "build_private_provider_composition",
    "parse_private_provider_revocation_head_json",
    "private_provider_composition_sha256",
    "private_provider_revocation_head_sha256",
    "private_provider_revocation_head_signature",
    "signed_private_provider_revocation_head",
    "verify_private_provider_revocation_head",
]
