"""Physically unified canonical paid-lane authority checkpoint — Cycle34A.

Fixture-only, production-quarantined checkpoint that proves synthetic fixture
eligibility and reservation. It confers no live execution, accounting, transition,
checkpoint, sink or transport authority.
"""

from __future__ import annotations

import ast
import fcntl
import hashlib
import hmac
import inspect
import json
import os
import re
import secrets
import sqlite3
import stat
import struct
import threading
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, closing, suppress
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Never, Protocol, cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_source_authority import (
    OWNER_PRIVATE_SOURCE_VAULT_CONTRACT_V1_SHA256,
    PRIVATE_SOURCE_AUTHORITY_MODULE_SOURCE_SHA256,
    OwnerPrivateEncryptedSourceBundleV1,
    require_private_source_authority_module_source,
)
from .private_source_bundle_store import (
    OWNER_PRIVATE_SOURCE_EXACT_CURRENT_RESOLVER_CONTRACT_SHA256,
    PRIVATE_SOURCE_BUNDLE_STORE_MODULE_SOURCE_SHA256,
    require_private_source_bundle_store_module_source,
)
from .private_source_head_store import (
    PRIVATE_SOURCE_HEAD_STORE_MODULE_SOURCE_SHA256,
    OpaqueSourceBundleRevisionV1,
    OwnerPrivateSourceAuthoritySnapshotV1,
    owner_private_source_authority_head_v1_sha256,
    owner_private_source_authority_snapshot_v1_sha256,
    require_private_source_head_store_module_source,
)
from .private_source_head_store import (
    OwnerPrivateSourceAuthorityHeadV1 as SignedSourceHeadFixtureV1,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_I63: int = 2**63 - 1
MAX_CENTS: int = 1_000_000_000
MAX_DB_BYTES: int = 4_294_967_296
MAX_DB_PAGES: int = 1_048_576
MAX_PLAINTEXT_BYTES: int = 67_108_864
MAX_CIPHERTEXT_BYTES: int = 67_108_880
MAX_RECEIPT_PAIRS: int = 8
MAX_HEAD_CHAIN: int = 4_096
MAX_PENDING_SELECTORS: int = 64
MAX_ACTIVE_BUNDLES: int = 64
PENDING_TTL_MS: int = 300_000
COLLISION_RETRIES: int = 8
NONCE_COLLISION_RETRIES: int = 8
MAX_FIXTURE_VERIFICATION_KEYS: int = 16
MAX_REVOKED_PER_HEAD: int = 8
MAX_HEADS_PER_CHAIN: int = 4_096
MAX_ACTIVE_REVISIONS: int = 4_096
MAX_CUMULATIVE_REVOKED: int = 4_096
MAX_DOCUMENT_BYTES: int = 1_048_576
MAX_REVOCATION_SET_BYTES: int = 1_048_576
MAX_REVISION_SET_BYTES: int = 1_048_576
MAX_CANDIDATE_PLAINTEXT_BYTES: int = 1_048_576
MAX_SOURCE_PLAINTEXT_BYTES: int = 67_108_864
MAX_EVIDENCE_PLAINTEXT_BYTES: int = 67_108_864
MAX_MUTABLE_CURRENT_ROWS: int = 4_096
MAX_APPEND_ONLY_ROWS: int = 8_192
MAX_OPEN_HOLDS_PER_OWNER: int = 64
MAX_OPEN_HOLDS_GLOBAL: int = 1_024
MAX_STORES: int = 8
MAX_MIGRATION_ROWS: int = 1_024
MAX_CORPUS_BYTES: int = 256_000_000
MAX_LOCK_TIMEOUT_MS: int = 5_000
MAX_FUTURE_SKEW_MS: int = 300_000
MAX_PAST_ISSUANCE_SKEW_MS: int = 60_000
WITNESS_TTL_MS: int = 30_000
MARKER_TTL_MS: int = 300_000
PENDING_HANDLE_TTL_MS: int = 300_000
MAX_ACTIVE_HANDLES: int = 64

CONSTRUCTION_POLICY_V1: Mapping[str, object] = MappingProxyType(
    {
        "ordinary_constructor": "always-reject",
        "only_public_constructor": "open",
        "production_class_subclassable": False,
        "open_cls_identity": "exact-PrivatePaidLaneEligibilityCheckpointStoreV1",
        "production_fixture_writer_gate": "always-reject-until-certified-34d",
        "epoch0_runtime_activation_switch": False,
        "same_process_reflection_is_security_boundary": False,
        "stronger_same_process_boundary_requirement": "native-or-external",
    }
)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_HEX64: re.Pattern[str] = re.compile(r"^[0-9a-f]{64}$")
_OWNER_PATH: re.Pattern[str] = re.compile(r"^opspd1_[0-9a-f]{64}$")
_REGISTRY_ID: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_KEY_ID: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_KEY_VERSION: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SAFE_ASSERTION_ID: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._:@/-]{1,128}$")
_PRINTABLE_NON_WS: re.Pattern[str] = re.compile(r"^[!-~]{1,256}$")
_STORE_ID: re.Pattern[str] = re.compile(r"^mpstore1_[0-9a-f]{64}$")
_SOURCE_BUNDLE_ID: re.Pattern[str] = re.compile(r"^opsbs1_[0-9a-f]{64}$")
_SOURCE_SELECTOR: re.Pattern[str] = re.compile(r"^opsbs1_[0-9a-f]{64}$")
_EFFECT_BLIND: re.Pattern[str] = re.compile(r"^[0-9a-f]{64}$")
_MIGRATION_BASENAME: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._-]{1,160}$")

# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

_SEMANTIC_SOURCE_DOMAIN: bytes = (
    b"antiek.midnight-oil.private-paid-lane-checkpoint-semantic-source.v1\x00"
)
_CONTRACT_DOMAIN: bytes = b"antiek.midnight-oil.private-paid-lane-checkpoint-contract.v1\x00"
_PREDECESSOR_CYCLE33_CONTRACT_SHA256 = (
    "6da8daafe21e1ff320751750bcb67da159dab248938cfa8e4812a9d828f7106f"
)
_PREDECESSOR_CYCLE32_SOURCE_SHA256 = (
    "54409180c7ebac048027ecb3788711c7fc3fadcc940ec01663b363dbd2217c43"
)
_PREDECESSOR_CYCLE30_CAPABILITY_SHA256 = (
    "662eea6e32db95fcee1ba45f68959a89c8765076d423dfe606c3d6faf69cad1e"
)

# CapabilityV4 domains
_CAPABILITY_V4_DOCUMENT_DOMAIN: bytes = (
    b"antiek.midnight-oil.provider-capability-v4-fixture.document.v1\x00"
)
_CAPABILITY_V4_SIGNATURE_DOMAIN: bytes = (
    b"antiek.midnight-oil.provider-capability-v4-fixture.signature.v1\x00"
)

# Revocation domains
_REVOCATION_HEAD_DOMAIN: bytes = b"antiek.midnight-oil.provider-revocation-head-fixture.v1\x00"
_REVOCATION_SIGNATURE_DOMAIN: bytes = (
    b"antiek.midnight-oil.provider-revocation-head-fixture-signature.v1\x00"
)

# Source head domains (inherited Cycle32)
_SOURCE_SNAPSHOT_DOMAIN: bytes = (
    b"antiek.midnight-oil.owner-private-source-authority-snapshot.v1\x00"
)
_SOURCE_HEAD_DOMAIN: bytes = b"antiek.midnight-oil.owner-private-source-authority-head.v1\x00"
_SOURCE_SIGNATURE_DOMAIN: bytes = (
    b"antiek.midnight-oil.owner-private-source-authority-signature.v1\x00"
)

# Source AEAD domain (inherited Cycle31)
_SOURCE_AEAD_DOMAIN: bytes = b"antiek.midnight-oil.owner-private-source-aead.v1\x00"

# Cycle34 AES purposes
_CANDIDATE_AES_DOMAIN: bytes = b"antiek.midnight-oil.private-paid-candidate-aes256gcm.v1\x00"
_EVIDENCE_AES_DOMAIN: bytes = b"antiek.midnight-oil.private-paid-evidence-aes256gcm.v1\x00"

# HMAC blind domains
_BLIND_DOMAINS: dict[str, bytes] = {
    "consent_v1": b"antiek.midnight-oil.private-paid-blind.consent.v1\x00",
    "cursor_v1": b"antiek.midnight-oil.private-paid-blind.cursor.v1\x00",
    "account_v1": b"antiek.midnight-oil.private-paid-blind.account.v1\x00",
    "project_v1": b"antiek.midnight-oil.private-paid-blind.project.v1\x00",
    "request_v1": b"antiek.midnight-oil.private-paid-blind.request.v1\x00",
    "idempotency_v1": b"antiek.midnight-oil.private-paid-blind.idempotency.v1\x00",
    "effect_v1": b"antiek.midnight-oil.private-paid-blind.effect.v1\x00",
    "test_claim_v1": b"antiek.midnight-oil.private-paid-blind.test-claim.v1\x00",
}
_BLIND_PURPOSES = Literal[
    "consent_v1",
    "cursor_v1",
    "account_v1",
    "project_v1",
    "request_v1",
    "idempotency_v1",
    "effect_v1",
    "test_claim_v1",
]

# Pending source handle domain
_PENDING_SOURCE_DOMAIN: bytes = b"antiek.midnight-oil.private-paid-pending-source.v1\x00"
_MIGRATION_ROW_DOMAIN: bytes = b"antiek.midnight-oil.private-paid-migration-row.v1\x00"
_SOURCE_MANIFEST_DOMAIN: bytes = b"antiek.midnight-oil.private-paid-source-manifest.v1\x00"
_COPY_AUDIT_DOMAIN: bytes = b"antiek.midnight-oil.private-paid-copy-audit.v1\x00"
_COPY_BUDGET_INVARIANT_DOMAIN: bytes = (
    b"antiek.midnight-oil.private-paid-copy-budget-invariant.v1\x00"
)
_COPY_CHAIN_AUDIT_DOMAIN: bytes = b"antiek.midnight-oil.private-paid-copy-chain-audit.v1\x00"
_CUTOVER_MARKER_DOMAIN: bytes = b"antiek.midnight-oil.private-paid-cutover-marker.v1\x00"
_CUTOVER_MARKER_SIGNATURE_DOMAIN: bytes = (
    b"antiek.midnight-oil.private-paid-cutover-marker-signature.v1\x00"
)
_EXTERNAL_PIN_DOMAIN: bytes = b"antiek.midnight-oil.private-paid-external-pin.v1\x00"
_READY_DOMAIN: bytes = b"antiek.midnight-oil.private-paid-ready.v1\x00"
_SOURCE_STORE_ROWS_DOMAIN: bytes = (
    b"antiek.midnight-oil.private-paid-source-store-ordered-rows.v1\x00"
)
_MIGRATION_LIFECYCLE_STATE_DOMAIN: bytes = (
    b"antiek.midnight-oil.private-paid-migration-state.v1\x00"
)
_MIGRATION_LIFECYCLE_SIGNATURE_DOMAIN: bytes = (
    b"antiek.midnight-oil.private-paid-migration-state-signature.v1\x00"
)
_MIGRATION_RECOVERY_TICKET_DOMAIN: bytes = (
    b"antiek.midnight-oil.private-paid-recovery-ticket.v1\x00"
)
_MIGRATION_RECOVERY_TICKET_SIGNATURE_DOMAIN: bytes = (
    b"antiek.midnight-oil.private-paid-recovery-ticket-signature.v1\x00"
)
_MIGRATION_RECOVERY_ADMISSION_DOMAIN: bytes = (
    b"antiek.midnight-oil.private-paid-recovery-admission.v1\x00"
)
_MIGRATION_RECOVERY_ADMISSION_SIGNATURE_DOMAIN: bytes = (
    b"antiek.midnight-oil.private-paid-recovery-admission-signature.v1\x00"
)

_MIGRATION_ROLE_TABLES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "owner_private_source_v1": (
            "source_heads",
            "source_current",
            "encrypted_source_bundles",
        ),
        "paid_lane_fixture_v1": (
            "owner_operations",
            "consent_claims",
            "queue_leases",
            "budget_accounts",
        ),
        "provider_authority_v4": (
            "provider_capabilities_v4",
            "provider_revocation_heads",
            "provider_revocation_current",
        ),
    }
)
_MIGRATION_CHILD_FINAL_VERSION: int = 6
_MIGRATION_ROLE_SCHEMA_TABLES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "owner_private_source_v1": (
            "adapter_state",
            "source_heads",
            "source_current",
            "encrypted_source_bundles",
            "mutator_attempts",
        ),
        "paid_lane_fixture_v1": (
            "adapter_state",
            "owner_operations",
            "consent_claims",
            "queue_leases",
            "budget_accounts",
            "paid_admissions",
            "mutator_attempts",
        ),
        "provider_authority_v4": (
            "adapter_state",
            "provider_capabilities_v4",
            "provider_revocation_heads",
            "provider_revocation_current",
            "mutator_attempts",
        ),
    }
)


def _migration_role_schema_sha256(role: str) -> str:
    tables = _MIGRATION_ROLE_SCHEMA_TABLES.get(role)
    if tables is None:
        raise ValueError("unknown migration source role")
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(_migration_role_schema_sql(role))
        return _migration_role_schema_sha256_from_connection(
            connection,
            role,
            required_pragmas={
                "foreign_keys": 1,
                "journal_mode": "wal",
                "trusted_schema": 0,
                "user_version": 1,
            },
        )
    finally:
        connection.close()


def _migration_role_schema_sql(role: str) -> str:
    tables = _MIGRATION_ROLE_SCHEMA_TABLES.get(role)
    if tables is None:
        raise ValueError("unknown migration source role")
    statements = [
        "CREATE TABLE adapter_state(singleton INTEGER PRIMARY KEY CHECK(singleton=1),"
        "admission_enabled INTEGER NOT NULL CHECK(admission_enabled IN (0,1)),"
        "writer_enabled INTEGER NOT NULL CHECK(writer_enabled IN (0,1)),"
        "active_invocations INTEGER NOT NULL CHECK(active_invocations>=0),"
        "open_accounting_cents INTEGER NOT NULL CHECK(open_accounting_cents>=0),"
        "version INTEGER NOT NULL CHECK(version>=1))",
        "CREATE TABLE mutator_attempts(name TEXT PRIMARY KEY,planted_at INTEGER NOT NULL)",
    ]
    for table in tables:
        if table in {"adapter_state", "mutator_attempts"}:
            continue
        statements.append(f'CREATE TABLE "{table}"(id TEXT PRIMARY KEY,payload BLOB)')
        if role == "paid_lane_fixture_v1" and table == "paid_admissions":
            statements.append(
                'CREATE TRIGGER paid_admissions_admission_gate BEFORE INSERT ON "paid_admissions" '
                "WHEN (SELECT admission_enabled FROM adapter_state WHERE singleton=1)=0 "
                "BEGIN SELECT RAISE(ABORT,'admission denied'); END"
            )
        statements.append(
            f'CREATE TRIGGER "{table}_writer_gate" BEFORE INSERT ON "{table}" '
            "WHEN (SELECT writer_enabled FROM adapter_state WHERE singleton=1)=0 "
            "BEGIN SELECT RAISE(ABORT,'writer revoked'); END"
        )
        for verb in ("UPDATE", "DELETE"):
            statements.append(
                f'CREATE TRIGGER "{table}_{verb.lower()}_writer_gate" BEFORE {verb} ON "{table}" '
                "WHEN (SELECT writer_enabled FROM adapter_state WHERE singleton=1)=0 "
                "BEGIN SELECT RAISE(ABORT,'writer revoked'); END"
            )
    return ";".join(statements) + ";"


def _migration_role_schema_sha256_from_connection(
    connection: sqlite3.Connection,
    role: str,
    *,
    required_pragmas: Mapping[str, int | str] | None = None,
) -> str:
    tables = _MIGRATION_ROLE_SCHEMA_TABLES.get(role)
    if tables is None:
        raise ValueError("unknown migration source role")
    pragmas: Mapping[str, int | str]
    if required_pragmas is None:
        pragmas = {
            "foreign_keys": int(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
            "journal_mode": str(connection.execute("PRAGMA journal_mode").fetchone()[0]),
            "trusted_schema": int(connection.execute("PRAGMA trusted_schema").fetchone()[0]),
            "user_version": int(connection.execute("PRAGMA user_version").fetchone()[0]),
        }
    else:
        pragmas = required_pragmas
    master = [
        list(row)
        for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' "
            "ORDER BY type,name"
        )
    ]
    table_metadata = []
    for table in tables:
        table_metadata.append(
            {
                "table": table,
                "columns": [
                    list(row) for row in connection.execute(f'PRAGMA table_info("{table}")')
                ],
                "foreign_keys": [
                    list(row) for row in connection.execute(f'PRAGMA foreign_key_list("{table}")')
                ],
                "indexes": [
                    list(row) for row in connection.execute(f'PRAGMA index_list("{table}")')
                ],
            }
        )
    material = {"role": role, "master": master, "tables": table_metadata, "pragmas": pragmas}
    return hashlib.sha256(
        b"antiek.midnight-oil.private-paid-source-store-schema.v1\x00" + _canonical_json(material)
    ).hexdigest()


def _migration_barrier_id(freeze_nonce: str) -> str:
    if not _HEX64.fullmatch(freeze_nonce):
        raise ValueError("migration freeze nonce")
    return (
        "barrier1_"
        + hashlib.sha256(
            b"antiek.midnight-oil.private-paid-native-writer-barrier.v1\x00"
            + bytes.fromhex(freeze_nonce)
        ).hexdigest()
    )


# ---------------------------------------------------------------------------
# Normative _SCHEMA_SQL_V1 — 18 tables, 13 explicit indexes
# ---------------------------------------------------------------------------

_SCHEMA_SQL_V1: str = """\
CREATE TABLE paid_lane_schema (
  singleton INTEGER NOT NULL PRIMARY KEY CHECK (singleton = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 1),
  migration_epoch INTEGER NOT NULL DEFAULT 0 CHECK (migration_epoch IN (0,1)),
  store_id TEXT NOT NULL UNIQUE,
  semantic_source_sha256 TEXT NOT NULL,
  contract_sha256 TEXT NOT NULL,
  cutover_marker_sha256 TEXT DEFAULT NULL,
  created_at_ms INTEGER NOT NULL CHECK (created_at_ms >= 0),
  CHECK ((migration_epoch = 0 AND cutover_marker_sha256 IS NULL) OR
         (migration_epoch = 1 AND cutover_marker_sha256 IS NOT NULL))
) STRICT;

CREATE TABLE provider_capabilities_v4 (
  capability_sha256 TEXT NOT NULL PRIMARY KEY,
  capability_id TEXT NOT NULL UNIQUE,
  owner_path_discriminator TEXT NOT NULL,
  revocation_registry_id TEXT NOT NULL,
  revocation_trusted_floor_sha256 TEXT NOT NULL,
  issued_at_ms INTEGER NOT NULL CHECK (issued_at_ms >= 0),
  expires_at_ms INTEGER NOT NULL CHECK (expires_at_ms > issued_at_ms),
  key_id TEXT NOT NULL,
  document_json BLOB NOT NULL CHECK (length(document_json) BETWEEN 1 AND 1048576),
  signature_ed25519 TEXT NOT NULL,
  UNIQUE (owner_path_discriminator, capability_sha256),
  UNIQUE (owner_path_discriminator, capability_sha256, revocation_registry_id)
) STRICT;

CREATE TABLE provider_revocation_heads (
  head_sha256 TEXT NOT NULL PRIMARY KEY,
  registry_id TEXT NOT NULL,
  owner_path_discriminator TEXT NOT NULL,
  epoch INTEGER NOT NULL CHECK (epoch >= 0),
  predecessor_head_sha256 TEXT DEFAULT NULL
    REFERENCES provider_revocation_heads(head_sha256) ON DELETE RESTRICT,
  issued_at_ms INTEGER NOT NULL CHECK (issued_at_ms >= 0),
  revoked_capability_hashes_json BLOB NOT NULL
    CHECK (length(revoked_capability_hashes_json) BETWEEN 2 AND 1048576),
  key_id TEXT NOT NULL,
  document_json BLOB NOT NULL CHECK (length(document_json) BETWEEN 1 AND 1048576),
  signature_ed25519 TEXT NOT NULL,
  UNIQUE (registry_id, owner_path_discriminator, epoch),
  UNIQUE (registry_id, owner_path_discriminator, head_sha256, epoch),
  CHECK ((epoch = 0 AND predecessor_head_sha256 IS NULL) OR
         (epoch > 0 AND predecessor_head_sha256 IS NOT NULL))
) STRICT;

CREATE TABLE provider_revocation_current (
  registry_id TEXT NOT NULL,
  owner_path_discriminator TEXT NOT NULL,
  head_sha256 TEXT NOT NULL,
  epoch INTEGER NOT NULL CHECK (epoch >= 0),
  state_version INTEGER NOT NULL CHECK (state_version >= 1),
  updated_at_ms INTEGER NOT NULL CHECK (updated_at_ms >= 0),
  PRIMARY KEY (registry_id, owner_path_discriminator),
  FOREIGN KEY (registry_id, owner_path_discriminator, head_sha256, epoch)
    REFERENCES provider_revocation_heads(registry_id, owner_path_discriminator, head_sha256, epoch)
    ON DELETE RESTRICT
) STRICT;

CREATE TABLE source_heads (
  head_sha256 TEXT NOT NULL PRIMARY KEY,
  registry_id TEXT NOT NULL,
  owner_path_discriminator TEXT NOT NULL,
  epoch INTEGER NOT NULL CHECK (epoch >= 0),
  previous_head_sha256 TEXT NOT NULL,
  issued_at_ms INTEGER NOT NULL CHECK (issued_at_ms >= 0),
  active_bundle_revisions_json BLOB NOT NULL
    CHECK (length(active_bundle_revisions_json) BETWEEN 2 AND 1048576),
  snapshot_json BLOB NOT NULL CHECK (length(snapshot_json) BETWEEN 1 AND 1048576),
  key_id TEXT NOT NULL,
  document_json BLOB NOT NULL CHECK (length(document_json) BETWEEN 1 AND 1048576),
  signature_ed25519 TEXT NOT NULL,
  UNIQUE (registry_id, owner_path_discriminator, epoch),
  UNIQUE (registry_id, owner_path_discriminator, head_sha256, epoch)
) STRICT;

CREATE TABLE source_current (
  registry_id TEXT NOT NULL,
  owner_path_discriminator TEXT NOT NULL,
  head_sha256 TEXT NOT NULL,
  epoch INTEGER NOT NULL CHECK (epoch >= 0),
  state_version INTEGER NOT NULL CHECK (state_version >= 1),
  updated_at_ms INTEGER NOT NULL CHECK (updated_at_ms >= 0),
  PRIMARY KEY (registry_id, owner_path_discriminator),
  FOREIGN KEY (registry_id, owner_path_discriminator, head_sha256, epoch)
    REFERENCES source_heads(registry_id, owner_path_discriminator, head_sha256, epoch)
    ON DELETE RESTRICT
) STRICT;

CREATE TABLE encrypted_source_bundles (
  opaque_source_bundle_id TEXT NOT NULL PRIMARY KEY,
  owner_path_discriminator TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'sealed' CHECK (state = 'sealed'),
  row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version = 1),
  aead_suite TEXT NOT NULL DEFAULT 'aes-256-gcm' CHECK (aead_suite = 'aes-256-gcm'),
  key_version TEXT NOT NULL,
  nonce_length INTEGER NOT NULL DEFAULT 12 CHECK (nonce_length = 12),
  nonce BLOB NOT NULL CHECK (length(nonce) = 12),
  aad_schema TEXT NOT NULL DEFAULT 'owner_private_source_aad_v1'
    CHECK (aad_schema = 'owner_private_source_aad_v1'),
  aad_json BLOB NOT NULL CHECK (length(aad_json) BETWEEN 1 AND 4096),
  ciphertext_schema TEXT NOT NULL DEFAULT 'owner_private_encrypted_source_bundle_v1_json',
  ciphertext_type TEXT NOT NULL DEFAULT 'application/json',
  ciphertext_length INTEGER NOT NULL CHECK (ciphertext_length BETWEEN 16 AND 67108880),
  ciphertext BLOB NOT NULL CHECK (length(ciphertext) = ciphertext_length),
  UNIQUE (owner_path_discriminator, opaque_source_bundle_id),
  UNIQUE (owner_path_discriminator, key_version, nonce)
) STRICT;

CREATE TABLE owner_operations (
  owner_path_discriminator TEXT NOT NULL,
  operation_id TEXT NOT NULL,
  job_id TEXT NOT NULL,
  execution_id TEXT NOT NULL,
  stage_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('queued','running','cancel_requested','cancelled','terminal')),
  state_version INTEGER NOT NULL CHECK (state_version >= 1),
  cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0,1)),
  cancellation_version INTEGER NOT NULL DEFAULT 0 CHECK (cancellation_version >= 0),
  created_at_ms INTEGER NOT NULL CHECK (created_at_ms >= 0),
  updated_at_ms INTEGER NOT NULL CHECK (updated_at_ms >= created_at_ms),
  PRIMARY KEY (owner_path_discriminator, operation_id),
  UNIQUE (owner_path_discriminator, job_id, execution_id, stage_id),
  CHECK ((cancel_requested = 0 AND cancellation_version = 0 AND state NOT IN ('cancel_requested','cancelled')) OR
         (cancel_requested = 1 AND cancellation_version >= 1 AND state IN ('cancel_requested','cancelled')))
) STRICT;

CREATE TABLE consent_claims (
  owner_path_discriminator TEXT NOT NULL,
  consent_blind_id BLOB NOT NULL CHECK (length(consent_blind_id) = 32),
  approved_ceiling_cents INTEGER NOT NULL CHECK (approved_ceiling_cents BETWEEN 1 AND 1000000000),
  version INTEGER NOT NULL CHECK (version >= 1),
  issued_at_ms INTEGER NOT NULL CHECK (issued_at_ms >= 0),
  expires_at_ms INTEGER NOT NULL CHECK (expires_at_ms > issued_at_ms),
  state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open','withdrawn','claimed')),
  claimed_effect_blind_id BLOB DEFAULT NULL CHECK (claimed_effect_blind_id IS NULL OR length(claimed_effect_blind_id) = 32),
  claimed_at_ms INTEGER DEFAULT NULL CHECK (claimed_at_ms IS NULL OR claimed_at_ms >= issued_at_ms),
  updated_at_ms INTEGER NOT NULL CHECK (updated_at_ms >= issued_at_ms),
  PRIMARY KEY (owner_path_discriminator, consent_blind_id),
  UNIQUE (owner_path_discriminator, claimed_effect_blind_id),
  CHECK ((state IN ('open','withdrawn') AND claimed_effect_blind_id IS NULL AND claimed_at_ms IS NULL) OR
         (state = 'claimed' AND claimed_effect_blind_id IS NOT NULL AND claimed_at_ms IS NOT NULL))
) STRICT;

CREATE TABLE queue_leases (
  owner_path_discriminator TEXT NOT NULL,
  queue_operation_id TEXT NOT NULL,
  lease_owner TEXT NOT NULL,
  generation INTEGER NOT NULL CHECK (generation >= 1),
  cursor_blind_id BLOB NOT NULL CHECK (length(cursor_blind_id) = 32),
  row_version INTEGER NOT NULL CHECK (row_version >= 1),
  acquired_at_ms INTEGER NOT NULL CHECK (acquired_at_ms >= 0),
  exclusive_until_ms INTEGER NOT NULL CHECK (exclusive_until_ms > acquired_at_ms),
  updated_at_ms INTEGER NOT NULL CHECK (updated_at_ms >= acquired_at_ms),
  PRIMARY KEY (owner_path_discriminator, queue_operation_id),
  UNIQUE (owner_path_discriminator, queue_operation_id, lease_owner, generation, cursor_blind_id)
) STRICT;

CREATE TABLE budget_accounts (
  owner_path_discriminator TEXT NOT NULL,
  account_scope_blind_id BLOB NOT NULL CHECK (length(account_scope_blind_id) = 32),
  project_scope_blind_id BLOB NOT NULL CHECK (length(project_scope_blind_id) = 32),
  approved_ceiling_cents INTEGER NOT NULL CHECK (approved_ceiling_cents BETWEEN 1 AND 1000000000),
  confirmed_cents INTEGER NOT NULL DEFAULT 0 CHECK (confirmed_cents BETWEEN 0 AND 1000000000),
  open_cents INTEGER NOT NULL DEFAULT 0 CHECK (open_cents BETWEEN 0 AND 1000000000),
  unknown_cents INTEGER NOT NULL DEFAULT 0 CHECK (unknown_cents BETWEEN 0 AND 1000000000),
  row_version INTEGER NOT NULL CHECK (row_version >= 1),
  updated_at_ms INTEGER NOT NULL CHECK (updated_at_ms >= 0),
  PRIMARY KEY (owner_path_discriminator, account_scope_blind_id, project_scope_blind_id),
  CHECK (confirmed_cents + open_cents + unknown_cents <= approved_ceiling_cents)
) STRICT;

CREATE TABLE logical_effects (
  effect_blind_id BLOB NOT NULL PRIMARY KEY CHECK (length(effect_blind_id) = 32),
  owner_path_discriminator TEXT NOT NULL,
  operation_id TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'admission_committed'
    CHECK (state IN ('admission_committed','cancellation_committed','cancelled_proven_not_dispatched',
                     'attempt_started','proven_no_network','returned','settled',
                     'private_rejected_paid','paid_unknown')),
  state_version INTEGER NOT NULL DEFAULT 1 CHECK (state_version >= 1),
  created_at_ms INTEGER NOT NULL CHECK (created_at_ms >= 0),
  updated_at_ms INTEGER NOT NULL CHECK (updated_at_ms >= created_at_ms),
  UNIQUE (owner_path_discriminator, effect_blind_id),
  FOREIGN KEY (owner_path_discriminator, operation_id)
    REFERENCES owner_operations(owner_path_discriminator, operation_id) ON DELETE RESTRICT
) STRICT;

CREATE TABLE paid_admissions (
  admission_id TEXT NOT NULL PRIMARY KEY,
  effect_blind_id BLOB NOT NULL UNIQUE CHECK (length(effect_blind_id) = 32),
  owner_path_discriminator TEXT NOT NULL,
  provider_capability_id TEXT NOT NULL,
  provider_capability_sha256 TEXT NOT NULL,
  provider_revocation_registry_id TEXT NOT NULL,
  provider_revocation_head_sha256 TEXT NOT NULL,
  provider_revocation_epoch INTEGER NOT NULL CHECK (provider_revocation_epoch >= 0),
  source_registry_id TEXT NOT NULL,
  source_head_sha256 TEXT NOT NULL,
  source_epoch INTEGER NOT NULL CHECK (source_epoch >= 0),
  opaque_source_bundle_id TEXT NOT NULL,
  source_row_version INTEGER NOT NULL CHECK (source_row_version = 1),
  operation_id TEXT NOT NULL,
  owner_operation_state_version INTEGER NOT NULL CHECK (owner_operation_state_version >= 1),
  owner_operation_cancellation_version INTEGER NOT NULL DEFAULT 0 CHECK (owner_operation_cancellation_version = 0),
  consent_blind_id BLOB NOT NULL CHECK (length(consent_blind_id) = 32),
  consent_version INTEGER NOT NULL CHECK (consent_version >= 1),
  queue_operation_id TEXT NOT NULL,
  lease_owner TEXT NOT NULL,
  lease_generation INTEGER NOT NULL CHECK (lease_generation >= 1),
  cursor_blind_id BLOB NOT NULL CHECK (length(cursor_blind_id) = 32),
  account_scope_blind_id BLOB NOT NULL CHECK (length(account_scope_blind_id) = 32),
  project_scope_blind_id BLOB NOT NULL CHECK (length(project_scope_blind_id) = 32),
  budget_row_version INTEGER NOT NULL CHECK (budget_row_version >= 1),
  projected_max_cents INTEGER NOT NULL CHECK (projected_max_cents BETWEEN 1 AND 1000000000),
  request_material_blind_id BLOB NOT NULL CHECK (length(request_material_blind_id) = 32),
  provider_idempotency_blind_id BLOB NOT NULL CHECK (length(provider_idempotency_blind_id) = 32),
  state TEXT NOT NULL DEFAULT 'admission_committed' CHECK (state = 'admission_committed'),
  aead_suite TEXT NOT NULL DEFAULT 'aes-256-gcm' CHECK (aead_suite = 'aes-256-gcm'),
  key_version TEXT NOT NULL,
  nonce_length INTEGER NOT NULL DEFAULT 12 CHECK (nonce_length = 12),
  nonce BLOB NOT NULL CHECK (length(nonce) = 12),
  aad_schema TEXT NOT NULL DEFAULT 'private_paid_candidate_aad_v1',
  aad_json BLOB NOT NULL CHECK (length(aad_json) BETWEEN 1 AND 4096),
  ciphertext_schema TEXT NOT NULL DEFAULT 'unified_paid_admission_candidate_v1_json',
  ciphertext_type TEXT NOT NULL DEFAULT 'application/json',
  ciphertext_length INTEGER NOT NULL CHECK (ciphertext_length BETWEEN 17 AND 1048592),
  ciphertext BLOB NOT NULL CHECK (length(ciphertext) = ciphertext_length),
  admitted_at_ms INTEGER NOT NULL CHECK (admitted_at_ms >= 0),
  UNIQUE (owner_path_discriminator, request_material_blind_id),
  UNIQUE (owner_path_discriminator, provider_idempotency_blind_id),
  UNIQUE (owner_path_discriminator, key_version, nonce),
  FOREIGN KEY (effect_blind_id) REFERENCES logical_effects(effect_blind_id) ON DELETE RESTRICT,
  FOREIGN KEY (owner_path_discriminator, provider_capability_sha256,
               provider_revocation_registry_id)
    REFERENCES provider_capabilities_v4(owner_path_discriminator, capability_sha256,
                                        revocation_registry_id) ON DELETE RESTRICT,
  FOREIGN KEY (provider_revocation_registry_id, owner_path_discriminator,
               provider_revocation_head_sha256, provider_revocation_epoch)
    REFERENCES provider_revocation_heads(registry_id, owner_path_discriminator, head_sha256, epoch)
    ON DELETE RESTRICT,
  FOREIGN KEY (source_registry_id, owner_path_discriminator, source_head_sha256, source_epoch)
    REFERENCES source_heads(registry_id, owner_path_discriminator, head_sha256, epoch)
    ON DELETE RESTRICT,
  FOREIGN KEY (owner_path_discriminator, opaque_source_bundle_id)
    REFERENCES encrypted_source_bundles(owner_path_discriminator, opaque_source_bundle_id)
    ON DELETE RESTRICT,
  FOREIGN KEY (owner_path_discriminator, operation_id)
    REFERENCES owner_operations(owner_path_discriminator, operation_id) ON DELETE RESTRICT,
  FOREIGN KEY (owner_path_discriminator, consent_blind_id)
    REFERENCES consent_claims(owner_path_discriminator, consent_blind_id) ON DELETE RESTRICT,
  FOREIGN KEY (owner_path_discriminator, queue_operation_id, lease_owner, lease_generation, cursor_blind_id)
    REFERENCES queue_leases(owner_path_discriminator, queue_operation_id, lease_owner, generation, cursor_blind_id)
    ON DELETE RESTRICT,
  FOREIGN KEY (owner_path_discriminator, account_scope_blind_id, project_scope_blind_id)
    REFERENCES budget_accounts(owner_path_discriminator, account_scope_blind_id, project_scope_blind_id)
    ON DELETE RESTRICT
) STRICT;

CREATE TABLE budget_holds (
  hold_id TEXT NOT NULL PRIMARY KEY,
  effect_blind_id BLOB NOT NULL UNIQUE CHECK (length(effect_blind_id) = 32),
  admission_id TEXT NOT NULL UNIQUE,
  owner_path_discriminator TEXT NOT NULL,
  account_scope_blind_id BLOB NOT NULL CHECK (length(account_scope_blind_id) = 32),
  project_scope_blind_id BLOB NOT NULL CHECK (length(project_scope_blind_id) = 32),
  projected_cents INTEGER NOT NULL CHECK (projected_cents BETWEEN 1 AND 1000000000),
  known_charge_cents INTEGER DEFAULT NULL CHECK (known_charge_cents IS NULL OR known_charge_cents BETWEEN 0 AND projected_cents),
  state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open','released','confirmed','unknown')),
  row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
  created_at_ms INTEGER NOT NULL CHECK (created_at_ms >= 0),
  updated_at_ms INTEGER NOT NULL CHECK (updated_at_ms >= created_at_ms),
  FOREIGN KEY (effect_blind_id) REFERENCES logical_effects(effect_blind_id) ON DELETE RESTRICT,
  FOREIGN KEY (admission_id) REFERENCES paid_admissions(admission_id) ON DELETE RESTRICT,
  FOREIGN KEY (owner_path_discriminator, account_scope_blind_id, project_scope_blind_id)
    REFERENCES budget_accounts(owner_path_discriminator, account_scope_blind_id, project_scope_blind_id)
    ON DELETE RESTRICT,
  CHECK ((state IN ('open','released','unknown') AND known_charge_cents IS NULL) OR
         (state = 'confirmed' AND known_charge_cents IS NOT NULL))
) STRICT;

CREATE TABLE paid_attempts (
  attempt_id TEXT NOT NULL PRIMARY KEY,
  admission_id TEXT NOT NULL UNIQUE,
  effect_blind_id BLOB NOT NULL UNIQUE CHECK (length(effect_blind_id) = 32),
  owner_path_discriminator TEXT NOT NULL,
  attempt_ordinal INTEGER NOT NULL DEFAULT 1 CHECK (attempt_ordinal = 1),
  provider_idempotency_blind_id BLOB NOT NULL CHECK (length(provider_idempotency_blind_id) = 32),
  current_state TEXT NOT NULL DEFAULT 'attempt_started'
    CHECK (current_state IN ('attempt_started','proven_no_network','returned','settled',
                             'private_rejected_paid','paid_unknown')),
  state_version INTEGER NOT NULL DEFAULT 1 CHECK (state_version >= 1),
  current_event_sequence INTEGER NOT NULL DEFAULT 1 CHECK (current_event_sequence >= 1),
  started_at_ms INTEGER NOT NULL CHECK (started_at_ms >= 0),
  updated_at_ms INTEGER NOT NULL CHECK (updated_at_ms >= started_at_ms),
  UNIQUE (owner_path_discriminator, provider_idempotency_blind_id),
  FOREIGN KEY (admission_id) REFERENCES paid_admissions(admission_id) ON DELETE RESTRICT,
  FOREIGN KEY (effect_blind_id) REFERENCES logical_effects(effect_blind_id) ON DELETE RESTRICT
) STRICT;

CREATE TABLE paid_effect_transitions (
  transition_id TEXT NOT NULL PRIMARY KEY,
  effect_blind_id BLOB NOT NULL CHECK (length(effect_blind_id) = 32),
  sequence INTEGER NOT NULL CHECK (sequence >= 1),
  prior_state TEXT DEFAULT NULL
    CHECK (prior_state IS NULL OR prior_state IN ('admission_committed','cancellation_committed',
           'cancelled_proven_not_dispatched','attempt_started','proven_no_network','returned',
           'settled','private_rejected_paid','paid_unknown')),
  state TEXT NOT NULL
    CHECK (state IN ('admission_committed','cancellation_committed',
           'cancelled_proven_not_dispatched','attempt_started','proven_no_network','returned',
           'settled','private_rejected_paid','paid_unknown')),
  prior_state_version INTEGER NOT NULL CHECK (prior_state_version >= 0),
  state_version INTEGER NOT NULL CHECK (state_version = prior_state_version + 1),
  attempt_id TEXT DEFAULT NULL REFERENCES paid_attempts(attempt_id) ON DELETE RESTRICT,
  owner_operation_state_version INTEGER NOT NULL CHECK (owner_operation_state_version >= 1),
  owner_operation_cancel_requested INTEGER NOT NULL CHECK (owner_operation_cancel_requested IN (0,1)),
  owner_operation_cancellation_version INTEGER NOT NULL CHECK (owner_operation_cancellation_version >= 0),
  transitioned_at_ms INTEGER NOT NULL CHECK (transitioned_at_ms >= 0),
  UNIQUE (effect_blind_id, sequence),
  UNIQUE (effect_blind_id, state_version),
  FOREIGN KEY (effect_blind_id) REFERENCES logical_effects(effect_blind_id) ON DELETE RESTRICT
) STRICT;

CREATE TABLE paid_attempt_events (
  event_id TEXT NOT NULL PRIMARY KEY,
  attempt_id TEXT NOT NULL,
  effect_transition_id TEXT NOT NULL UNIQUE,
  owner_path_discriminator TEXT NOT NULL,
  sequence INTEGER NOT NULL CHECK (sequence >= 1),
  prior_state TEXT DEFAULT NULL
    CHECK (prior_state IS NULL OR prior_state IN ('attempt_started','proven_no_network','returned',
                                                  'settled','private_rejected_paid','paid_unknown')),
  state TEXT NOT NULL
    CHECK (state IN ('attempt_started','proven_no_network','returned','settled',
                     'private_rejected_paid','paid_unknown')),
  evidence_kind TEXT NOT NULL
    CHECK (evidence_kind IN ('attempt_started','proven_no_network','returned','settled',
                             'private_rejected_paid','paid_unknown')),
  known_charge_cents INTEGER DEFAULT NULL CHECK (known_charge_cents IS NULL OR known_charge_cents BETWEEN 0 AND 1000000000),
  aead_suite TEXT NOT NULL DEFAULT 'aes-256-gcm' CHECK (aead_suite = 'aes-256-gcm'),
  key_version TEXT NOT NULL,
  nonce_length INTEGER NOT NULL DEFAULT 12 CHECK (nonce_length = 12),
  nonce BLOB NOT NULL CHECK (length(nonce) = 12),
  aad_schema TEXT NOT NULL DEFAULT 'private_paid_attempt_evidence_aad_v1',
  aad_json BLOB NOT NULL CHECK (length(aad_json) BETWEEN 1 AND 4096),
  ciphertext_schema TEXT NOT NULL DEFAULT 'fixture_transition_evidence_v1_json',
  ciphertext_type TEXT NOT NULL DEFAULT 'application/json',
  ciphertext_length INTEGER NOT NULL CHECK (ciphertext_length BETWEEN 17 AND 67108880),
  ciphertext BLOB NOT NULL CHECK (length(ciphertext) = ciphertext_length),
  occurred_at_ms INTEGER NOT NULL CHECK (occurred_at_ms >= 0),
  UNIQUE (attempt_id, sequence),
  UNIQUE (owner_path_discriminator, key_version, nonce),
  FOREIGN KEY (attempt_id) REFERENCES paid_attempts(attempt_id) ON DELETE RESTRICT,
  FOREIGN KEY (effect_transition_id) REFERENCES paid_effect_transitions(transition_id) ON DELETE RESTRICT,
  CHECK ((state IN ('settled','private_rejected_paid') AND known_charge_cents IS NOT NULL) OR
         (state NOT IN ('settled','private_rejected_paid') AND known_charge_cents IS NULL))
) STRICT;

CREATE TABLE migration_cutover_proof (
  migration_epoch INTEGER NOT NULL PRIMARY KEY CHECK (migration_epoch = 1),
  prior_migration_epoch INTEGER NOT NULL CHECK (prior_migration_epoch = 0),
  target_store_id TEXT NOT NULL UNIQUE,
  freeze_nonce TEXT NOT NULL,
  source_manifest_sha256 TEXT NOT NULL,
  copy_audit_sha256 TEXT NOT NULL,
  semantic_source_sha256 TEXT NOT NULL,
  contract_sha256 TEXT NOT NULL,
  sealed_at_ms INTEGER NOT NULL CHECK (sealed_at_ms >= 0),
  marker_committed_at_ms INTEGER NOT NULL CHECK (marker_committed_at_ms >= sealed_at_ms),
  marker_key_id TEXT NOT NULL,
  marker_sha256 TEXT NOT NULL UNIQUE,
  marker_signature_ed25519 TEXT NOT NULL
) STRICT;

CREATE INDEX idx_provider_capabilities_v4_owner_expiry
  ON provider_capabilities_v4(owner_path_discriminator, expires_at_ms);
CREATE INDEX idx_provider_revocation_heads_registry_epoch
  ON provider_revocation_heads(registry_id, owner_path_discriminator, epoch);
CREATE INDEX idx_source_heads_registry_epoch
  ON source_heads(registry_id, owner_path_discriminator, epoch);
CREATE INDEX idx_encrypted_source_bundles_owner_state
  ON encrypted_source_bundles(owner_path_discriminator, state);
CREATE INDEX idx_owner_operations_job
  ON owner_operations(owner_path_discriminator, job_id, execution_id, stage_id);
CREATE INDEX idx_consent_claims_state_expiry
  ON consent_claims(owner_path_discriminator, state, expires_at_ms);
CREATE INDEX idx_queue_leases_expiry
  ON queue_leases(owner_path_discriminator, exclusive_until_ms);
CREATE INDEX idx_logical_effects_owner_state
  ON logical_effects(owner_path_discriminator, state);
CREATE INDEX idx_paid_admissions_revocation
  ON paid_admissions(provider_revocation_registry_id, owner_path_discriminator,
                     provider_revocation_head_sha256, provider_revocation_epoch);
CREATE INDEX idx_budget_holds_account_state
  ON budget_holds(owner_path_discriminator, account_scope_blind_id,
                  project_scope_blind_id, state);
CREATE INDEX idx_paid_attempts_state
  ON paid_attempts(owner_path_discriminator, current_state);
CREATE INDEX idx_paid_effect_transitions_effect_sequence
  ON paid_effect_transitions(effect_blind_id, sequence);
CREATE INDEX idx_paid_attempt_events_attempt_sequence
  ON paid_attempt_events(attempt_id, sequence);
"""

_EXPECTED_TABLE_NAMES: tuple[str, ...] = (
    "paid_lane_schema",
    "provider_capabilities_v4",
    "provider_revocation_heads",
    "provider_revocation_current",
    "source_heads",
    "source_current",
    "encrypted_source_bundles",
    "owner_operations",
    "consent_claims",
    "queue_leases",
    "budget_accounts",
    "logical_effects",
    "paid_admissions",
    "budget_holds",
    "paid_attempts",
    "paid_effect_transitions",
    "paid_attempt_events",
    "migration_cutover_proof",
)

_EXPECTED_TABLE_SET: frozenset[str] = frozenset(_EXPECTED_TABLE_NAMES)

_EXPECTED_INDEX_NAMES: tuple[str, ...] = (
    "idx_provider_capabilities_v4_owner_expiry",
    "idx_provider_revocation_heads_registry_epoch",
    "idx_source_heads_registry_epoch",
    "idx_encrypted_source_bundles_owner_state",
    "idx_owner_operations_job",
    "idx_consent_claims_state_expiry",
    "idx_queue_leases_expiry",
    "idx_logical_effects_owner_state",
    "idx_paid_admissions_revocation",
    "idx_budget_holds_account_state",
    "idx_paid_attempts_state",
    "idx_paid_effect_transitions_effect_sequence",
    "idx_paid_attempt_events_attempt_sequence",
)

_EXPECTED_INDEX_SET: frozenset[str] = frozenset(_EXPECTED_INDEX_NAMES)

# Exact 46 autoindex names
_EXPECTED_AUTOINDEX_NAMES: frozenset[str] = frozenset(
    {
        "sqlite_autoindex_paid_lane_schema_1",
        "sqlite_autoindex_provider_capabilities_v4_1",
        "sqlite_autoindex_provider_capabilities_v4_2",
        "sqlite_autoindex_provider_capabilities_v4_3",
        "sqlite_autoindex_provider_capabilities_v4_4",
        "sqlite_autoindex_provider_revocation_heads_1",
        "sqlite_autoindex_provider_revocation_heads_2",
        "sqlite_autoindex_provider_revocation_heads_3",
        "sqlite_autoindex_provider_revocation_current_1",
        "sqlite_autoindex_source_heads_1",
        "sqlite_autoindex_source_heads_2",
        "sqlite_autoindex_source_heads_3",
        "sqlite_autoindex_source_current_1",
        "sqlite_autoindex_encrypted_source_bundles_1",
        "sqlite_autoindex_encrypted_source_bundles_2",
        "sqlite_autoindex_encrypted_source_bundles_3",
        "sqlite_autoindex_owner_operations_1",
        "sqlite_autoindex_owner_operations_2",
        "sqlite_autoindex_consent_claims_1",
        "sqlite_autoindex_consent_claims_2",
        "sqlite_autoindex_queue_leases_1",
        "sqlite_autoindex_queue_leases_2",
        "sqlite_autoindex_budget_accounts_1",
        "sqlite_autoindex_logical_effects_1",
        "sqlite_autoindex_logical_effects_2",
        "sqlite_autoindex_paid_admissions_1",
        "sqlite_autoindex_paid_admissions_2",
        "sqlite_autoindex_paid_admissions_3",
        "sqlite_autoindex_paid_admissions_4",
        "sqlite_autoindex_paid_admissions_5",
        "sqlite_autoindex_budget_holds_1",
        "sqlite_autoindex_budget_holds_2",
        "sqlite_autoindex_budget_holds_3",
        "sqlite_autoindex_paid_attempts_1",
        "sqlite_autoindex_paid_attempts_2",
        "sqlite_autoindex_paid_attempts_3",
        "sqlite_autoindex_paid_attempts_4",
        "sqlite_autoindex_paid_effect_transitions_1",
        "sqlite_autoindex_paid_effect_transitions_2",
        "sqlite_autoindex_paid_effect_transitions_3",
        "sqlite_autoindex_paid_attempt_events_1",
        "sqlite_autoindex_paid_attempt_events_2",
        "sqlite_autoindex_paid_attempt_events_3",
        "sqlite_autoindex_paid_attempt_events_4",
        "sqlite_autoindex_migration_cutover_proof_1",
        "sqlite_autoindex_migration_cutover_proof_2",
    }
)

# Expected table-to-autoindex count
_EXPECTED_AUTOINDEX_TABLE_COUNTS: dict[str, int] = {
    "paid_lane_schema": 1,
    "provider_capabilities_v4": 4,
    "provider_revocation_heads": 3,
    "provider_revocation_current": 1,
    "source_heads": 3,
    "source_current": 1,
    "encrypted_source_bundles": 3,
    "owner_operations": 2,
    "consent_claims": 2,
    "queue_leases": 2,
    "budget_accounts": 1,
    "logical_effects": 2,
    "paid_admissions": 5,
    "budget_holds": 3,
    "paid_attempts": 4,
    "paid_effect_transitions": 3,
    "paid_attempt_events": 4,
    "migration_cutover_proof": 2,
}

# ---------------------------------------------------------------------------
# Canonical JSON / hashing helpers
# ---------------------------------------------------------------------------


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    ).encode("utf-8")


def _json_default(o: object) -> object:
    if isinstance(o, bytes):
        return o.decode("latin-1")
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def _canonical_model_json(model: BaseModel) -> bytes:
    return _canonical_json(model.model_dump(mode="json"))


def _migration_encode(value: object) -> object:
    """Canonical migration encoding; binary values never pass through UTF-8."""
    if isinstance(value, BaseModel):
        return {name: _migration_encode(getattr(value, name)) for name in type(value).model_fields}
    if isinstance(value, bytes):
        return ["blob", value.hex()]
    if isinstance(value, tuple):
        return [_migration_encode(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _migration_encode(item) for key, item in value.items()}
    if value is None or type(value) in (bool, int, str):
        return value
    raise TypeError(f"unsupported migration value: {type(value).__name__}")


def _bounded_migration_bytes(value: object, *, bound: int) -> bytes:
    encoded = _canonical_json(_migration_encode(value))
    _require_migration_byte_length(len(encoded), bound=bound)
    return encoded


def _require_migration_byte_length(length: int, *, bound: int = MAX_CORPUS_BYTES) -> None:
    if type(length) is not int or length < 0 or length > bound:
        raise ValueError("migration corpus byte bound")


def _require_migration_collection_count(count: int) -> None:
    if type(count) is not int or count < 0 or count > MAX_MIGRATION_ROWS:
        raise ValueError("migration collection row bound")


def _trim_outer_ascii_ws(s: str) -> str:
    """Trim ASCII space/tab/CR/LF/FF/VT from both ends."""
    return s.strip(" \t\r\n\x0c\x0b")


def _compact_sql(value: str) -> str:
    """Normalize SQL for comparison: lowercase, strip whitespace outside strings, remove IF NOT EXISTS."""
    compact: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(value):
        character = value[index]
        if quote is not None:
            compact.append(character)
            if character == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    compact.append(value[index + 1])
                    index += 1
                else:
                    quote = None
        elif character in {"'", '"'}:
            quote = character
            compact.append(character)
        elif not character.isspace():
            compact.append(character.lower())
        index += 1
    return "".join(compact).replace("ifnotexists", "")


def _material(value: BaseModel | Mapping[str, object], omitted: frozenset[str]) -> bytes:
    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    return _canonical_json({key: item for key, item in raw.items() if key not in omitted})


def _digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + _canonical_json(value)).hexdigest()


def _same(first: str, second: str) -> bool:
    return hmac.compare_digest(first, second)


def _valid_i63(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool) and 0 <= value <= MAX_I63


def _issued_at_is_current(*, issued_at_ms: int, now_ms: int) -> bool:
    return issued_at_ms - MAX_PAST_ISSUANCE_SKEW_MS <= now_ms <= issued_at_ms + MAX_FUTURE_SKEW_MS


def _require_predecessor_runtime_sources() -> None:
    require_private_source_authority_module_source()
    require_private_source_head_store_module_source()
    require_private_source_bundle_store_module_source()


def _require_bounded_bytes(value: bytes, *, bound: int, allow_empty: bool = False) -> None:
    if type(value) is not bytes or (not allow_empty and not value) or len(value) > bound:
        raise PrivatePaidLaneEligibilityCheckpointRejected()


def _copy_keyring(value: Mapping[str, bytes]) -> dict[str, bytes]:
    copied: dict[str, bytes] = {}
    try:
        for index, (key_id, key) in enumerate(value.items()):
            if (
                index >= MAX_FIXTURE_VERIFICATION_KEYS
                or type(key_id) is not str
                or _KEY_ID.fullmatch(key_id) is None
                or type(key) is not bytes
                or len(key) != 32
                or key_id in copied
                or key in copied.values()
            ):
                raise ValueError
            copied[key_id] = bytes(key)
    except Exception:
        raise PrivatePaidLaneEligibilityCheckpointRejected() from None
    return copied


def _copy_verification_keyring(value: tuple[VerificationKeyV1, ...]) -> dict[str, bytes]:
    if type(value) is not tuple or len(value) > MAX_FIXTURE_VERIFICATION_KEYS:
        raise ValueError("invalid verification keyring")
    copied: dict[str, bytes] = {}
    public_keys: set[bytes] = set()
    for key in value:
        if type(key) is not VerificationKeyV1:
            raise ValueError("invalid verification key")
        if key.key_id in copied or key.public_key_bytes in public_keys:
            raise ValueError("duplicate verification key")
        copied[key.key_id] = bytes(key.public_key_bytes)
        public_keys.add(bytes(key.public_key_bytes))
    return copied


def _reject_duplicates(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _parse_strict_json(data: bytes, max_bytes: int) -> dict[str, object]:
    if type(data) is not bytes or not data or len(data) > max_bytes:
        raise ValueError("invalid json")
    result = json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    if not isinstance(result, dict):
        raise ValueError("not a dict")
    return result


# ---------------------------------------------------------------------------
# HMAC blind identity computation
# ---------------------------------------------------------------------------


def _u32be(n: int) -> bytes:
    return struct.pack(">I", n)


# ---------------------------------------------------------------------------
# Closed base model
# ---------------------------------------------------------------------------


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]


# ---------------------------------------------------------------------------
# Rejection exception
# ---------------------------------------------------------------------------


class PrivatePaidLaneEligibilityCheckpointRejected(ValueError):
    def __init__(self) -> None:
        super().__init__("private paid-lane eligibility checkpoint rejected")

    def __repr__(self) -> str:
        return "PrivatePaidLaneEligibilityCheckpointRejected()"


# ---------------------------------------------------------------------------
# Key provider protocols
# ---------------------------------------------------------------------------


class OwnerPrivateSourceKeyProviderV1(Protocol):
    def open_aes256gcm_key(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        key_version: str,
    ) -> AbstractContextManager[bytearray]: ...


class PrivatePaidLaneOwnerKeyProviderV1(Protocol):
    def authenticate_owner_path(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
    ) -> AbstractContextManager[None]: ...

    def open_hmac_sha256_key(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        purpose: Literal[
            "consent_v1",
            "cursor_v1",
            "account_v1",
            "project_v1",
            "request_v1",
            "idempotency_v1",
            "effect_v1",
            "test_claim_v1",
        ],
    ) -> AbstractContextManager[bytearray]: ...

    def open_aes256gcm_key(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        key_version: str,
        purpose: Literal["admission_candidate_v1", "attempt_evidence_v1"],
    ) -> AbstractContextManager[bytearray]: ...


# ---------------------------------------------------------------------------
# Verification key model
# ---------------------------------------------------------------------------


class VerificationKeyV1(_Closed):
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    public_key_bytes: bytes

    @model_validator(mode="after")
    def _validate_key(self) -> VerificationKeyV1:
        if len(self.public_key_bytes) != 32:
            raise ValueError("public key must be 32 bytes")
        return self


# ---------------------------------------------------------------------------
# Floor pin models
# ---------------------------------------------------------------------------


class ProviderRevocationFloorPinV1(_Closed):
    schema_version: Literal[1] = 1
    registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    floor_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    floor_epoch: int = Field(ge=0, le=MAX_I63)


class OwnerPrivateSourceFloorPinV1(_Closed):
    schema_version: Literal[1] = 1
    registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    floor_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    floor_epoch: int = Field(ge=0, le=MAX_I63)


# ---------------------------------------------------------------------------
# Signed CapabilityV4 fixture
# ---------------------------------------------------------------------------


class SignedProviderCapabilityV4FixtureV1(_Closed):
    schema_version: Literal[4] = 4
    capability_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    revocation_registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    revocation_trusted_floor_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    model: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    route: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    api_mode: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    processing_region: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    output_schema: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    account_scope_blind_id: bytes = Field(min_length=32, max_length=32)
    project_scope_blind_id: bytes = Field(min_length=32, max_length=32)
    router_role: Literal["planner", "gatherer", "verifier", "synthesizer"]
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    core_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    envelope_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_max_cents: int = Field(ge=1, le=MAX_CENTS)
    maximum_output_bytes: int = Field(ge=1, le=MAX_PLAINTEXT_BYTES)
    issued_at_ms: int = Field(ge=0, le=MAX_I63)
    expires_at_ms: int = Field(ge=0, le=MAX_I63)
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    issuer_role: Literal["private_provider_capability_v4_fixture_issuer"] = (
        "private_provider_capability_v4_fixture_issuer"
    )
    key_purpose: Literal["private_provider_capability_v4_fixture_v1"] = (
        "private_provider_capability_v4_fixture_v1"
    )
    signature_scheme: Literal["ed25519"] = "ed25519"
    capability_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_ed25519: str = Field(pattern=r"^[0-9a-f]{128}$")
    # Quarantine literals
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> SignedProviderCapabilityV4FixtureV1:
        expected = _capability_v4_document_sha256(self)
        if self.capability_sha256 != expected:
            raise ValueError("capability sha256 mismatch")
        if self.expires_at_ms <= self.issued_at_ms:
            raise ValueError("expires_at_ms must exceed issued_at_ms")
        return self


# ---------------------------------------------------------------------------
# Signed Revocation Head fixture
# ---------------------------------------------------------------------------


class SignedProviderRevocationHeadFixtureV1(_Closed):
    schema_version: Literal[1] = 1
    registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    epoch: int = Field(ge=0, le=MAX_I63)
    predecessor_head_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    issued_at_ms: int = Field(ge=0, le=MAX_I63)
    revoked_capability_sha256s: tuple[str, ...] = Field(max_length=MAX_CUMULATIVE_REVOKED)
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    issuer_role: Literal["private_provider_revocation_fixture_issuer"] = (
        "private_provider_revocation_fixture_issuer"
    )
    key_purpose: Literal["private_provider_revocation_fixture_v1"] = (
        "private_provider_revocation_fixture_v1"
    )
    signature_scheme: Literal["ed25519"] = "ed25519"
    head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_ed25519: str = Field(pattern=r"^[0-9a-f]{128}$")
    # Quarantine literals
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> SignedProviderRevocationHeadFixtureV1:
        if self.epoch >= MAX_HEADS_PER_CHAIN:
            raise ValueError("revocation epoch bound")
        if self.revoked_capability_sha256s != tuple(sorted(set(self.revoked_capability_sha256s))):
            raise ValueError("revocation set must be sorted unique")
        expected = _revocation_head_document_sha256(self)
        if self.head_sha256 != expected:
            raise ValueError("head sha256 mismatch")
        if (self.epoch == 0) != (self.predecessor_head_sha256 is None):
            raise ValueError("epoch/predecessor constraint")
        if self.epoch == 0 and self.revoked_capability_sha256s:
            raise ValueError("revocation genesis must be empty")
        for h in self.revoked_capability_sha256s:
            if not _HEX64.fullmatch(h):
                raise ValueError("invalid revoked hash")
        return self


# ---------------------------------------------------------------------------
# Source head models are exact identity aliases imported from Cycle32
# private_source_head_store. Do not redefine them here.


# ---------------------------------------------------------------------------
# CapabilityV4 / revocation hash helpers
# ---------------------------------------------------------------------------


def _capability_v4_document_sha256(
    value: SignedProviderCapabilityV4FixtureV1 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _CAPABILITY_V4_DOCUMENT_DOMAIN
        + _material(value, frozenset({"capability_sha256", "signature_ed25519"}))
    ).hexdigest()


def _revocation_head_document_sha256(
    value: SignedProviderRevocationHeadFixtureV1 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _REVOCATION_HEAD_DOMAIN + _material(value, frozenset({"head_sha256", "signature_ed25519"}))
    ).hexdigest()


def _source_snapshot_sha256(
    value: OwnerPrivateSourceAuthoritySnapshotV1 | Mapping[str, object],
) -> str:
    return owner_private_source_authority_snapshot_v1_sha256(value)


def _source_head_document_sha256(
    value: SignedSourceHeadFixtureV1 | Mapping[str, object],
) -> str:
    return owner_private_source_authority_head_v1_sha256(value)


# ---------------------------------------------------------------------------
# Input models for fixture writers
# ---------------------------------------------------------------------------


class FixtureOwnerOperationPutV1(_Closed):
    schema_version: Literal[1] = 1
    operation_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    job_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    execution_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    stage_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    state: Literal["queued", "running", "terminal"]


class FixtureOwnerOperationAdvanceV1(_Closed):
    schema_version: Literal[1] = 1
    operation_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    expected_state: str
    expected_state_version: int = Field(ge=1, le=MAX_I63)
    next_state: str


class FixtureOwnerOperationCancelV1(_Closed):
    schema_version: Literal[1] = 1
    operation_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    expected_state: str
    expected_state_version: int = Field(ge=1, le=MAX_I63)
    expected_cancellation_version: Literal[0] = 0
    next_cancellation_version: Literal[1] = 1


class FixtureConsentPutV1(_Closed):
    schema_version: Literal[1] = 1
    consent_receipt_material: bytes
    consent_config_material: bytes
    approved_ceiling_cents: int = Field(ge=1, le=MAX_CENTS)
    version: Literal[1] = 1
    issued_at_ms: int = Field(ge=0, le=MAX_I63)
    expires_at_ms: int = Field(ge=0, le=MAX_I63)


class FixtureConsentWithdrawV1(_Closed):
    schema_version: Literal[1] = 1
    consent_receipt_material: bytes
    consent_config_material: bytes
    expected_version: int = Field(ge=1, le=MAX_I63)
    next_version: int = Field(ge=1, le=MAX_I63)


class FixtureConsentClaimForTestV1(_Closed):
    schema_version: Literal[1] = 1
    consent_receipt_material: bytes
    consent_config_material: bytes
    expected_version: int = Field(ge=1, le=MAX_I63)
    effect_material: bytes


class FixtureQueueLeasePutV1(_Closed):
    schema_version: Literal[1] = 1
    queue_operation_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    lease_owner: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    cursor_material: bytes
    generation: Literal[1] = 1
    row_version: Literal[1] = 1
    acquired_at_ms: int = Field(ge=0, le=MAX_I63)
    exclusive_until_ms: int = Field(ge=0, le=MAX_I63)


class FixtureQueueLeaseTakeoverV1(_Closed):
    schema_version: Literal[1] = 1
    queue_operation_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    expected_lease_owner: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    expected_generation: int = Field(ge=1, le=MAX_I63)
    expected_cursor_material: bytes
    expected_row_version: int = Field(ge=1, le=MAX_I63)
    next_lease_owner: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    next_cursor_material: bytes
    next_generation: int = Field(ge=1, le=MAX_I63)
    next_exclusive_until_ms: int = Field(ge=0, le=MAX_I63)


class FixtureQueueLeaseRenewV1(_Closed):
    schema_version: Literal[1] = 1
    queue_operation_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    expected_lease_owner: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    expected_generation: int = Field(ge=1, le=MAX_I63)
    expected_cursor_material: bytes
    expected_row_version: int = Field(ge=1, le=MAX_I63)
    next_row_version: int = Field(ge=1, le=MAX_I63)
    next_exclusive_until_ms: int = Field(ge=0, le=MAX_I63)


class FixtureBudgetPutV1(_Closed):
    schema_version: Literal[1] = 1
    account_scope_material: bytes
    project_scope_material: bytes
    approved_ceiling_cents: int = Field(ge=1, le=MAX_CENTS)
    confirmed_cents: Literal[0] = 0
    open_cents: Literal[0] = 0
    unknown_cents: Literal[0] = 0
    row_version: Literal[1] = 1


class FixtureBudgetMutateV1(_Closed):
    schema_version: Literal[1] = 1
    account_scope_material: bytes
    project_scope_material: bytes
    expected_row_version: int = Field(ge=1, le=MAX_I63)
    next_approved_ceiling_cents: int = Field(ge=1, le=MAX_CENTS)


class FixtureProviderCapabilityPutV1(_Closed):
    schema_version: Literal[1] = 1
    signed_provider_capability_v4: SignedProviderCapabilityV4FixtureV1


class FixtureProviderRevocationAppendV1(_Closed):
    schema_version: Literal[1] = 1
    registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    expected_current_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_current_epoch: int = Field(ge=0, le=MAX_I63)
    expected_state_version: int = Field(ge=1, le=MAX_I63)
    signed_successor: SignedProviderRevocationHeadFixtureV1


class FixtureSourceReceiptPairV1(_Closed):
    receipt_id: str = Field(pattern=r"^opsr5_[0-9a-f]{24}$")
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class UnifiedPaidAdmissionCandidateV1(_Closed):
    schema_version: Literal[1] = 1
    provider_capability_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    provider_capability_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_revocation_registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    provider_revocation_trusted_floor_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_revocation_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_revocation_epoch: int = Field(ge=0, le=MAX_I63)
    source_registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    source_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_epoch: int = Field(ge=0, le=MAX_I63)
    opaque_source_bundle_id: str = Field(pattern=r"^opsbs1_[0-9a-f]{64}$")
    source_row_version: Literal[1] = 1
    operation_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    job_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    execution_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    stage_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    expected_owner_operation_state: str
    expected_owner_operation_state_version: int = Field(ge=1, le=MAX_I63)
    expected_owner_operation_cancel_requested: Literal[False] = False
    expected_owner_operation_cancellation_version: Literal[0] = 0
    consent_receipt_material: bytes
    consent_config_material: bytes
    consent_version: int = Field(ge=1, le=MAX_I63)
    consent_expires_at_ms: int = Field(ge=0, le=MAX_I63)
    consent_approved_ceiling_cents: int = Field(ge=1, le=MAX_CENTS)
    queue_operation_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    lease_owner: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    lease_generation: int = Field(ge=1, le=MAX_I63)
    queue_cursor_material: bytes
    lease_exclusive_until_ms: int = Field(ge=0, le=MAX_I63)
    account_scope_material: bytes
    project_scope_material: bytes
    budget_row_version: int = Field(ge=1, le=MAX_I63)
    projected_max_cents: int = Field(ge=1, le=MAX_CENTS)
    request_material: bytes
    provider_idempotency_material: bytes
    router_role: Literal["planner", "gatherer", "verifier", "synthesizer"]
    provider: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    model: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    route: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    api_mode: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    processing_region: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    output_schema: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    maximum_output_bytes: int = Field(ge=1, le=MAX_PLAINTEXT_BYTES)
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    core_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    envelope_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_receipt_pairs: tuple[FixtureSourceReceiptPairV1, ...] = Field(
        max_length=MAX_RECEIPT_PAIRS
    )
    asserted_effect_blind_id: bytes = Field(min_length=32, max_length=32)
    # Quarantine literals
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class FixtureSourceBundleAndHeadAppendV1(_Closed):
    schema_version: Literal[1] = 1
    registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    expected_current_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_current_epoch: int = Field(ge=0, le=MAX_I63)
    expected_state_version: int = Field(ge=1, le=MAX_I63)
    pending_source_bundle_handle: Any  # Private constructor — validated at runtime
    exact_bundle: Any  # Validated at runtime as the exact Cycle31 model
    key_version: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    signed_successor: SignedSourceHeadFixtureV1


# ---------------------------------------------------------------------------
# Pending source bundle handle
# ---------------------------------------------------------------------------

_PENDING_HANDLE_CONSTRUCTOR = object()


class PendingUnifiedSourceBundleHandleV1:
    """One-shot, process-bound pending source bundle handle."""

    schema_version: Literal[1]
    handle_id: str
    opaque_source_bundle_id: str
    store_id: str
    owner_path_discriminator: str
    registry_id: str
    expected_current_head_sha256: str
    expected_current_epoch: int
    expected_state_version: int
    created_at_ms: int
    expires_at_ms: int
    creator_pid: int
    boot_nonce: bytes
    authority_object_identity: int
    pending_mac: bytes
    consumed: bool

    __slots__ = (
        "schema_version",
        "handle_id",
        "opaque_source_bundle_id",
        "store_id",
        "owner_path_discriminator",
        "registry_id",
        "expected_current_head_sha256",
        "expected_current_epoch",
        "expected_state_version",
        "created_at_ms",
        "expires_at_ms",
        "creator_pid",
        "boot_nonce",
        "authority_object_identity",
        "pending_mac",
        "consumed",
    )

    def __init__(
        self,
        token: object,
        *,
        schema_version: Literal[1],
        handle_id: str,
        opaque_source_bundle_id: str,
        store_id: str,
        owner_path_discriminator: str,
        registry_id: str,
        expected_current_head_sha256: str,
        expected_current_epoch: int,
        expected_state_version: int,
        created_at_ms: int,
        expires_at_ms: int,
        creator_pid: int,
        boot_nonce: bytes,
        authority_object_identity: int,
        pending_mac: bytes,
    ) -> None:
        if token is not _PENDING_HANDLE_CONSTRUCTOR:
            raise TypeError("pending source bundle handle is store-created")
        for slot in (
            "schema_version",
            "handle_id",
            "opaque_source_bundle_id",
            "store_id",
            "owner_path_discriminator",
            "registry_id",
            "expected_current_head_sha256",
            "expected_current_epoch",
            "expected_state_version",
            "created_at_ms",
            "expires_at_ms",
        ):
            object.__setattr__(self, slot, locals()[slot])
        object.__setattr__(self, "creator_pid", creator_pid)
        object.__setattr__(self, "boot_nonce", bytes(boot_nonce))
        object.__setattr__(self, "authority_object_identity", authority_object_identity)
        object.__setattr__(self, "pending_mac", bytes(pending_mac))
        object.__setattr__(self, "consumed", False)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("pending source bundle handle is immutable")

    def __reduce__(self) -> Never:
        raise TypeError("pending source bundle handle is process-local")

    def __copy__(self) -> Never:
        raise TypeError("pending source bundle handle is process-local")

    def __deepcopy__(self, memo: object) -> Never:
        raise TypeError("pending source bundle handle is process-local")

    def __repr__(self) -> str:
        return "PendingUnifiedSourceBundleHandleV1(redacted=True)"


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class FixtureOwnerOperationResultV1(_Closed):
    applied: bool
    replayed: bool
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    state: str
    state_version: int = Field(ge=1, le=MAX_I63)
    cancel_requested: int = Field(ge=0, le=1)
    cancellation_version: int = Field(ge=0, le=MAX_I63)
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class FixtureConsentResultV1(_Closed):
    applied: bool
    replayed: bool
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    consent_blind_id: bytes
    state: str
    version: int = Field(ge=1, le=MAX_I63)
    expires_at_ms: int = Field(ge=0, le=MAX_I63)
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class FixtureQueueLeaseResultV1(_Closed):
    applied: bool
    replayed: bool
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    queue_operation_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    lease_owner: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    generation: int = Field(ge=1, le=MAX_I63)
    cursor_blind_id: bytes
    row_version: int = Field(ge=1, le=MAX_I63)
    exclusive_until_ms: int = Field(ge=0, le=MAX_I63)
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class FixtureBudgetResultV1(_Closed):
    applied: bool
    replayed: bool
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    account_scope_blind_id: bytes
    project_scope_blind_id: bytes
    approved_ceiling_cents: int = Field(ge=1, le=MAX_CENTS)
    confirmed_cents: int = Field(ge=0, le=MAX_CENTS)
    open_cents: int = Field(ge=0, le=MAX_CENTS)
    unknown_cents: int = Field(ge=0, le=MAX_CENTS)
    row_version: int = Field(ge=1, le=MAX_I63)
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class FixtureCapabilityResultV1(_Closed):
    applied: bool
    replayed: bool
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    capability_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    capability_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    revocation_registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    revocation_trusted_floor_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at_ms: int = Field(ge=0, le=MAX_I63)
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class FixtureHeadResultV1(_Closed):
    applied: bool
    replayed: bool
    head_kind: Literal["provider_revocation", "source"]
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    current_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_epoch: int = Field(ge=0, le=MAX_I63)
    state_version: int = Field(ge=1, le=MAX_I63)
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class QuarantinedPaidAdmissionResultV1(_Closed):
    """34B stub — not implemented in 34A."""

    replayed: bool
    effect_blind_id: bytes
    admission_id: str
    hold_id: str
    state: Literal["admission_committed"] = "admission_committed"
    state_version: int = Field(ge=1, le=MAX_I63)
    migration_epoch: Literal[1] = 1
    provider_capability_id: str
    provider_capability_sha256: str
    provider_revocation_registry_id: str
    provider_revocation_trusted_floor_sha256: str
    provider_revocation_head_sha256: str
    provider_revocation_epoch: int = Field(ge=0, le=MAX_I63)
    source_registry_id: str
    source_head_sha256: str
    source_epoch: int = Field(ge=0, le=MAX_I63)
    opaque_source_bundle_id: str
    source_row_version: Literal[1] = 1
    projected_max_cents: int = Field(ge=1, le=MAX_CENTS)
    hold_state: Literal["open"] = "open"
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class QuarantinedEffectTransitionResultV1(_Closed):
    """34C stub — not implemented in 34A."""

    replayed: bool
    effect_blind_id: bytes
    admission_id: str
    attempt_id: str | None = None
    transition_id: str | None = None
    event_id: str | None = None
    prior_state: str | None = None
    state: str = "admission_committed"
    state_version: int = Field(ge=0, le=MAX_I63)
    hold_state: str = "open"
    confirmed_cents: int = Field(ge=0, le=MAX_CENTS)
    open_cents: int = Field(ge=0, le=MAX_CENTS)
    unknown_cents: int = Field(ge=0, le=MAX_CENTS)
    transitioned_at_ms: int = Field(ge=0, le=MAX_I63)
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


# ---------------------------------------------------------------------------
# Fail-closed stubs for 34D
# ---------------------------------------------------------------------------


class QuarantinedPrecutoverHandleV1:
    """Process-bound, nonserializable handle for epoch-zero operations."""

    __slots__ = ("_consumed", "_process_id", "_boot_nonce", "store_id", "created_at_ms")
    _consumed: bool
    _process_id: int
    _boot_nonce: bytes
    store_id: str
    created_at_ms: int

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    def __init_subclass__(cls, **kwargs: object) -> Never:
        del cls, kwargs
        raise TypeError("precutover handle is final")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("precutover handle is immutable")

    def __reduce__(self) -> Never:
        raise TypeError("precutover handle is process-local")

    def __copy__(self) -> Never:
        raise TypeError("precutover handle is process-local")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("precutover handle is process-local")


def _issue_process_handle(handle_type: type[object], values: Mapping[str, object]) -> object:
    handle = object.__new__(handle_type)
    for name, value in values.items():
        object.__setattr__(handle, name, value)
    return handle


def _require_process_handle(
    handle: object,
    handle_type: type[object],
    *,
    store: PrivatePaidLaneEligibilityCheckpointStoreV1,
) -> None:
    if (
        type(handle) is not handle_type
        or getattr(handle, "_process_id", getattr(handle, "creator_pid", None)) != os.getpid()
        or getattr(handle, "_boot_nonce", getattr(handle, "boot_nonce", None)) != store._boot_nonce
        or getattr(handle, "store_id", getattr(handle, "target_store_id", None)) != store.store_id
        or getattr(handle, "target_database_path", store.database_path) != store.database_path
        or getattr(handle, "_consumed", getattr(handle, "consumed", None)) is not False
        or store._migration_root_handle is not handle
    ):
        raise ValueError("migration handle mismatch")


class MigrationSourceStoreV1(_Closed):
    store_kind: str
    store_id: str
    schema_sha256: str
    native_writer_barrier_id: str
    final_version: int = Field(ge=0, le=MAX_I63)
    row_count: int = Field(ge=0, le=MAX_MIGRATION_ROWS)
    ordered_rows_sha256: str

    @model_validator(mode="after")
    def _closed_identity(self) -> MigrationSourceStoreV1:
        if (
            not _REGISTRY_ID.fullmatch(self.store_kind)
            or not _REGISTRY_ID.fullmatch(self.store_id)
            or not _HEX64.fullmatch(self.schema_sha256)
            or not _REGISTRY_ID.fullmatch(self.native_writer_barrier_id)
            or not _HEX64.fullmatch(self.ordered_rows_sha256)
        ):
            raise ValueError("migration source identity")
        return self


class ProviderCapabilityV4MigrationRowV1(_Closed):
    capability_sha256: str
    capability_id: str
    owner_path_discriminator: str
    revocation_registry_id: str
    revocation_trusted_floor_sha256: str
    issued_at_ms: int = Field(ge=0, le=MAX_I63)
    expires_at_ms: int = Field(ge=0, le=MAX_I63)
    key_id: str
    document_json: bytes
    signature_ed25519: bytes

    @model_validator(mode="after")
    def _closed_row(self) -> ProviderCapabilityV4MigrationRowV1:
        try:
            document = SignedProviderCapabilityV4FixtureV1.model_validate_json(self.document_json)
            if (
                self.document_json != _canonical_json(document.model_dump(mode="json"))
                or self.capability_sha256 != document.capability_sha256
                or self.capability_id != document.capability_id
                or self.owner_path_discriminator != document.owner_path_discriminator
                or self.revocation_registry_id != document.revocation_registry_id
                or self.revocation_trusted_floor_sha256 != document.revocation_trusted_floor_sha256
                or self.issued_at_ms != document.issued_at_ms
                or self.expires_at_ms != document.expires_at_ms
                or self.key_id != document.key_id
                or self.signature_ed25519 != bytes.fromhex(document.signature_ed25519)
                or self.issued_at_ms >= self.expires_at_ms
                or len(self.document_json) > MAX_DOCUMENT_BYTES
            ):
                raise ValueError
        except Exception:
            raise ValueError("capability migration row mismatch") from None
        return self


class ProviderRevocationHeadMigrationRowV1(_Closed):
    head_sha256: str
    registry_id: str
    owner_path_discriminator: str
    epoch: int = Field(ge=0, le=MAX_HEADS_PER_CHAIN - 1)
    predecessor_head_sha256: str | None
    issued_at_ms: int = Field(ge=0, le=MAX_I63)
    revoked_capability_hashes_json: bytes
    key_id: str
    document_json: bytes
    signature_ed25519: bytes

    @model_validator(mode="after")
    def _closed_row(self) -> ProviderRevocationHeadMigrationRowV1:
        try:
            document = SignedProviderRevocationHeadFixtureV1.model_validate_json(self.document_json)
            revoked = _canonical_json(list(document.revoked_capability_sha256s))
            if (
                self.document_json != _canonical_json(document.model_dump(mode="json"))
                or self.head_sha256 != document.head_sha256
                or self.registry_id != document.registry_id
                or self.owner_path_discriminator != document.owner_path_discriminator
                or self.epoch != document.epoch
                or self.predecessor_head_sha256 != document.predecessor_head_sha256
                or self.issued_at_ms != document.issued_at_ms
                or self.revoked_capability_hashes_json != revoked
                or self.key_id != document.key_id
                or self.signature_ed25519 != bytes.fromhex(document.signature_ed25519)
                or len(self.document_json) > MAX_DOCUMENT_BYTES
            ):
                raise ValueError
        except Exception:
            raise ValueError("revocation migration row mismatch") from None
        return self


class ProviderRevocationCurrentMigrationRowV1(_Closed):
    registry_id: str
    owner_path_discriminator: str
    head_sha256: str
    epoch: int = Field(ge=0, le=MAX_HEADS_PER_CHAIN - 1)
    state_version: int = Field(ge=1, le=MAX_I63)
    updated_at_ms: int = Field(ge=0, le=MAX_I63)

    @model_validator(mode="after")
    def _closed_row(self) -> ProviderRevocationCurrentMigrationRowV1:
        if (
            not _REGISTRY_ID.fullmatch(self.registry_id)
            or not _OWNER_PATH.fullmatch(self.owner_path_discriminator)
            or not _HEX64.fullmatch(self.head_sha256)
            or self.state_version != self.epoch + 1
        ):
            raise ValueError("revocation current row mismatch")
        return self


class SourceHeadMigrationRowV1(_Closed):
    head_sha256: str
    registry_id: str
    owner_path_discriminator: str
    epoch: int = Field(ge=0, le=MAX_HEADS_PER_CHAIN - 1)
    previous_head_sha256: str
    issued_at_ms: int = Field(ge=0, le=MAX_I63)
    active_bundle_revisions_json: bytes
    snapshot_json: bytes
    key_id: str
    document_json: bytes
    signature_ed25519: bytes

    @model_validator(mode="after")
    def _closed_row(self) -> SourceHeadMigrationRowV1:
        try:
            document = SignedSourceHeadFixtureV1.model_validate_json(self.document_json)
            snapshot = _canonical_json(document.snapshot.model_dump(mode="json"))
            revisions = _canonical_json(
                [row.model_dump(mode="json") for row in document.snapshot.active_bundle_revisions]
            )
            if (
                self.document_json != _canonical_json(document.model_dump(mode="json"))
                or self.head_sha256 != document.head_sha256
                or self.registry_id != document.registry_id
                or self.owner_path_discriminator != document.owner_path_discriminator
                or self.epoch != document.epoch
                or self.previous_head_sha256 != document.previous_head_sha256
                or self.issued_at_ms != document.issued_at_ms
                or self.snapshot_json != snapshot
                or self.active_bundle_revisions_json != revisions
                or document.snapshot.tombstoned_bundle_ids != ()
                or self.key_id != document.key_id
                or self.signature_ed25519 != bytes.fromhex(document.signature_ed25519)
            ):
                raise ValueError
        except Exception:
            raise ValueError("source migration row mismatch") from None
        return self


class SourceCurrentMigrationRowV1(_Closed):
    registry_id: str
    owner_path_discriminator: str
    head_sha256: str
    epoch: int = Field(ge=0, le=MAX_HEADS_PER_CHAIN - 1)
    state_version: int = Field(ge=1, le=MAX_I63)
    updated_at_ms: int = Field(ge=0, le=MAX_I63)

    @model_validator(mode="after")
    def _closed_row(self) -> SourceCurrentMigrationRowV1:
        if (
            not _REGISTRY_ID.fullmatch(self.registry_id)
            or not _OWNER_PATH.fullmatch(self.owner_path_discriminator)
            or not _HEX64.fullmatch(self.head_sha256)
            or self.state_version != self.epoch + 1
        ):
            raise ValueError("source current row mismatch")
        return self


class EncryptedSourceBundleMigrationRowV1(_Closed):
    opaque_source_bundle_id: str
    owner_path_discriminator: str
    state: Literal["sealed"] = "sealed"
    row_version: Literal[1] = 1
    aead_suite: Literal["aes-256-gcm"] = "aes-256-gcm"
    key_version: str
    nonce_length: Literal[12] = 12
    nonce: bytes
    aad_schema: Literal["owner_private_source_aad_v1"] = "owner_private_source_aad_v1"
    aad_json: bytes
    ciphertext_schema: str
    ciphertext_type: str
    ciphertext_length: int = Field(ge=16, le=MAX_CIPHERTEXT_BYTES)
    ciphertext: bytes

    @model_validator(mode="after")
    def _closed_ciphertext(self) -> EncryptedSourceBundleMigrationRowV1:
        expected_aad = _canonical_json(
            {
                "aead_suite": self.aead_suite,
                "categorical_state": self.state,
                "ciphertext_length": self.ciphertext_length,
                "ciphertext_schema": self.ciphertext_schema,
                "ciphertext_type": self.ciphertext_type,
                "key_version": self.key_version,
                "nonce_length": self.nonce_length,
                "opaque_source_bundle_id": self.opaque_source_bundle_id,
                "owner_path_discriminator": self.owner_path_discriminator,
                "row_revision": self.row_version,
                "schema_version": 1,
            }
        )
        if (
            len(self.nonce) != self.nonce_length
            or len(self.aad_json) > MAX_DOCUMENT_BYTES
            or len(self.ciphertext) != self.ciphertext_length
            or not _SOURCE_BUNDLE_ID.fullmatch(self.opaque_source_bundle_id)
            or not _OWNER_PATH.fullmatch(self.owner_path_discriminator)
            or not _KEY_VERSION.fullmatch(self.key_version)
            or self.ciphertext_schema != "owner_private_encrypted_source_bundle_v1_json"
            or self.ciphertext_type != "application/json"
            or self.aad_json != expected_aad
        ):
            raise ValueError("encrypted source row framing mismatch")
        return self


class OwnerOperationMigrationRowV1(_Closed):
    owner_path_discriminator: str
    operation_id: str
    job_id: str
    execution_id: str
    stage_id: str
    state: Literal["cancelled", "terminal"]
    state_version: int = Field(ge=1, le=MAX_I63)
    cancel_requested: int = Field(ge=0, le=1)
    cancellation_version: int = Field(ge=0, le=MAX_I63)
    created_at_ms: int = Field(ge=0, le=MAX_I63)
    updated_at_ms: int = Field(ge=0, le=MAX_I63)

    @model_validator(mode="after")
    def _closed_row(self) -> OwnerOperationMigrationRowV1:
        if (
            not _OWNER_PATH.fullmatch(self.owner_path_discriminator)
            or any(
                not _SAFE_ASSERTION_ID.fullmatch(value)
                for value in (self.operation_id, self.job_id, self.execution_id, self.stage_id)
            )
            or self.created_at_ms > self.updated_at_ms
            or (
                self.state == "cancelled"
                and not (self.cancel_requested == 1 and self.cancellation_version >= 1)
            )
            or (
                self.state == "terminal"
                and not (self.cancel_requested == 0 and self.cancellation_version == 0)
            )
        ):
            raise ValueError("operation migration row mismatch")
        return self


class ConsentClaimMigrationRowV1(_Closed):
    owner_path_discriminator: str
    consent_blind_id: bytes
    approved_ceiling_cents: int = Field(ge=1, le=MAX_CENTS)
    version: int = Field(ge=1, le=MAX_I63)
    issued_at_ms: int = Field(ge=0, le=MAX_I63)
    expires_at_ms: int = Field(ge=0, le=MAX_I63)
    state: Literal["open", "withdrawn"]
    claimed_effect_blind_id: None = None
    claimed_at_ms: None = None
    updated_at_ms: int = Field(ge=0, le=MAX_I63)

    @model_validator(mode="after")
    def _closed_row(self) -> ConsentClaimMigrationRowV1:
        if (
            not _OWNER_PATH.fullmatch(self.owner_path_discriminator)
            or len(self.consent_blind_id) != 32
            or not self.issued_at_ms < self.expires_at_ms
            or self.updated_at_ms < self.issued_at_ms
        ):
            raise ValueError("consent migration row mismatch")
        return self


class QueueLeaseMigrationRowV1(_Closed):
    owner_path_discriminator: str
    queue_operation_id: str
    lease_owner: str
    generation: int = Field(ge=1, le=MAX_I63)
    cursor_blind_id: bytes
    row_version: int = Field(ge=1, le=MAX_I63)
    acquired_at_ms: int = Field(ge=0, le=MAX_I63)
    exclusive_until_ms: int = Field(ge=0, le=MAX_I63)
    updated_at_ms: int = Field(ge=0, le=MAX_I63)

    @model_validator(mode="after")
    def _closed_row(self) -> QueueLeaseMigrationRowV1:
        if (
            not _OWNER_PATH.fullmatch(self.owner_path_discriminator)
            or not _SAFE_ASSERTION_ID.fullmatch(self.queue_operation_id)
            or not _SAFE_ASSERTION_ID.fullmatch(self.lease_owner)
            or len(self.cursor_blind_id) != 32
            or not self.acquired_at_ms < self.exclusive_until_ms
            or not self.acquired_at_ms <= self.updated_at_ms <= self.exclusive_until_ms
        ):
            raise ValueError("lease migration row mismatch")
        return self


class BudgetAccountMigrationRowV1(_Closed):
    owner_path_discriminator: str
    account_scope_blind_id: bytes
    project_scope_blind_id: bytes
    approved_ceiling_cents: int = Field(ge=1, le=MAX_CENTS)
    confirmed_cents: Literal[0] = 0
    open_cents: Literal[0] = 0
    unknown_cents: Literal[0] = 0
    row_version: int = Field(ge=1, le=MAX_I63)
    updated_at_ms: int = Field(ge=0, le=MAX_I63)

    @model_validator(mode="after")
    def _closed_row(self) -> BudgetAccountMigrationRowV1:
        if (
            not _OWNER_PATH.fullmatch(self.owner_path_discriminator)
            or len(self.account_scope_blind_id) != 32
            or len(self.project_scope_blind_id) != 32
        ):
            raise ValueError("budget migration row mismatch")
        return self


class FrozenPaidLaneMigrationCorpusV1(_Closed):
    schema_version: Literal[1] = 1
    target_migration_epoch: Literal[1] = 1
    freeze_nonce: str
    quiesced_at_ms: int = Field(ge=0, le=MAX_I63)
    drained_at_ms: int = Field(ge=0, le=MAX_I63)
    sealed_at_ms: int = Field(ge=0, le=MAX_I63)
    source_stores: tuple[MigrationSourceStoreV1, ...]
    provider_capabilities_v4: tuple[ProviderCapabilityV4MigrationRowV1, ...] = ()
    provider_revocation_heads: tuple[ProviderRevocationHeadMigrationRowV1, ...] = ()
    provider_revocation_current: tuple[ProviderRevocationCurrentMigrationRowV1, ...] = ()
    source_heads: tuple[SourceHeadMigrationRowV1, ...] = ()
    source_current: tuple[SourceCurrentMigrationRowV1, ...] = ()
    encrypted_source_bundles: tuple[EncryptedSourceBundleMigrationRowV1, ...] = ()
    owner_operations: tuple[OwnerOperationMigrationRowV1, ...] = ()
    consent_claims: tuple[ConsentClaimMigrationRowV1, ...] = ()
    queue_leases: tuple[QueueLeaseMigrationRowV1, ...] = ()
    budget_accounts: tuple[BudgetAccountMigrationRowV1, ...] = ()
    source_manifest_sha256: str

    @model_validator(mode="after")
    def _closed_corpus(self) -> FrozenPaidLaneMigrationCorpusV1:
        collections: tuple[tuple[str, tuple[BaseModel, ...], tuple[str, ...]], ...] = (
            ("provider_capabilities_v4", self.provider_capabilities_v4, ("capability_sha256",)),
            (
                "provider_revocation_heads",
                self.provider_revocation_heads,
                ("registry_id", "owner_path_discriminator", "epoch"),
            ),
            (
                "provider_revocation_current",
                self.provider_revocation_current,
                ("registry_id", "owner_path_discriminator"),
            ),
            (
                "source_heads",
                self.source_heads,
                ("registry_id", "owner_path_discriminator", "epoch"),
            ),
            ("source_current", self.source_current, ("registry_id", "owner_path_discriminator")),
            (
                "encrypted_source_bundles",
                self.encrypted_source_bundles,
                ("opaque_source_bundle_id",),
            ),
            (
                "owner_operations",
                self.owner_operations,
                ("owner_path_discriminator", "operation_id"),
            ),
            (
                "consent_claims",
                self.consent_claims,
                ("owner_path_discriminator", "consent_blind_id"),
            ),
            ("queue_leases", self.queue_leases, ("owner_path_discriminator", "queue_operation_id")),
            (
                "budget_accounts",
                self.budget_accounts,
                ("owner_path_discriminator", "account_scope_blind_id", "project_scope_blind_id"),
            ),
        )
        for _, bounded_rows, _ in collections:
            _require_migration_collection_count(len(bounded_rows))
        if not (
            self.quiesced_at_ms <= self.drained_at_ms <= self.sealed_at_ms
            and 0 < len(self.source_stores) <= MAX_STORES
        ):
            raise ValueError("migration closure bounds")
        _bounded_migration_bytes(self, bound=MAX_CORPUS_BYTES)
        source_keys = tuple((row.store_kind, row.store_id) for row in self.source_stores)
        expected_roles = tuple(sorted(_MIGRATION_ROLE_TABLES))
        if (
            tuple(row.store_kind for row in self.source_stores) != expected_roles
            or source_keys != tuple(sorted(set(source_keys)))
            or len({row.store_id for row in self.source_stores}) != len(expected_roles)
        ):
            raise ValueError("source stores not canonical")
        barrier_ids = {row.native_writer_barrier_id for row in self.source_stores}
        if barrier_ids != {_migration_barrier_id(self.freeze_nonce)}:
            raise ValueError("source stores do not share one barrier")
        for source_store in self.source_stores:
            if (
                source_store.schema_sha256 != _migration_role_schema_sha256(source_store.store_kind)
                or source_store.final_version != _MIGRATION_CHILD_FINAL_VERSION
            ):
                raise ValueError("source store closed contract mismatch")
        for _, rows, key_fields in collections:
            keys = tuple(tuple(getattr(row, field) for field in key_fields) for row in rows)
            if keys != tuple(sorted(set(keys))):
                raise ValueError("migration collection not canonical")
        for capability_row in self.provider_capabilities_v4:
            if (
                capability_row.issued_at_ms >= capability_row.expires_at_ms
                or not _HEX64.fullmatch(capability_row.capability_sha256)
                or not _SAFE_ASSERTION_ID.fullmatch(capability_row.capability_id)
                or not _OWNER_PATH.fullmatch(capability_row.owner_path_discriminator)
                or not _REGISTRY_ID.fullmatch(capability_row.revocation_registry_id)
                or not _HEX64.fullmatch(capability_row.revocation_trusted_floor_sha256)
                or not _KEY_ID.fullmatch(capability_row.key_id)
                or len(capability_row.signature_ed25519) != 64
                or not _canonical_migration_document(capability_row.document_json)
            ):
                raise ValueError("capability issuance window")
        for operation_row in self.owner_operations:
            if operation_row.created_at_ms > operation_row.updated_at_ms or (
                operation_row.state == "cancelled"
                and (operation_row.cancel_requested != 1 or operation_row.cancellation_version < 1)
            ):
                raise ValueError("operation closure mismatch")
        if any(row.exclusive_until_ms > self.sealed_at_ms for row in self.queue_leases):
            raise ValueError("live lease in frozen corpus")
        for revocation_row in self.provider_revocation_heads:
            if (
                not _HEX64.fullmatch(revocation_row.head_sha256)
                or not _REGISTRY_ID.fullmatch(revocation_row.registry_id)
                or not _OWNER_PATH.fullmatch(revocation_row.owner_path_discriminator)
                or (revocation_row.epoch == 0) != (revocation_row.predecessor_head_sha256 is None)
                or (
                    revocation_row.predecessor_head_sha256 is not None
                    and not _HEX64.fullmatch(revocation_row.predecessor_head_sha256)
                )
                or len(revocation_row.signature_ed25519) != 64
                or len(revocation_row.revoked_capability_hashes_json) > MAX_REVOCATION_SET_BYTES
                or not _canonical_migration_document(revocation_row.document_json)
            ):
                raise ValueError("revocation head closure")
        for source_row in self.source_heads:
            if (
                not _HEX64.fullmatch(source_row.head_sha256)
                or not _REGISTRY_ID.fullmatch(source_row.registry_id)
                or not _OWNER_PATH.fullmatch(source_row.owner_path_discriminator)
                or not _HEX64.fullmatch(source_row.previous_head_sha256)
                or len(source_row.signature_ed25519) != 64
                or len(source_row.active_bundle_revisions_json) > MAX_REVISION_SET_BYTES
                or len(source_row.snapshot_json) > MAX_DOCUMENT_BYTES
                or not _canonical_migration_document(source_row.document_json)
            ):
                raise ValueError("source head closure")
        for grouped_heads, currents in (
            (self.provider_revocation_heads, self.provider_revocation_current),
            (self.source_heads, self.source_current),
        ):
            groups: dict[tuple[str, str], list[object]] = {}
            for head in grouped_heads:
                groups.setdefault((head.registry_id, head.owner_path_discriminator), []).append(
                    head
                )
            current_by_group = {
                (row.registry_id, row.owner_path_discriminator): row for row in currents
            }
            if set(current_by_group) != set(groups):
                raise ValueError("head/current roster mismatch")
            for group_key, heads in groups.items():
                prior_revoked: tuple[str, ...] = ()
                prior_revisions: tuple[OpaqueSourceBundleRevisionV1, ...] = ()
                for index, head_value in enumerate(heads):
                    any_head: Any = head_value
                    if any_head.epoch != index:
                        raise ValueError("head epoch gap")
                    if index:
                        predecessor: Any = heads[index - 1]
                        previous_hash = getattr(
                            any_head,
                            "predecessor_head_sha256",
                            getattr(any_head, "previous_head_sha256", None),
                        )
                        if (
                            previous_hash != predecessor.head_sha256
                            or any_head.issued_at_ms <= predecessor.issued_at_ms
                        ):
                            raise ValueError("head chain fork")
                    if isinstance(any_head, ProviderRevocationHeadMigrationRowV1):
                        revoked = SignedProviderRevocationHeadFixtureV1.model_validate_json(
                            any_head.document_json
                        ).revoked_capability_sha256s
                        additions = tuple(item for item in revoked if item not in prior_revoked)
                        if (
                            (index == 0 and revoked != ())
                            or not set(prior_revoked).issubset(revoked)
                            or len(additions) > MAX_REVOKED_PER_HEAD
                        ):
                            raise ValueError("revocation cumulative successor mismatch")
                        prior_revoked = revoked
                    elif isinstance(any_head, SourceHeadMigrationRowV1):
                        revisions = SignedSourceHeadFixtureV1.model_validate_json(
                            any_head.document_json
                        ).snapshot.active_bundle_revisions
                        prior_keys = {
                            (item.opaque_source_bundle_id, item.row_revision)
                            for item in prior_revisions
                        }
                        next_keys = {
                            (item.opaque_source_bundle_id, item.row_revision) for item in revisions
                        }
                        new_keys = next_keys - prior_keys
                        if index and (
                            not prior_keys.issubset(next_keys)
                            or len(new_keys) != 1
                            or next(iter(new_keys))[1] != 1
                        ):
                            raise ValueError("source add-only successor mismatch")
                        prior_revisions = revisions
                terminal: Any = heads[-1]
                current: Any = current_by_group[group_key]
                if (
                    current.head_sha256 != terminal.head_sha256
                    or current.epoch != terminal.epoch
                    or current.state_version != terminal.epoch + 1
                    or current.updated_at_ms < terminal.issued_at_ms
                ):
                    raise ValueError("head current is not terminal")
        revocation_groups = {
            (row.revocation_registry_id, row.owner_path_discriminator): {
                head.head_sha256
                for head in self.provider_revocation_heads
                if (head.registry_id, head.owner_path_discriminator)
                == (row.revocation_registry_id, row.owner_path_discriminator)
            }
            for row in self.provider_capabilities_v4
        }
        if any(
            row.revocation_trusted_floor_sha256
            not in revocation_groups.get(
                (row.revocation_registry_id, row.owner_path_discriminator), set()
            )
            for row in self.provider_capabilities_v4
        ):
            raise ValueError("capability revocation floor mismatch")
        active_bundles = {
            (head.owner_path_discriminator, revision.opaque_source_bundle_id, revision.row_revision)
            for head in self.source_heads
            for revision in SignedSourceHeadFixtureV1.model_validate_json(
                head.document_json
            ).snapshot.active_bundle_revisions
        }
        stored_bundles = {
            (row.owner_path_discriminator, row.opaque_source_bundle_id, row.row_version)
            for row in self.encrypted_source_bundles
        }
        nonces = tuple(
            (row.owner_path_discriminator, row.key_version, row.nonce)
            for row in self.encrypted_source_bundles
        )
        if active_bundles != stored_bundles:
            raise ValueError("source bundle roster mismatch")
        if len(nonces) != len(set(nonces)):
            raise ValueError("source bundle nonce reuse")
        for source_store in self.source_stores:
            tables = _MIGRATION_ROLE_TABLES[source_store.store_kind]
            role_rows = tuple(
                (table_name, row) for table_name in tables for row in getattr(self, table_name)
            )
            sequence = [
                [table_name, _migration_row_sha256(table_name, row)]
                for table_name, row in role_rows
            ]
            role_bytes = source_store.store_kind.encode()
            expected_digest = hashlib.sha256(
                _SOURCE_STORE_ROWS_DOMAIN
                + _u32be(len(role_bytes))
                + role_bytes
                + _canonical_json(sequence)
            ).hexdigest()
            if (
                source_store.row_count != len(role_rows)
                or source_store.ordered_rows_sha256 != expected_digest
            ):
                raise ValueError("source store provenance mismatch")
        if not _HEX64.fullmatch(self.source_manifest_sha256):
            raise ValueError("manifest hash syntax")
        if self.source_manifest_sha256 != _migration_source_manifest_sha256(self):
            raise ValueError("manifest hash mismatch")
        return self


def _migration_source_manifest_sha256(corpus: FrozenPaidLaneMigrationCorpusV1) -> str:
    collection_names = (
        "provider_capabilities_v4",
        "provider_revocation_heads",
        "provider_revocation_current",
        "source_heads",
        "source_current",
        "encrypted_source_bundles",
        "owner_operations",
        "consent_claims",
        "queue_leases",
        "budget_accounts",
    )
    collections: list[dict[str, object]] = []
    for table_name in collection_names:
        rows = getattr(corpus, table_name)
        row_hashes: list[str] = []
        for row in rows:
            row_hashes.append(_migration_row_sha256(table_name, row))
        collections.append(
            {
                "table_name": table_name,
                "row_count": len(rows),
                "ordered_row_sha256s": row_hashes,
            }
        )
    material = {
        "schema_version": 1,
        "freeze_nonce": corpus.freeze_nonce,
        "quiesced_at_ms": corpus.quiesced_at_ms,
        "drained_at_ms": corpus.drained_at_ms,
        "sealed_at_ms": corpus.sealed_at_ms,
        "source_stores": [row.model_dump(mode="json") for row in corpus.source_stores],
        "collections": sorted(collections, key=lambda item: str(item["table_name"])),
    }
    return hashlib.sha256(_SOURCE_MANIFEST_DOMAIN + _canonical_json(material)).hexdigest()


def _migration_row_sha256(table_name: str, row: BaseModel) -> str:
    columns: list[list[object]] = []
    for name in type(row).model_fields:
        value = getattr(row, name)
        tag: str
        encoded: object
        if value is None:
            tag, encoded = "null", None
        elif type(value) is int:
            tag, encoded = "integer", value
        elif type(value) is bytes:
            tag, encoded = "blob", value.hex()
        elif type(value) is str:
            tag, encoded = "text", value
        else:
            raise ValueError("unsupported migration row value")
        columns.append([name, tag, encoded])
    return _typed_migration_row_sha256(table_name, columns)


def _typed_migration_row_sha256(table_name: str, columns: list[list[object]]) -> str:
    table_bytes = table_name.encode()
    return hashlib.sha256(
        _MIGRATION_ROW_DOMAIN + _u32be(len(table_bytes)) + table_bytes + _canonical_json(columns)
    ).hexdigest()


def _canonical_migration_document(value: bytes) -> bool:
    try:
        return _canonical_json(_parse_strict_json(value, MAX_DOCUMENT_BYTES)) == value
    except Exception:
        return False


class PaidLaneTableRowCountsV1(_Closed):
    paid_lane_schema: int = Field(ge=0, le=MAX_MIGRATION_ROWS)
    provider_capabilities_v4: int = Field(ge=0, le=MAX_MIGRATION_ROWS)
    provider_revocation_heads: int = Field(ge=0, le=MAX_MIGRATION_ROWS)
    provider_revocation_current: int = Field(ge=0, le=MAX_MIGRATION_ROWS)
    source_heads: int = Field(ge=0, le=MAX_MIGRATION_ROWS)
    source_current: int = Field(ge=0, le=MAX_MIGRATION_ROWS)
    encrypted_source_bundles: int = Field(ge=0, le=MAX_MIGRATION_ROWS)
    owner_operations: int = Field(ge=0, le=MAX_MIGRATION_ROWS)
    consent_claims: int = Field(ge=0, le=MAX_MIGRATION_ROWS)
    queue_leases: int = Field(ge=0, le=MAX_MIGRATION_ROWS)
    budget_accounts: int = Field(ge=0, le=MAX_MIGRATION_ROWS)
    logical_effects: Literal[0] = 0
    paid_admissions: Literal[0] = 0
    budget_holds: Literal[0] = 0
    paid_attempts: Literal[0] = 0
    paid_effect_transitions: Literal[0] = 0
    paid_attempt_events: Literal[0] = 0
    migration_cutover_proof: Literal[0] = 0


class CopyAuditV1(_Closed):
    schema_version: Literal[1] = 1
    target_store_id: str
    target_schema_version: Literal[1] = 1
    target_migration_epoch: Literal[0] = 0
    source_manifest_sha256: str
    table_row_counts: PaidLaneTableRowCountsV1
    ordered_table_row_sha256s: tuple[tuple[str, tuple[str, ...]], ...]
    foreign_key_check_rows: tuple[tuple[object, ...], ...] = ()
    budget_invariant_sha256: str
    chain_audit_sha256: str

    @model_validator(mode="after")
    def _closed_audit(self) -> CopyAuditV1:
        expected_tables = tuple(PaidLaneTableRowCountsV1.model_fields)
        names = tuple(name for name, _ in self.ordered_table_row_sha256s)
        if (
            not _STORE_ID.fullmatch(self.target_store_id)
            or not _HEX64.fullmatch(self.source_manifest_sha256)
            or not _HEX64.fullmatch(self.budget_invariant_sha256)
            or not _HEX64.fullmatch(self.chain_audit_sha256)
            or self.foreign_key_check_rows != ()
            or names != expected_tables
            or len(set(names)) != len(names)
        ):
            raise ValueError("copy audit closure")
        counts = self.table_row_counts.model_dump()
        for table_name, hashes in self.ordered_table_row_sha256s:
            if len(hashes) != counts[table_name] or any(
                not _HEX64.fullmatch(value) for value in hashes
            ):
                raise ValueError("copy audit row hashes")
        return self


def _copy_floor_pin_map(
    pins: tuple[ProviderRevocationFloorPinV1, ...] | tuple[OwnerPrivateSourceFloorPinV1, ...],
) -> dict[tuple[str, str], ProviderRevocationFloorPinV1 | OwnerPrivateSourceFloorPinV1]:
    ordered = tuple(sorted(pins, key=lambda pin: (pin.registry_id, pin.owner_path_discriminator)))
    if pins != ordered or len(pins) > MAX_MUTABLE_CURRENT_ROWS:
        raise ValueError("copy intent floor pin order")
    result = {(pin.registry_id, pin.owner_path_discriminator): pin for pin in pins}
    if len(result) != len(pins):
        raise ValueError("copy intent duplicate floor pin")
    return result


def _audit_corpus_authority_v1(
    corpus: FrozenPaidLaneMigrationCorpusV1,
    *,
    capability_keys: Mapping[str, bytes],
    revocation_keys: Mapping[str, bytes],
    source_keys: Mapping[str, bytes],
    revocation_pins: Mapping[
        tuple[str, str], ProviderRevocationFloorPinV1 | OwnerPrivateSourceFloorPinV1
    ],
    source_pins: Mapping[
        tuple[str, str], ProviderRevocationFloorPinV1 | OwnerPrivateSourceFloorPinV1
    ],
) -> None:
    revocation_current = {
        (row.registry_id, row.owner_path_discriminator): row
        for row in corpus.provider_revocation_current
    }
    source_current = {
        (row.registry_id, row.owner_path_discriminator): row for row in corpus.source_current
    }
    if set(revocation_current) != set(revocation_pins) or set(source_current) != set(source_pins):
        raise ValueError("copy intent authority roster")
    for capability_row in corpus.provider_capabilities_v4:
        capability = SignedProviderCapabilityV4FixtureV1.model_validate_json(
            capability_row.document_json
        )
        verify_capability_v4(capability, verification_keys=capability_keys)
        if (
            capability.capability_sha256 != capability_row.capability_sha256
            or capability.capability_id != capability_row.capability_id
            or capability.owner_path_discriminator != capability_row.owner_path_discriminator
            or capability.revocation_registry_id != capability_row.revocation_registry_id
            or capability.revocation_trusted_floor_sha256
            != capability_row.revocation_trusted_floor_sha256
            or capability.issued_at_ms != capability_row.issued_at_ms
            or capability.expires_at_ms != capability_row.expires_at_ms
            or capability.key_id != capability_row.key_id
            or bytes.fromhex(capability.signature_ed25519) != capability_row.signature_ed25519
            or _canonical_model_json(capability) != capability_row.document_json
        ):
            raise ValueError("copy intent capability authority")
    for key, pin in revocation_pins.items():
        known_capabilities = {
            row.capability_sha256
            for row in corpus.provider_capabilities_v4
            if (row.revocation_registry_id, row.owner_path_discriminator) == key
        }
        revocation_heads = tuple(
            revocation_row
            for revocation_row in corpus.provider_revocation_heads
            if (revocation_row.registry_id, revocation_row.owner_path_discriminator) == key
        )
        revocation_current_row = revocation_current[key]
        if (
            not revocation_heads
            or revocation_heads[-1].head_sha256 != revocation_current_row.head_sha256
        ):
            raise ValueError("copy intent revocation current")
        floor = tuple(item for item in revocation_heads if item.epoch == pin.floor_epoch)
        if len(floor) != 1 or floor[0].head_sha256 != pin.floor_head_sha256:
            raise ValueError("copy intent revocation floor")
        for revocation_row in revocation_heads:
            revocation_head = SignedProviderRevocationHeadFixtureV1.model_validate_json(
                revocation_row.document_json
            )
            verify_revocation_head(revocation_head, verification_keys=revocation_keys)
            if (
                revocation_head.head_sha256 != revocation_row.head_sha256
                or bytes.fromhex(revocation_head.signature_ed25519)
                != revocation_row.signature_ed25519
                or any(
                    revoked not in known_capabilities
                    for revoked in revocation_head.revoked_capability_sha256s
                )
            ):
                raise ValueError("copy intent revocation authority")
    for key, pin in source_pins.items():
        source_heads = tuple(
            source_row
            for source_row in corpus.source_heads
            if (source_row.registry_id, source_row.owner_path_discriminator) == key
        )
        source_current_row = source_current[key]
        if not source_heads or source_heads[-1].head_sha256 != source_current_row.head_sha256:
            raise ValueError("copy intent source current")
        source_floor = tuple(item for item in source_heads if item.epoch == pin.floor_epoch)
        if len(source_floor) != 1 or source_floor[0].head_sha256 != pin.floor_head_sha256:
            raise ValueError("copy intent source floor")
        for source_row in source_heads:
            source_head = SignedSourceHeadFixtureV1.model_validate_json(source_row.document_json)
            verify_source_head(source_head, verification_keys=source_keys)
            if (
                source_head.head_sha256 != source_row.head_sha256
                or bytes.fromhex(source_head.signature_ed25519) != source_row.signature_ed25519
            ):
                raise ValueError("copy intent source authority")


def _copy_audit_intent_v1(
    *,
    corpus: FrozenPaidLaneMigrationCorpusV1,
    target_store_id: str,
    semantic_source_sha256: str,
    contract_sha256: str,
    provider_capability_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_verification_keys: tuple[VerificationKeyV1, ...],
    source_head_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_floor_pins: tuple[ProviderRevocationFloorPinV1, ...],
    source_floor_pins: tuple[OwnerPrivateSourceFloorPinV1, ...],
) -> CopyAuditV1:
    if type(corpus) is not FrozenPaidLaneMigrationCorpusV1:
        raise ValueError("copy intent corpus type")
    corpus = FrozenPaidLaneMigrationCorpusV1.model_validate(corpus.model_dump(mode="python"))
    if (
        not _STORE_ID.fullmatch(target_store_id)
        or not _HEX64.fullmatch(semantic_source_sha256)
        or not _HEX64.fullmatch(contract_sha256)
    ):
        raise ValueError("copy intent target identity")
    capability_keys = _copy_verification_keyring(provider_capability_verification_keys)
    revocation_keys = _copy_verification_keyring(provider_revocation_verification_keys)
    source_keys = _copy_verification_keyring(source_head_verification_keys)
    revocation_pins = _copy_floor_pin_map(provider_revocation_floor_pins)
    source_pins = _copy_floor_pin_map(source_floor_pins)
    _audit_corpus_authority_v1(
        corpus,
        capability_keys=capability_keys,
        revocation_keys=revocation_keys,
        source_keys=source_keys,
        revocation_pins=revocation_pins,
        source_pins=source_pins,
    )
    migrated_tables = (
        "provider_capabilities_v4",
        "provider_revocation_heads",
        "provider_revocation_current",
        "source_heads",
        "source_current",
        "encrypted_source_bundles",
        "owner_operations",
        "consent_claims",
        "queue_leases",
        "budget_accounts",
    )
    hashes_by_table: dict[str, tuple[str, ...]] = {
        table_name: tuple(
            _migration_row_sha256(table_name, row) for row in getattr(corpus, table_name)
        )
        for table_name in migrated_tables
    }
    schema_columns: list[list[object]] = [
        ["singleton", "integer", 1],
        ["schema_version", "integer", 1],
        ["migration_epoch", "integer", 0],
        ["store_id", "text", target_store_id],
        ["semantic_source_sha256", "text", semantic_source_sha256],
        ["contract_sha256", "text", contract_sha256],
        ["cutover_marker_sha256", "null", None],
        ["created_at_ms", "integer", 0],
    ]
    hashes_by_table["paid_lane_schema"] = (
        _typed_migration_row_sha256("paid_lane_schema", schema_columns),
    )
    for table_name in PaidLaneTableRowCountsV1.model_fields:
        hashes_by_table.setdefault(table_name, ())
    ordered = tuple(
        (table_name, hashes_by_table[table_name])
        for table_name in PaidLaneTableRowCountsV1.model_fields
    )
    counts = PaidLaneTableRowCountsV1.model_validate(
        {table_name: len(row_hashes) for table_name, row_hashes in ordered}
    )
    budget_row_hashes = hashes_by_table["budget_accounts"]
    budget_material = {
        "schema_version": 1,
        "source_manifest_sha256": corpus.source_manifest_sha256,
        "budget_account_row_sha256s": budget_row_hashes,
        "approved_ceiling_cents_total": sum(
            row.approved_ceiling_cents for row in corpus.budget_accounts
        ),
        "confirmed_cents_total": 0,
        "open_cents_total": 0,
        "unknown_cents_total": 0,
    }
    chain_tables = (
        "provider_capabilities_v4",
        "provider_revocation_heads",
        "provider_revocation_current",
        "source_heads",
        "source_current",
        "encrypted_source_bundles",
    )
    chain_material = {
        "schema_version": 1,
        "source_manifest_sha256": corpus.source_manifest_sha256,
        "ordered_table_row_sha256s": [
            [table_name, list(hashes_by_table[table_name])] for table_name in chain_tables
        ],
        "authority_inputs": {
            "provider_capability_keys": [
                [key_id, hashlib.sha256(public_key).hexdigest()]
                for key_id, public_key in sorted(capability_keys.items())
            ],
            "provider_revocation_keys": [
                [key_id, hashlib.sha256(public_key).hexdigest()]
                for key_id, public_key in sorted(revocation_keys.items())
            ],
            "source_head_keys": [
                [key_id, hashlib.sha256(public_key).hexdigest()]
                for key_id, public_key in sorted(source_keys.items())
            ],
            "provider_revocation_floor_pins": [
                pin.model_dump(mode="json") for pin in provider_revocation_floor_pins
            ],
            "source_floor_pins": [pin.model_dump(mode="json") for pin in source_floor_pins],
        },
    }
    return CopyAuditV1(
        target_store_id=target_store_id,
        source_manifest_sha256=corpus.source_manifest_sha256,
        table_row_counts=counts,
        ordered_table_row_sha256s=ordered,
        budget_invariant_sha256=hashlib.sha256(
            _COPY_BUDGET_INVARIANT_DOMAIN + _canonical_json(budget_material)
        ).hexdigest(),
        chain_audit_sha256=hashlib.sha256(
            _COPY_CHAIN_AUDIT_DOMAIN + _canonical_json(chain_material)
        ).hexdigest(),
    )


_COPY_MIGRATION_MODELS: Mapping[str, type[BaseModel]] = MappingProxyType(
    {
        "provider_capabilities_v4": ProviderCapabilityV4MigrationRowV1,
        "provider_revocation_heads": ProviderRevocationHeadMigrationRowV1,
        "provider_revocation_current": ProviderRevocationCurrentMigrationRowV1,
        "source_heads": SourceHeadMigrationRowV1,
        "source_current": SourceCurrentMigrationRowV1,
        "encrypted_source_bundles": EncryptedSourceBundleMigrationRowV1,
        "owner_operations": OwnerOperationMigrationRowV1,
        "consent_claims": ConsentClaimMigrationRowV1,
        "queue_leases": QueueLeaseMigrationRowV1,
        "budget_accounts": BudgetAccountMigrationRowV1,
    }
)


_COPY_TABLE_ORDER_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "provider_capabilities_v4": ("capability_sha256",),
        "provider_revocation_heads": ("registry_id", "owner_path_discriminator", "epoch"),
        "provider_revocation_current": ("registry_id", "owner_path_discriminator"),
        "source_heads": ("registry_id", "owner_path_discriminator", "epoch"),
        "source_current": ("registry_id", "owner_path_discriminator"),
        "encrypted_source_bundles": ("opaque_source_bundle_id",),
        "owner_operations": ("owner_path_discriminator", "operation_id"),
        "consent_claims": ("owner_path_discriminator", "consent_blind_id"),
        "queue_leases": ("owner_path_discriminator", "queue_operation_id"),
        "budget_accounts": (
            "owner_path_discriminator",
            "account_scope_blind_id",
            "project_scope_blind_id",
        ),
    }
)


def _copy_audit_observed_target_v1(
    connection: sqlite3.Connection,
    *,
    corpus: FrozenPaidLaneMigrationCorpusV1,
    target_store_id: str,
    semantic_source_sha256: str,
    contract_sha256: str,
    provider_capability_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_verification_keys: tuple[VerificationKeyV1, ...],
    source_head_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_floor_pins: tuple[ProviderRevocationFloorPinV1, ...],
    source_floor_pins: tuple[OwnerPrivateSourceFloorPinV1, ...],
) -> CopyAuditV1:
    if type(connection) is not sqlite3.Connection:
        raise ValueError("copy target connection type")
    expected = _copy_audit_intent_v1(
        corpus=corpus,
        target_store_id=target_store_id,
        semantic_source_sha256=semantic_source_sha256,
        contract_sha256=contract_sha256,
        provider_capability_verification_keys=provider_capability_verification_keys,
        provider_revocation_verification_keys=provider_revocation_verification_keys,
        source_head_verification_keys=source_head_verification_keys,
        provider_revocation_floor_pins=provider_revocation_floor_pins,
        source_floor_pins=source_floor_pins,
    )
    _audit_schema(connection)
    singleton = connection.execute(
        "SELECT singleton,schema_version,migration_epoch,store_id,semantic_source_sha256,"
        "contract_sha256,cutover_marker_sha256,created_at_ms FROM paid_lane_schema"
    ).fetchall()
    if singleton != [(1, 1, 0, target_store_id, semantic_source_sha256, contract_sha256, None, 0)]:
        raise ValueError("copy target singleton")
    if connection.execute("PRAGMA foreign_key_check").fetchall() != []:
        raise ValueError("copy target foreign keys")
    for table_name, order_fields in _COPY_TABLE_ORDER_FIELDS.items():
        expected_rows = getattr(corpus, table_name)
        columns = tuple(_COPY_MIGRATION_MODELS[table_name].model_fields)
        selected = connection.execute(
            f"SELECT {','.join(columns)} FROM {table_name} "
            f"ORDER BY {','.join(order_fields)} LIMIT ?",
            (MAX_MIGRATION_ROWS + 1,),
        ).fetchall()
        expected_storage = [
            tuple(
                (
                    value.hex()
                    if isinstance(value, bytes) and column == "signature_ed25519"
                    else value
                )
                for column in columns
                for value in (getattr(row, column),)
            )
            for row in expected_rows
        ]
        if selected != expected_storage:
            raise ValueError("copy target row mismatch")
    for table_name in (
        "logical_effects",
        "paid_admissions",
        "budget_holds",
        "paid_attempts",
        "paid_effect_transitions",
        "paid_attempt_events",
        "migration_cutover_proof",
    ):
        if connection.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone() is not None:
            raise ValueError("copy target runtime row")
    _audit_authority_chains(
        connection,
        revocation_floor_pins={
            (pin.registry_id, pin.owner_path_discriminator): pin
            for pin in provider_revocation_floor_pins
        },
        source_floor_pins={
            (pin.registry_id, pin.owner_path_discriminator): pin for pin in source_floor_pins
        },
        revocation_verification_keys=_copy_verification_keyring(
            provider_revocation_verification_keys
        ),
        source_verification_keys=_copy_verification_keyring(source_head_verification_keys),
    )
    return expected


def _reconcile_copy_prepared_target_v1(
    connection: sqlite3.Connection,
    *,
    corpus: FrozenPaidLaneMigrationCorpusV1,
    expected_copy_audit_sha256: str,
    target_store_id: str,
    semantic_source_sha256: str,
    contract_sha256: str,
    provider_capability_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_verification_keys: tuple[VerificationKeyV1, ...],
    source_head_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_floor_pins: tuple[ProviderRevocationFloorPinV1, ...],
    source_floor_pins: tuple[OwnerPrivateSourceFloorPinV1, ...],
) -> tuple[CopyAuditV1, bool]:
    if type(connection) is not sqlite3.Connection or not connection.in_transaction:
        raise ValueError("copy target transaction state")
    intent = _copy_audit_intent_v1(
        corpus=corpus,
        target_store_id=target_store_id,
        semantic_source_sha256=semantic_source_sha256,
        contract_sha256=contract_sha256,
        provider_capability_verification_keys=provider_capability_verification_keys,
        provider_revocation_verification_keys=provider_revocation_verification_keys,
        source_head_verification_keys=source_head_verification_keys,
        provider_revocation_floor_pins=provider_revocation_floor_pins,
        source_floor_pins=source_floor_pins,
    )
    if _copy_audit_sha256(intent) != expected_copy_audit_sha256:
        raise ValueError("copy target audit intent")
    _audit_schema(connection)
    singleton = connection.execute(
        "SELECT singleton,schema_version,migration_epoch,store_id,"
        "semantic_source_sha256,contract_sha256,cutover_marker_sha256,created_at_ms "
        "FROM paid_lane_schema"
    ).fetchall()
    if singleton != [(1, 1, 0, target_store_id, semantic_source_sha256, contract_sha256, None, 0)]:
        raise ValueError("copy target singleton")
    for table_name in (
        "logical_effects",
        "paid_admissions",
        "budget_holds",
        "paid_attempts",
        "paid_effect_transitions",
        "paid_attempt_events",
        "migration_cutover_proof",
    ):
        if connection.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone() is not None:
            raise ValueError("copy target runtime row")
    populated_tables = tuple(
        table_name
        for table_name in _COPY_TABLE_ORDER_FIELDS
        if connection.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone() is not None
    )
    copied = not populated_tables
    if copied:
        for table_name in _COPY_TABLE_ORDER_FIELDS:
            for row in getattr(corpus, table_name):
                columns = tuple(type(row).model_fields)
                values = tuple(
                    value.hex()
                    if isinstance(value, bytes) and column == "signature_ed25519"
                    else value
                    for column in columns
                    for value in (getattr(row, column),)
                )
                connection.execute(
                    f"INSERT INTO {table_name} ({','.join(columns)}) "
                    f"VALUES ({','.join('?' for _ in columns)})",
                    values,
                )
    audit = _copy_audit_observed_target_v1(
        connection,
        corpus=corpus,
        target_store_id=target_store_id,
        semantic_source_sha256=semantic_source_sha256,
        contract_sha256=contract_sha256,
        provider_capability_verification_keys=provider_capability_verification_keys,
        provider_revocation_verification_keys=provider_revocation_verification_keys,
        source_head_verification_keys=source_head_verification_keys,
        provider_revocation_floor_pins=provider_revocation_floor_pins,
        source_floor_pins=source_floor_pins,
    )
    if audit != intent:
        raise ValueError("copy target audit mismatch")
    return audit, copied


class SignedCutoverMarkerV1(_Closed):
    schema_version: Literal[1] = 1
    target_store_id: str
    prior_migration_epoch: Literal[0] = 0
    migration_epoch: Literal[1] = 1
    freeze_nonce: str
    source_manifest_sha256: str
    copy_audit_sha256: str
    semantic_source_sha256: str
    contract_sha256: str
    sealed_at_ms: int = Field(ge=0, le=MAX_I63)
    marker_committed_at_ms: int = Field(ge=0, le=MAX_I63)
    key_id: str
    issuer_role: Literal["private_paid_cutover_fixture_issuer"] = (
        "private_paid_cutover_fixture_issuer"
    )
    purpose: Literal["private_paid_cutover_fixture_v1"] = "private_paid_cutover_fixture_v1"
    scheme: Literal["ed25519"] = "ed25519"
    marker_sha256: str
    signature_ed25519: bytes

    @model_validator(mode="after")
    def _closed_marker(self) -> SignedCutoverMarkerV1:
        for value in (
            self.source_manifest_sha256,
            self.copy_audit_sha256,
            self.semantic_source_sha256,
            self.contract_sha256,
        ):
            if not _HEX64.fullmatch(value):
                raise ValueError("marker hash syntax")
        if (
            not _STORE_ID.fullmatch(self.target_store_id)
            or not _HEX64.fullmatch(self.freeze_nonce)
            or not _KEY_ID.fullmatch(self.key_id)
            or self.marker_committed_at_ms < self.sealed_at_ms
            or len(self.signature_ed25519) != 64
        ):
            raise ValueError("marker closure")
        material = self.model_dump(mode="json", exclude={"marker_sha256", "signature_ed25519"})
        expected = hashlib.sha256(_CUTOVER_MARKER_DOMAIN + _canonical_json(material)).hexdigest()
        if self.marker_sha256 != expected:
            raise ValueError("marker hash mismatch")
        return self


def _copy_audit_sha256(audit: CopyAuditV1) -> str:
    return hashlib.sha256(
        _COPY_AUDIT_DOMAIN + _canonical_json(audit.model_dump(mode="json"))
    ).hexdigest()


_MIGRATION_LIFECYCLE_PHASES = Literal[
    "schema_only",
    "barrier_acquired",
    "sources_sealed",
    "copy_prepared",
    "copied_epoch0",
    "abort_prepared",
    "abort_renamed_to_tombstone",
    "abort_rename_fsynced",
    "abort_tombstone_unlinked",
    "abort_deletion_fsynced",
    "abort_sources_revalidated",
    "abort_barrier_released",
]
_MIGRATION_PRECOPY_TRANSITIONS: Mapping[str, str] = MappingProxyType(
    {
        "schema_only": "barrier_acquired",
        "barrier_acquired": "sources_sealed",
        "sources_sealed": "copy_prepared",
        "copy_prepared": "copied_epoch0",
    }
)
_MIGRATION_ABORT_TRANSITIONS: Mapping[str, str] = MappingProxyType(
    {
        "abort_prepared": "abort_renamed_to_tombstone",
        "abort_renamed_to_tombstone": "abort_rename_fsynced",
        "abort_rename_fsynced": "abort_tombstone_unlinked",
        "abort_tombstone_unlinked": "abort_deletion_fsynced",
        "abort_deletion_fsynced": "abort_sources_revalidated",
        "abort_sources_revalidated": "abort_barrier_released",
    }
)


def _migration_lifecycle_state_sha256(value: Mapping[str, object]) -> str:
    material = {
        key: item for key, item in value.items() if key not in {"state_sha256", "signature_ed25519"}
    }
    return hashlib.sha256(_MIGRATION_LIFECYCLE_STATE_DOMAIN + _canonical_json(material)).hexdigest()


class SignedMigrationLifecycleStateV1(_Closed):
    schema_version: Literal[1] = 1
    target_store_id: str
    root_id: str
    root_manifest_sha256: str
    barrier_id: str | None
    freeze_nonce: str | None
    source_manifest_sha256: str | None
    copy_audit_sha256: str | None
    target_parent_dev: int = Field(ge=0, le=MAX_I63)
    target_parent_ino: int = Field(ge=1, le=MAX_I63)
    target_basename: str
    target_dev: int = Field(ge=0, le=MAX_I63)
    target_ino: int = Field(ge=1, le=MAX_I63)
    tombstone_basename: str
    lifecycle_phase: _MIGRATION_LIFECYCLE_PHASES
    phase_version: int = Field(ge=0, le=MAX_I63)
    issuer_sequence: int = Field(ge=0, le=MAX_I63)
    prepared_at_ms: int = Field(ge=0, le=MAX_I63)
    updated_at_ms: int = Field(ge=0, le=MAX_I63)
    witness_sha256: str | None
    previous_state_sha256: str
    state_sha256: str
    issuer_key_id: str
    signature_ed25519: bytes

    @model_validator(mode="after")
    def _closed_lifecycle_state(self) -> SignedMigrationLifecycleStateV1:
        optional_hashes = (
            self.freeze_nonce,
            self.source_manifest_sha256,
            self.copy_audit_sha256,
            self.witness_sha256,
        )
        if (
            not _STORE_ID.fullmatch(self.target_store_id)
            or not _REGISTRY_ID.fullmatch(self.root_id)
            or not _HEX64.fullmatch(self.root_manifest_sha256)
            or not _HEX64.fullmatch(self.previous_state_sha256)
            or not _HEX64.fullmatch(self.state_sha256)
            or not _KEY_ID.fullmatch(self.issuer_key_id)
            or len(self.signature_ed25519) != 64
            or self.updated_at_ms < self.prepared_at_ms
            or any(value is not None and not _HEX64.fullmatch(value) for value in optional_hashes)
            or (self.barrier_id is not None and not _REGISTRY_ID.fullmatch(self.barrier_id))
            or not _MIGRATION_BASENAME.fullmatch(self.target_basename)
            or self.target_basename in {".", ".."}
            or self.tombstone_basename != f".{self.target_basename}.abort-v1"
            or len(self.tombstone_basename.encode()) > 255
            or (
                self.freeze_nonce is not None
                and self.barrier_id != _migration_barrier_id(self.freeze_nonce)
            )
        ):
            raise ValueError("migration lifecycle identity")
        pin_presence = (
            self.barrier_id is not None,
            self.freeze_nonce is not None,
            self.source_manifest_sha256 is not None,
            self.copy_audit_sha256 is not None,
            self.witness_sha256 is not None,
        )
        expected_presence = {
            "schema_only": (False, False, False, False, False),
            "barrier_acquired": (True, True, False, False, True),
            "sources_sealed": (True, True, True, False, True),
            "copy_prepared": (True, True, True, True, True),
            "copied_epoch0": (True, True, True, True, True),
        }
        minimum_abort_version = {
            "abort_prepared": 1,
            "abort_renamed_to_tombstone": 2,
            "abort_rename_fsynced": 3,
            "abort_tombstone_unlinked": 4,
            "abort_deletion_fsynced": 5,
            "abort_sources_revalidated": 6,
            "abort_barrier_released": 7,
        }
        expected_precopy_version = {
            "schema_only": 0,
            "barrier_acquired": 1,
            "sources_sealed": 2,
            "copy_prepared": 3,
            "copied_epoch0": 4,
        }
        if self.issuer_sequence != self.phase_version:
            raise ValueError("migration lifecycle sequence/version mismatch")
        if self.lifecycle_phase.startswith("abort_"):
            if (
                pin_presence not in set(expected_presence.values())
                or self.phase_version < minimum_abort_version[self.lifecycle_phase]
            ):
                raise ValueError("migration abort pin class")
        elif (
            pin_presence != expected_presence[self.lifecycle_phase]
            or self.phase_version != expected_precopy_version[self.lifecycle_phase]
        ):
            raise ValueError("migration lifecycle phase pins")
        expected_state_sha256 = _migration_lifecycle_state_sha256(self.model_dump(mode="python"))
        if self.state_sha256 != expected_state_sha256:
            raise ValueError("migration lifecycle state hash")
        return self


_MIGRATION_EPOCH0_RECOVERY_PHASES = Literal[
    "schema_only",
    "barrier_acquired",
    "sources_sealed",
    "copy_prepared",
    "copied_epoch0",
]


class Epoch0RecoveryAuthorityPinsV1(_Closed):
    schema_version: Literal[1] = 1
    target_store_id: str
    root_id: str
    root_manifest_sha256: str
    target_parent_dev: int = Field(ge=0, le=MAX_I63)
    target_parent_ino: int = Field(ge=1, le=MAX_I63)
    target_basename: str
    target_dev: int = Field(ge=0, le=MAX_I63)
    target_ino: int = Field(ge=1, le=MAX_I63)
    lifecycle_phase: _MIGRATION_EPOCH0_RECOVERY_PHASES
    phase_version: int = Field(ge=0, le=4)
    issuer_sequence: int = Field(ge=0, le=4)
    state_sha256: str
    barrier_id: str | None
    freeze_nonce: str | None
    source_manifest_sha256: str | None
    copy_audit_sha256: str | None
    witness_sha256: str | None

    @model_validator(mode="after")
    def _closed_recovery_pins(self) -> Epoch0RecoveryAuthorityPinsV1:
        optional_hashes = (
            self.freeze_nonce,
            self.source_manifest_sha256,
            self.copy_audit_sha256,
            self.witness_sha256,
        )
        expected = {
            "schema_only": (0, (False, False, False, False, False)),
            "barrier_acquired": (1, (True, True, False, False, True)),
            "sources_sealed": (2, (True, True, True, False, True)),
            "copy_prepared": (3, (True, True, True, True, True)),
            "copied_epoch0": (4, (True, True, True, True, True)),
        }
        version, presence = expected[self.lifecycle_phase]
        actual_presence = (
            self.barrier_id is not None,
            self.freeze_nonce is not None,
            self.source_manifest_sha256 is not None,
            self.copy_audit_sha256 is not None,
            self.witness_sha256 is not None,
        )
        if (
            not _STORE_ID.fullmatch(self.target_store_id)
            or not _REGISTRY_ID.fullmatch(self.root_id)
            or not _HEX64.fullmatch(self.root_manifest_sha256)
            or not _HEX64.fullmatch(self.state_sha256)
            or not _MIGRATION_BASENAME.fullmatch(self.target_basename)
            or self.target_basename in {".", ".."}
            or any(value is not None and not _HEX64.fullmatch(value) for value in optional_hashes)
            or (self.barrier_id is not None and not _REGISTRY_ID.fullmatch(self.barrier_id))
            or (
                self.freeze_nonce is not None
                and self.barrier_id != _migration_barrier_id(self.freeze_nonce)
            )
            or self.phase_version != version
            or self.issuer_sequence != version
            or actual_presence != presence
        ):
            raise ValueError("epoch0 recovery authority pins")
        return self


class SignedMigrationRecoveryTicketV1(_Closed):
    schema_version: Literal[1] = 1
    issuer_key_id: str
    issuer_generation_nonce: str
    root_id: str
    root_dev: int = Field(ge=0, le=MAX_I63)
    root_ino: int = Field(ge=1, le=MAX_I63)
    root_manifest_sha256: str
    target_store_id: str
    target_parent_dev: int = Field(ge=0, le=MAX_I63)
    target_parent_ino: int = Field(ge=1, le=MAX_I63)
    target_basename: str
    target_dev: int = Field(ge=0, le=MAX_I63)
    target_ino: int = Field(ge=1, le=MAX_I63)
    maximum_issuer_sequence: Literal[4] = 4
    ticket_nonce: str
    issued_at_ms: int = Field(ge=0, le=MAX_I63)
    ticket_sha256: str
    signature_ed25519: bytes

    @model_validator(mode="after")
    def _closed_recovery_ticket(self) -> SignedMigrationRecoveryTicketV1:
        if (
            not _KEY_ID.fullmatch(self.issuer_key_id)
            or not _HEX64.fullmatch(self.issuer_generation_nonce)
            or not _REGISTRY_ID.fullmatch(self.root_id)
            or not _HEX64.fullmatch(self.root_manifest_sha256)
            or not _STORE_ID.fullmatch(self.target_store_id)
            or not _MIGRATION_BASENAME.fullmatch(self.target_basename)
            or self.target_basename in {".", ".."}
            or not _HEX64.fullmatch(self.ticket_nonce)
            or not _HEX64.fullmatch(self.ticket_sha256)
            or len(self.signature_ed25519) != 64
        ):
            raise ValueError("migration recovery ticket identity")
        material = self.model_dump(mode="json", exclude={"ticket_sha256", "signature_ed25519"})
        expected = hashlib.sha256(
            _MIGRATION_RECOVERY_TICKET_DOMAIN + _canonical_json(material)
        ).hexdigest()
        if self.ticket_sha256 != expected:
            raise ValueError("migration recovery ticket hash")
        return self


class SignedEpoch0RecoveryAdmissionV1(_Closed):
    schema_version: Literal[1] = 1
    issuer_key_id: str
    issuer_generation_nonce: str
    ticket_sha256: str
    authenticated_peer_pid: int = Field(ge=1, le=MAX_I63)
    caller_boot_nonce: str
    handle_nonce: str
    descriptor_mode: Literal["target"] = "target"
    authority_pins: Epoch0RecoveryAuthorityPinsV1
    issued_at_ms: int = Field(ge=0, le=MAX_I63)
    admission_sha256: str
    signature_ed25519: bytes

    @model_validator(mode="after")
    def _closed_recovery_admission(self) -> SignedEpoch0RecoveryAdmissionV1:
        if (
            not _KEY_ID.fullmatch(self.issuer_key_id)
            or not _HEX64.fullmatch(self.issuer_generation_nonce)
            or not _HEX64.fullmatch(self.ticket_sha256)
            or not _HEX64.fullmatch(self.caller_boot_nonce)
            or not _HEX64.fullmatch(self.handle_nonce)
            or not _HEX64.fullmatch(self.admission_sha256)
            or len(self.signature_ed25519) != 64
        ):
            raise ValueError("epoch0 recovery admission identity")
        material = self.model_dump(mode="json", exclude={"admission_sha256", "signature_ed25519"})
        expected = hashlib.sha256(
            _MIGRATION_RECOVERY_ADMISSION_DOMAIN + _canonical_json(material)
        ).hexdigest()
        if self.admission_sha256 != expected:
            raise ValueError("epoch0 recovery admission hash")
        return self


class Epoch0RecoveryCopyCompletionV1(_Closed):
    schema_version: Literal[1] = 1
    prepared_state: SignedMigrationLifecycleStateV1
    copied_state: SignedMigrationLifecycleStateV1
    copy_audit: CopyAuditV1
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class Epoch0RecoveryCopyPreparationCompletionV1(_Closed):
    schema_version: Literal[1] = 1
    sealed_state: SignedMigrationLifecycleStateV1
    prepared_state: SignedMigrationLifecycleStateV1
    copy_audit: CopyAuditV1
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class Epoch0RecoveryBarrierAcquisitionCompletionV1(_Closed):
    schema_version: Literal[1] = 1
    schema_only_state: SignedMigrationLifecycleStateV1
    barrier_acquired_state: SignedMigrationLifecycleStateV1
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


def _verify_signed_migration_recovery_ticket(
    ticket: SignedMigrationRecoveryTicketV1, verification_key: VerificationKeyV1
) -> None:
    if (
        type(ticket) is not SignedMigrationRecoveryTicketV1
        or type(verification_key) is not VerificationKeyV1
    ):
        raise ValueError("migration recovery ticket verifier type")
    ticket = SignedMigrationRecoveryTicketV1.model_validate(ticket.model_dump(mode="python"))
    if ticket.issuer_key_id != verification_key.key_id:
        raise ValueError("migration recovery ticket key")
    Ed25519PublicKey.from_public_bytes(verification_key.public_key_bytes).verify(
        ticket.signature_ed25519,
        _MIGRATION_RECOVERY_TICKET_SIGNATURE_DOMAIN + bytes.fromhex(ticket.ticket_sha256),
    )


def _verify_signed_epoch0_recovery_admission(
    admission: SignedEpoch0RecoveryAdmissionV1,
    verification_key: VerificationKeyV1,
) -> None:
    if (
        type(admission) is not SignedEpoch0RecoveryAdmissionV1
        or type(verification_key) is not VerificationKeyV1
    ):
        raise ValueError("epoch0 recovery admission verifier type")
    admission = SignedEpoch0RecoveryAdmissionV1.model_validate(admission.model_dump(mode="python"))
    if admission.issuer_key_id != verification_key.key_id:
        raise ValueError("epoch0 recovery admission key")
    Ed25519PublicKey.from_public_bytes(verification_key.public_key_bytes).verify(
        admission.signature_ed25519,
        _MIGRATION_RECOVERY_ADMISSION_SIGNATURE_DOMAIN + bytes.fromhex(admission.admission_sha256),
    )


def _verify_signed_migration_lifecycle_state(
    state: SignedMigrationLifecycleStateV1, verification_key: VerificationKeyV1
) -> None:
    if (
        type(state) is not SignedMigrationLifecycleStateV1
        or type(verification_key) is not VerificationKeyV1
    ):
        raise ValueError("migration lifecycle verifier type mismatch")
    state = SignedMigrationLifecycleStateV1.model_validate(state.model_dump(mode="python"))
    verification_key = VerificationKeyV1.model_validate(verification_key.model_dump(mode="python"))
    if state.issuer_key_id != verification_key.key_id:
        raise ValueError("migration lifecycle issuer key mismatch")
    Ed25519PublicKey.from_public_bytes(verification_key.public_key_bytes).verify(
        state.signature_ed25519,
        _MIGRATION_LIFECYCLE_SIGNATURE_DOMAIN + bytes.fromhex(state.state_sha256),
    )


def _verify_migration_lifecycle_genesis(
    state: SignedMigrationLifecycleStateV1, verification_key: VerificationKeyV1
) -> None:
    _verify_signed_migration_lifecycle_state(state, verification_key)
    if (
        state.lifecycle_phase != "schema_only"
        or state.phase_version != 0
        or state.issuer_sequence != 0
        or state.previous_state_sha256 != "0" * 64
    ):
        raise ValueError("migration lifecycle genesis mismatch")


def _verify_migration_lifecycle_transition(
    prior: SignedMigrationLifecycleStateV1,
    successor: SignedMigrationLifecycleStateV1,
    verification_key: VerificationKeyV1,
) -> None:
    _verify_signed_migration_lifecycle_state(prior, verification_key)
    _verify_signed_migration_lifecycle_state(successor, verification_key)
    static_fields = (
        "target_store_id",
        "root_id",
        "root_manifest_sha256",
        "target_parent_dev",
        "target_parent_ino",
        "target_basename",
        "target_dev",
        "target_ino",
        "tombstone_basename",
        "prepared_at_ms",
        "issuer_key_id",
    )
    if any(getattr(prior, field) != getattr(successor, field) for field in static_fields):
        raise ValueError("migration lifecycle static identity changed")
    if (
        successor.previous_state_sha256 != prior.state_sha256
        or successor.phase_version != prior.phase_version + 1
        or successor.issuer_sequence != prior.issuer_sequence + 1
        or successor.updated_at_ms < prior.updated_at_ms
    ):
        raise ValueError("migration lifecycle chain mismatch")
    expected_phase = _MIGRATION_PRECOPY_TRANSITIONS.get(prior.lifecycle_phase)
    if (
        prior.lifecycle_phase
        in {"schema_only", "barrier_acquired", "sources_sealed", "copy_prepared", "copied_epoch0"}
        and successor.lifecycle_phase == "abort_prepared"
    ):
        expected_phase = "abort_prepared"
    if prior.lifecycle_phase.startswith("abort_"):
        expected_phase = _MIGRATION_ABORT_TRANSITIONS.get(prior.lifecycle_phase)
    if successor.lifecycle_phase != expected_phase:
        raise ValueError("migration lifecycle phase transition")
    prior_pins = (
        prior.barrier_id,
        prior.freeze_nonce,
        prior.source_manifest_sha256,
        prior.copy_audit_sha256,
        prior.witness_sha256,
    )
    successor_pins = (
        successor.barrier_id,
        successor.freeze_nonce,
        successor.source_manifest_sha256,
        successor.copy_audit_sha256,
        successor.witness_sha256,
    )
    if prior.lifecycle_phase.startswith("abort_") or successor.lifecycle_phase.startswith("abort_"):
        if successor_pins != prior_pins:
            raise ValueError("migration abort pins changed")
    elif any(
        old is not None and old != new for old, new in zip(prior_pins, successor_pins, strict=True)
    ):
        raise ValueError("migration lifecycle pin changed")


def _verify_epoch0_recovery_copy_completion_v1(
    completion: Epoch0RecoveryCopyCompletionV1,
    *,
    issuer_verification_key: VerificationKeyV1,
    expected_prepared_pins: Epoch0RecoveryAuthorityPinsV1,
) -> None:
    if (
        type(completion) is not Epoch0RecoveryCopyCompletionV1
        or type(issuer_verification_key) is not VerificationKeyV1
        or type(expected_prepared_pins) is not Epoch0RecoveryAuthorityPinsV1
        or expected_prepared_pins.lifecycle_phase != "copy_prepared"
    ):
        raise ValueError("epoch0 recovery copy completion type")
    completion = Epoch0RecoveryCopyCompletionV1.model_validate(completion.model_dump(mode="python"))
    prepared = completion.prepared_state
    copied = completion.copied_state
    audit = completion.copy_audit
    _verify_signed_migration_lifecycle_state(prepared, issuer_verification_key)
    _verify_migration_lifecycle_transition(prepared, copied, issuer_verification_key)
    prepared_pins = Epoch0RecoveryAuthorityPinsV1.model_validate(
        {
            "target_store_id": prepared.target_store_id,
            "root_id": prepared.root_id,
            "root_manifest_sha256": prepared.root_manifest_sha256,
            "target_parent_dev": prepared.target_parent_dev,
            "target_parent_ino": prepared.target_parent_ino,
            "target_basename": prepared.target_basename,
            "target_dev": prepared.target_dev,
            "target_ino": prepared.target_ino,
            "lifecycle_phase": prepared.lifecycle_phase,
            "phase_version": prepared.phase_version,
            "issuer_sequence": prepared.issuer_sequence,
            "state_sha256": prepared.state_sha256,
            "barrier_id": prepared.barrier_id,
            "freeze_nonce": prepared.freeze_nonce,
            "source_manifest_sha256": prepared.source_manifest_sha256,
            "copy_audit_sha256": prepared.copy_audit_sha256,
            "witness_sha256": prepared.witness_sha256,
        }
    )
    audit_sha256 = _copy_audit_sha256(audit)
    if (
        prepared_pins != expected_prepared_pins
        or prepared.lifecycle_phase != "copy_prepared"
        or copied.lifecycle_phase != "copied_epoch0"
        or copied.phase_version != 4
        or copied.issuer_sequence != 4
        or prepared.copy_audit_sha256 != audit_sha256
        or copied.copy_audit_sha256 != audit_sha256
        or prepared.source_manifest_sha256 != audit.source_manifest_sha256
        or copied.source_manifest_sha256 != audit.source_manifest_sha256
        or prepared.target_store_id != audit.target_store_id
        or copied.target_store_id != audit.target_store_id
    ):
        raise ValueError("epoch0 recovery copy completion mismatch")


def _verify_epoch0_recovery_copy_preparation_completion_v1(
    completion: Epoch0RecoveryCopyPreparationCompletionV1,
    *,
    issuer_verification_key: VerificationKeyV1,
    expected_sealed_pins: Epoch0RecoveryAuthorityPinsV1,
) -> None:
    if (
        type(completion) is not Epoch0RecoveryCopyPreparationCompletionV1
        or type(issuer_verification_key) is not VerificationKeyV1
        or type(expected_sealed_pins) is not Epoch0RecoveryAuthorityPinsV1
        or expected_sealed_pins.lifecycle_phase != "sources_sealed"
    ):
        raise ValueError("epoch0 recovery copy preparation completion type")
    completion = Epoch0RecoveryCopyPreparationCompletionV1.model_validate(
        completion.model_dump(mode="python")
    )
    sealed = completion.sealed_state
    prepared = completion.prepared_state
    audit = completion.copy_audit
    _verify_signed_migration_lifecycle_state(sealed, issuer_verification_key)
    _verify_migration_lifecycle_transition(sealed, prepared, issuer_verification_key)
    sealed_pins = Epoch0RecoveryAuthorityPinsV1.model_validate(
        {
            "target_store_id": sealed.target_store_id,
            "root_id": sealed.root_id,
            "root_manifest_sha256": sealed.root_manifest_sha256,
            "target_parent_dev": sealed.target_parent_dev,
            "target_parent_ino": sealed.target_parent_ino,
            "target_basename": sealed.target_basename,
            "target_dev": sealed.target_dev,
            "target_ino": sealed.target_ino,
            "lifecycle_phase": sealed.lifecycle_phase,
            "phase_version": sealed.phase_version,
            "issuer_sequence": sealed.issuer_sequence,
            "state_sha256": sealed.state_sha256,
            "barrier_id": sealed.barrier_id,
            "freeze_nonce": sealed.freeze_nonce,
            "source_manifest_sha256": sealed.source_manifest_sha256,
            "copy_audit_sha256": sealed.copy_audit_sha256,
            "witness_sha256": sealed.witness_sha256,
        }
    )
    audit_sha256 = _copy_audit_sha256(audit)
    if (
        sealed_pins != expected_sealed_pins
        or sealed.lifecycle_phase != "sources_sealed"
        or prepared.lifecycle_phase != "copy_prepared"
        or prepared.phase_version != 3
        or prepared.issuer_sequence != 3
        or sealed.copy_audit_sha256 is not None
        or prepared.copy_audit_sha256 != audit_sha256
        or sealed.source_manifest_sha256 != audit.source_manifest_sha256
        or prepared.source_manifest_sha256 != audit.source_manifest_sha256
        or sealed.target_store_id != audit.target_store_id
        or prepared.target_store_id != audit.target_store_id
    ):
        raise ValueError("epoch0 recovery copy preparation completion mismatch")


def _verify_epoch0_recovery_barrier_acquisition_completion_v1(
    completion: Epoch0RecoveryBarrierAcquisitionCompletionV1,
    *,
    issuer_verification_key: VerificationKeyV1,
    expected_schema_only_pins: Epoch0RecoveryAuthorityPinsV1,
) -> None:
    if (
        type(completion) is not Epoch0RecoveryBarrierAcquisitionCompletionV1
        or type(issuer_verification_key) is not VerificationKeyV1
        or type(expected_schema_only_pins) is not Epoch0RecoveryAuthorityPinsV1
        or expected_schema_only_pins.lifecycle_phase != "schema_only"
    ):
        raise ValueError("epoch0 recovery barrier acquisition completion type")
    completion = Epoch0RecoveryBarrierAcquisitionCompletionV1.model_validate(
        completion.model_dump(mode="python")
    )
    schema_only = completion.schema_only_state
    barrier_acquired = completion.barrier_acquired_state
    _verify_signed_migration_lifecycle_state(schema_only, issuer_verification_key)
    _verify_migration_lifecycle_transition(schema_only, barrier_acquired, issuer_verification_key)
    schema_only_pins = Epoch0RecoveryAuthorityPinsV1.model_validate(
        {
            "target_store_id": schema_only.target_store_id,
            "root_id": schema_only.root_id,
            "root_manifest_sha256": schema_only.root_manifest_sha256,
            "target_parent_dev": schema_only.target_parent_dev,
            "target_parent_ino": schema_only.target_parent_ino,
            "target_basename": schema_only.target_basename,
            "target_dev": schema_only.target_dev,
            "target_ino": schema_only.target_ino,
            "lifecycle_phase": schema_only.lifecycle_phase,
            "phase_version": schema_only.phase_version,
            "issuer_sequence": schema_only.issuer_sequence,
            "state_sha256": schema_only.state_sha256,
            "barrier_id": schema_only.barrier_id,
            "freeze_nonce": schema_only.freeze_nonce,
            "source_manifest_sha256": schema_only.source_manifest_sha256,
            "copy_audit_sha256": schema_only.copy_audit_sha256,
            "witness_sha256": schema_only.witness_sha256,
        }
    )
    if (
        schema_only_pins != expected_schema_only_pins
        or schema_only.lifecycle_phase != "schema_only"
        or barrier_acquired.lifecycle_phase != "barrier_acquired"
        or barrier_acquired.phase_version != 1
        or barrier_acquired.issuer_sequence != 1
        or barrier_acquired.barrier_id is None
        or barrier_acquired.freeze_nonce is None
        or barrier_acquired.witness_sha256 is None
        or barrier_acquired.source_manifest_sha256 is not None
        or barrier_acquired.copy_audit_sha256 is not None
        or barrier_acquired.barrier_id != _migration_barrier_id(barrier_acquired.freeze_nonce)
    ):
        raise ValueError("epoch0 recovery barrier acquisition completion mismatch")


_MAX_MIGRATION_LIFECYCLE_DOCUMENT_BYTES = 65_536


def _migration_lifecycle_state_basename(target_basename: str) -> str:
    if not _MIGRATION_BASENAME.fullmatch(target_basename) or target_basename in {".", ".."}:
        raise ValueError("migration lifecycle target basename")
    basename = f".{target_basename}.migration-state-v1.json"
    if len(basename.encode()) > 255:
        raise ValueError("migration lifecycle state basename")
    return basename


def _migration_lifecycle_state_document(state: SignedMigrationLifecycleStateV1) -> bytes:
    if type(state) is not SignedMigrationLifecycleStateV1:
        raise ValueError("migration lifecycle document type")
    state = SignedMigrationLifecycleStateV1.model_validate(state.model_dump(mode="python"))
    material = state.model_dump(mode="python")
    material["signature_ed25519"] = state.signature_ed25519.hex()
    encoded = _canonical_json(material)
    if len(encoded) > _MAX_MIGRATION_LIFECYCLE_DOCUMENT_BYTES:
        raise ValueError("migration lifecycle document bound")
    return encoded


def _parse_migration_lifecycle_state_document(
    document: bytes, verification_key: VerificationKeyV1
) -> SignedMigrationLifecycleStateV1:
    parsed = _parse_strict_json(document, _MAX_MIGRATION_LIFECYCLE_DOCUMENT_BYTES)
    signature = parsed.get("signature_ed25519")
    if type(signature) is not str or not re.fullmatch(r"[0-9a-f]{128}", signature):
        raise ValueError("migration lifecycle signature encoding")
    parsed["signature_ed25519"] = bytes.fromhex(signature)
    state = SignedMigrationLifecycleStateV1.model_validate(parsed)
    if document != _migration_lifecycle_state_document(state):
        raise ValueError("migration lifecycle document not canonical")
    _verify_signed_migration_lifecycle_state(state, verification_key)
    return state


def _migration_lifecycle_parent_identity(parent_fd: int) -> tuple[int, int]:
    if type(parent_fd) is not int or parent_fd < 0:
        raise ValueError("migration lifecycle parent descriptor")
    info = os.fstat(parent_fd)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("migration lifecycle parent identity")
    return int(info.st_dev), int(info.st_ino)


def _migration_lifecycle_entry_identity(parent_fd: int, basename: str) -> tuple[int, int] | None:
    try:
        info = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise ValueError("migration lifecycle target identity")
    return int(info.st_dev), int(info.st_ino)


def _verify_migration_lifecycle_target_state(
    parent_fd: int, state: SignedMigrationLifecycleStateV1
) -> None:
    expected = (state.target_dev, state.target_ino)
    target = _migration_lifecycle_entry_identity(parent_fd, state.target_basename)
    tombstone = _migration_lifecycle_entry_identity(parent_fd, state.tombstone_basename)
    if state.lifecycle_phase.startswith("abort_"):
        for suffix in ("-wal", "-shm", "-journal"):
            try:
                os.stat(
                    f"{state.target_basename}{suffix}",
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                continue
            else:
                raise ValueError("migration lifecycle sqlite sidecar remains")
    before_abort = {
        "schema_only",
        "barrier_acquired",
        "sources_sealed",
        "copy_prepared",
        "copied_epoch0",
    }
    if state.lifecycle_phase in before_abort:
        accepted = target == expected and tombstone is None
    elif state.lifecycle_phase == "abort_prepared":
        accepted = (target == expected and tombstone is None) or (
            target is None and tombstone == expected
        )
    elif state.lifecycle_phase == "abort_renamed_to_tombstone":
        accepted = target is None and tombstone == expected
    elif state.lifecycle_phase == "abort_rename_fsynced":
        accepted = target is None and tombstone in {None, expected}
    else:
        accepted = target is None and tombstone is None
    if not accepted:
        raise ValueError("migration lifecycle target phase mismatch")


def _migration_lifecycle_temporary_basenames(
    parent_fd: int, target_basename: str
) -> tuple[str, ...]:
    prefix = f".{target_basename}.migration-state-v1."
    return tuple(
        sorted(
            name
            for name in os.listdir(parent_fd)
            if name.startswith(prefix)
            and name.endswith(".tmp")
            and re.fullmatch(r"[0-9a-f]{24}", name[len(prefix) : -4])
        )
    )


def _cleanup_migration_lifecycle_temporaries(parent_fd: int, target_basename: str) -> None:
    removed = False
    for basename in _migration_lifecycle_temporary_basenames(parent_fd, target_basename):
        info = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ValueError("migration lifecycle temporary identity")
        os.unlink(basename, dir_fd=parent_fd)
        removed = True
    if removed:
        os.fsync(parent_fd)


def _read_signed_migration_lifecycle_state(
    *, parent_fd: int, target_basename: str, verification_key: VerificationKeyV1
) -> SignedMigrationLifecycleStateV1:
    parent_identity = _migration_lifecycle_parent_identity(parent_fd)
    state_basename = _migration_lifecycle_state_basename(target_basename)
    path_info = os.stat(state_basename, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not stat.S_ISREG(path_info.st_mode)
        or path_info.st_uid != os.getuid()
        or path_info.st_nlink != 1
        or stat.S_IMODE(path_info.st_mode) != 0o600
        or not 0 < path_info.st_size <= _MAX_MIGRATION_LIFECYCLE_DOCUMENT_BYTES
    ):
        raise ValueError("migration lifecycle state file identity")
    descriptor = os.open(
        state_basename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (path_info.st_dev, path_info.st_ino):
            raise ValueError("migration lifecycle state changed during open")
        chunks: list[bytes] = []
        remaining = _MAX_MIGRATION_LIFECYCLE_DOCUMENT_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        document = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(document) != opened.st_size
            or len(document) > _MAX_MIGRATION_LIFECYCLE_DOCUMENT_BYTES
            or (after.st_dev, after.st_ino, after.st_size)
            != (opened.st_dev, opened.st_ino, opened.st_size)
        ):
            raise ValueError("migration lifecycle state changed during read")
    finally:
        os.close(descriptor)
    path_after = os.stat(state_basename, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not stat.S_ISREG(path_after.st_mode)
        or path_after.st_uid != os.getuid()
        or path_after.st_nlink != 1
        or stat.S_IMODE(path_after.st_mode) != 0o600
        or (path_after.st_dev, path_after.st_ino, path_after.st_size)
        != (opened.st_dev, opened.st_ino, opened.st_size)
    ):
        raise ValueError("migration lifecycle state changed after read")
    state = _parse_migration_lifecycle_state_document(document, verification_key)
    if (
        state.target_parent_dev,
        state.target_parent_ino,
    ) != parent_identity or state.target_basename != target_basename:
        raise ValueError("migration lifecycle state parent mismatch")
    if _migration_lifecycle_temporary_basenames(parent_fd, target_basename):
        raise ValueError("migration lifecycle orphan temporary")
    _verify_migration_lifecycle_target_state(parent_fd, state)
    return state


def _authenticate_epoch0_recovery_state_v1(
    *,
    parent_fd: int,
    target_fd: int,
    verification_key: VerificationKeyV1,
    expected: Epoch0RecoveryAuthorityPinsV1,
) -> SignedMigrationLifecycleStateV1:
    if (
        type(parent_fd) is not int
        or type(target_fd) is not int
        or type(expected) is not Epoch0RecoveryAuthorityPinsV1
    ):
        raise ValueError("epoch0 recovery descriptor type")
    expected = Epoch0RecoveryAuthorityPinsV1.model_validate(expected.model_dump(mode="python"))
    if _migration_lifecycle_parent_identity(parent_fd) != (
        expected.target_parent_dev,
        expected.target_parent_ino,
    ):
        raise ValueError("epoch0 recovery parent identity")
    target_info = os.fstat(target_fd)
    if (
        not stat.S_ISREG(target_info.st_mode)
        or target_info.st_uid != os.getuid()
        or target_info.st_nlink != 1
        or stat.S_IMODE(target_info.st_mode) != 0o600
        or (target_info.st_dev, target_info.st_ino) != (expected.target_dev, expected.target_ino)
        or _migration_lifecycle_entry_identity(parent_fd, expected.target_basename)
        != (expected.target_dev, expected.target_ino)
    ):
        raise ValueError("epoch0 recovery target identity")
    state = _read_signed_migration_lifecycle_state(
        parent_fd=parent_fd,
        target_basename=expected.target_basename,
        verification_key=verification_key,
    )
    fields = (
        "target_store_id",
        "root_id",
        "root_manifest_sha256",
        "target_parent_dev",
        "target_parent_ino",
        "target_basename",
        "target_dev",
        "target_ino",
        "lifecycle_phase",
        "phase_version",
        "issuer_sequence",
        "state_sha256",
        "barrier_id",
        "freeze_nonce",
        "source_manifest_sha256",
        "copy_audit_sha256",
        "witness_sha256",
    )
    if any(getattr(state, field) != getattr(expected, field) for field in fields):
        raise ValueError("epoch0 recovery signed state mismatch")
    target_after = os.fstat(target_fd)
    if (target_after.st_dev, target_after.st_ino) != (
        expected.target_dev,
        expected.target_ino,
    ) or _migration_lifecycle_entry_identity(parent_fd, expected.target_basename) != (
        expected.target_dev,
        expected.target_ino,
    ):
        raise ValueError("epoch0 recovery target changed during authentication")
    return state


def _persist_signed_migration_lifecycle_state(
    *,
    parent_fd: int,
    state: SignedMigrationLifecycleStateV1,
    verification_key: VerificationKeyV1,
    expected_prior_state_sha256: str | None,
    _fault_hook: Callable[[Literal["after_rename", "after_parent_fsync", "after_reread"]], None]
    | None = None,
) -> SignedMigrationLifecycleStateV1:
    parent_identity = _migration_lifecycle_parent_identity(parent_fd)
    if (
        type(state) is not SignedMigrationLifecycleStateV1
        or (state.target_parent_dev, state.target_parent_ino) != parent_identity
    ):
        raise ValueError("migration lifecycle persistence parent mismatch")
    _verify_signed_migration_lifecycle_state(state, verification_key)
    state_basename = _migration_lifecycle_state_basename(state.target_basename)
    locked_parent_fd = os.open(
        ".",
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent_fd,
    )
    try:
        locked_parent_identity = _migration_lifecycle_parent_identity(locked_parent_fd)
    except Exception:
        os.close(locked_parent_fd)
        raise
    if locked_parent_identity != parent_identity:
        os.close(locked_parent_fd)
        raise ValueError("migration lifecycle locked parent mismatch")
    temporary_basename: str | None = None
    try:
        fcntl.flock(locked_parent_fd, fcntl.LOCK_EX)
        _cleanup_migration_lifecycle_temporaries(locked_parent_fd, state.target_basename)
        _verify_migration_lifecycle_target_state(locked_parent_fd, state)
        if expected_prior_state_sha256 is None:
            try:
                os.stat(state_basename, dir_fd=locked_parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("migration lifecycle genesis already exists")
            _verify_migration_lifecycle_genesis(state, verification_key)
        else:
            if not _HEX64.fullmatch(expected_prior_state_sha256):
                raise ValueError("migration lifecycle expected prior hash")
            prior = _read_signed_migration_lifecycle_state(
                parent_fd=locked_parent_fd,
                target_basename=state.target_basename,
                verification_key=verification_key,
            )
            if prior.state_sha256 != expected_prior_state_sha256:
                raise ValueError("migration lifecycle compare-and-swap mismatch")
            _verify_migration_lifecycle_transition(prior, state, verification_key)
        encoded = _migration_lifecycle_state_document(state)
        temporary_basename = (
            f".{state.target_basename}.migration-state-v1.{secrets.token_hex(12)}.tmp"
        )
        temporary_fd = os.open(
            temporary_basename,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=locked_parent_fd,
        )
        try:
            os.fchmod(temporary_fd, 0o600)
            view = memoryview(encoded)
            while view:
                written = os.write(temporary_fd, view)
                if written <= 0:
                    raise OSError("short migration lifecycle state write")
                view = view[written:]
            os.fsync(temporary_fd)
        finally:
            os.close(temporary_fd)
        os.rename(
            temporary_basename,
            state_basename,
            src_dir_fd=locked_parent_fd,
            dst_dir_fd=locked_parent_fd,
        )
        temporary_basename = None
        if _fault_hook is not None:
            _fault_hook("after_rename")
        os.fsync(locked_parent_fd)
        if _fault_hook is not None:
            _fault_hook("after_parent_fsync")
        persisted = _read_signed_migration_lifecycle_state(
            parent_fd=locked_parent_fd,
            target_basename=state.target_basename,
            verification_key=verification_key,
        )
        if persisted != state:
            raise ValueError("migration lifecycle persistence mismatch")
        if _fault_hook is not None:
            _fault_hook("after_reread")
        return persisted
    finally:
        if temporary_basename is not None:
            with suppress(FileNotFoundError):
                os.unlink(temporary_basename, dir_fd=locked_parent_fd)
                os.fsync(locked_parent_fd)
        fcntl.flock(locked_parent_fd, fcntl.LOCK_UN)
        os.close(locked_parent_fd)


def _confirm_signed_migration_lifecycle_state_durable(
    *,
    parent_fd: int,
    expected_state: SignedMigrationLifecycleStateV1,
    verification_key: VerificationKeyV1,
) -> SignedMigrationLifecycleStateV1:
    parent_identity = _migration_lifecycle_parent_identity(parent_fd)
    if (
        type(expected_state) is not SignedMigrationLifecycleStateV1
        or (expected_state.target_parent_dev, expected_state.target_parent_ino) != parent_identity
    ):
        raise ValueError("migration lifecycle durability parent mismatch")
    _verify_signed_migration_lifecycle_state(expected_state, verification_key)
    locked_parent_fd = os.open(
        ".",
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent_fd,
    )
    try:
        if _migration_lifecycle_parent_identity(locked_parent_fd) != parent_identity:
            raise ValueError("migration lifecycle durability locked parent mismatch")
        fcntl.flock(locked_parent_fd, fcntl.LOCK_EX)
        _cleanup_migration_lifecycle_temporaries(locked_parent_fd, expected_state.target_basename)
        _verify_migration_lifecycle_target_state(locked_parent_fd, expected_state)
        observed = _read_signed_migration_lifecycle_state(
            parent_fd=locked_parent_fd,
            target_basename=expected_state.target_basename,
            verification_key=verification_key,
        )
        if observed != expected_state:
            raise ValueError("migration lifecycle durability state mismatch")
        os.fsync(locked_parent_fd)
        confirmed = _read_signed_migration_lifecycle_state(
            parent_fd=locked_parent_fd,
            target_basename=expected_state.target_basename,
            verification_key=verification_key,
        )
        if confirmed != expected_state:
            raise ValueError("migration lifecycle durability reread mismatch")
        return confirmed
    finally:
        with suppress(OSError):
            fcntl.flock(locked_parent_fd, fcntl.LOCK_UN)
        os.close(locked_parent_fd)


def _verify_signed_cutover_marker(
    marker: SignedCutoverMarkerV1, verification_keys: tuple[VerificationKeyV1, ...]
) -> None:
    keyring = _copy_verification_keyring(verification_keys)
    key = keyring.get(marker.key_id)
    if key is None:
        raise ValueError("cutover verification key unavailable")
    Ed25519PublicKey.from_public_bytes(key).verify(
        marker.signature_ed25519,
        _CUTOVER_MARKER_SIGNATURE_DOMAIN + bytes.fromhex(marker.marker_sha256),
    )


class QuarantinedSyntheticExternalPinRecordV1(_Closed):
    schema_version: Literal[1] = 1
    pin_store_id: str
    target_store_id: str
    migration_epoch: Literal[1] = 1
    cutover_marker_sha256: str
    source_manifest_sha256: str
    copy_audit_sha256: str
    semantic_source_sha256: str
    contract_sha256: str
    installed_at_ms: int = Field(ge=0, le=MAX_I63)
    pin_sha256: str

    @model_validator(mode="after")
    def _hash_matches(self) -> QuarantinedSyntheticExternalPinRecordV1:
        if not _REGISTRY_ID.fullmatch(self.pin_store_id) or not _STORE_ID.fullmatch(
            self.target_store_id
        ):
            raise ValueError("pin identity mismatch")
        for value in (
            self.cutover_marker_sha256,
            self.source_manifest_sha256,
            self.copy_audit_sha256,
            self.semantic_source_sha256,
            self.contract_sha256,
        ):
            if not _HEX64.fullmatch(value):
                raise ValueError("pin hash syntax")
        material = self.model_dump(mode="json", exclude={"pin_sha256"})
        expected = hashlib.sha256(_EXTERNAL_PIN_DOMAIN + _canonical_json(material)).hexdigest()
        if self.pin_sha256 != expected:
            raise ValueError("pin hash mismatch")
        return self


class QuarantinedSyntheticReadyRecordV1(_Closed):
    schema_version: Literal[1] = 1
    pin_sha256: str
    legacy_root_id: str
    legacy_read_only: Literal[True] = True
    new_runtime_ready: Literal[True] = True
    ready_at_ms: int = Field(ge=0, le=MAX_I63)
    ready_sha256: str

    @model_validator(mode="after")
    def _hash_matches(self) -> QuarantinedSyntheticReadyRecordV1:
        material = self.model_dump(mode="json", exclude={"ready_sha256"})
        expected = hashlib.sha256(_READY_DOMAIN + _canonical_json(material)).hexdigest()
        if self.ready_sha256 != expected:
            raise ValueError("ready hash mismatch")
        return self


class QuarantinedMigrationSealResultV1(_Closed):
    store_id: str
    freeze_nonce: str
    source_manifest_sha256: str
    canonical_corpus_sha256: str
    sealed_at_ms: int = Field(ge=0, le=MAX_I63)
    source_store_count: int = Field(ge=0, le=MAX_STORES)
    collection_row_counts: PaidLaneTableRowCountsV1
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class QuarantinedSealedCorpusHandleV1:
    barrier_id: str
    boot_nonce: bytes
    canonical_corpus_sha256: str
    consumed: bool
    creator_pid: int
    freeze_nonce: str
    legacy_root_id: str
    schema_version: int
    sealed_at_ms: int
    source_manifest_sha256: str
    target_database_path: Path
    target_store_id: str
    __slots__ = (
        "barrier_id",
        "boot_nonce",
        "canonical_corpus_sha256",
        "consumed",
        "creator_pid",
        "freeze_nonce",
        "legacy_root_id",
        "schema_version",
        "sealed_at_ms",
        "source_manifest_sha256",
        "target_database_path",
        "target_store_id",
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    def __init_subclass__(cls, **kwargs: object) -> Never:
        del cls, kwargs
        raise TypeError("sealed corpus handle is final")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("sealed corpus handle is immutable")

    def __reduce__(self) -> Never:
        raise TypeError("sealed corpus handle is process-local")

    def __copy__(self) -> Never:
        raise TypeError("sealed corpus handle is process-local")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("sealed corpus handle is process-local")


class QuarantinedCopiedCorpusHandleV1:
    barrier_id: str
    boot_nonce: bytes
    canonical_corpus_sha256: str
    consumed: bool
    copied_at_ms: int
    copy_audit_sha256: str
    creator_pid: int
    freeze_nonce: str
    legacy_root_id: str
    schema_version: int
    source_manifest_sha256: str
    target_database_path: Path
    target_store_id: str
    __slots__ = (
        "barrier_id",
        "boot_nonce",
        "canonical_corpus_sha256",
        "consumed",
        "copied_at_ms",
        "copy_audit_sha256",
        "creator_pid",
        "freeze_nonce",
        "legacy_root_id",
        "schema_version",
        "source_manifest_sha256",
        "target_database_path",
        "target_store_id",
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    def __init_subclass__(cls, **kwargs: object) -> Never:
        del cls, kwargs
        raise TypeError("copied corpus handle is final")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("copied corpus handle is immutable")

    def __reduce__(self) -> Never:
        raise TypeError("copied corpus handle is process-local")

    def __copy__(self) -> Never:
        raise TypeError("copied corpus handle is process-local")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("copied corpus handle is process-local")


class QuarantinedMigrationCopyResultV1(_Closed):
    store_id: str
    migration_epoch: Literal[0] = 0
    source_manifest_sha256: str
    canonical_corpus_sha256: str
    copy_audit_sha256: str
    table_row_counts: PaidLaneTableRowCountsV1
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class QuarantinedAbortUncutResultV1(_Closed):
    store_id: str
    prior_migration_epoch: Literal[0] = 0
    marker_absent: Literal[True] = True
    schema_identity_verified: Literal[True] = True
    source_manifest_sha256: str | None = None
    copy_audit_sha256: str | None = None
    target_deleted: Literal[True] = True
    sidecars_deleted: Literal[True] = True
    parent_fsynced: Literal[True] = True
    sources_unchanged: Literal[True] = True
    aborted_at_ms: int = Field(ge=0, le=MAX_I63)
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class QuarantinedCutoverResultV1(_Closed):
    store_id: str
    migration_epoch: Literal[1] = 1
    cutover_marker_sha256: str
    source_manifest_sha256: str
    copy_audit_sha256: str
    pin_sha256: str | None = None
    ready_sha256: str | None = None
    legacy_read_only: bool = True
    committed_at_ms: int = Field(ge=0, le=MAX_I63)
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class QuarantinedForwardRecoveryResultV1(_Closed):
    store_id: str
    migration_epoch: Literal[1] = 1
    cutover_marker_sha256: str
    source_manifest_sha256: str
    copy_audit_sha256: str
    pin_sha256: str | None = None
    ready_sha256: str | None = None
    legacy_read_only: bool = True
    recovered_at_ms: int = Field(ge=0, le=MAX_I63)
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


class QuarantinedBackupResultV1(_Closed):
    store_id: str
    migration_epoch: Literal[1] = 1
    cutover_marker_sha256: str
    destination_basename: str
    backup_sha256: str
    backup_bytes: int = Field(ge=0, le=MAX_DB_BYTES)
    completed_at_ms: int = Field(ge=0, le=MAX_I63)
    audit_passed: Literal[True] = True
    self_promoting: Literal[False] = False
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False


# Stub types referenced by open() signature
class QuarantinedSyntheticLegacyRootV1:
    pass


class QuarantinedSyntheticExternalPinStoreV1:
    __slots__ = ("store_id", "pin_sha256", "ready_sha256")

    def __init__(
        self,
        *,
        store_id: str,
        pin_sha256: str | None = None,
        ready_sha256: str | None = None,
    ) -> None:
        if not _STORE_ID.fullmatch(store_id):
            raise PrivatePaidLaneEligibilityCheckpointRejected()
        if pin_sha256 is not None and not _HEX64.fullmatch(pin_sha256):
            raise PrivatePaidLaneEligibilityCheckpointRejected()
        if ready_sha256 is not None and not _HEX64.fullmatch(ready_sha256):
            raise PrivatePaidLaneEligibilityCheckpointRejected()
        self.store_id = store_id
        self.pin_sha256 = pin_sha256
        self.ready_sha256 = ready_sha256


# ---------------------------------------------------------------------------
# Schema audit
# ---------------------------------------------------------------------------


def _parse_schema_sql(sql: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Parse _SCHEMA_SQL_V1 into (tables, indexes) in order."""
    trimmed = _trim_outer_ascii_ws(sql)
    if trimmed.endswith(";"):
        trimmed = _trim_outer_ascii_ws(trimmed[:-1])

    tables: list[tuple[str, str]] = []
    indexes: list[tuple[str, str]] = []

    # Use SQLite to parse statements
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(sql)
        rows = conn.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE sql IS NOT NULL "
            "ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END, name"
        ).fetchall()
        for row_type, row_name, row_sql in rows:
            if row_type == "table":
                tables.append((row_name, str(row_sql)))
            elif row_type == "index" and not str(row_name).startswith("sqlite_autoindex"):
                indexes.append((row_name, str(row_sql)))
    finally:
        conn.close()

    return tables, indexes


def _normalize_schema_sql(sql: str) -> str:
    value = _trim_outer_ascii_ws(sql)
    if value.endswith(";"):
        value = _trim_outer_ascii_ws(value[:-1])
    return value


def _schema_sql_objects(connection: sqlite3.Connection) -> list[tuple[str, str, str]]:
    return [
        (str(row[0]), str(row[1]), _normalize_schema_sql(str(row[2])))
        for row in connection.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE sql IS NOT NULL AND type IN ('table','index') "
            "AND name NOT LIKE 'sqlite_autoindex_%' "
            "ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END, name"
        ).fetchall()
    ]


def _pragma_rows(
    connection: sqlite3.Connection, pragma: str, name: str
) -> tuple[tuple[object, ...], ...]:
    escaped = name.replace("'", "''")
    return tuple(
        tuple(row) for row in connection.execute(f"PRAGMA {pragma}('{escaped}')").fetchall()
    )


def _schema_metadata(connection: sqlite3.Connection) -> dict[str, object]:
    metadata: dict[str, object] = {"objects": _schema_sql_objects(connection)}
    tables = sorted(
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    )
    for table in tables:
        metadata[f"table_xinfo:{table}"] = _pragma_rows(connection, "table_xinfo", table)
        metadata[f"foreign_key_list:{table}"] = _pragma_rows(connection, "foreign_key_list", table)
        index_list = _pragma_rows(connection, "index_list", table)
        metadata[f"index_list:{table}"] = index_list
        for index_row in index_list:
            index_name = str(index_row[1])
            metadata[f"index_xinfo:{index_name}"] = _pragma_rows(
                connection, "index_xinfo", index_name
            )
    return metadata


def _audit_schema(connection: sqlite3.Connection) -> None:
    """Full schema audit: 18 tables, 13 indexes, 46 autoindexes, settings."""
    expected_connection = sqlite3.connect(":memory:")
    try:
        expected_connection.execute("PRAGMA foreign_keys=ON")
        expected_connection.executescript(_SCHEMA_SQL_V1)
        if _schema_metadata(connection) != _schema_metadata(expected_connection):
            raise PrivatePaidLaneEligibilityCheckpointRejected()
    finally:
        expected_connection.close()

    # Verify 18 tables
    table_rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    table_names = {str(row[0]) for row in table_rows}
    if table_names != _EXPECTED_TABLE_SET:
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    # Verify no views or triggers
    extras = connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('view','trigger')"
    ).fetchone()
    if extras is None or extras[0] != 0:
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    # Verify 13 explicit indexes
    idx_rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name NOT LIKE 'sqlite_autoindex_%' "
        "ORDER BY name"
    ).fetchall()
    idx_names = {str(row[0]) for row in idx_rows}
    if idx_names != _EXPECTED_INDEX_SET:
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    # Verify 46 autoindexes
    auto_rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name LIKE 'sqlite_autoindex_%' "
        "ORDER BY name"
    ).fetchall()
    auto_names = {str(row[0]) for row in auto_rows}
    if auto_names != _EXPECTED_AUTOINDEX_NAMES:
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    # Verify autoindex counts per table
    for table_name, expected_count in _EXPECTED_AUTOINDEX_TABLE_COUNTS.items():
        actual = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='index' AND tbl_name=? AND name LIKE 'sqlite_autoindex_%'",
            (table_name,),
        ).fetchone()
        if actual is None or actual[0] != expected_count:
            raise PrivatePaidLaneEligibilityCheckpointRejected()

    # Verify settings
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
        "busy_timeout": MAX_LOCK_TIMEOUT_MS,
        "foreign_keys": 1,
        "journal_mode_wal": 1,
        "page_size": 4096,
        "max_page_count": MAX_DB_PAGES,
        "synchronous": 2,
        "temp_store": 2,
    }:
        raise PrivatePaidLaneEligibilityCheckpointRejected()


def _audit_authority_chains(
    connection: sqlite3.Connection,
    *,
    revocation_floor_pins: Mapping[tuple[str, str], ProviderRevocationFloorPinV1],
    source_floor_pins: Mapping[tuple[str, str], OwnerPrivateSourceFloorPinV1],
    revocation_verification_keys: Mapping[str, bytes],
    source_verification_keys: Mapping[str, bytes],
) -> None:
    revocation_current_pairs = tuple(
        (str(row[0]), str(row[1]))
        for row in connection.execute(
            "SELECT registry_id, owner_path_discriminator FROM provider_revocation_current "
            "ORDER BY registry_id, owner_path_discriminator LIMIT ?",
            (MAX_MUTABLE_CURRENT_ROWS + 1,),
        ).fetchall()
    )
    if revocation_current_pairs != tuple(sorted(revocation_floor_pins)):
        raise PrivatePaidLaneEligibilityCheckpointRejected()
    source_current_pairs = tuple(
        (str(row[0]), str(row[1]))
        for row in connection.execute(
            "SELECT registry_id, owner_path_discriminator FROM source_current "
            "ORDER BY registry_id, owner_path_discriminator LIMIT ?",
            (MAX_MUTABLE_CURRENT_ROWS + 1,),
        ).fetchall()
    )
    if source_current_pairs != tuple(sorted(source_floor_pins)):
        raise PrivatePaidLaneEligibilityCheckpointRejected()
    for (registry_id, owner), pin in revocation_floor_pins.items():
        current = connection.execute(
            "SELECT head_sha256, epoch, state_version, updated_at_ms "
            "FROM provider_revocation_current "
            "WHERE registry_id=? AND owner_path_discriminator=?",
            (registry_id, owner),
        ).fetchone()
        if current is None or current[1] < pin.floor_epoch:
            raise PrivatePaidLaneEligibilityCheckpointRejected()
        rows = connection.execute(
            "SELECT head_sha256, registry_id, owner_path_discriminator, epoch, "
            "predecessor_head_sha256, issued_at_ms, revoked_capability_hashes_json, "
            "key_id, document_json, signature_ed25519 "
            "FROM provider_revocation_heads "
            "WHERE registry_id=? AND owner_path_discriminator=? AND epoch BETWEEN ? AND ? "
            "ORDER BY epoch LIMIT ?",
            (registry_id, owner, pin.floor_epoch, current[1], MAX_HEADS_PER_CHAIN + 1),
        ).fetchall()
        if len(rows) != current[1] - pin.floor_epoch + 1 or len(rows) > MAX_HEADS_PER_CHAIN:
            raise PrivatePaidLaneEligibilityCheckpointRejected()
        known = {
            str(cap_row[0])
            for cap_row in connection.execute(
                "SELECT capability_sha256 FROM provider_capabilities_v4 "
                "WHERE owner_path_discriminator=? AND revocation_registry_id=? LIMIT ?",
                (owner, registry_id, MAX_MUTABLE_CURRENT_ROWS + 1),
            ).fetchall()
        }
        if len(known) > MAX_MUTABLE_CURRENT_ROWS:
            raise PrivatePaidLaneEligibilityCheckpointRejected()
        previous_head: str | None = None
        previous_issued: int | None = None
        previous_tuple: tuple[str, ...] = ()
        for offset, row in enumerate(rows):
            head = SignedProviderRevocationHeadFixtureV1.model_validate_json(bytes(row[8]))
            verify_revocation_head(head, verification_keys=revocation_verification_keys)
            revoked = tuple(json.loads(bytes(row[6]).decode("utf-8")))
            if (
                row[0] != head.head_sha256
                or row[1] != registry_id
                or row[2] != owner
                or row[3] != pin.floor_epoch + offset
                or row[4] != head.predecessor_head_sha256
                or row[5] != head.issued_at_ms
                or row[7] != head.key_id
                or bytes(row[8]) != _canonical_model_json(head)
                or row[9] != head.signature_ed25519
                or head.registry_id != registry_id
                or head.owner_path_discriminator != owner
                or head.epoch != pin.floor_epoch + offset
                or head.revoked_capability_sha256s != revoked
                or bytes(row[6]) != _canonical_json(list(head.revoked_capability_sha256s))
            ):
                raise PrivatePaidLaneEligibilityCheckpointRejected()
            if offset == 0:
                if head.head_sha256 != pin.floor_head_sha256:
                    raise PrivatePaidLaneEligibilityCheckpointRejected()
                if head.epoch == 0 and (
                    head.predecessor_head_sha256 is not None
                    or head.revoked_capability_sha256s != ()
                ):
                    raise PrivatePaidLaneEligibilityCheckpointRejected()
            else:
                previous_set = set(previous_tuple)
                next_set = set(head.revoked_capability_sha256s)
                additions = tuple(
                    item for item in head.revoked_capability_sha256s if item not in previous_set
                )
                if (
                    head.predecessor_head_sha256 != previous_head
                    or previous_issued is None
                    or head.issued_at_ms <= previous_issued
                    or not previous_set.issubset(next_set)
                    or len(additions) > MAX_REVOKED_PER_HEAD
                ):
                    raise PrivatePaidLaneEligibilityCheckpointRejected()
            if any(item not in known for item in head.revoked_capability_sha256s):
                raise PrivatePaidLaneEligibilityCheckpointRejected()
            previous_head = head.head_sha256
            previous_issued = head.issued_at_ms
            previous_tuple = head.revoked_capability_sha256s
        if (
            previous_head != current[0]
            or current[2] != current[1] + 1
            or not _valid_i63(current[3])
            or previous_issued is None
            or current[3] < previous_issued
        ):
            raise PrivatePaidLaneEligibilityCheckpointRejected()

    for (registry_id, owner), source_pin in source_floor_pins.items():
        current = connection.execute(
            "SELECT head_sha256, epoch, state_version, updated_at_ms FROM source_current "
            "WHERE registry_id=? AND owner_path_discriminator=?",
            (registry_id, owner),
        ).fetchone()
        if current is None or current[1] < source_pin.floor_epoch:
            raise PrivatePaidLaneEligibilityCheckpointRejected()
        rows = connection.execute(
            "SELECT head_sha256, registry_id, owner_path_discriminator, epoch, "
            "previous_head_sha256, issued_at_ms, active_bundle_revisions_json, "
            "snapshot_json, key_id, document_json, signature_ed25519 "
            "FROM source_heads "
            "WHERE registry_id=? AND owner_path_discriminator=? AND epoch BETWEEN ? AND ? "
            "ORDER BY epoch LIMIT ?",
            (registry_id, owner, source_pin.floor_epoch, current[1], MAX_HEADS_PER_CHAIN + 1),
        ).fetchall()
        if len(rows) != current[1] - source_pin.floor_epoch + 1 or len(rows) > MAX_HEADS_PER_CHAIN:
            raise PrivatePaidLaneEligibilityCheckpointRejected()
        previous_head = None
        previous_issued = None
        previous_active: tuple[OpaqueSourceBundleRevisionV1, ...] = ()
        for offset, row in enumerate(rows):
            source_head = SignedSourceHeadFixtureV1.model_validate_json(bytes(row[9]))
            verify_source_head(source_head, verification_keys=source_verification_keys)
            active: tuple[OpaqueSourceBundleRevisionV1, ...] = tuple(
                OpaqueSourceBundleRevisionV1.model_validate(item)
                for item in json.loads(bytes(row[6]).decode("utf-8"))
            )
            if (
                row[0] != source_head.head_sha256
                or row[1] != registry_id
                or row[2] != owner
                or row[3] != source_pin.floor_epoch + offset
                or row[4] != source_head.previous_head_sha256
                or row[5] != source_head.issued_at_ms
                or row[8] != source_head.key_id
                or bytes(row[9]) != _canonical_model_json(source_head)
                or row[10] != source_head.signature_ed25519
                or source_head.registry_id != registry_id
                or source_head.owner_path_discriminator != owner
                or source_head.epoch != source_pin.floor_epoch + offset
                or source_head.snapshot.active_bundle_revisions != active
                or bytes(row[6])
                != _canonical_json([item.model_dump(mode="json") for item in active])
                or _canonical_json(source_head.snapshot.model_dump(mode="json")) != bytes(row[7])
                or source_head.snapshot.tombstoned_bundle_ids != ()
            ):
                raise PrivatePaidLaneEligibilityCheckpointRejected()

            if offset == 0:
                if source_head.head_sha256 != source_pin.floor_head_sha256:
                    raise PrivatePaidLaneEligibilityCheckpointRejected()
            else:
                expected_existing = tuple(item for item in active if item in previous_active)
                source_additions: tuple[OpaqueSourceBundleRevisionV1, ...] = tuple(
                    item for item in active if item not in previous_active
                )
                if (
                    source_head.previous_head_sha256 != previous_head
                    or previous_issued is None
                    or source_head.issued_at_ms <= previous_issued
                    or expected_existing != previous_active
                    or len(source_additions) != 1
                    or source_additions[0].row_revision != 1
                ):
                    raise PrivatePaidLaneEligibilityCheckpointRejected()
            previous_head = source_head.head_sha256
            previous_issued = source_head.issued_at_ms
            previous_active = active
        if (
            previous_head != current[0]
            or current[2] != current[1] + 1
            or not _valid_i63(current[3])
            or previous_issued is None
            or current[3] < previous_issued
            or len(previous_active) > MAX_ACTIVE_REVISIONS
        ):
            raise PrivatePaidLaneEligibilityCheckpointRejected()
        active_ids = tuple(item.opaque_source_bundle_id for item in previous_active)
        if len(active_ids) != len(set(active_ids)):
            raise PrivatePaidLaneEligibilityCheckpointRejected()
        for revision in previous_active:
            bundle_row = connection.execute(
                "SELECT owner_path_discriminator, state, row_version, aead_suite, "
                "key_version, nonce_length, nonce, aad_schema, aad_json, "
                "ciphertext_schema, ciphertext_type, ciphertext_length, ciphertext "
                "FROM encrypted_source_bundles WHERE opaque_source_bundle_id=?",
                (revision.opaque_source_bundle_id,),
            ).fetchone()
            if bundle_row is None:
                raise PrivatePaidLaneEligibilityCheckpointRejected()
            expected_aad = _canonical_json(
                {
                    "schema_version": 1,
                    "opaque_source_bundle_id": revision.opaque_source_bundle_id,
                    "owner_path_discriminator": owner,
                    "categorical_state": "sealed",
                    "aead_suite": "aes-256-gcm",
                    "key_version": bundle_row[4],
                    "nonce_length": 12,
                    "ciphertext_schema": "owner_private_encrypted_source_bundle_v1_json",
                    "ciphertext_type": "application/json",
                    "ciphertext_length": bundle_row[11],
                    "row_revision": 1,
                }
            )
            if (
                bundle_row[0] != owner
                or bundle_row[1] != "sealed"
                or bundle_row[2] != 1
                or bundle_row[3] != "aes-256-gcm"
                or type(bundle_row[4]) is not str
                or _KEY_VERSION.fullmatch(bundle_row[4]) is None
                or bundle_row[5] != 12
                or type(bundle_row[6]) is not bytes
                or len(bundle_row[6]) != 12
                or bundle_row[7] != "owner_private_source_aad_v1"
                or bytes(bundle_row[8]) != expected_aad
                or bundle_row[9] != "owner_private_encrypted_source_bundle_v1_json"
                or bundle_row[10] != "application/json"
                or not isinstance(bundle_row[11], int)
                or not 16 <= bundle_row[11] <= MAX_CIPHERTEXT_BYTES
                or type(bundle_row[12]) is not bytes
                or len(bundle_row[12]) != bundle_row[11]
            ):
                raise PrivatePaidLaneEligibilityCheckpointRejected()


_BOUNDED_34A_TABLES: Mapping[str, int] = MappingProxyType(
    {
        "provider_capabilities_v4": MAX_MUTABLE_CURRENT_ROWS,
        "provider_revocation_current": MAX_MUTABLE_CURRENT_ROWS,
        "source_current": MAX_MUTABLE_CURRENT_ROWS,
        "encrypted_source_bundles": MAX_MUTABLE_CURRENT_ROWS,
        "owner_operations": MAX_MUTABLE_CURRENT_ROWS,
        "consent_claims": MAX_MUTABLE_CURRENT_ROWS,
        "queue_leases": MAX_MUTABLE_CURRENT_ROWS,
        "budget_accounts": MAX_MUTABLE_CURRENT_ROWS,
    }
)


def _audit_34a_row_bounds(connection: sqlite3.Connection) -> None:
    for table_name, bound in _BOUNDED_34A_TABLES.items():
        rows = connection.execute(
            f"SELECT 1 FROM {table_name} LIMIT ?",  # table names are frozen constants.
            (bound + 1,),
        ).fetchall()
        if len(rows) > bound:
            raise PrivatePaidLaneEligibilityCheckpointRejected()


def _require_insert_capacity(
    connection: sqlite3.Connection, *, table_name: str, bound: int
) -> None:
    if table_name not in _BOUNDED_34A_TABLES:
        raise PrivatePaidLaneEligibilityCheckpointRejected()
    rows = connection.execute(
        f"SELECT 1 FROM {table_name} LIMIT ?",  # table names are frozen constants.
        (bound,),
    ).fetchall()
    if len(rows) >= bound:
        raise PrivatePaidLaneEligibilityCheckpointRejected()


# ---------------------------------------------------------------------------
# Authorizer callback
# ---------------------------------------------------------------------------


def _authorizer(action: int, *args: Any) -> int:
    """SQLite authorizer that denies DELETE/DROP/ALTER/ATTACH/DETACH after init."""
    denied_actions = {
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_DROP_INDEX,
        sqlite3.SQLITE_DROP_VTABLE,
        sqlite3.SQLITE_ALTER_TABLE,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
    }
    if action in denied_actions:
        return sqlite3.SQLITE_DENY
    # Deny writable PRAGMAs (allow read-only)
    if action == sqlite3.SQLITE_PRAGMA and args:
        pragma_name = str(args[0]).lower() if args else ""
        writable_pragmas = {
            "journal_mode",
            "synchronous",
            "temp_store",
            "page_size",
            "max_page_count",
            "busy_timeout",
            "cache_size",
            "mmap_size",
            "writable_schema",
            "legacy_alter_table",
        }
        if pragma_name in writable_pragmas:
            return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


# ---------------------------------------------------------------------------
# Store class
# ---------------------------------------------------------------------------


class PrivatePaidLaneEligibilityCheckpointStoreV1:
    """One-owner, fixture-only, physically unified paid-lane authority checkpoint."""

    _sealed: bool
    _lock: threading.Lock
    _owner_key_provider: PrivatePaidLaneOwnerKeyProviderV1
    _source_key_provider: OwnerPrivateSourceKeyProviderV1
    _capability_verification_keys: Mapping[str, bytes]
    _revocation_verification_keys: Mapping[str, bytes]
    _source_verification_keys: Mapping[str, bytes]
    _cutover_verification_keys: Mapping[str, bytes]
    _revocation_floor_pins: Mapping[tuple[str, str], ProviderRevocationFloorPinV1]
    _source_floor_pins: Mapping[tuple[str, str], OwnerPrivateSourceFloorPinV1]
    _boot_nonce: bytes
    _pending_key: bytes
    _construction_mac: bytes
    _pid: int
    database_path: Path
    owner_path_discriminator: str
    store_id: str
    open_mode: Literal[
        "create_epoch0",
        "precutover_epoch0",
        "pinned_epoch1",
        "forward_recovery_epoch1",
    ]
    semantic_source_sha256: str
    contract_sha256: str
    _active_handles: dict[str, PendingUnifiedSourceBundleHandleV1]
    _observed_hmac_keys: dict[bytes, _BLIND_PURPOSES]
    _synthetic_legacy_root: object
    _migration_root_handle: object | None

    __slots__ = (
        "__weakref__",
        "_sealed",
        "_lock",
        "_owner_key_provider",
        "_source_key_provider",
        "_capability_verification_keys",
        "_revocation_verification_keys",
        "_source_verification_keys",
        "_cutover_verification_keys",
        "_revocation_floor_pins",
        "_source_floor_pins",
        "_boot_nonce",
        "_pending_key",
        "_construction_mac",
        "_pid",
        "database_path",
        "owner_path_discriminator",
        "store_id",
        "open_mode",
        "semantic_source_sha256",
        "contract_sha256",
        "_active_handles",
        "_observed_hmac_keys",
        "_synthetic_legacy_root",
        "_migration_root_handle",
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    def __init_subclass__(cls, **kwargs: object) -> Never:
        del cls, kwargs
        raise TypeError("PrivatePaidLaneEligibilityCheckpointStoreV1 is final")

    def __copy__(self) -> Never:
        raise TypeError("paid-lane checkpoint store cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("paid-lane checkpoint store cannot be copied")

    @classmethod
    def open(
        cls,
        *,
        database_path: Path,
        open_mode: Literal[
            "create_epoch0",
            "precutover_epoch0",
            "pinned_epoch1",
            "forward_recovery_epoch1",
        ],
        expected_store_id: str,
        expected_schema_version: Literal[1],
        expected_migration_epoch: Literal[0, 1],
        expected_cutover_marker_sha256: str | None,
        expected_source_manifest_sha256: str | None,
        expected_copy_audit_sha256: str | None,
        expected_external_pin_store_id: str | None,
        expected_semantic_source_sha256: str,
        expected_contract_sha256: str,
        provider_capability_verification_keys: tuple[VerificationKeyV1, ...],
        provider_revocation_verification_keys: tuple[VerificationKeyV1, ...],
        source_head_verification_keys: tuple[VerificationKeyV1, ...],
        cutover_verification_keys: tuple[VerificationKeyV1, ...],
        provider_revocation_floor_pins: tuple[ProviderRevocationFloorPinV1, ...],
        source_floor_pins: tuple[OwnerPrivateSourceFloorPinV1, ...],
        source_bundle_key_provider: OwnerPrivateSourceKeyProviderV1,
        owner_key_provider: PrivatePaidLaneOwnerKeyProviderV1,
        synthetic_legacy_root: QuarantinedSyntheticLegacyRootV1 | None,
        synthetic_external_pin_store: QuarantinedSyntheticExternalPinStoreV1 | None,
    ) -> PrivatePaidLaneEligibilityCheckpointStoreV1:
        try:
            if cls is not PrivatePaidLaneEligibilityCheckpointStoreV1:
                raise ValueError("store class identity mismatch")
            _require_predecessor_runtime_sources()
            # Validate mode-dependent arguments
            if open_mode == "create_epoch0":
                if expected_cutover_marker_sha256 is not None:
                    raise ValueError("marker must be null for create_epoch0")
                if expected_source_manifest_sha256 is not None:
                    raise ValueError("manifest must be null for create_epoch0")
                if expected_copy_audit_sha256 is not None:
                    raise ValueError("copy_audit must be null for create_epoch0")
                if expected_external_pin_store_id is None:
                    raise ValueError("external_pin required for create_epoch0")
                if synthetic_legacy_root is None:
                    raise ValueError("synthetic_legacy_root required for create_epoch0")
                if synthetic_external_pin_store is None:
                    raise ValueError("external_pin_store required for create_epoch0")
                if (
                    synthetic_external_pin_store.store_id != expected_external_pin_store_id
                    or synthetic_external_pin_store.pin_sha256 is not None
                    or synthetic_external_pin_store.ready_sha256 is not None
                ):
                    raise ValueError("external pin must be absent for create_epoch0")
            elif open_mode == "precutover_epoch0":
                if expected_cutover_marker_sha256 is not None:
                    raise ValueError
                if synthetic_legacy_root is None:
                    raise ValueError
                if expected_external_pin_store_id is None or synthetic_external_pin_store is None:
                    raise ValueError
                if (
                    synthetic_external_pin_store.store_id != expected_external_pin_store_id
                    or synthetic_external_pin_store.pin_sha256 is not None
                    or synthetic_external_pin_store.ready_sha256 is not None
                ):
                    raise ValueError
            elif open_mode == "pinned_epoch1":
                raise ValueError("pinned_epoch1 requires exact 34D cutover lifecycle")
            elif open_mode == "forward_recovery_epoch1":
                raise ValueError("forward_recovery_epoch1 requires exact 34D recovery lifecycle")
            else:
                raise ValueError

            # Validate expected schema/contract
            if expected_schema_version != 1:
                raise ValueError
            if expected_migration_epoch not in (0, 1):
                raise ValueError
            if expected_migration_epoch == 0 and expected_cutover_marker_sha256 is not None:
                raise ValueError
            if expected_migration_epoch == 1 and expected_cutover_marker_sha256 is None:
                raise ValueError

            # Validate keyrings
            cap_keys = _copy_verification_keyring(provider_capability_verification_keys)
            rev_keys = _copy_verification_keyring(provider_revocation_verification_keys)
            src_keys = _copy_verification_keyring(source_head_verification_keys)
            cut_keys = _copy_verification_keyring(cutover_verification_keys)

            # Validate floor pins
            if len(provider_revocation_floor_pins) > MAX_MUTABLE_CURRENT_ROWS:
                raise ValueError("revocation floor pin bound")
            if (
                tuple(
                    sorted(
                        provider_revocation_floor_pins,
                        key=lambda p: (p.registry_id, p.owner_path_discriminator),
                    )
                )
                != provider_revocation_floor_pins
            ):
                raise ValueError("revocation floor pins must be sorted")
            rev_floor_map: dict[tuple[str, str], ProviderRevocationFloorPinV1] = {}
            for pin in provider_revocation_floor_pins:
                key = (pin.registry_id, pin.owner_path_discriminator)
                if key in rev_floor_map:
                    raise ValueError
                rev_floor_map[key] = pin

            if len(source_floor_pins) > MAX_MUTABLE_CURRENT_ROWS:
                raise ValueError("source floor pin bound")
            if (
                tuple(
                    sorted(
                        source_floor_pins, key=lambda p: (p.registry_id, p.owner_path_discriminator)
                    )
                )
                != source_floor_pins
            ):
                raise ValueError("source floor pins must be sorted")
            src_floor_map: dict[tuple[str, str], OwnerPrivateSourceFloorPinV1] = {}
            for src_pin in source_floor_pins:
                key = (src_pin.registry_id, src_pin.owner_path_discriminator)
                if key in src_floor_map:
                    raise ValueError
                src_floor_map[key] = src_pin

            # Compute semantic/contract
            semantic_sha256 = compute_private_paid_lane_semantic_sha256()
            contract_sha256 = compute_private_paid_lane_contract_sha256(
                semantic_sha256=semantic_sha256,
                sql=_SCHEMA_SQL_V1,
                predecessor_cycle33_contract=_PREDECESSOR_CYCLE33_CONTRACT_SHA256,
                predecessor_cycle32_source=_PREDECESSOR_CYCLE32_SOURCE_SHA256,
                predecessor_cycle30_capability=_PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
            )

            if expected_semantic_source_sha256 != semantic_sha256:
                raise ValueError
            if expected_contract_sha256 != contract_sha256:
                raise ValueError

            # Validate store_id syntax
            if type(expected_store_id) is not str or not _STORE_ID.fullmatch(expected_store_id):
                raise ValueError

            # Validate owner discriminator via provider
            # We need at least one owner_path_discriminator to construct the store.
            # Use the one from the first revocation floor pin or source floor pin.
            owner_discriminator: str | None = None
            for pin in provider_revocation_floor_pins:
                owner_discriminator = pin.owner_path_discriminator
                break
            if owner_discriminator is None:
                for src_pin in source_floor_pins:
                    owner_discriminator = src_pin.owner_path_discriminator
                    break
            if owner_discriminator is None:
                raise ValueError

            # Path setup
            raw_path = os.fspath(database_path)
            if not raw_path.strip() or raw_path == ":memory:":
                raise ValueError
            raw_supplied = Path(raw_path)
            _reject_symlinked_ancestors(raw_supplied)
            supplied = raw_supplied.resolve(strict=False)
            _reject_symlinked_ancestors(supplied)
            canonical = supplied
            canonical.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            create_new = open_mode == "create_epoch0"
            if create_new and canonical.exists():
                raise ValueError("create_epoch0 requires a fresh target")
            _validate_secure_durable_path(canonical, require_exists=not create_new)

            def initialize_validated_open() -> PrivatePaidLaneEligibilityCheckpointStoreV1:
                instance = object.__new__(cls)
                object.__setattr__(instance, "_sealed", False)
                instance.database_path = canonical
                instance.owner_path_discriminator = owner_discriminator
                instance.store_id = expected_store_id
                instance.open_mode = open_mode
                instance.semantic_source_sha256 = semantic_sha256
                instance.contract_sha256 = contract_sha256
                instance._lock = threading.Lock()
                instance._owner_key_provider = owner_key_provider
                instance._source_key_provider = source_bundle_key_provider
                instance._capability_verification_keys = MappingProxyType(cap_keys)
                instance._revocation_verification_keys = MappingProxyType(rev_keys)
                instance._source_verification_keys = MappingProxyType(src_keys)
                instance._cutover_verification_keys = MappingProxyType(cut_keys)
                instance._revocation_floor_pins = MappingProxyType(rev_floor_map)
                instance._source_floor_pins = MappingProxyType(src_floor_map)
                instance._active_handles = {}
                instance._observed_hmac_keys = {}
                instance._synthetic_legacy_root = synthetic_legacy_root
                instance._migration_root_handle = None
                instance._boot_nonce = secrets.token_bytes(32)
                instance._pending_key = secrets.token_bytes(32)
                instance._pid = os.getpid()
                instance._initialize_schema(
                    create_new=create_new,
                    expected_migration_epoch=expected_migration_epoch,
                    expected_cutover_marker_sha256=expected_cutover_marker_sha256,
                    expected_source_manifest_sha256=expected_source_manifest_sha256,
                    expected_copy_audit_sha256=expected_copy_audit_sha256,
                )
                instance._construction_mac = instance._compute_construction_mac()
                object.__setattr__(instance, "_sealed", True)
                return instance

            return initialize_validated_open()
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("paid-lane checkpoint store is immutable")
        object.__setattr__(self, name, value)

    def _compute_construction_mac(self) -> bytes:
        material = _canonical_json(
            {
                "object_identity": id(self),
                "pid": self._pid,
                "boot_nonce": self._boot_nonce.hex(),
                "database_path": os.fspath(self.database_path),
                "owner_path_discriminator": self.owner_path_discriminator,
                "store_id": self.store_id,
                "open_mode": self.open_mode,
                "semantic_source_sha256": self.semantic_source_sha256,
                "contract_sha256": self.contract_sha256,
                "synthetic_legacy_root_identity": id(self._synthetic_legacy_root),
                "migration_root_handle_identity": id(self._migration_root_handle),
            }
        )
        return hmac.new(self._pending_key, material, hashlib.sha256).digest()

    def _validate_exact_open_instance(self) -> None:
        try:
            if (
                type(self) is not PrivatePaidLaneEligibilityCheckpointStoreV1
                or self._sealed is not True
                or self._pid != os.getpid()
                or type(self._boot_nonce) is not bytes
                or len(self._boot_nonce) != 32
                or type(self._pending_key) is not bytes
                or len(self._pending_key) != 32
                or type(self._construction_mac) is not bytes
                or len(self._construction_mac) != 32
                or type(self._lock) is not type(threading.Lock())
                or type(self._active_handles) is not dict
                or type(self._observed_hmac_keys) is not dict
                or not hmac.compare_digest(self._construction_mac, self._compute_construction_mac())
            ):
                raise ValueError
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def _connect(self) -> sqlite3.Connection:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        _require_predecessor_runtime_sources()
        _validate_secure_durable_path(self.database_path, require_exists=True)
        connection = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute("PRAGMA page_size=4096")
            connection.execute(f"PRAGMA max_page_count={MAX_DB_PAGES}")
            _chmod_sidecars(self.database_path)
            _audit_schema(connection)
            _audit_34a_row_bounds(connection)
            connection.set_authorizer(_authorizer)
            return connection
        except Exception:
            connection.close()
            raise

    def _initialize_schema(
        self,
        *,
        create_new: bool,
        expected_migration_epoch: int,
        expected_cutover_marker_sha256: str | None,
        expected_source_manifest_sha256: str | None,
        expected_copy_audit_sha256: str | None,
    ) -> None:
        if not create_new:
            with closing(
                sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
            ) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=FULL")
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute("PRAGMA temp_store=MEMORY")
                conn.execute(f"PRAGMA max_page_count={MAX_DB_PAGES}")
                _audit_schema(conn)
                _audit_34a_row_bounds(conn)
                row = conn.execute(
                    "SELECT store_id, semantic_source_sha256, contract_sha256, "
                    "migration_epoch, cutover_marker_sha256 "
                    "FROM paid_lane_schema WHERE singleton=1"
                ).fetchone()
                if (
                    row is None
                    or row[0] != self.store_id
                    or row[1] != self.semantic_source_sha256
                    or row[2] != self.contract_sha256
                    or row[3] != expected_migration_epoch
                    or row[4] != expected_cutover_marker_sha256
                ):
                    raise ValueError("schema identity mismatch")
                _audit_authority_chains(
                    conn,
                    revocation_floor_pins=self._revocation_floor_pins,
                    source_floor_pins=self._source_floor_pins,
                    revocation_verification_keys=self._revocation_verification_keys,
                    source_verification_keys=self._source_verification_keys,
                )
                if expected_migration_epoch == 1:
                    proof = conn.execute(
                        "SELECT target_store_id, source_manifest_sha256, copy_audit_sha256, "
                        "semantic_source_sha256, contract_sha256, marker_sha256 "
                        "FROM migration_cutover_proof WHERE migration_epoch=1"
                    ).fetchone()
                    if (
                        proof is None
                        or proof[0] != self.store_id
                        or proof[1] != expected_source_manifest_sha256
                        or proof[2] != expected_copy_audit_sha256
                        or proof[3] != self.semantic_source_sha256
                        or proof[4] != self.contract_sha256
                        or proof[5] != expected_cutover_marker_sha256
                    ):
                        raise ValueError("cutover proof mismatch")
            _chmod_sidecars(self.database_path)
            return

        with closing(sqlite3.connect(self.database_path, timeout=30, isolation_level=None)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA page_size=4096")
            conn.execute(f"PRAGMA max_page_count={MAX_DB_PAGES}")
            _chmod_sidecars(self.database_path)

            # executescript runs each statement in its own autocommit transaction
            conn.executescript(_SCHEMA_SQL_V1)

            # Now do the singleton insert in an explicit transaction
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT store_id, semantic_source_sha256, contract_sha256 "
                    "FROM paid_lane_schema WHERE singleton=1"
                ).fetchone()
                if row is None:
                    if expected_migration_epoch != 0 or expected_cutover_marker_sha256 is not None:
                        raise ValueError("fresh schema must be epoch zero")
                    conn.execute(
                        "INSERT INTO paid_lane_schema "
                        "(singleton, schema_version, migration_epoch, store_id, "
                        "semantic_source_sha256, contract_sha256, created_at_ms) "
                        "VALUES (1, 1, 0, ?, ?, ?, ?)",
                        (
                            self.store_id,
                            self.semantic_source_sha256,
                            self.contract_sha256,
                            0,
                        ),
                    )
                else:
                    if (
                        row[0] != self.store_id
                        or row[1] != self.semantic_source_sha256
                        or row[2] != self.contract_sha256
                    ):
                        raise ValueError("schema identity mismatch")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        os.chmod(self.database_path, 0o600)
        _chmod_sidecars(self.database_path)

    # -----------------------------------------------------------------------
    # Owner operation APIs
    # -----------------------------------------------------------------------

    def put_fixture_owner_operation(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        value: FixtureOwnerOperationPutV1,
        now_ms: int,
    ) -> FixtureOwnerOperationResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT state, state_version, cancel_requested, cancellation_version, "
                        "job_id, execution_id, stage_id, created_at_ms, updated_at_ms "
                        "FROM owner_operations "
                        "WHERE owner_path_discriminator=? AND operation_id=?",
                        (owner_path_discriminator, value.operation_id),
                    ).fetchone()
                    if row is not None:
                        # Exact replay check
                        if (
                            row[0] == value.state
                            and row[1] == 1
                            and row[2] == 0
                            and row[3] == 0
                            and row[4] == value.job_id
                            and row[5] == value.execution_id
                            and row[6] == value.stage_id
                            and row[7] == now_ms
                            and row[8] == now_ms
                        ):
                            connection.execute("COMMIT")
                            return FixtureOwnerOperationResultV1(
                                applied=False,
                                replayed=True,
                                owner_path_discriminator=owner_path_discriminator,
                                operation_id=value.operation_id,
                                state=row[0],
                                state_version=row[1],
                                cancel_requested=row[2],
                                cancellation_version=row[3],
                            )
                        raise ValueError("operation already exists with different state")
                    _require_insert_capacity(
                        connection,
                        table_name="owner_operations",
                        bound=MAX_MUTABLE_CURRENT_ROWS,
                    )
                    connection.execute(
                        "INSERT INTO owner_operations "
                        "(owner_path_discriminator, operation_id, job_id, execution_id, "
                        "stage_id, state, state_version, cancel_requested, "
                        "cancellation_version, created_at_ms, updated_at_ms) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            owner_path_discriminator,
                            value.operation_id,
                            value.job_id,
                            value.execution_id,
                            value.stage_id,
                            value.state,
                            1,
                            0,
                            0,
                            now_ms,
                            now_ms,
                        ),
                    )
                    connection.execute("COMMIT")
                    return FixtureOwnerOperationResultV1(
                        applied=True,
                        replayed=False,
                        owner_path_discriminator=owner_path_discriminator,
                        operation_id=value.operation_id,
                        state=value.state,
                        state_version=1,
                        cancel_requested=0,
                        cancellation_version=0,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def advance_fixture_owner_operation(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        command: FixtureOwnerOperationAdvanceV1,
        now_ms: int,
    ) -> FixtureOwnerOperationResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            valid_transitions = {
                ("queued", "running"),
                ("queued", "terminal"),
                ("running", "terminal"),
            }
            if (command.expected_state, command.next_state) not in valid_transitions:
                raise ValueError("invalid transition")
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT state, state_version, cancel_requested, cancellation_version "
                        "FROM owner_operations "
                        "WHERE owner_path_discriminator=? AND operation_id=?",
                        (owner_path_discriminator, command.operation_id),
                    ).fetchone()
                    if row is None:
                        raise ValueError("operation not found")
                    if row[0] != command.expected_state or row[1] != command.expected_state_version:
                        raise ValueError("state/version mismatch")
                    if row[2] != 0 or row[3] != 0:
                        raise ValueError("operation is cancelled")
                    next_version = command.expected_state_version + 1
                    connection.execute(
                        "UPDATE owner_operations SET state=?, state_version=?, "
                        "updated_at_ms=? WHERE owner_path_discriminator=? AND operation_id=?",
                        (
                            command.next_state,
                            next_version,
                            now_ms,
                            owner_path_discriminator,
                            command.operation_id,
                        ),
                    )
                    connection.execute("COMMIT")
                    return FixtureOwnerOperationResultV1(
                        applied=True,
                        replayed=False,
                        owner_path_discriminator=owner_path_discriminator,
                        operation_id=command.operation_id,
                        state=command.next_state,
                        state_version=next_version,
                        cancel_requested=0,
                        cancellation_version=0,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def cancel_fixture_owner_operation(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        command: FixtureOwnerOperationCancelV1,
        now_ms: int,
    ) -> FixtureOwnerOperationResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT state, state_version, cancel_requested, cancellation_version "
                        "FROM owner_operations "
                        "WHERE owner_path_discriminator=? AND operation_id=?",
                        (owner_path_discriminator, command.operation_id),
                    ).fetchone()
                    if row is None:
                        raise ValueError("operation not found")
                    if row[0] != command.expected_state:
                        raise ValueError("state mismatch")
                    if row[1] != command.expected_state_version:
                        raise ValueError("state version mismatch")
                    if row[2] != command.expected_cancellation_version:
                        raise ValueError("cancellation version mismatch")
                    next_cancel_version = command.next_cancellation_version
                    connection.execute(
                        "UPDATE owner_operations SET state='cancel_requested', "
                        "cancel_requested=1, cancellation_version=?, "
                        "updated_at_ms=? "
                        "WHERE owner_path_discriminator=? AND operation_id=?",
                        (
                            next_cancel_version,
                            now_ms,
                            owner_path_discriminator,
                            command.operation_id,
                        ),
                    )
                    connection.execute("COMMIT")
                    return FixtureOwnerOperationResultV1(
                        applied=True,
                        replayed=False,
                        owner_path_discriminator=owner_path_discriminator,
                        operation_id=command.operation_id,
                        state="cancel_requested",
                        state_version=command.expected_state_version,
                        cancel_requested=1,
                        cancellation_version=next_cancel_version,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    # -----------------------------------------------------------------------
    # Consent APIs
    # -----------------------------------------------------------------------

    def put_fixture_consent(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        value: FixtureConsentPutV1,
        now_ms: int,
    ) -> FixtureConsentResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            if value.expires_at_ms <= value.issued_at_ms:
                raise ValueError
            consent_blind_id = self._blind_consent(
                owner_path_authority,
                owner_path_discriminator,
                value.consent_receipt_material,
                value.consent_config_material,
            )
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT state, version, approved_ceiling_cents, expires_at_ms, issued_at_ms, "
                        "claimed_effect_blind_id, claimed_at_ms, updated_at_ms "
                        "FROM consent_claims "
                        "WHERE owner_path_discriminator=? AND consent_blind_id=?",
                        (owner_path_discriminator, consent_blind_id),
                    ).fetchone()
                    if row is not None:
                        # Exact replay
                        if (
                            row[0] == "open"
                            and row[1] == value.version
                            and row[2] == value.approved_ceiling_cents
                            and row[3] == value.expires_at_ms
                            and row[4] == value.issued_at_ms
                            and row[5] is None
                            and row[6] is None
                            and row[7] == now_ms
                        ):
                            connection.execute("COMMIT")
                            return FixtureConsentResultV1(
                                applied=False,
                                replayed=True,
                                owner_path_discriminator=owner_path_discriminator,
                                consent_blind_id=consent_blind_id,
                                state="open",
                                version=value.version,
                                expires_at_ms=row[3],
                            )
                        raise ValueError("consent already exists with different state")
                    _require_insert_capacity(
                        connection,
                        table_name="consent_claims",
                        bound=MAX_MUTABLE_CURRENT_ROWS,
                    )
                    connection.execute(
                        "INSERT INTO consent_claims "
                        "(owner_path_discriminator, consent_blind_id, approved_ceiling_cents, "
                        "version, issued_at_ms, expires_at_ms, state, "
                        "claimed_effect_blind_id, claimed_at_ms, updated_at_ms) "
                        "VALUES (?,?,?, ?,?,?, 'open', NULL, NULL, ?)",
                        (
                            owner_path_discriminator,
                            consent_blind_id,
                            value.approved_ceiling_cents,
                            value.version,
                            value.issued_at_ms,
                            value.expires_at_ms,
                            now_ms,
                        ),
                    )
                    connection.execute("COMMIT")
                    return FixtureConsentResultV1(
                        applied=True,
                        replayed=False,
                        owner_path_discriminator=owner_path_discriminator,
                        consent_blind_id=consent_blind_id,
                        state="open",
                        version=value.version,
                        expires_at_ms=value.expires_at_ms,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def withdraw_fixture_consent(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        command: FixtureConsentWithdrawV1,
        now_ms: int,
    ) -> FixtureConsentResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            consent_blind_id = self._blind_consent(
                owner_path_authority,
                owner_path_discriminator,
                command.consent_receipt_material,
                command.consent_config_material,
            )
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT state, version, approved_ceiling_cents, expires_at_ms "
                        "FROM consent_claims "
                        "WHERE owner_path_discriminator=? AND consent_blind_id=?",
                        (owner_path_discriminator, consent_blind_id),
                    ).fetchone()
                    if row is None:
                        raise ValueError("consent not found")
                    if row[0] != "open":
                        raise ValueError("consent not open")
                    if row[1] != command.expected_version:
                        raise ValueError("version mismatch")
                    next_version = command.next_version
                    if next_version != command.expected_version + 1:
                        raise ValueError("next version must be exactly +1")
                    connection.execute(
                        "UPDATE consent_claims SET state='withdrawn', version=?, "
                        "updated_at_ms=? "
                        "WHERE owner_path_discriminator=? AND consent_blind_id=?",
                        (next_version, now_ms, owner_path_discriminator, consent_blind_id),
                    )
                    connection.execute("COMMIT")
                    return FixtureConsentResultV1(
                        applied=True,
                        replayed=False,
                        owner_path_discriminator=owner_path_discriminator,
                        consent_blind_id=consent_blind_id,
                        state="withdrawn",
                        version=next_version,
                        expires_at_ms=row[3],
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def claim_fixture_consent_for_test(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        command: FixtureConsentClaimForTestV1,
        now_ms: int,
    ) -> FixtureConsentResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            consent_blind_id = self._blind_consent(
                owner_path_authority,
                owner_path_discriminator,
                command.consent_receipt_material,
                command.consent_config_material,
            )
            effect_blind_id = self._blind_test_claim(
                owner_path_authority,
                owner_path_discriminator,
                command.consent_receipt_material,
                command.consent_config_material,
                command.effect_material,
            )
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT state, version, approved_ceiling_cents, expires_at_ms "
                        "FROM consent_claims "
                        "WHERE owner_path_discriminator=? AND consent_blind_id=?",
                        (owner_path_discriminator, consent_blind_id),
                    ).fetchone()
                    if row is None:
                        raise ValueError("consent not found")
                    if row[0] != "open":
                        raise ValueError("consent not open")
                    if row[1] != command.expected_version:
                        raise ValueError("version mismatch")
                    next_version = command.expected_version + 1
                    connection.execute(
                        "UPDATE consent_claims SET state='claimed', version=?, "
                        "claimed_effect_blind_id=?, claimed_at_ms=?, updated_at_ms=? "
                        "WHERE owner_path_discriminator=? AND consent_blind_id=?",
                        (
                            next_version,
                            effect_blind_id,
                            now_ms,
                            now_ms,
                            owner_path_discriminator,
                            consent_blind_id,
                        ),
                    )
                    connection.execute("COMMIT")
                    return FixtureConsentResultV1(
                        applied=True,
                        replayed=False,
                        owner_path_discriminator=owner_path_discriminator,
                        consent_blind_id=consent_blind_id,
                        state="claimed",
                        version=next_version,
                        expires_at_ms=row[3],
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    # -----------------------------------------------------------------------
    # Queue lease APIs
    # -----------------------------------------------------------------------

    def put_fixture_queue_lease(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        value: FixtureQueueLeasePutV1,
        now_ms: int,
    ) -> FixtureQueueLeaseResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            if value.exclusive_until_ms <= value.acquired_at_ms:
                raise ValueError
            cursor_blind_id = self._blind_cursor(
                owner_path_authority,
                owner_path_discriminator,
                value.queue_operation_id,
                value.cursor_material,
            )
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = connection.execute(
                        "SELECT lease_owner, generation, cursor_blind_id, row_version, "
                        "acquired_at_ms, exclusive_until_ms, updated_at_ms FROM queue_leases "
                        "WHERE owner_path_discriminator=? AND queue_operation_id=?",
                        (owner_path_discriminator, value.queue_operation_id),
                    ).fetchone()
                    if existing is not None:
                        if (
                            existing[0] == value.lease_owner
                            and existing[1] == value.generation
                            and existing[2] == cursor_blind_id
                            and existing[3] == value.row_version
                            and existing[4] == value.acquired_at_ms
                            and existing[5] == value.exclusive_until_ms
                            and existing[6] == now_ms
                        ):
                            connection.execute("COMMIT")
                            return FixtureQueueLeaseResultV1(
                                applied=False,
                                replayed=True,
                                owner_path_discriminator=owner_path_discriminator,
                                queue_operation_id=value.queue_operation_id,
                                lease_owner=value.lease_owner,
                                generation=value.generation,
                                cursor_blind_id=cursor_blind_id,
                                row_version=value.row_version,
                                exclusive_until_ms=value.exclusive_until_ms,
                            )
                        raise ValueError("lease already exists")
                    _require_insert_capacity(
                        connection,
                        table_name="queue_leases",
                        bound=MAX_MUTABLE_CURRENT_ROWS,
                    )
                    connection.execute(
                        "INSERT INTO queue_leases "
                        "(owner_path_discriminator, queue_operation_id, lease_owner, "
                        "generation, cursor_blind_id, row_version, acquired_at_ms, "
                        "exclusive_until_ms, updated_at_ms) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            owner_path_discriminator,
                            value.queue_operation_id,
                            value.lease_owner,
                            value.generation,
                            cursor_blind_id,
                            value.row_version,
                            value.acquired_at_ms,
                            value.exclusive_until_ms,
                            now_ms,
                        ),
                    )
                    connection.execute("COMMIT")
                    return FixtureQueueLeaseResultV1(
                        applied=True,
                        replayed=False,
                        owner_path_discriminator=owner_path_discriminator,
                        queue_operation_id=value.queue_operation_id,
                        lease_owner=value.lease_owner,
                        generation=value.generation,
                        cursor_blind_id=cursor_blind_id,
                        row_version=value.row_version,
                        exclusive_until_ms=value.exclusive_until_ms,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def takeover_fixture_queue_lease(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        command: FixtureQueueLeaseTakeoverV1,
        now_ms: int,
    ) -> FixtureQueueLeaseResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            if command.next_exclusive_until_ms <= now_ms:
                raise ValueError
            expected_cursor = self._blind_cursor(
                owner_path_authority,
                owner_path_discriminator,
                command.queue_operation_id,
                command.expected_cursor_material,
            )
            next_cursor = self._blind_cursor(
                owner_path_authority,
                owner_path_discriminator,
                command.queue_operation_id,
                command.next_cursor_material,
            )
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT lease_owner, generation, cursor_blind_id, row_version, "
                        "exclusive_until_ms FROM queue_leases "
                        "WHERE owner_path_discriminator=? AND queue_operation_id=?",
                        (owner_path_discriminator, command.queue_operation_id),
                    ).fetchone()
                    if row is None:
                        raise ValueError("lease not found")
                    next_version = command.expected_row_version + 1
                    if row[0] != command.expected_lease_owner:
                        raise ValueError("lease owner mismatch")
                    if row[1] != command.expected_generation:
                        raise ValueError("generation mismatch")
                    if row[2] != expected_cursor:
                        raise ValueError("cursor mismatch")
                    if row[3] != command.expected_row_version:
                        raise ValueError("row version mismatch")
                    if now_ms < row[4]:
                        raise ValueError("old lease still exclusive")
                    if command.next_generation != command.expected_generation + 1:
                        raise ValueError("next generation must be exactly +1")
                    connection.execute(
                        "UPDATE queue_leases SET lease_owner=?, generation=?, "
                        "cursor_blind_id=?, row_version=?, acquired_at_ms=?, "
                        "exclusive_until_ms=?, updated_at_ms=? "
                        "WHERE owner_path_discriminator=? AND queue_operation_id=?",
                        (
                            command.next_lease_owner,
                            command.next_generation,
                            next_cursor,
                            next_version,
                            now_ms,
                            command.next_exclusive_until_ms,
                            now_ms,
                            owner_path_discriminator,
                            command.queue_operation_id,
                        ),
                    )
                    connection.execute("COMMIT")
                    return FixtureQueueLeaseResultV1(
                        applied=True,
                        replayed=False,
                        owner_path_discriminator=owner_path_discriminator,
                        queue_operation_id=command.queue_operation_id,
                        lease_owner=command.next_lease_owner,
                        generation=command.next_generation,
                        cursor_blind_id=next_cursor,
                        row_version=next_version,
                        exclusive_until_ms=command.next_exclusive_until_ms,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def renew_fixture_queue_lease(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        command: FixtureQueueLeaseRenewV1,
        now_ms: int,
    ) -> FixtureQueueLeaseResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            expected_cursor = self._blind_cursor(
                owner_path_authority,
                owner_path_discriminator,
                command.queue_operation_id,
                command.expected_cursor_material,
            )
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT lease_owner, generation, cursor_blind_id, row_version, "
                        "exclusive_until_ms FROM queue_leases "
                        "WHERE owner_path_discriminator=? AND queue_operation_id=?",
                        (owner_path_discriminator, command.queue_operation_id),
                    ).fetchone()
                    if row is None:
                        raise ValueError("lease not found")
                    if row[0] != command.expected_lease_owner:
                        raise ValueError("lease owner mismatch")
                    if row[1] != command.expected_generation:
                        raise ValueError("generation mismatch")
                    if row[2] != expected_cursor:
                        raise ValueError("cursor mismatch")
                    if row[3] != command.expected_row_version:
                        raise ValueError("row version mismatch")
                    if command.next_exclusive_until_ms >= row[4]:
                        raise ValueError("new expiry must be before old expiry")
                    if command.next_row_version != command.expected_row_version + 1:
                        raise ValueError("row version must increment by 1")
                    connection.execute(
                        "UPDATE queue_leases SET row_version=?, "
                        "exclusive_until_ms=?, updated_at_ms=? "
                        "WHERE owner_path_discriminator=? AND queue_operation_id=?",
                        (
                            command.next_row_version,
                            command.next_exclusive_until_ms,
                            now_ms,
                            owner_path_discriminator,
                            command.queue_operation_id,
                        ),
                    )
                    connection.execute("COMMIT")
                    return FixtureQueueLeaseResultV1(
                        applied=True,
                        replayed=False,
                        owner_path_discriminator=owner_path_discriminator,
                        queue_operation_id=command.queue_operation_id,
                        lease_owner=row[0],
                        generation=row[1],
                        cursor_blind_id=expected_cursor,
                        row_version=command.next_row_version,
                        exclusive_until_ms=command.next_exclusive_until_ms,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    # -----------------------------------------------------------------------
    # Budget APIs
    # -----------------------------------------------------------------------

    def put_fixture_budget(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        value: FixtureBudgetPutV1,
        now_ms: int,
    ) -> FixtureBudgetResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            account_blind = self._blind_account(
                owner_path_authority,
                owner_path_discriminator,
                value.account_scope_material,
            )
            project_blind = self._blind_project(
                owner_path_authority,
                owner_path_discriminator,
                value.project_scope_material,
            )
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = connection.execute(
                        "SELECT approved_ceiling_cents, confirmed_cents, open_cents, "
                        "unknown_cents, row_version, updated_at_ms FROM budget_accounts "
                        "WHERE owner_path_discriminator=? "
                        "AND account_scope_blind_id=? AND project_scope_blind_id=?",
                        (owner_path_discriminator, account_blind, project_blind),
                    ).fetchone()
                    if existing is not None:
                        if (
                            existing[0] == value.approved_ceiling_cents
                            and existing[1] == 0
                            and existing[2] == 0
                            and existing[3] == 0
                            and existing[4] == value.row_version
                            and existing[5] == now_ms
                        ):
                            connection.execute("COMMIT")
                            return FixtureBudgetResultV1(
                                applied=False,
                                replayed=True,
                                owner_path_discriminator=owner_path_discriminator,
                                account_scope_blind_id=account_blind,
                                project_scope_blind_id=project_blind,
                                approved_ceiling_cents=value.approved_ceiling_cents,
                                confirmed_cents=0,
                                open_cents=0,
                                unknown_cents=0,
                                row_version=value.row_version,
                            )
                        raise ValueError("budget already exists")
                    _require_insert_capacity(
                        connection,
                        table_name="budget_accounts",
                        bound=MAX_MUTABLE_CURRENT_ROWS,
                    )
                    connection.execute(
                        "INSERT INTO budget_accounts "
                        "(owner_path_discriminator, account_scope_blind_id, "
                        "project_scope_blind_id, approved_ceiling_cents, "
                        "confirmed_cents, open_cents, unknown_cents, "
                        "row_version, updated_at_ms) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            owner_path_discriminator,
                            account_blind,
                            project_blind,
                            value.approved_ceiling_cents,
                            0,
                            0,
                            0,
                            value.row_version,
                            now_ms,
                        ),
                    )
                    connection.execute("COMMIT")
                    return FixtureBudgetResultV1(
                        applied=True,
                        replayed=False,
                        owner_path_discriminator=owner_path_discriminator,
                        account_scope_blind_id=account_blind,
                        project_scope_blind_id=project_blind,
                        confirmed_cents=0,
                        open_cents=0,
                        unknown_cents=0,
                        approved_ceiling_cents=value.approved_ceiling_cents,
                        row_version=value.row_version,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def mutate_fixture_budget(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        command: FixtureBudgetMutateV1,
        now_ms: int,
    ) -> FixtureBudgetResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            account_blind = self._blind_account(
                owner_path_authority,
                owner_path_discriminator,
                command.account_scope_material,
            )
            project_blind = self._blind_project(
                owner_path_authority,
                owner_path_discriminator,
                command.project_scope_material,
            )
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT approved_ceiling_cents, confirmed_cents, "
                        "open_cents, unknown_cents, row_version "
                        "FROM budget_accounts "
                        "WHERE owner_path_discriminator=? "
                        "AND account_scope_blind_id=? AND project_scope_blind_id=?",
                        (owner_path_discriminator, account_blind, project_blind),
                    ).fetchone()
                    if row is None:
                        raise ValueError("budget not found")
                    next_version = command.expected_row_version + 1
                    if row[4] != command.expected_row_version:
                        raise ValueError("row version mismatch")
                    if command.next_approved_ceiling_cents < row[1] + row[2] + row[3]:
                        raise ValueError("ceiling below categorized totals")
                    connection.execute(
                        "UPDATE budget_accounts SET approved_ceiling_cents=?, "
                        "row_version=?, updated_at_ms=? "
                        "WHERE owner_path_discriminator=? "
                        "AND account_scope_blind_id=? AND project_scope_blind_id=?",
                        (
                            command.next_approved_ceiling_cents,
                            next_version,
                            now_ms,
                            owner_path_discriminator,
                            account_blind,
                            project_blind,
                        ),
                    )
                    connection.execute("COMMIT")
                    return FixtureBudgetResultV1(
                        applied=True,
                        replayed=False,
                        owner_path_discriminator=owner_path_discriminator,
                        account_scope_blind_id=account_blind,
                        project_scope_blind_id=project_blind,
                        confirmed_cents=row[1],
                        open_cents=row[2],
                        unknown_cents=row[3],
                        approved_ceiling_cents=command.next_approved_ceiling_cents,
                        row_version=next_version,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    # -----------------------------------------------------------------------
    # Provider capability API
    # -----------------------------------------------------------------------

    def put_fixture_provider_capability_v4(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        value: FixtureProviderCapabilityPutV1,
        now_ms: int,
    ) -> FixtureCapabilityResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            cap = value.signed_provider_capability_v4
            if cap.owner_path_discriminator != owner_path_discriminator:
                raise ValueError("owner mismatch")
            verify_capability_v4(cap, verification_keys=self._capability_verification_keys)
            doc_bytes = _canonical_model_json(cap)
            _require_bounded_bytes(doc_bytes, bound=MAX_DOCUMENT_BYTES)
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = connection.execute(
                        "SELECT capability_id, owner_path_discriminator, revocation_registry_id, "
                        "revocation_trusted_floor_sha256, issued_at_ms, expires_at_ms, key_id, "
                        "document_json, signature_ed25519 FROM provider_capabilities_v4 "
                        "WHERE capability_sha256=?",
                        (cap.capability_sha256,),
                    ).fetchone()
                    if existing is not None:
                        # Exact replay
                        if (
                            existing[0] == cap.capability_id
                            and existing[1] == cap.owner_path_discriminator
                            and existing[2] == cap.revocation_registry_id
                            and existing[3] == cap.revocation_trusted_floor_sha256
                            and existing[4] == cap.issued_at_ms
                            and existing[5] == cap.expires_at_ms
                            and existing[6] == cap.key_id
                            and bytes(existing[7]) == doc_bytes
                            and existing[8] == cap.signature_ed25519
                        ):
                            connection.execute("COMMIT")
                            return FixtureCapabilityResultV1(
                                applied=False,
                                replayed=True,
                                owner_path_discriminator=owner_path_discriminator,
                                capability_id=cap.capability_id,
                                capability_sha256=cap.capability_sha256,
                                revocation_registry_id=cap.revocation_registry_id,
                                revocation_trusted_floor_sha256=(
                                    cap.revocation_trusted_floor_sha256
                                ),
                                expires_at_ms=cap.expires_at_ms,
                            )
                        raise ValueError("capability id mismatch on replay")
                    _require_insert_capacity(
                        connection,
                        table_name="provider_capabilities_v4",
                        bound=MAX_MUTABLE_CURRENT_ROWS,
                    )
                    connection.execute(
                        "INSERT INTO provider_capabilities_v4 "
                        "(capability_sha256, capability_id, owner_path_discriminator, "
                        "revocation_registry_id, revocation_trusted_floor_sha256, "
                        "issued_at_ms, expires_at_ms, key_id, "
                        "document_json, signature_ed25519) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            cap.capability_sha256,
                            cap.capability_id,
                            cap.owner_path_discriminator,
                            cap.revocation_registry_id,
                            cap.revocation_trusted_floor_sha256,
                            cap.issued_at_ms,
                            cap.expires_at_ms,
                            cap.key_id,
                            doc_bytes,
                            cap.signature_ed25519,
                        ),
                    )
                    connection.execute("COMMIT")
                    return FixtureCapabilityResultV1(
                        applied=True,
                        replayed=False,
                        owner_path_discriminator=owner_path_discriminator,
                        capability_id=cap.capability_id,
                        capability_sha256=cap.capability_sha256,
                        revocation_registry_id=cap.revocation_registry_id,
                        revocation_trusted_floor_sha256=cap.revocation_trusted_floor_sha256,
                        expires_at_ms=cap.expires_at_ms,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    # -----------------------------------------------------------------------
    # Revocation head CAS
    # -----------------------------------------------------------------------

    def append_fixture_provider_revocation(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        command: FixtureProviderRevocationAppendV1,
        now_ms: int,
    ) -> FixtureHeadResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            head = command.signed_successor
            if head.owner_path_discriminator != owner_path_discriminator:
                raise ValueError("owner mismatch")
            if head.registry_id != command.registry_id:
                raise ValueError("registry mismatch")
            if head.epoch >= MAX_HEADS_PER_CHAIN:
                raise ValueError("revocation epoch bound")
            verify_revocation_head(head, verification_keys=self._revocation_verification_keys)
            if not _issued_at_is_current(issued_at_ms=head.issued_at_ms, now_ms=now_ms):
                raise ValueError("revocation issuance window")
            doc_bytes = _canonical_model_json(head)
            revoked_json = json.dumps(
                sorted(head.revoked_capability_sha256s),
                separators=(",", ":"),
            ).encode()
            _require_bounded_bytes(doc_bytes, bound=MAX_DOCUMENT_BYTES)
            _require_bounded_bytes(revoked_json, bound=MAX_REVOCATION_SET_BYTES, allow_empty=True)
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    _audit_authority_chains(
                        connection,
                        revocation_floor_pins=self._revocation_floor_pins,
                        source_floor_pins=self._source_floor_pins,
                        revocation_verification_keys=self._revocation_verification_keys,
                        source_verification_keys=self._source_verification_keys,
                    )
                    # Verify current
                    current = connection.execute(
                        "SELECT c.head_sha256, c.epoch, c.state_version, "
                        "h.issued_at_ms, h.revoked_capability_hashes_json "
                        "FROM provider_revocation_current AS c "
                        "JOIN provider_revocation_heads AS h "
                        "ON h.registry_id=c.registry_id "
                        "AND h.owner_path_discriminator=c.owner_path_discriminator "
                        "AND h.head_sha256=c.head_sha256 "
                        "AND h.epoch=c.epoch "
                        "WHERE c.registry_id=? AND c.owner_path_discriminator=?",
                        (command.registry_id, owner_path_discriminator),
                    ).fetchone()
                    if current is None:
                        raise ValueError("no current revocation head")
                    if (
                        current[0] != command.expected_current_head_sha256
                        or current[1] != command.expected_current_epoch
                        or current[2] != command.expected_state_version
                    ):
                        raise ValueError("current mismatch")
                    # Verify predecessor
                    if head.epoch != command.expected_current_epoch + 1:
                        raise ValueError("epoch must be exactly +1")
                    if head.predecessor_head_sha256 != command.expected_current_head_sha256:
                        raise ValueError("predecessor mismatch")
                    if head.epoch <= 0 and head.predecessor_head_sha256 is not None:
                        raise ValueError
                    if head.epoch > 0 and head.predecessor_head_sha256 is None:
                        raise ValueError
                    previous_revoked = tuple(json.loads(bytes(current[4]).decode("utf-8")))
                    if (
                        any(
                            type(item) is not str or _HEX64.fullmatch(item) is None
                            for item in previous_revoked
                        )
                        or tuple(sorted(previous_revoked)) != previous_revoked
                        or len(set(previous_revoked)) != len(previous_revoked)
                    ):
                        raise ValueError("corrupt predecessor revocation set")
                    previous_set = set(previous_revoked)
                    next_set = set(head.revoked_capability_sha256s)
                    additions = next_set - previous_set
                    if (
                        not previous_set.issubset(next_set)
                        or len(additions) > MAX_REVOKED_PER_HEAD
                        or tuple(sorted(next_set)) != head.revoked_capability_sha256s
                        or head.issued_at_ms <= current[3]
                    ):
                        raise ValueError("invalid cumulative revocation successor")
                    if len(next_set) > MAX_CUMULATIVE_REVOKED:
                        raise ValueError("revocation set bound")
                    if additions:
                        known = {
                            str(row[0])
                            for row in connection.execute(
                                "SELECT capability_sha256 FROM provider_capabilities_v4 "
                                "WHERE owner_path_discriminator=? "
                                "AND revocation_registry_id=? LIMIT ?",
                                (
                                    owner_path_discriminator,
                                    command.registry_id,
                                    MAX_MUTABLE_CURRENT_ROWS + 1,
                                ),
                            ).fetchall()
                        }
                        if len(known) > MAX_MUTABLE_CURRENT_ROWS:
                            raise ValueError("capability membership scan bound")
                        if not additions.issubset(known):
                            raise ValueError("unknown revoked capability")
                    # Insert head
                    connection.execute(
                        "INSERT INTO provider_revocation_heads "
                        "(head_sha256, registry_id, owner_path_discriminator, epoch, "
                        "predecessor_head_sha256, issued_at_ms, "
                        "revoked_capability_hashes_json, key_id, "
                        "document_json, signature_ed25519) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            head.head_sha256,
                            head.registry_id,
                            head.owner_path_discriminator,
                            head.epoch,
                            head.predecessor_head_sha256,
                            head.issued_at_ms,
                            revoked_json,
                            head.key_id,
                            doc_bytes,
                            head.signature_ed25519,
                        ),
                    )
                    # Update current
                    next_sv = command.expected_state_version + 1
                    connection.execute(
                        "UPDATE provider_revocation_current "
                        "SET head_sha256=?, epoch=?, state_version=?, updated_at_ms=? "
                        "WHERE registry_id=? AND owner_path_discriminator=?",
                        (
                            head.head_sha256,
                            head.epoch,
                            next_sv,
                            now_ms,
                            command.registry_id,
                            owner_path_discriminator,
                        ),
                    )
                    connection.execute("COMMIT")
                    return FixtureHeadResultV1(
                        applied=True,
                        replayed=False,
                        head_kind="provider_revocation",
                        owner_path_discriminator=owner_path_discriminator,
                        registry_id=command.registry_id,
                        current_head_sha256=head.head_sha256,
                        current_epoch=head.epoch,
                        state_version=next_sv,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    # -----------------------------------------------------------------------
    # Source bundle + head append
    # -----------------------------------------------------------------------

    def mint_pending_fixture_source_bundle(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        registry_id: str,
        expected_current_head_sha256: str,
        expected_current_epoch: int,
        expected_state_version: int,
        now_ms: int,
    ) -> PendingUnifiedSourceBundleHandleV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            with self._lock, closing(self._connect()) as connection:
                current = connection.execute(
                    "SELECT head_sha256, epoch, state_version "
                    "FROM source_current "
                    "WHERE registry_id=? AND owner_path_discriminator=?",
                    (registry_id, owner_path_discriminator),
                ).fetchone()
                if current is None:
                    raise ValueError("no current source head")
                if (
                    current[0] != expected_current_head_sha256
                    or current[1] != expected_current_epoch
                    or current[2] != expected_state_version
                ):
                    raise ValueError("current mismatch")
                # Check handle count
                if len(self._active_handles) >= MAX_ACTIVE_HANDLES:
                    raise ValueError("too many active handles")
                # Generate handle with collision retry
                for _ in range(COLLISION_RETRIES):
                    handle_id = "mphs1_" + secrets.token_hex(32)
                    selector = "opsbs1_" + secrets.token_hex(32)
                    active_selector_collision = any(
                        not live_handle.consumed
                        and live_handle.expires_at_ms > now_ms
                        and live_handle.opaque_source_bundle_id == selector
                        for live_handle in self._active_handles.values()
                    )
                    if (
                        handle_id not in self._active_handles
                        and not active_selector_collision
                        and not self._selector_exists(connection, selector)
                    ):
                        break
                else:
                    raise ValueError("selector collision exhaustion")
                expires_at = now_ms + PENDING_HANDLE_TTL_MS
                mac_data = _canonical_json(
                    {
                        "schema_version": 1,
                        "handle_id": handle_id,
                        "opaque_source_bundle_id": selector,
                        "store_id": self.store_id,
                        "owner_path_discriminator": owner_path_discriminator,
                        "registry_id": registry_id,
                        "expected_current_head_sha256": expected_current_head_sha256,
                        "expected_current_epoch": expected_current_epoch,
                        "expected_state_version": expected_state_version,
                        "created_at_ms": now_ms,
                        "expires_at_ms": expires_at,
                        "creator_pid": self._pid,
                        "boot_nonce": self._boot_nonce.hex(),
                        "authority_object_identity": id(owner_path_authority),
                    }
                )
                mac = hmac.digest(
                    self._pending_key,
                    _PENDING_SOURCE_DOMAIN + mac_data,
                    "sha256",
                )
                handle = PendingUnifiedSourceBundleHandleV1(
                    _PENDING_HANDLE_CONSTRUCTOR,
                    schema_version=1,
                    handle_id=handle_id,
                    opaque_source_bundle_id=selector,
                    store_id=self.store_id,
                    owner_path_discriminator=owner_path_discriminator,
                    registry_id=registry_id,
                    expected_current_head_sha256=expected_current_head_sha256,
                    expected_current_epoch=expected_current_epoch,
                    expected_state_version=expected_state_version,
                    created_at_ms=now_ms,
                    expires_at_ms=expires_at,
                    creator_pid=self._pid,
                    boot_nonce=self._boot_nonce,
                    authority_object_identity=id(owner_path_authority),
                    pending_mac=mac,
                )
                self._active_handles[handle_id] = handle
                return handle
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def append_fixture_source_bundle_and_head(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        command: FixtureSourceBundleAndHeadAppendV1,
        now_ms: int,
    ) -> FixtureHeadResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if not _valid_i63(now_ms):
                raise ValueError
            self._require_fixture_writer_authority()
            handle = command.pending_source_bundle_handle
            if not isinstance(handle, PendingUnifiedSourceBundleHandleV1):
                raise ValueError("invalid handle type")
            if handle.consumed:
                raise ValueError("handle already consumed")
            if handle.creator_pid != os.getpid() or handle.creator_pid != self._pid:
                raise ValueError("handle process mismatch")
            if handle.boot_nonce != self._boot_nonce:
                raise ValueError("handle boot mismatch")
            if handle.authority_object_identity != id(owner_path_authority):
                raise ValueError("handle authority mismatch")
            if handle.store_id != self.store_id:
                raise ValueError("handle store mismatch")
            if self._active_handles.get(handle.handle_id) is not handle:
                raise ValueError("handle not active")
            mac_data = _canonical_json(
                {
                    "schema_version": handle.schema_version,
                    "handle_id": handle.handle_id,
                    "opaque_source_bundle_id": handle.opaque_source_bundle_id,
                    "store_id": handle.store_id,
                    "owner_path_discriminator": handle.owner_path_discriminator,
                    "registry_id": handle.registry_id,
                    "expected_current_head_sha256": handle.expected_current_head_sha256,
                    "expected_current_epoch": handle.expected_current_epoch,
                    "expected_state_version": handle.expected_state_version,
                    "created_at_ms": handle.created_at_ms,
                    "expires_at_ms": handle.expires_at_ms,
                    "creator_pid": handle.creator_pid,
                    "boot_nonce": handle.boot_nonce.hex(),
                    "authority_object_identity": handle.authority_object_identity,
                }
            )
            expected_mac = hmac.digest(
                self._pending_key, _PENDING_SOURCE_DOMAIN + mac_data, "sha256"
            )
            if not hmac.compare_digest(handle.pending_mac, expected_mac):
                raise ValueError("handle mac mismatch")
            successor = command.signed_successor
            bundle = command.exact_bundle
            if type(bundle) is not OwnerPrivateEncryptedSourceBundleV1:
                raise ValueError("invalid source bundle type")
            OwnerPrivateEncryptedSourceBundleV1.model_validate(bundle.model_dump(mode="python"))
            if successor.owner_path_discriminator != owner_path_discriminator:
                raise ValueError("owner mismatch")
            if successor.registry_id != command.registry_id:
                raise ValueError("registry mismatch")
            verify_source_head(successor, verification_keys=self._source_verification_keys)
            if not _issued_at_is_current(issued_at_ms=successor.issued_at_ms, now_ms=now_ms):
                raise ValueError("source issuance window")
            plaintext = bundle.model_dump_json().encode("utf-8")
            _require_bounded_bytes(plaintext, bound=MAX_SOURCE_PLAINTEXT_BYTES)
            head_doc_bytes = _canonical_model_json(successor)
            active_revisions_json = _canonical_json(
                [
                    item.model_dump(mode="json")
                    for item in successor.snapshot.active_bundle_revisions
                ]
            )
            snapshot_json = _canonical_json(successor.snapshot.model_dump(mode="json"))
            _require_bounded_bytes(head_doc_bytes, bound=MAX_DOCUMENT_BYTES)
            _require_bounded_bytes(
                active_revisions_json, bound=MAX_REVISION_SET_BYTES, allow_empty=True
            )
            _require_bounded_bytes(snapshot_json, bound=MAX_DOCUMENT_BYTES)

            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    _audit_authority_chains(
                        connection,
                        revocation_floor_pins=self._revocation_floor_pins,
                        source_floor_pins=self._source_floor_pins,
                        revocation_verification_keys=self._revocation_verification_keys,
                        source_verification_keys=self._source_verification_keys,
                    )
                    # Re-verify handle
                    if handle.consumed:
                        raise ValueError("handle consumed concurrently")
                    if now_ms >= handle.expires_at_ms:
                        raise ValueError("handle expired")
                    # Verify current source
                    current = connection.execute(
                        "SELECT head_sha256, epoch, state_version "
                        "FROM source_current "
                        "WHERE registry_id=? AND owner_path_discriminator=?",
                        (command.registry_id, owner_path_discriminator),
                    ).fetchone()
                    if current is None:
                        raise ValueError("no current source head")
                    if (
                        current[0] != command.expected_current_head_sha256
                        or current[1] != command.expected_current_epoch
                        or current[2] != command.expected_state_version
                    ):
                        raise ValueError("current mismatch")
                    if current[0] != handle.expected_current_head_sha256:
                        raise ValueError("handle head mismatch")
                    if current[1] != handle.expected_current_epoch:
                        raise ValueError("handle epoch mismatch")
                    if current[2] != handle.expected_state_version:
                        raise ValueError("handle state_version mismatch")
                    # Verify successor
                    if successor.epoch != command.expected_current_epoch + 1:
                        raise ValueError("epoch must be +1")
                    if successor.previous_head_sha256 != command.expected_current_head_sha256:
                        raise ValueError("predecessor mismatch")
                    predecessor_snapshot = connection.execute(
                        "SELECT active_bundle_revisions_json, issued_at_ms FROM source_heads "
                        "WHERE registry_id=? AND owner_path_discriminator=? "
                        "AND head_sha256=? AND epoch=?",
                        (
                            command.registry_id,
                            owner_path_discriminator,
                            command.expected_current_head_sha256,
                            command.expected_current_epoch,
                        ),
                    ).fetchone()
                    if predecessor_snapshot is None:
                        raise ValueError("predecessor head not found")
                    if successor.issued_at_ms <= predecessor_snapshot[1]:
                        raise ValueError("successor source time must increase")
                    predecessor_active = tuple(
                        OpaqueSourceBundleRevisionV1.model_validate(item)
                        for item in json.loads(bytes(predecessor_snapshot[0]).decode("utf-8"))
                    )
                    expected_new_revision = OpaqueSourceBundleRevisionV1(
                        opaque_source_bundle_id=handle.opaque_source_bundle_id
                    )
                    expected_active = tuple(
                        sorted(
                            (*predecessor_active, expected_new_revision),
                            key=lambda item: item.opaque_source_bundle_id,
                        )
                    )
                    if (
                        successor.snapshot.registry_id != command.registry_id
                        or successor.snapshot.owner_path_discriminator != owner_path_discriminator
                        or successor.snapshot.epoch != successor.epoch
                        or successor.snapshot.issued_at_ms != successor.issued_at_ms
                        or successor.snapshot.tombstoned_bundle_ids != ()
                        or successor.snapshot.active_bundle_revisions != expected_active
                        or len(expected_active) > MAX_ACTIVE_REVISIONS
                    ):
                        raise ValueError("successor source roster mismatch")
                    _require_insert_capacity(
                        connection,
                        table_name="encrypted_source_bundles",
                        bound=MAX_MUTABLE_CURRENT_ROWS,
                    )
                    # Consume handle
                    object.__setattr__(handle, "consumed", True)
                    self._active_handles.pop(handle.handle_id, None)
                    bundle_id = handle.opaque_source_bundle_id
                    source_key_version = command.key_version
                    ciphertext_length = len(plaintext) + 16
                    if ciphertext_length > MAX_CIPHERTEXT_BYTES:
                        raise ValueError("source bundle ciphertext bound")
                    metadata = {
                        "schema_version": 1,
                        "opaque_source_bundle_id": bundle_id,
                        "owner_path_discriminator": owner_path_discriminator,
                        "categorical_state": "sealed",
                        "aead_suite": "aes-256-gcm",
                        "key_version": source_key_version,
                        "nonce_length": 12,
                        "ciphertext_schema": "owner_private_encrypted_source_bundle_v1_json",
                        "ciphertext_type": "application/json",
                        "ciphertext_length": ciphertext_length,
                        "row_revision": 1,
                    }
                    aad = _SOURCE_AEAD_DOMAIN + _canonical_json(metadata)
                    used_nonces = {
                        bytes(row[0])
                        for row in connection.execute(
                            "SELECT nonce FROM encrypted_source_bundles "
                            "WHERE owner_path_discriminator=? AND key_version=? LIMIT ?",
                            (
                                owner_path_discriminator,
                                source_key_version,
                                MAX_MUTABLE_CURRENT_ROWS + 1,
                            ),
                        ).fetchall()
                    }
                    if len(used_nonces) > MAX_MUTABLE_CURRENT_ROWS:
                        raise ValueError("source nonce scan bound")
                    nonce = None
                    for _ in range(NONCE_COLLISION_RETRIES):
                        candidate_nonce = secrets.token_bytes(12)
                        if candidate_nonce not in used_nonces:
                            nonce = candidate_nonce
                            break
                    if nonce is None:
                        raise ValueError("nonce collision exhaustion")
                    with self._source_key_provider.open_aes256gcm_key(
                        owner_path_authority=owner_path_authority,
                        owner_path_discriminator=owner_path_discriminator,
                        key_version=source_key_version,
                    ) as source_key:
                        if type(source_key) is not bytearray or len(source_key) != 32:
                            raise ValueError("invalid source key")
                        try:
                            ciphertext = AESGCM(bytes(source_key)).encrypt(nonce, plaintext, aad)
                        finally:
                            source_key[:] = b"\x00" * len(source_key)
                    if len(ciphertext) != ciphertext_length:
                        raise ValueError("source ciphertext length mismatch")
                    aad_json = _canonical_json(
                        {
                            "schema_version": 1,
                            "opaque_source_bundle_id": bundle_id,
                            "owner_path_discriminator": owner_path_discriminator,
                            "categorical_state": "sealed",
                            "aead_suite": "aes-256-gcm",
                            "key_version": source_key_version,
                            "nonce_length": 12,
                            "ciphertext_schema": "owner_private_encrypted_source_bundle_v1_json",
                            "ciphertext_type": "application/json",
                            "ciphertext_length": ciphertext_length,
                            "row_revision": 1,
                        }
                    )
                    connection.execute(
                        "INSERT INTO encrypted_source_bundles "
                        "(opaque_source_bundle_id, owner_path_discriminator, state, "
                        "row_version, aead_suite, key_version, nonce_length, nonce, "
                        "aad_schema, aad_json, ciphertext_schema, ciphertext_type, "
                        "ciphertext_length, ciphertext) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            bundle_id,
                            owner_path_discriminator,
                            "sealed",
                            1,
                            "aes-256-gcm",
                            source_key_version,
                            12,
                            nonce,
                            "owner_private_source_aad_v1",
                            aad_json,
                            "owner_private_encrypted_source_bundle_v1_json",
                            "application/json",
                            ciphertext_length,
                            ciphertext,
                        ),
                    )
                    # Append source head
                    connection.execute(
                        "INSERT INTO source_heads "
                        "(head_sha256, registry_id, owner_path_discriminator, epoch, "
                        "previous_head_sha256, issued_at_ms, "
                        "active_bundle_revisions_json, snapshot_json, "
                        "key_id, document_json, signature_ed25519) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            successor.head_sha256,
                            successor.registry_id,
                            successor.owner_path_discriminator,
                            successor.epoch,
                            successor.previous_head_sha256,
                            successor.issued_at_ms,
                            active_revisions_json,
                            snapshot_json,
                            successor.key_id,
                            head_doc_bytes,
                            successor.signature_ed25519,
                        ),
                    )
                    # Update source current
                    next_sv = command.expected_state_version + 1
                    connection.execute(
                        "UPDATE source_current "
                        "SET head_sha256=?, epoch=?, state_version=?, updated_at_ms=? "
                        "WHERE registry_id=? AND owner_path_discriminator=?",
                        (
                            successor.head_sha256,
                            successor.epoch,
                            next_sv,
                            now_ms,
                            command.registry_id,
                            owner_path_discriminator,
                        ),
                    )
                    connection.execute("COMMIT")
                    return FixtureHeadResultV1(
                        applied=True,
                        replayed=False,
                        head_kind="source",
                        owner_path_discriminator=owner_path_discriminator,
                        registry_id=command.registry_id,
                        current_head_sha256=successor.head_sha256,
                        current_epoch=successor.epoch,
                        state_version=next_sv,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    # -----------------------------------------------------------------------
    # Fail-closed stubs for 34B/C/D
    # -----------------------------------------------------------------------

    def admit_quarantined_effect(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        candidate: UnifiedPaidAdmissionCandidateV1,
        now_ms: int,
    ) -> QuarantinedPaidAdmissionResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if type(candidate) is not UnifiedPaidAdmissionCandidateV1 or not _valid_i63(now_ms):
                raise ValueError
            raise ValueError
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def transition_quarantined_effect(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        command: Any,
        now_ms: int,
    ) -> QuarantinedEffectTransitionResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if command is None or not _valid_i63(now_ms):
                raise ValueError
            raise ValueError
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def backup_to(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        destination: Path,
        destination_mode: Literal[0o600],
        expected_store_id: str,
        expected_migration_epoch: Literal[1],
        expected_cutover_marker_sha256: str,
        now_ms: int,
    ) -> QuarantinedBackupResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            self._authenticate_owner(owner_path_authority, owner_path_discriminator)
            if (
                not isinstance(destination, Path)
                or destination_mode != 0o600
                or expected_store_id != self.store_id
                or expected_migration_epoch != 1
                or not _HEX64.fullmatch(expected_cutover_marker_sha256)
                or not _valid_i63(now_ms)
            ):
                raise ValueError
            raise ValueError
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def create_empty_checkpoint_root(self, *, now_ms: int) -> QuarantinedPrecutoverHandleV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        try:
            if self.open_mode != "create_epoch0" or not _valid_i63(now_ms):
                raise ValueError
            with self._lock, self._connect() as connection:
                if self._migration_root_handle is not None:
                    raise ValueError("precutover handle already issued")
                row = connection.execute(
                    "SELECT schema_version,migration_epoch,cutover_marker_sha256 "
                    "FROM paid_lane_schema WHERE singleton=1"
                ).fetchone()
                if row != (1, 0, None):
                    raise ValueError
                counts = connection.execute(
                    "SELECT COUNT(*) FROM migration_cutover_proof"
                ).fetchone()
                if counts != (0,):
                    raise ValueError
                handle = cast(
                    QuarantinedPrecutoverHandleV1,
                    _issue_process_handle(
                        QuarantinedPrecutoverHandleV1,
                        {
                            "_consumed": False,
                            "_process_id": os.getpid(),
                            "_boot_nonce": self._boot_nonce,
                            "store_id": self.store_id,
                            "created_at_ms": now_ms,
                        },
                    ),
                )
                object.__setattr__(self, "_migration_root_handle", handle)
                object.__setattr__(self, "_construction_mac", self._compute_construction_mac())
                return handle
        except Exception:
            raise PrivatePaidLaneEligibilityCheckpointRejected() from None

    def seal_frozen_fixture_corpus(
        self,
        precutover_handle: QuarantinedPrecutoverHandleV1,
        synthetic_legacy_root: object,
        synthetic_writer_barrier: object,
        now_ms: int,
    ) -> tuple[QuarantinedMigrationSealResultV1, QuarantinedSealedCorpusHandleV1]:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        del precutover_handle, synthetic_legacy_root, synthetic_writer_barrier, now_ms
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    def copy_sealed_fixture_corpus(
        self,
        precutover_handle: QuarantinedPrecutoverHandleV1,
        sealed_corpus_handle: QuarantinedSealedCorpusHandleV1,
        now_ms: int,
    ) -> tuple[QuarantinedMigrationCopyResultV1, QuarantinedCopiedCorpusHandleV1]:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        del precutover_handle, sealed_corpus_handle, now_ms
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    def abort_uncut_checkpoint_root(
        self,
        precutover_handle: QuarantinedPrecutoverHandleV1,
        migration_handle: QuarantinedSealedCorpusHandleV1 | QuarantinedCopiedCorpusHandleV1 | None,
        synthetic_writer_barrier: object | None,
        now_ms: int,
    ) -> QuarantinedAbortUncutResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        del precutover_handle, migration_handle, synthetic_writer_barrier, now_ms
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    def recover_and_abort_uncut_checkpoint_root_after_restart(
        self, *args: object, **kwargs: object
    ) -> QuarantinedAbortUncutResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    def commit_fixture_cutover(self, *args: object, **kwargs: object) -> QuarantinedCutoverResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    def resume_fixture_cutover_forward_only(
        self, *args: object, **kwargs: object
    ) -> QuarantinedForwardRecoveryResultV1:
        PrivatePaidLaneEligibilityCheckpointStoreV1._validate_exact_open_instance(self)
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _authenticate_owner(self, authority: object, discriminator: str) -> None:
        with self._owner_key_provider.authenticate_owner_path(
            owner_path_authority=authority,
            owner_path_discriminator=discriminator,
        ):
            pass
        if discriminator != self.owner_path_discriminator:
            raise ValueError("owner discriminator mismatch")

    def _require_fixture_writer_authority(self) -> None:
        raise PrivatePaidLaneEligibilityCheckpointRejected()

    def _blind_v1(
        self,
        purpose: _BLIND_PURPOSES,
        parts: tuple[bytes, ...],
        *,
        authority: object,
        discriminator: str,
    ) -> bytes:
        if type(purpose) is not str or purpose not in _BLIND_DOMAINS or type(parts) is not tuple:
            raise ValueError("invalid blind input")
        for part in parts:
            if type(part) is not bytes or len(part) > 2**32 - 1:
                raise ValueError("invalid blind part")
        with self._owner_key_provider.open_hmac_sha256_key(
            owner_path_authority=authority,
            owner_path_discriminator=discriminator,
            purpose=purpose,
        ) as key:
            if type(key) is not bytearray or len(key) != 32:
                raise ValueError("invalid hmac key")
            key_fingerprint = hmac.digest(self._pending_key, bytes(key), "sha256")
            with self._lock:
                observed_purpose = self._observed_hmac_keys.get(key_fingerprint)
                if observed_purpose is not None and observed_purpose != purpose:
                    key[:] = b"\x00" * len(key)
                    raise ValueError("shared hmac key")
                self._observed_hmac_keys[key_fingerprint] = purpose
            msg = bytearray(_BLIND_DOMAINS[purpose])
            for part in parts:
                msg.extend(_u32be(len(part)))
                msg.extend(part)
            try:
                return hmac.new(bytes(key), bytes(msg), hashlib.sha256).digest()
            finally:
                key[:] = b"\x00" * len(key)
                msg[:] = b"\x00" * len(msg)

    def _blind_consent(
        self,
        authority: object,
        discriminator: str,
        receipt_material: bytes,
        config_material: bytes,
    ) -> bytes:
        return self._blind_v1(
            "consent_v1",
            (receipt_material, config_material),
            authority=authority,
            discriminator=discriminator,
        )

    def _blind_cursor(
        self,
        authority: object,
        discriminator: str,
        queue_operation_id: str,
        cursor_material: bytes,
    ) -> bytes:
        return self._blind_v1(
            "cursor_v1",
            (queue_operation_id.encode("utf-8"), cursor_material),
            authority=authority,
            discriminator=discriminator,
        )

    def _blind_account(
        self,
        authority: object,
        discriminator: str,
        account_material: bytes,
    ) -> bytes:
        return self._blind_v1(
            "account_v1", (account_material,), authority=authority, discriminator=discriminator
        )

    def _blind_project(
        self,
        authority: object,
        discriminator: str,
        project_material: bytes,
    ) -> bytes:
        return self._blind_v1(
            "project_v1", (project_material,), authority=authority, discriminator=discriminator
        )

    def _blind_request(
        self, authority: object, discriminator: str, request_material: bytes
    ) -> bytes:
        return self._blind_v1(
            "request_v1", (request_material,), authority=authority, discriminator=discriminator
        )

    def _blind_idempotency(
        self,
        authority: object,
        discriminator: str,
        provider: str,
        model: str,
        route: str,
        provider_idempotency_material: bytes,
    ) -> bytes:
        return self._blind_v1(
            "idempotency_v1",
            (
                provider.encode("utf-8"),
                model.encode("utf-8"),
                route.encode("utf-8"),
                provider_idempotency_material,
            ),
            authority=authority,
            discriminator=discriminator,
        )

    def _blind_effect(
        self,
        authority: object,
        discriminator: str,
        operation_id: str,
        job_id: str,
        execution_id: str,
        stage_id: str,
        router_role: str,
        provider: str,
        model: str,
        route: str,
        request_material: bytes,
    ) -> bytes:
        return self._blind_v1(
            "effect_v1",
            (
                discriminator.encode("utf-8"),
                operation_id.encode("utf-8"),
                job_id.encode("utf-8"),
                execution_id.encode("utf-8"),
                stage_id.encode("utf-8"),
                router_role.encode("utf-8"),
                provider.encode("utf-8"),
                model.encode("utf-8"),
                route.encode("utf-8"),
                request_material,
            ),
            authority=authority,
            discriminator=discriminator,
        )

    def _blind_test_claim(
        self,
        authority: object,
        discriminator: str,
        receipt_material: bytes,
        config_material: bytes,
        effect_material: bytes,
    ) -> bytes:
        return self._blind_v1(
            "test_claim_v1",
            (receipt_material, config_material, effect_material),
            authority=authority,
            discriminator=discriminator,
        )

    def _selector_exists(self, connection: sqlite3.Connection, selector: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM encrypted_source_bundles WHERE opaque_source_bundle_id=? LIMIT 1",
            (selector,),
        ).fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------


def verify_capability_v4(
    cap: SignedProviderCapabilityV4FixtureV1,
    *,
    verification_keys: Mapping[str, bytes],
) -> None:
    keys = _copy_keyring(verification_keys)
    key = keys.get(cap.key_id)
    if key is None:
        raise PrivatePaidLaneEligibilityCheckpointRejected()
    Ed25519PublicKey.from_public_bytes(key).verify(
        bytes.fromhex(cap.signature_ed25519),
        _CAPABILITY_V4_SIGNATURE_DOMAIN + bytes.fromhex(cap.capability_sha256),
    )


def verify_revocation_head(
    head: SignedProviderRevocationHeadFixtureV1,
    *,
    verification_keys: Mapping[str, bytes],
) -> None:
    keys = _copy_keyring(verification_keys)
    key = keys.get(head.key_id)
    if key is None:
        raise PrivatePaidLaneEligibilityCheckpointRejected()
    Ed25519PublicKey.from_public_bytes(key).verify(
        bytes.fromhex(head.signature_ed25519),
        _REVOCATION_SIGNATURE_DOMAIN + bytes.fromhex(head.head_sha256),
    )


def verify_source_head(
    head: SignedSourceHeadFixtureV1,
    *,
    verification_keys: Mapping[str, bytes],
) -> None:
    keys = _copy_keyring(verification_keys)
    key = keys.get(head.key_id)
    if key is None:
        raise PrivatePaidLaneEligibilityCheckpointRejected()
    Ed25519PublicKey.from_public_bytes(key).verify(
        bytes.fromhex(head.signature_ed25519),
        _SOURCE_SIGNATURE_DOMAIN + bytes.fromhex(head.head_sha256),
    )


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _reject_symlinked_ancestors(path: Path) -> None:
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("symlinked ancestor")


def _validate_secure_durable_path(path: Path, *, require_exists: bool) -> None:
    _reject_symlinked_ancestors(path)
    uid = os.getuid()
    parent_stat = path.parent.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(parent_stat.st_mode)
        or parent_stat.st_uid != uid
        or stat.S_IMODE(parent_stat.st_mode) != 0o700
    ):
        raise ValueError("invalid parent permissions")
    if not path.exists():
        if require_exists:
            raise ValueError("path does not exist")
        return
    file_stat = path.stat(follow_symlinks=False)
    if (
        not stat.S_ISREG(file_stat.st_mode)
        or file_stat.st_uid != uid
        or stat.S_IMODE(file_stat.st_mode) != 0o600
        or file_stat.st_nlink != 1
    ):
        raise ValueError("invalid file permissions")


def _chmod_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists():
            os.chmod(sidecar, 0o600)


# ---------------------------------------------------------------------------
# Semantic and contract identity computation
# ---------------------------------------------------------------------------


def compute_private_paid_lane_semantic_sha256() -> str:
    """Compute semantic identity by AST-hashing the module, excluding identity assignments."""
    source_file = inspect.getfile(PrivatePaidLaneEligibilityCheckpointStoreV1)
    with open(source_file, encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=source_file)

    # Collect all module-level assignments, excluding identity hash assignments
    excluded_names = {
        "PRIVATE_PAID_LANE_CHECKPOINT_SEMANTIC_SHA256_V1",
        "PRIVATE_PAID_LANE_CHECKPOINT_CONTRACT_SHA256_V1",
    }
    parts: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in excluded_names:
                    continue
            parts.append(ast.dump(node))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in excluded_names:
                continue
            parts.append(ast.dump(node))
        elif isinstance(
            node,
            (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            parts.append(ast.dump(node))

    combined = "\n".join(parts)
    return hashlib.sha256(_SEMANTIC_SOURCE_DOMAIN + combined.encode("utf-8")).hexdigest()


def compute_private_paid_lane_contract_sha256(
    *,
    semantic_sha256: str,
    sql: str,
    predecessor_cycle33_contract: str | None,
    predecessor_cycle32_source: str | None,
    predecessor_cycle30_capability: str | None,
) -> str:
    """Compute contract identity binding semantic hash + SQL + domains + bounds + literals."""
    result_models = (
        FixtureOwnerOperationResultV1,
        FixtureConsentResultV1,
        FixtureQueueLeaseResultV1,
        FixtureBudgetResultV1,
        FixtureCapabilityResultV1,
        FixtureHeadResultV1,
        QuarantinedPaidAdmissionResultV1,
        QuarantinedEffectTransitionResultV1,
        QuarantinedBackupResultV1,
        QuarantinedMigrationSealResultV1,
        QuarantinedMigrationCopyResultV1,
        QuarantinedAbortUncutResultV1,
        QuarantinedCutoverResultV1,
        QuarantinedForwardRecoveryResultV1,
    )
    command_models = (
        FixtureOwnerOperationPutV1,
        FixtureOwnerOperationAdvanceV1,
        FixtureOwnerOperationCancelV1,
        FixtureConsentPutV1,
        FixtureConsentWithdrawV1,
        FixtureConsentClaimForTestV1,
        FixtureQueueLeasePutV1,
        FixtureQueueLeaseTakeoverV1,
        FixtureQueueLeaseRenewV1,
        FixtureBudgetPutV1,
        FixtureBudgetMutateV1,
        FixtureProviderCapabilityPutV1,
        FixtureProviderRevocationAppendV1,
        FixtureSourceBundleAndHeadAppendV1,
    )
    public_method_names = (
        "open",
        "put_fixture_owner_operation",
        "advance_fixture_owner_operation",
        "cancel_fixture_owner_operation",
        "put_fixture_consent",
        "withdraw_fixture_consent",
        "claim_fixture_consent_for_test",
        "put_fixture_queue_lease",
        "takeover_fixture_queue_lease",
        "renew_fixture_queue_lease",
        "put_fixture_budget",
        "mutate_fixture_budget",
        "put_fixture_provider_capability_v4",
        "append_fixture_provider_revocation",
        "mint_pending_fixture_source_bundle",
        "append_fixture_source_bundle_and_head",
        "admit_quarantined_effect",
        "transition_quarantined_effect",
        "backup_to",
        "create_empty_checkpoint_root",
        "seal_frozen_fixture_corpus",
        "copy_sealed_fixture_corpus",
        "abort_uncut_checkpoint_root",
        "recover_and_abort_uncut_checkpoint_root_after_restart",
        "commit_fixture_cutover",
        "resume_fixture_cutover_forward_only",
    )
    contract_material = {
        "semantic_source_sha256": semantic_sha256,
        "schema_sql_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
        "schema_sql_compact": _compact_sql(sql),
        "schema_table_count": len(_EXPECTED_TABLE_SET),
        "schema_explicit_index_count": len(_EXPECTED_INDEX_SET),
        "schema_autoindex_count": len(_EXPECTED_AUTOINDEX_NAMES),
        "schema_tables": sorted(_EXPECTED_TABLE_SET),
        "schema_indexes": sorted(_EXPECTED_INDEX_SET),
        "schema_autoindexes": sorted(_EXPECTED_AUTOINDEX_NAMES),
        "predecessor_identities": {
            "cycle30_capability_contract_sha256": predecessor_cycle30_capability,
            "cycle31_authority_semantic_sha256": PRIVATE_SOURCE_AUTHORITY_MODULE_SOURCE_SHA256,
            "cycle31_vault_contract_sha256": OWNER_PRIVATE_SOURCE_VAULT_CONTRACT_V1_SHA256,
            "cycle32_head_semantic_sha256": PRIVATE_SOURCE_HEAD_STORE_MODULE_SOURCE_SHA256,
            "cycle32_bundle_semantic_sha256": PRIVATE_SOURCE_BUNDLE_STORE_MODULE_SOURCE_SHA256,
            "cycle32_exact_current_resolver_contract_sha256": (
                OWNER_PRIVATE_SOURCE_EXACT_CURRENT_RESOLVER_CONTRACT_SHA256
            ),
            "cycle32_source_argument_sha256": predecessor_cycle32_source,
            "cycle33_contract_sha256": predecessor_cycle33_contract,
            "cycle32_runtime_aliases": {
                "SignedSourceHeadFixtureV1": SignedSourceHeadFixtureV1.__qualname__,
                "OwnerPrivateSourceAuthoritySnapshotV1": (
                    OwnerPrivateSourceAuthoritySnapshotV1.__qualname__
                ),
                "OpaqueSourceBundleRevisionV1": OpaqueSourceBundleRevisionV1.__qualname__,
                "OwnerPrivateEncryptedSourceBundleV1": (
                    OwnerPrivateEncryptedSourceBundleV1.__qualname__
                ),
            },
            "cycle31_32_model_json_schemas": {
                "SignedSourceHeadFixtureV1": SignedSourceHeadFixtureV1.model_json_schema(),
                "OwnerPrivateSourceAuthoritySnapshotV1": (
                    OwnerPrivateSourceAuthoritySnapshotV1.model_json_schema()
                ),
                "OpaqueSourceBundleRevisionV1": OpaqueSourceBundleRevisionV1.model_json_schema(),
                "OwnerPrivateEncryptedSourceBundleV1": (
                    OwnerPrivateEncryptedSourceBundleV1.model_json_schema()
                ),
            },
        },
        "public_method_signatures": {
            name: str(inspect.signature(getattr(PrivatePaidLaneEligibilityCheckpointStoreV1, name)))
            for name in public_method_names
        },
        "provider_protocol_signatures": {
            "PrivatePaidLaneOwnerKeyProviderV1.authenticate_owner_path": str(
                inspect.signature(PrivatePaidLaneOwnerKeyProviderV1.authenticate_owner_path)
            ),
            "PrivatePaidLaneOwnerKeyProviderV1.open_hmac_sha256_key": str(
                inspect.signature(PrivatePaidLaneOwnerKeyProviderV1.open_hmac_sha256_key)
            ),
            "PrivatePaidLaneOwnerKeyProviderV1.open_aes256gcm_key": str(
                inspect.signature(PrivatePaidLaneOwnerKeyProviderV1.open_aes256gcm_key)
            ),
            "OwnerPrivateSourceKeyProviderV1.open_aes256gcm_key": str(
                inspect.signature(OwnerPrivateSourceKeyProviderV1.open_aes256gcm_key)
            ),
        },
        "result_model_json_schemas": {
            model.__name__: model.model_json_schema() for model in result_models
        },
        "command_model_json_schemas": {
            model.__name__: model.model_json_schema() for model in command_models
        },
        "cap_v4_document_domain": _CAPABILITY_V4_DOCUMENT_DOMAIN.decode(),
        "cap_v4_signature_domain": _CAPABILITY_V4_SIGNATURE_DOMAIN.decode(),
        "revocation_head_domain": _REVOCATION_HEAD_DOMAIN.decode(),
        "revocation_signature_domain": _REVOCATION_SIGNATURE_DOMAIN.decode(),
        "source_snapshot_domain": _SOURCE_SNAPSHOT_DOMAIN.decode(),
        "source_head_domain": _SOURCE_HEAD_DOMAIN.decode(),
        "source_signature_domain": _SOURCE_SIGNATURE_DOMAIN.decode(),
        "source_aead_domain": _SOURCE_AEAD_DOMAIN.decode(),
        "candidate_aes_domain": _CANDIDATE_AES_DOMAIN.decode(),
        "evidence_aes_domain": _EVIDENCE_AES_DOMAIN.decode(),
        "pending_source_domain": _PENDING_SOURCE_DOMAIN.decode(),
        "blind_domains": {k: v.decode() for k, v in _BLIND_DOMAINS.items()},
        "open_modes": (
            "create_epoch0",
            "precutover_epoch0",
            "pinned_epoch1",
            "forward_recovery_epoch1",
        ),
        "construction_policy": dict(CONSTRUCTION_POLICY_V1),
        "predecessor_runtime_attestations": (
            "require_private_source_authority_module_source",
            "require_private_source_head_store_module_source",
            "require_private_source_bundle_store_module_source",
            "open-and-every-authority-connection-before-read",
        ),
        "bounded_34a_tables": dict(_BOUNDED_34A_TABLES),
        "replay_policy": (
            "exact-put-and-capability-replay-only",
            "cas-successors-fail-closed-without-original-command-history",
            "source-consumed-handle-never-retries",
        ),
        "mutation_algebra": (
            "initial-operation-state-version-1",
            "initial-queue-row-version-1",
            "initial-budget-row-version-1",
            "consent-withdraw-expected-plus-one",
            "queue-takeover-generation-expected-plus-one",
            "budget-mutate-row-version-expected-plus-one",
            "revocation-epoch-current-plus-one",
            "source-epoch-current-plus-one",
            "signed-issued-minus-60000-le-now-le-issued-plus-300000",
        ),
        "bounds": {
            "max_i63": MAX_I63,
            "max_cents": MAX_CENTS,
            "max_db_bytes": MAX_DB_BYTES,
            "max_db_pages": MAX_DB_PAGES,
            "max_plaintext_bytes": MAX_PLAINTEXT_BYTES,
            "max_ciphertext_bytes": MAX_CIPHERTEXT_BYTES,
            "max_receipt_pairs": MAX_RECEIPT_PAIRS,
            "max_head_chain": MAX_HEAD_CHAIN,
            "max_pending_selectors": MAX_PENDING_SELECTORS,
            "max_active_bundles": MAX_ACTIVE_BUNDLES,
            "pending_ttl_ms": PENDING_TTL_MS,
            "nonce_collision_retries": NONCE_COLLISION_RETRIES,
            "max_lock_timeout_ms": MAX_LOCK_TIMEOUT_MS,
            "max_verification_keys": MAX_FIXTURE_VERIFICATION_KEYS,
            "max_heads_per_chain": MAX_HEADS_PER_CHAIN,
            "max_revoked_per_head": MAX_REVOKED_PER_HEAD,
            "max_cumulative_revoked": MAX_CUMULATIVE_REVOKED,
            "max_active_revisions": MAX_ACTIVE_REVISIONS,
            "max_document_bytes": MAX_DOCUMENT_BYTES,
            "max_revocation_set_bytes": MAX_REVOCATION_SET_BYTES,
            "max_revision_set_bytes": MAX_REVISION_SET_BYTES,
            "max_candidate_plaintext_bytes": MAX_CANDIDATE_PLAINTEXT_BYTES,
            "max_source_plaintext_bytes": MAX_SOURCE_PLAINTEXT_BYTES,
            "max_evidence_plaintext_bytes": MAX_EVIDENCE_PLAINTEXT_BYTES,
            "max_mutable_current_rows": MAX_MUTABLE_CURRENT_ROWS,
            "max_append_only_rows": MAX_APPEND_ONLY_ROWS,
            "max_open_holds_per_owner": MAX_OPEN_HOLDS_PER_OWNER,
            "max_open_holds_global": MAX_OPEN_HOLDS_GLOBAL,
            "max_stores": MAX_STORES,
            "max_migration_rows": MAX_MIGRATION_ROWS,
            "max_corpus_bytes": MAX_CORPUS_BYTES,
            "max_future_skew_ms": MAX_FUTURE_SKEW_MS,
            "max_past_issuance_skew_ms": MAX_PAST_ISSUANCE_SKEW_MS,
            "witness_ttl_ms": WITNESS_TTL_MS,
            "marker_ttl_ms": MARKER_TTL_MS,
            "max_active_handles": MAX_ACTIVE_HANDLES,
            "pending_handle_ttl_ms": PENDING_HANDLE_TTL_MS,
            "collision_retries": COLLISION_RETRIES,
        },
        "blind_execution_boundary": {
            "cycle34a_fixture_paths": (
                "consent_v1",
                "cursor_v1",
                "account_v1",
                "project_v1",
                "test_claim_v1",
            ),
            "cycle34b_deferred_private_algorithms": (
                "request_v1",
                "idempotency_v1",
                "effect_v1",
            ),
            "module_level_arbitrary_key_api": False,
        },
        "migration_materials": (
            "source-manifest",
            "copy-audit",
            "signed-cutover-marker",
            "external-pin",
            "ready-record",
            "barrier-forward-recovery",
        ),
        "migration_prerequisite_domains": {
            "row": _MIGRATION_ROW_DOMAIN.decode(),
            "source_manifest": _SOURCE_MANIFEST_DOMAIN.decode(),
            "copy_audit": _COPY_AUDIT_DOMAIN.decode(),
            "cutover_marker": _CUTOVER_MARKER_DOMAIN.decode(),
            "cutover_marker_signature": _CUTOVER_MARKER_SIGNATURE_DOMAIN.decode(),
            "external_pin": _EXTERNAL_PIN_DOMAIN.decode(),
            "ready": _READY_DOMAIN.decode(),
        },
        "migration_prerequisite_model_json_schemas": {
            model.__name__: model.model_json_schema()
            for model in (
                MigrationSourceStoreV1,
                ProviderCapabilityV4MigrationRowV1,
                ProviderRevocationHeadMigrationRowV1,
                ProviderRevocationCurrentMigrationRowV1,
                SourceHeadMigrationRowV1,
                SourceCurrentMigrationRowV1,
                EncryptedSourceBundleMigrationRowV1,
                OwnerOperationMigrationRowV1,
                ConsentClaimMigrationRowV1,
                QueueLeaseMigrationRowV1,
                BudgetAccountMigrationRowV1,
                FrozenPaidLaneMigrationCorpusV1,
                CopyAuditV1,
                SignedCutoverMarkerV1,
                QuarantinedSyntheticExternalPinRecordV1,
                QuarantinedSyntheticReadyRecordV1,
            )
        },
        "confers_execution_authority": False,
        "confers_checkpoint_authority": False,
        "confers_sink_authority": False,
        "confers_transition_authority": False,
        "production_consumer_enabled": False,
        "synthetic_fixture_eligibility_only": True,
        "live_migration_verified": False,
        "user_accounting_effect": False,
        "transport_reachable": False,
    }
    return hashlib.sha256(_CONTRACT_DOMAIN + _canonical_json(contract_material)).hexdigest()


# Exported identity values (computed at module load)
PRIVATE_PAID_LANE_CHECKPOINT_SEMANTIC_SHA256_V1: str = compute_private_paid_lane_semantic_sha256()
PRIVATE_PAID_LANE_CHECKPOINT_CONTRACT_SHA256_V1: str = compute_private_paid_lane_contract_sha256(
    semantic_sha256=PRIVATE_PAID_LANE_CHECKPOINT_SEMANTIC_SHA256_V1,
    sql=_SCHEMA_SQL_V1,
    predecessor_cycle33_contract=_PREDECESSOR_CYCLE33_CONTRACT_SHA256,
    predecessor_cycle32_source=_PREDECESSOR_CYCLE32_SOURCE_SHA256,
    predecessor_cycle30_capability=_PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
)


__all__ = [
    "PRIVATE_PAID_LANE_CHECKPOINT_SEMANTIC_SHA256_V1",
    "PRIVATE_PAID_LANE_CHECKPOINT_CONTRACT_SHA256_V1",
    "PrivatePaidLaneEligibilityCheckpointRejected",
    "PrivatePaidLaneEligibilityCheckpointStoreV1",
    "SignedProviderCapabilityV4FixtureV1",
    "SignedProviderRevocationHeadFixtureV1",
    "SignedSourceHeadFixtureV1",
    "OwnerPrivateSourceAuthoritySnapshotV1",
    "OpaqueSourceBundleRevisionV1",
    "VerificationKeyV1",
    "ProviderRevocationFloorPinV1",
    "OwnerPrivateSourceFloorPinV1",
    "FixtureOwnerOperationPutV1",
    "FixtureOwnerOperationAdvanceV1",
    "FixtureOwnerOperationCancelV1",
    "FixtureConsentPutV1",
    "FixtureConsentWithdrawV1",
    "FixtureConsentClaimForTestV1",
    "FixtureQueueLeasePutV1",
    "FixtureQueueLeaseTakeoverV1",
    "FixtureQueueLeaseRenewV1",
    "FixtureBudgetPutV1",
    "FixtureBudgetMutateV1",
    "FixtureProviderCapabilityPutV1",
    "FixtureProviderRevocationAppendV1",
    "FixtureSourceBundleAndHeadAppendV1",
    "FixtureSourceReceiptPairV1",
    "UnifiedPaidAdmissionCandidateV1",
    "PendingUnifiedSourceBundleHandleV1",
    "FixtureOwnerOperationResultV1",
    "FixtureConsentResultV1",
    "FixtureQueueLeaseResultV1",
    "FixtureBudgetResultV1",
    "FixtureCapabilityResultV1",
    "FixtureHeadResultV1",
    "QuarantinedPaidAdmissionResultV1",
    "QuarantinedEffectTransitionResultV1",
    "OwnerPrivateSourceKeyProviderV1",
    "PrivatePaidLaneOwnerKeyProviderV1",
    "verify_capability_v4",
    "verify_revocation_head",
    "verify_source_head",
    "compute_private_paid_lane_semantic_sha256",
    "compute_private_paid_lane_contract_sha256",
    "_SCHEMA_SQL_V1",
]
