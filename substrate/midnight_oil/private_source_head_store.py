"""Signed opaque source-head contracts and connection-bound repository helpers.

This module deliberately has no signer, private key, database opener, transaction
owner, bundle encryption, plaintext resolver, witness, or production consumer.
The future bundle store must supply one already-open SQLite connection and own
every ``BEGIN`` / ``COMMIT`` / ``ROLLBACK`` boundary.
"""

from __future__ import annotations

import ast
import hashlib
import hmac
import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_OWNER_PRIVATE_SOURCE_HEAD_BYTES = 1_000_000
MAX_OWNER_PRIVATE_SOURCE_HEAD_CHAIN = 128
MAX_OWNER_PRIVATE_SOURCE_BUNDLES = 64
MAX_OWNER_PRIVATE_SOURCE_HEAD_AGE_MS = 300_000
MAX_OWNER_PRIVATE_SOURCE_HEAD_FUTURE_SKEW_MS = 60_000
MAX_OWNER_PRIVATE_SOURCE_HEAD_KEYS = 64
ZERO_SHA256 = "0" * 64

_SNAPSHOT_DOMAIN = b"antiek.midnight-oil.owner-private-source-authority-snapshot.v1\x00"
_HEAD_DOMAIN = b"antiek.midnight-oil.owner-private-source-authority-head.v1\x00"
_HEAD_SIGNATURE_DOMAIN = b"antiek.midnight-oil.owner-private-source-authority-signature.v1\x00"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_KEY_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")
_OWNER_PATH = re.compile(r"opspd1_[0-9a-f]{64}")
_REGISTRY_ID = re.compile(r"opsreg1_[0-9a-f]{64}")

_HEADS_DDL = """
CREATE TABLE IF NOT EXISTS owner_private_source_authority_heads (
    head_sha256 TEXT PRIMARY KEY,
    registry_id TEXT NOT NULL,
    owner_path_discriminator TEXT NOT NULL,
    epoch INTEGER NOT NULL UNIQUE,
    previous_head_sha256 TEXT NOT NULL,
    issued_at_ms INTEGER NOT NULL,
    document_json TEXT NOT NULL
)
"""
_CURRENT_DDL = """
CREATE TABLE IF NOT EXISTS owner_private_source_authority_current (
    registry_id TEXT PRIMARY KEY,
    owner_path_discriminator TEXT NOT NULL UNIQUE,
    head_sha256 TEXT NOT NULL,
    FOREIGN KEY (head_sha256)
        REFERENCES owner_private_source_authority_heads(head_sha256)
)
"""


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]


class OpaqueSourceBundleRevisionV1(_Closed):
    schema_version: Literal[1] = 1
    opaque_source_bundle_id: str = Field(pattern=r"^opsbs1_[0-9a-f]{64}$")
    row_revision: Literal[1] = 1
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class OwnerPrivateSourceAuthoritySnapshotV1(_Closed):
    schema_version: Literal[1] = 1
    registry_id: str = Field(pattern=r"^opsreg1_[0-9a-f]{64}$")
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    epoch: int = Field(ge=0)
    issued_at_ms: int = Field(ge=0)
    active_bundle_revisions: tuple[OpaqueSourceBundleRevisionV1, ...] = Field(
        max_length=MAX_OWNER_PRIVATE_SOURCE_BUNDLES
    )
    tombstoned_bundle_ids: tuple[str, ...] = Field(max_length=MAX_OWNER_PRIVATE_SOURCE_BUNDLES)
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivateSourceAuthoritySnapshotV1:
        active_ids = tuple(
            member.opaque_source_bundle_id for member in self.active_bundle_revisions
        )
        tombstones = self.tombstoned_bundle_ids
        if (
            any(
                type(member) is not OpaqueSourceBundleRevisionV1
                for member in self.active_bundle_revisions
            )
            or active_ids != tuple(sorted(active_ids))
            or len(set(active_ids)) != len(active_ids)
            or tombstones != ()
            or self.snapshot_sha256 != owner_private_source_authority_snapshot_v1_sha256(self)
        ):
            raise ValueError("owner-private source authority snapshot conflicts")
        return self


class OwnerPrivateSourceAuthorityHeadV1(_Closed):
    schema_version: Literal[1] = 1
    registry_id: str = Field(pattern=r"^opsreg1_[0-9a-f]{64}$")
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    epoch: int = Field(ge=0)
    issued_at_ms: int = Field(ge=0)
    previous_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot: OwnerPrivateSourceAuthoritySnapshotV1
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    issuer_role: Literal["owner_private_source_head_issuer"] = "owner_private_source_head_issuer"
    key_purpose: Literal["owner_private_source_head_issuer_v1"] = (
        "owner_private_source_head_issuer_v1"
    )
    signature_scheme: Literal["ed25519"] = "ed25519"
    head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_ed25519: str = Field(pattern=r"^[0-9a-f]{128}$")
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivateSourceAuthorityHeadV1:
        if (
            type(self.snapshot) is not OwnerPrivateSourceAuthoritySnapshotV1
            or self.snapshot.registry_id != self.registry_id
            or self.snapshot.owner_path_discriminator != self.owner_path_discriminator
            or self.snapshot.epoch != self.epoch
            or self.snapshot.issued_at_ms != self.issued_at_ms
            or (self.epoch == 0) != (self.previous_head_sha256 == ZERO_SHA256)
            or (self.epoch == 0 and self.snapshot.active_bundle_revisions != ())
            or self.head_sha256 != owner_private_source_authority_head_v1_sha256(self)
        ):
            raise ValueError("owner-private source authority head conflicts")
        return self


def _canonical_material(
    value: BaseModel | Mapping[str, object], *, omitted: frozenset[str]
) -> bytes:
    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    material = {key: item for key, item in raw.items() if key not in omitted}
    return json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def owner_private_source_authority_snapshot_v1_sha256(
    snapshot: OwnerPrivateSourceAuthoritySnapshotV1 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _SNAPSHOT_DOMAIN + _canonical_material(snapshot, omitted=frozenset({"snapshot_sha256"}))
    ).hexdigest()


def owner_private_source_authority_head_v1_sha256(
    head: OwnerPrivateSourceAuthorityHeadV1 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _HEAD_DOMAIN
        + _canonical_material(head, omitted=frozenset({"head_sha256", "signature_ed25519"}))
    ).hexdigest()


class OwnerPrivateSourceHeadRejected(ValueError):
    def __init__(self) -> None:
        super().__init__("owner-private source authority head rejected")

    def __repr__(self) -> str:
        return "OwnerPrivateSourceHeadRejected()"


class InvalidOwnerPrivateSourceHeadStore(RuntimeError):
    def __init__(self) -> None:
        super().__init__("owner-private source authority store requires reconciliation")

    def __repr__(self) -> str:
        return "InvalidOwnerPrivateSourceHeadStore()"


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def parse_owner_private_source_authority_head_v1_json(
    value: bytes,
) -> OwnerPrivateSourceAuthorityHeadV1:
    try:
        if (
            type(value) is not bytes
            or not value
            or len(value) > MAX_OWNER_PRIVATE_SOURCE_HEAD_BYTES
        ):
            raise ValueError
        json.loads(value.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
        return OwnerPrivateSourceAuthorityHeadV1.model_validate_json(value)
    except Exception:
        raise OwnerPrivateSourceHeadRejected() from None


def _copy_verification_keys(verification_keys: Mapping[str, bytes]) -> dict[str, bytes]:
    copied: dict[str, bytes] = {}
    try:
        for index, (key_id, public_key) in enumerate(verification_keys.items()):
            if (
                index >= MAX_OWNER_PRIVATE_SOURCE_HEAD_KEYS
                or type(key_id) is not str
                or _KEY_ID.fullmatch(key_id) is None
                or type(public_key) is not bytes
                or len(public_key) != 32
                or key_id in copied
                or public_key in copied.values()
            ):
                raise ValueError
            copied[key_id] = bytes(public_key)
    except Exception:
        raise OwnerPrivateSourceHeadRejected() from None
    return copied


def verify_owner_private_source_authority_head_v1(
    head: OwnerPrivateSourceAuthorityHeadV1,
    *,
    verification_keys: Mapping[str, bytes],
) -> None:
    try:
        if type(head) is not OwnerPrivateSourceAuthorityHeadV1:
            raise ValueError
        canonical = OwnerPrivateSourceAuthorityHeadV1.model_validate(head.model_dump(mode="python"))
        if canonical != head:
            raise ValueError
        keys = _copy_verification_keys(verification_keys)
        key = keys.get(canonical.key_id)
        if key is None:
            raise ValueError
        Ed25519PublicKey.from_public_bytes(key).verify(
            bytes.fromhex(canonical.signature_ed25519),
            _HEAD_SIGNATURE_DOMAIN + canonical.head_sha256.encode("ascii"),
        )
    except Exception:
        raise OwnerPrivateSourceHeadRejected() from None


def require_owner_private_source_head_fresh(
    head: OwnerPrivateSourceAuthorityHeadV1, *, now_ms: int
) -> None:
    if (
        type(head) is not OwnerPrivateSourceAuthorityHeadV1
        or type(now_ms) is not int
        or isinstance(now_ms, bool)
        or now_ms < 0
        or head.issued_at_ms - now_ms > MAX_OWNER_PRIVATE_SOURCE_HEAD_FUTURE_SKEW_MS
        or now_ms - head.issued_at_ms > MAX_OWNER_PRIVATE_SOURCE_HEAD_AGE_MS
    ):
        raise OwnerPrivateSourceHeadRejected() from None


def validate_owner_private_source_head_successor(
    current: OwnerPrivateSourceAuthorityHeadV1,
    successor: OwnerPrivateSourceAuthorityHeadV1,
) -> None:
    try:
        if (
            type(current) is not OwnerPrivateSourceAuthorityHeadV1
            or type(successor) is not OwnerPrivateSourceAuthorityHeadV1
            or successor.registry_id != current.registry_id
            or successor.owner_path_discriminator != current.owner_path_discriminator
            or successor.previous_head_sha256 != current.head_sha256
            or successor.epoch != current.epoch + 1
            or successor.issued_at_ms <= current.issued_at_ms
        ):
            raise ValueError
        canonical_current = OwnerPrivateSourceAuthorityHeadV1.model_validate(
            current.model_dump(mode="python")
        )
        canonical_successor = OwnerPrivateSourceAuthorityHeadV1.model_validate(
            successor.model_dump(mode="python")
        )
        if canonical_current != current or canonical_successor != successor:
            raise ValueError
        current_active = current.snapshot.active_bundle_revisions
        successor_active = successor.snapshot.active_bundle_revisions
        if len(successor_active) != len(current_active) + 1:
            raise ValueError
        current_by_selector = {row.opaque_source_bundle_id: row for row in current_active}
        successor_by_selector = {row.opaque_source_bundle_id: row for row in successor_active}
        if (
            any(
                successor_by_selector.get(selector) != row
                for selector, row in current_by_selector.items()
            )
            or len(set(successor_by_selector) - set(current_by_selector)) != 1
        ):
            raise ValueError
    except Exception:
        raise OwnerPrivateSourceHeadRejected() from None


@dataclass(frozen=True, slots=True)
class _SourceHeadCasResultV1:
    applied: bool
    current: OwnerPrivateSourceAuthorityHeadV1


class _SourceHeadRepositoryV1:
    """Head persistence on a caller-owned connection and transaction."""

    owner_path_discriminator: str
    registry_id: str
    trusted_floor_sha256: str
    verification_keys: Mapping[str, bytes]

    __slots__ = (
        "_sealed",
        "owner_path_discriminator",
        "registry_id",
        "trusted_floor_sha256",
        "verification_keys",
    )

    def __init__(
        self,
        *,
        owner_path_discriminator: str,
        registry_id: str,
        verification_keys: Mapping[str, bytes],
        trusted_floor_sha256: str,
    ) -> None:
        if (
            type(owner_path_discriminator) is not str
            or _OWNER_PATH.fullmatch(owner_path_discriminator) is None
            or type(registry_id) is not str
            or _REGISTRY_ID.fullmatch(registry_id) is None
            or type(trusted_floor_sha256) is not str
            or _HEX64.fullmatch(trusted_floor_sha256) is None
        ):
            raise OwnerPrivateSourceHeadRejected() from None
        object.__setattr__(self, "_sealed", False)
        object.__setattr__(self, "owner_path_discriminator", owner_path_discriminator)
        object.__setattr__(self, "registry_id", registry_id)
        object.__setattr__(
            self,
            "verification_keys",
            MappingProxyType(_copy_verification_keys(verification_keys)),
        )
        object.__setattr__(self, "trusted_floor_sha256", trusted_floor_sha256)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("source head repository is immutable")
        object.__setattr__(self, name, value)

    @staticmethod
    def require_transaction(connection: sqlite3.Connection) -> None:
        if type(connection) is not sqlite3.Connection or not connection.in_transaction:
            raise InvalidOwnerPrivateSourceHeadStore() from None

    def admit_trusted_floor(
        self, connection: sqlite3.Connection, head: OwnerPrivateSourceAuthorityHeadV1
    ) -> None:
        self.require_transaction(connection)
        self._require_pinned_head(head)
        verify_owner_private_source_authority_head_v1(
            head, verification_keys=self.verification_keys
        )
        if not hmac.compare_digest(head.head_sha256, self.trusted_floor_sha256):
            raise OwnerPrivateSourceHeadRejected() from None
        try:
            current = connection.execute(
                "SELECT head_sha256 FROM owner_private_source_authority_current"
            ).fetchall()
            counts = connection.execute(
                "SELECT (SELECT COUNT(*) FROM owner_private_source_authority_heads), "
                "(SELECT COUNT(*) FROM owner_private_source_authority_current)"
            ).fetchone()
            if not current:
                if counts != (0, 0):
                    raise ValueError
                self._insert_head(connection, head)
                connection.execute(
                    "INSERT INTO owner_private_source_authority_current "
                    "(registry_id, owner_path_discriminator, head_sha256) VALUES (?, ?, ?)",
                    (self.registry_id, self.owner_path_discriminator, head.head_sha256),
                )
                self._load_stored_chain(connection)
                return
            chain = self._load_stored_chain(connection)
            if not any(hmac.compare_digest(row.head_sha256, head.head_sha256) for row in chain):
                raise ValueError
        except OwnerPrivateSourceHeadRejected:
            raise
        except Exception:
            raise InvalidOwnerPrivateSourceHeadStore() from None

    def load_current_to_floor(
        self, connection: sqlite3.Connection, *, now_ms: int
    ) -> tuple[OwnerPrivateSourceAuthorityHeadV1, ...]:
        self.require_transaction(connection)
        chain = self._load_stored_chain(connection)
        for index, head in enumerate(chain):
            if hmac.compare_digest(head.head_sha256, self.trusted_floor_sha256):
                require_owner_private_source_head_fresh(chain[0], now_ms=now_ms)
                return chain[: index + 1]
        raise InvalidOwnerPrivateSourceHeadStore() from None

    def insert_and_advance(
        self,
        connection: sqlite3.Connection,
        *,
        expected_head_sha256: str,
        next_head: OwnerPrivateSourceAuthorityHeadV1,
        now_ms: int,
    ) -> _SourceHeadCasResultV1:
        self.require_transaction(connection)
        if type(expected_head_sha256) is not str or _HEX64.fullmatch(expected_head_sha256) is None:
            raise OwnerPrivateSourceHeadRejected() from None
        self._require_pinned_head(next_head)
        verify_owner_private_source_authority_head_v1(
            next_head, verification_keys=self.verification_keys
        )
        require_owner_private_source_head_fresh(next_head, now_ms=now_ms)
        current = self.load_current_to_floor(connection, now_ms=now_ms)[0]
        if not hmac.compare_digest(current.head_sha256, expected_head_sha256):
            return _SourceHeadCasResultV1(applied=False, current=current)
        if hmac.compare_digest(next_head.head_sha256, current.head_sha256):
            return _SourceHeadCasResultV1(applied=False, current=current)
        retained = connection.execute(
            "SELECT COUNT(*) FROM owner_private_source_authority_heads"
        ).fetchone()
        if retained is None or int(retained[0]) >= MAX_OWNER_PRIVATE_SOURCE_HEAD_CHAIN:
            raise InvalidOwnerPrivateSourceHeadStore() from None
        validate_owner_private_source_head_successor(current, next_head)
        self._insert_head(connection, next_head)
        changed = connection.execute(
            "UPDATE owner_private_source_authority_current SET head_sha256 = ? "
            "WHERE registry_id = ? AND owner_path_discriminator = ? "
            "AND head_sha256 = ? RETURNING head_sha256",
            (
                next_head.head_sha256,
                self.registry_id,
                self.owner_path_discriminator,
                expected_head_sha256,
            ),
        ).fetchone()
        if changed is None:
            raise InvalidOwnerPrivateSourceHeadStore() from None
        return _SourceHeadCasResultV1(applied=True, current=next_head)

    def _require_pinned_head(self, head: OwnerPrivateSourceAuthorityHeadV1) -> None:
        if (
            type(head) is not OwnerPrivateSourceAuthorityHeadV1
            or head.registry_id != self.registry_id
            or head.owner_path_discriminator != self.owner_path_discriminator
        ):
            raise OwnerPrivateSourceHeadRejected() from None

    @staticmethod
    def _insert_head(
        connection: sqlite3.Connection, head: OwnerPrivateSourceAuthorityHeadV1
    ) -> None:
        connection.execute(
            "INSERT INTO owner_private_source_authority_heads "
            "(head_sha256, registry_id, owner_path_discriminator, epoch, "
            "previous_head_sha256, issued_at_ms, document_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                head.head_sha256,
                head.registry_id,
                head.owner_path_discriminator,
                head.epoch,
                head.previous_head_sha256,
                head.issued_at_ms,
                head.model_dump_json(),
            ),
        )

    def _load_stored_chain(
        self, connection: sqlite3.Connection
    ) -> tuple[OwnerPrivateSourceAuthorityHeadV1, ...]:
        try:
            current_rows = connection.execute(
                "SELECT h.head_sha256, h.registry_id, h.owner_path_discriminator, "
                "h.epoch, h.previous_head_sha256, h.issued_at_ms, h.document_json "
                "FROM owner_private_source_authority_current c "
                "JOIN owner_private_source_authority_heads h "
                "ON h.head_sha256 = c.head_sha256 "
                "WHERE c.registry_id = ? AND c.owner_path_discriminator = ?",
                (self.registry_id, self.owner_path_discriminator),
            ).fetchall()
            pointer_count = connection.execute(
                "SELECT COUNT(*) FROM owner_private_source_authority_current"
            ).fetchone()
            if len(current_rows) != 1 or pointer_count != (1,):
                raise ValueError
            chain: list[OwnerPrivateSourceAuthorityHeadV1] = []
            seen: set[str] = set()
            row: Sequence[object] | None = current_rows[0]
            while row is not None:
                head = self._decode_stored_head(row)
                if head.head_sha256 in seen:
                    raise ValueError
                seen.add(head.head_sha256)
                chain.append(head)
                if len(chain) > MAX_OWNER_PRIVATE_SOURCE_HEAD_CHAIN:
                    raise ValueError
                parent = connection.execute(
                    "SELECT head_sha256, registry_id, owner_path_discriminator, "
                    "epoch, previous_head_sha256, issued_at_ms, document_json "
                    "FROM owner_private_source_authority_heads "
                    "WHERE head_sha256 = ?",
                    (head.previous_head_sha256,),
                ).fetchone()
                row = parent
            for child, parent in zip(chain, chain[1:], strict=False):
                validate_owner_private_source_head_successor(parent, child)
            total = connection.execute(
                "SELECT COUNT(*) FROM owner_private_source_authority_heads"
            ).fetchone()
            if total is None or int(total[0]) != len(chain):
                raise ValueError
            if chain[-1].epoch != 0:
                raise ValueError
            return tuple(chain)
        except Exception:
            raise InvalidOwnerPrivateSourceHeadStore() from None

    def _decode_stored_head(self, row: Sequence[object]) -> OwnerPrivateSourceAuthorityHeadV1:
        try:
            if len(row) != 7:
                raise ValueError
            head = parse_owner_private_source_authority_head_v1_json(str(row[6]).encode("utf-8"))
            self._require_pinned_head(head)
            verify_owner_private_source_authority_head_v1(
                head, verification_keys=self.verification_keys
            )
            if (
                not hmac.compare_digest(head.head_sha256, str(row[0]))
                or not hmac.compare_digest(head.registry_id, str(row[1]))
                or not hmac.compare_digest(head.owner_path_discriminator, str(row[2]))
                or head.epoch != row[3]
                or not hmac.compare_digest(head.previous_head_sha256, str(row[4]))
                or head.issued_at_ms != row[5]
            ):
                raise ValueError
            return head
        except Exception:
            raise InvalidOwnerPrivateSourceHeadStore() from None


def private_source_head_store_module_source_sha256() -> str:
    """Attest this module AST while excluding only its self identity literal."""
    tree = ast.parse(Path(__file__).read_bytes(), filename=__file__)
    name = "PRIVATE_SOURCE_HEAD_STORE_MODULE_SOURCE_SHA256"
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
                raise RuntimeError("private source head source identity conflicts")
            assignments += 1
            statement.value = ast.Constant(value="<self-semantic-module-source-sha256>")
    stores = sum(
        isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == name
        for node in ast.walk(tree)
    )
    if assignments != 1 or stores != 1:
        raise RuntimeError("private source head source assignment conflicts")
    material = ast.dump(tree, annotate_fields=True, include_attributes=False).encode()
    return hashlib.sha256(
        b"antiek.midnight-oil.owner-private-source-head-semantic-source.v1\x00" + material
    ).hexdigest()


PRIVATE_SOURCE_HEAD_STORE_MODULE_SOURCE_SHA256 = (
    "c0ce82858d8fc0ca011bc76fc77fbc3da27f0035ba1ff6fd3224482bd6516da0"
)


def require_private_source_head_store_module_source() -> None:
    if not hmac.compare_digest(
        private_source_head_store_module_source_sha256(),
        PRIVATE_SOURCE_HEAD_STORE_MODULE_SOURCE_SHA256,
    ):
        raise RuntimeError("private source head implementation conflicts")


__all__ = [
    "MAX_OWNER_PRIVATE_SOURCE_BUNDLES",
    "MAX_OWNER_PRIVATE_SOURCE_HEAD_AGE_MS",
    "MAX_OWNER_PRIVATE_SOURCE_HEAD_BYTES",
    "MAX_OWNER_PRIVATE_SOURCE_HEAD_CHAIN",
    "MAX_OWNER_PRIVATE_SOURCE_HEAD_FUTURE_SKEW_MS",
    "MAX_OWNER_PRIVATE_SOURCE_HEAD_KEYS",
    "PRIVATE_SOURCE_HEAD_STORE_MODULE_SOURCE_SHA256",
    "ZERO_SHA256",
    "InvalidOwnerPrivateSourceHeadStore",
    "OpaqueSourceBundleRevisionV1",
    "OwnerPrivateSourceAuthorityHeadV1",
    "OwnerPrivateSourceAuthoritySnapshotV1",
    "OwnerPrivateSourceHeadRejected",
    "owner_private_source_authority_head_v1_sha256",
    "owner_private_source_authority_snapshot_v1_sha256",
    "parse_owner_private_source_authority_head_v1_json",
    "private_source_head_store_module_source_sha256",
    "require_owner_private_source_head_fresh",
    "require_private_source_head_store_module_source",
    "validate_owner_private_source_head_successor",
    "verify_owner_private_source_authority_head_v1",
]
