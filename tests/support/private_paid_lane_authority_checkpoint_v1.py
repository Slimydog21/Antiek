"""Test-only issuers for Cycle34A paid-lane authority checkpoint fixtures."""

from __future__ import annotations

import fcntl
import hashlib
import json
import multiprocessing
import os
import re
import secrets
import select
import socket
import sqlite3
import stat
import struct
import tempfile
import threading
import time
from array import array
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import dataclass, field
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from pathlib import Path
from types import TracebackType
from typing import Literal, Never, cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel

from substrate.midnight_oil.private_paid_lane_authority_checkpoint import (
    _CAPABILITY_V4_SIGNATURE_DOMAIN,
    _MIGRATION_CHILD_FINAL_VERSION,
    _MIGRATION_LIFECYCLE_SIGNATURE_DOMAIN,
    _MIGRATION_RECOVERY_ADMISSION_DOMAIN,
    _MIGRATION_RECOVERY_ADMISSION_SIGNATURE_DOMAIN,
    _MIGRATION_RECOVERY_TICKET_DOMAIN,
    _MIGRATION_RECOVERY_TICKET_SIGNATURE_DOMAIN,
    _MIGRATION_ROLE_SCHEMA_TABLES,
    _PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
    _PREDECESSOR_CYCLE32_SOURCE_SHA256,
    _PREDECESSOR_CYCLE33_CONTRACT_SHA256,
    _REVOCATION_SIGNATURE_DOMAIN,
    _SCHEMA_SQL_V1,
    _SOURCE_SIGNATURE_DOMAIN,
    _SOURCE_STORE_ROWS_DOMAIN,
    MAX_DB_PAGES,
    BudgetAccountMigrationRowV1,
    ConsentClaimMigrationRowV1,
    EncryptedSourceBundleMigrationRowV1,
    Epoch0RecoveryAuthorityPinsV1,
    FrozenPaidLaneMigrationCorpusV1,
    MigrationSourceStoreV1,
    OpaqueSourceBundleRevisionV1,
    OwnerOperationMigrationRowV1,
    OwnerPrivateSourceAuthoritySnapshotV1,
    OwnerPrivateSourceFloorPinV1,
    PrivatePaidLaneEligibilityCheckpointStoreV1,
    ProviderCapabilityV4MigrationRowV1,
    ProviderRevocationCurrentMigrationRowV1,
    ProviderRevocationFloorPinV1,
    ProviderRevocationHeadMigrationRowV1,
    QuarantinedAbortUncutResultV1,
    QuarantinedSyntheticExternalPinRecordV1,
    QuarantinedSyntheticReadyRecordV1,
    QueueLeaseMigrationRowV1,
    SignedEpoch0RecoveryAdmissionV1,
    SignedMigrationLifecycleStateV1,
    SignedMigrationRecoveryTicketV1,
    SignedProviderCapabilityV4FixtureV1,
    SignedProviderRevocationHeadFixtureV1,
    SignedSourceHeadFixtureV1,
    SourceCurrentMigrationRowV1,
    SourceHeadMigrationRowV1,
    VerificationKeyV1,
    _audit_schema,
    _authenticate_epoch0_recovery_state_v1,
    _canonical_json,
    _capability_v4_document_sha256,
    _copy_audit_intent_v1,
    _copy_audit_observed_target_v1,
    _copy_audit_sha256,
    _migration_barrier_id,
    _migration_encode,
    _migration_lifecycle_entry_identity,
    _migration_lifecycle_parent_identity,
    _migration_lifecycle_state_document,
    _migration_lifecycle_state_sha256,
    _migration_role_schema_sha256,
    _migration_role_schema_sha256_from_connection,
    _migration_role_schema_sql,
    _migration_row_sha256,
    _migration_source_manifest_sha256,
    _parse_migration_lifecycle_state_document,
    _parse_strict_json,
    _read_signed_migration_lifecycle_state,
    _reconcile_copy_prepared_target_v1,
    _revocation_head_document_sha256,
    _source_head_document_sha256,
    _source_snapshot_sha256,
    _verify_migration_lifecycle_genesis,
    _verify_migration_lifecycle_transition,
    _verify_signed_epoch0_recovery_admission,
    _verify_signed_migration_recovery_ticket,
    compute_private_paid_lane_contract_sha256,
    compute_private_paid_lane_semantic_sha256,
)
from substrate.midnight_oil.private_paid_lane_authority_checkpoint import (
    QuarantinedSyntheticExternalPinStoreV1 as _OpenExternalPinStoreV1,
)
from substrate.midnight_oil.private_paid_lane_authority_checkpoint import (
    QuarantinedSyntheticLegacyRootV1 as _OpenLegacyRootV1,
)

_SUPPORT_ROOT_STATE = "legacy-root-state-v1.json"
_SUPPORT_PIN_STATE = "external-pin-state-v1.json"
_CHILD_ROLES = (
    "owner-private-source-v1",
    "paid-lane-fixture-v1",
    "provider-authority-v4",
)

_ISSUER_MAX_PACKET = 131_072
_ISSUER_WITNESS_SOCKET_NAME = "issuer-v1.sock"
_ISSUER_CANDIDATE_FIELDS = frozenset(SignedMigrationLifecycleStateV1.model_fields) - {
    "issuer_key_id",
    "state_sha256",
    "signature_ed25519",
    "witness_sha256",
}
_ISSUER_WITNESS_DOMAIN = b"antiek.midnight-oil.fixture-migration-root-witness.v1\0"
_ISSUER_MAX_CHILD_BYTES = 64 * 1024 * 1024


def _issuer_response(socket_: socket.socket, payload: bytes) -> None:
    if len(payload) > _ISSUER_MAX_PACKET:
        raise ValueError("issuer response bound")
    with suppress(OSError):
        socket_.sendall(payload)


def _issuer_received_descriptors(ancillary: list[tuple[int, int, bytes]]) -> list[int]:
    descriptors: list[int] = []
    for level, kind, data in ancillary:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            values = array("i")
            usable = len(data) - (len(data) % values.itemsize)
            values.frombytes(data[:usable])
            descriptors.extend(values)
    return descriptors


def _issuer_root_record(root_fd: int) -> dict[str, object]:
    root_info = os.fstat(root_fd)
    if (
        not stat.S_ISDIR(root_info.st_mode)
        or root_info.st_uid != os.getuid()
        or stat.S_IMODE(root_info.st_mode) != 0o700
    ):
        raise ValueError("issuer root identity")
    state_info = os.stat(_SUPPORT_ROOT_STATE, dir_fd=root_fd, follow_symlinks=False)
    if (
        not stat.S_ISREG(state_info.st_mode)
        or state_info.st_uid != os.getuid()
        or state_info.st_nlink != 1
        or stat.S_IMODE(state_info.st_mode) != 0o600
        or not 0 < state_info.st_size <= 1_048_576
    ):
        raise ValueError("issuer root state identity")
    descriptor = os.open(
        _SUPPORT_ROOT_STATE,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=root_fd,
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (state_info.st_dev, state_info.st_ino):
            raise ValueError("issuer root state changed during open")
        chunks: list[bytes] = []
        remaining = 1_048_577
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        document = b"".join(chunks)
        if len(document) != opened.st_size or len(document) > 1_048_576:
            raise ValueError("issuer root state changed during read")
    finally:
        os.close(descriptor)
    record = json.loads(document)
    if type(record) is not dict:
        raise ValueError("issuer root state shape")
    _audit_transition_evidence(record)
    return record


def _issuer_witness_sha256(
    *,
    root_record: Mapping[str, object],
    target_parent_identity: tuple[int, int],
    target_basename: str,
    target_identity: tuple[int, int],
) -> str:
    evidence = cast(list[dict[str, object]], root_record["transition_evidence"])
    return hashlib.sha256(
        _ISSUER_WITNESS_DOMAIN
        + _canonical_json(
            {
                "root_id": root_record["root_id"],
                "root_manifest_sha256": root_record["root_manifest_sha256"],
                "inventory_sha256": root_record["inventory_sha256"],
                "barrier_id": root_record["barrier_id"],
                "freeze_nonce": root_record["freeze_nonce"],
                "root_state": root_record["state"],
                "transition_evidence_tip": (
                    "0" * 64 if not evidence else evidence[-1]["evidence_sha256"]
                ),
                "target_parent_dev": target_parent_identity[0],
                "target_parent_ino": target_parent_identity[1],
                "target_basename": target_basename,
                "target_dev": target_identity[0],
                "target_ino": target_identity[1],
            }
        )
    ).hexdigest()


@contextmanager
def _issuer_transition_lock(root_fd: int) -> Iterator[None]:
    descriptor = os.open(
        ".migration.lock",
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=root_fd,
    )
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or (info.st_mode & 0o777) != 0o600
            or info.st_uid != os.getuid()
        ):
            raise ValueError("issuer transition lock identity")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _issuer_compatible_root_record(root_fd: int, phase: object) -> dict[str, object]:
    record = _issuer_root_record(root_fd)
    if type(phase) is not str:
        raise ValueError("issuer lifecycle phase type")
    expected_state = {
        "schema_only": "open",
        "barrier_acquired": "quiesced",
        "sources_sealed": "sealed",
        "copy_prepared": "sealed",
        "copied_epoch0": "sealed",
    }.get(phase)
    if expected_state is None or record.get("state") != expected_state:
        raise ValueError("issuer unsupported or incompatible root phase")
    if phase == "schema_only" and record.get("barrier_id") is not None:
        raise ValueError("issuer schema root phase")
    return record


def _issuer_fd_path(descriptor: int) -> Path:
    raw = fcntl.fcntl(descriptor, fcntl.F_GETPATH, b"\0" * 1024)
    path = Path(os.fsdecode(raw.split(b"\0", 1)[0]))
    info = path.stat()
    opened = os.fstat(descriptor)
    if (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
        raise ValueError("issuer root path identity")
    return path


def _issuer_root_path(root_fd: int) -> Path:
    return _issuer_fd_path(root_fd)


def _collect_sealed_corpus(
    root_path: Path, record: Mapping[str, object]
) -> FrozenPaidLaneMigrationCorpusV1:
    child_evidence = record.get("child_adapter_evidence")
    if type(child_evidence) is not dict:
        raise ValueError("sealed child evidence unavailable")
    measurements = child_evidence.get("sealed_measurements")
    if type(measurements) is not dict:
        raise ValueError("sealed measurements unavailable")
    barrier_id = record.get("barrier_id")
    freeze_nonce = record.get("freeze_nonce")
    acquired_at_ms = record.get("acquired_at_ms")
    if (
        type(barrier_id) is not str
        or type(freeze_nonce) is not str
        or type(acquired_at_ms) is not int
    ):
        raise ValueError("sealed corpus root pins")
    with _issuer_child_snapshot(root_path) as snapshot_root:
        measured_now = _measure_child_adapters(snapshot_root)
        if measured_now != measurements:
            raise ValueError("sealed source measurement drift")
        extracted = _extract_child_migration_rows(snapshot_root)
    source_stores: list[MigrationSourceStoreV1] = []
    for role in _CHILD_ROLES:
        measured = measurements.get(role)
        if type(measured) is not dict:
            raise ValueError("sealed role measurement unavailable")
        row_counts = measured.get("row_counts")
        if type(row_counts) is not list or any(
            type(item) is not list
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not int
            or item[1] < 0
            for item in row_counts
        ):
            raise ValueError("typed child migration extraction required")
        if any(item[0] not in _MIGRATION_ROW_MODELS and item[1] != 0 for item in row_counts):
            raise ValueError("non-migratable child rows remain")
        contract_role = _contract_role(role)
        owned_count = sum(
            len(extracted[table])
            for table in _MIGRATION_ROLE_SCHEMA_TABLES[contract_role]
            if table in extracted
        )
        if owned_count != sum(item[1] for item in row_counts if item[0] in _MIGRATION_ROW_MODELS):
            raise ValueError("typed child row count mismatch")
        source_stores.append(
            MigrationSourceStoreV1(
                store_kind=contract_role,
                store_id=role,
                schema_sha256=str(measured["schema_sha256"]),
                native_writer_barrier_id=barrier_id,
                final_version=int(measured["final_version"]),
                row_count=owned_count,
                ordered_rows_sha256=str(measured["ordered_rows_sha256"]),
            )
        )
    draft = FrozenPaidLaneMigrationCorpusV1.model_construct(
        freeze_nonce=freeze_nonce,
        quiesced_at_ms=acquired_at_ms,
        drained_at_ms=acquired_at_ms,
        sealed_at_ms=acquired_at_ms,
        source_stores=tuple(sorted(source_stores, key=lambda item: item.store_kind)),
        provider_capabilities_v4=extracted["provider_capabilities_v4"],
        provider_revocation_heads=extracted["provider_revocation_heads"],
        provider_revocation_current=extracted["provider_revocation_current"],
        source_heads=extracted["source_heads"],
        source_current=extracted["source_current"],
        encrypted_source_bundles=extracted["encrypted_source_bundles"],
        owner_operations=extracted["owner_operations"],
        consent_claims=extracted["consent_claims"],
        queue_leases=extracted["queue_leases"],
        budget_accounts=extracted["budget_accounts"],
        source_manifest_sha256="0" * 64,
    )
    return FrozenPaidLaneMigrationCorpusV1.model_validate(
        {
            **draft.model_dump(mode="python"),
            "source_manifest_sha256": _migration_source_manifest_sha256(draft),
        }
    )


@contextmanager
def _issuer_child_snapshot(root_path: Path) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="antiek-sealed-snapshot-") as temporary:
        snapshot_root = Path(temporary)
        snapshot_root.chmod(0o700)
        snapshot_children = snapshot_root / "children"
        snapshot_children.mkdir(mode=0o700)
        for role in _CHILD_ROLES:
            source = _child_path(root_path, role)
            _issuer_require_child_sidecars_absent(source)
            before = source.lstat()
            descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                opened = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_nlink != 1
                    or (opened.st_mode & 0o777) != 0o600
                    or opened.st_uid != os.getuid()
                    or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
                    or opened.st_size > _ISSUER_MAX_CHILD_BYTES
                ):
                    raise ValueError("issuer child identity")
                chunks: list[bytes] = []
                remaining = opened.st_size
                while remaining:
                    chunk = os.read(descriptor, min(65_536, remaining))
                    if not chunk:
                        raise ValueError("issuer child short read")
                    chunks.append(chunk)
                    remaining -= len(chunk)
                content = b"".join(chunks)
                os.lseek(descriptor, 0, os.SEEK_SET)
                confirmed = bytearray()
                while chunk := os.read(descriptor, 65_536):
                    confirmed.extend(chunk)
                    if len(confirmed) > _ISSUER_MAX_CHILD_BYTES:
                        raise ValueError("issuer child reread bound")
                after = source.lstat()
                _issuer_require_child_sidecars_absent(source)
                if (
                    bytes(confirmed) != content
                    or (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
                    or after.st_size != len(content)
                ):
                    raise ValueError("issuer child changed during snapshot")
            finally:
                os.close(descriptor)
            destination = _child_path(snapshot_root, role)
            output = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                view = memoryview(content)
                while view:
                    written = os.write(output, view)
                    if written <= 0:
                        raise OSError("issuer snapshot short write")
                    view = view[written:]
            finally:
                os.close(output)
        yield snapshot_root


def _issuer_require_child_sidecars_absent(source: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(f"{source}{suffix}")
        try:
            sidecar.lstat()
        except FileNotFoundError:
            continue
        raise ValueError("issuer child sidecar present")


def _issuer_acquire_target_lease(target_fd: int) -> sqlite3.Connection:
    target_path = _issuer_fd_path(target_fd)
    opened = os.fstat(target_fd)
    before = target_path.stat()
    _issuer_require_child_sidecars_absent(target_path)
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
        or (opened.st_mode & 0o777) != 0o600
        or opened.st_uid != os.getuid()
        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        or opened.st_size > _ISSUER_MAX_CHILD_BYTES
    ):
        raise ValueError("issuer copy target identity")
    connection = sqlite3.connect(
        f"{target_path.as_uri()}?mode=rw",
        uri=True,
        isolation_level=None,
    )
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute(f"PRAGMA max_page_count={MAX_DB_PAGES}")
        connection.execute("BEGIN IMMEDIATE")
        database_rows = connection.execute("PRAGMA database_list").fetchall()
        main_rows = [row for row in database_rows if row[1] == "main"]
        if len(main_rows) != 1:
            raise ValueError("issuer copy target database identity")
        sqlite_path = Path(str(main_rows[0][2])).resolve(strict=True)
        sqlite_opened = sqlite_path.stat()
        after = target_path.stat()
        if (sqlite_opened.st_dev, sqlite_opened.st_ino) != (opened.st_dev, opened.st_ino) or (
            after.st_dev,
            after.st_ino,
        ) != (opened.st_dev, opened.st_ino):
            raise ValueError("issuer copy target database identity")
    except BaseException:
        with suppress(sqlite3.Error):
            connection.execute("ROLLBACK")
        connection.close()
        raise
    return connection


def _issuer_release_target_lease(connection: sqlite3.Connection) -> None:
    with suppress(sqlite3.Error):
        connection.execute("ROLLBACK")
    connection.close()


@contextmanager
def _issuer_target_snapshot(target_fd: int, target_lease: sqlite3.Connection) -> Iterator[Path]:
    target_path = _issuer_fd_path(target_fd)
    opened = os.fstat(target_fd)
    before = target_path.stat()
    if not target_lease.in_transaction or (before.st_dev, before.st_ino) != (
        opened.st_dev,
        opened.st_ino,
    ):
        raise ValueError("issuer copy target changed before snapshot")
    with tempfile.TemporaryDirectory(prefix="antiek-copy-target-") as temporary:
        snapshot = Path(temporary) / "target.sqlite3"
        source = sqlite3.connect(f"{target_path.as_uri()}?mode=ro", uri=True, isolation_level=None)
        destination = sqlite3.connect(snapshot, isolation_level=None)
        try:
            source_rows = source.execute("PRAGMA database_list").fetchall()
            main_rows = [row for row in source_rows if row[1] == "main"]
            if len(main_rows) != 1:
                raise ValueError("issuer copy snapshot database identity")
            source_path = Path(str(main_rows[0][2])).resolve(strict=True)
            source_opened = source_path.stat()
            if (source_opened.st_dev, source_opened.st_ino) != (
                opened.st_dev,
                opened.st_ino,
            ):
                raise ValueError("issuer copy snapshot database identity")
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        snapshot.chmod(0o600)
        after = target_path.stat()
        if not target_lease.in_transaction or (after.st_dev, after.st_ino) != (
            opened.st_dev,
            opened.st_ino,
        ):
            raise ValueError("issuer copy target changed during snapshot")
        yield snapshot


def _issuer_copy_intent(
    *,
    target_fd: int,
    target_lease: sqlite3.Connection,
    corpus: FrozenPaidLaneMigrationCorpusV1,
    provider_capability_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_verification_keys: tuple[VerificationKeyV1, ...],
    source_head_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_floor_pins: tuple[ProviderRevocationFloorPinV1, ...],
    source_floor_pins: tuple[OwnerPrivateSourceFloorPinV1, ...],
    expected_target_store_id: str,
    expected_semantic_source_sha256: str,
    expected_contract_sha256: str,
) -> str:
    with _issuer_target_snapshot(target_fd, target_lease) as target_path:
        connection = sqlite3.connect(f"{target_path.as_uri()}?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute(f"PRAGMA max_page_count={MAX_DB_PAGES}")
            connection.execute("BEGIN")
            _audit_schema(connection)
            singleton = connection.execute(
                "SELECT singleton,schema_version,migration_epoch,store_id,"
                "semantic_source_sha256,contract_sha256,cutover_marker_sha256,"
                "created_at_ms FROM paid_lane_schema"
            ).fetchall()
            if singleton != [
                (
                    1,
                    1,
                    0,
                    expected_target_store_id,
                    expected_semantic_source_sha256,
                    expected_contract_sha256,
                    None,
                    0,
                )
            ]:
                raise ValueError("issuer copy target singleton")
            for table_name in (
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
            ):
                if connection.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone() is not None:
                    raise ValueError("issuer copy target not schema-only")
            audit = _copy_audit_intent_v1(
                corpus=corpus,
                target_store_id=expected_target_store_id,
                semantic_source_sha256=expected_semantic_source_sha256,
                contract_sha256=expected_contract_sha256,
                provider_capability_verification_keys=provider_capability_verification_keys,
                provider_revocation_verification_keys=provider_revocation_verification_keys,
                source_head_verification_keys=source_head_verification_keys,
                provider_revocation_floor_pins=provider_revocation_floor_pins,
                source_floor_pins=source_floor_pins,
            )
            connection.execute("COMMIT")
        except BaseException:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
    return _copy_audit_sha256(audit)


def _issuer_observed_copy(
    *,
    target_fd: int,
    target_lease: sqlite3.Connection,
    corpus: FrozenPaidLaneMigrationCorpusV1,
    provider_capability_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_verification_keys: tuple[VerificationKeyV1, ...],
    source_head_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_floor_pins: tuple[ProviderRevocationFloorPinV1, ...],
    source_floor_pins: tuple[OwnerPrivateSourceFloorPinV1, ...],
    expected_target_store_id: str,
    expected_semantic_source_sha256: str,
    expected_contract_sha256: str,
) -> str:
    with _issuer_target_snapshot(target_fd, target_lease) as target_path:
        connection = sqlite3.connect(f"{target_path.as_uri()}?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute(f"PRAGMA max_page_count={MAX_DB_PAGES}")
            connection.execute("BEGIN")
            audit = _copy_audit_observed_target_v1(
                connection,
                corpus=corpus,
                target_store_id=expected_target_store_id,
                semantic_source_sha256=expected_semantic_source_sha256,
                contract_sha256=expected_contract_sha256,
                provider_capability_verification_keys=provider_capability_verification_keys,
                provider_revocation_verification_keys=provider_revocation_verification_keys,
                source_head_verification_keys=source_head_verification_keys,
                provider_revocation_floor_pins=provider_revocation_floor_pins,
                source_floor_pins=source_floor_pins,
            )
            connection.execute("COMMIT")
        except BaseException:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
    return _copy_audit_sha256(audit)


def _issuer_authenticate_recovery_descriptors(
    *,
    root_fd: int,
    parent_fd: int,
    target_fd: int,
    ticket: SignedMigrationRecoveryTicketV1,
    verification_key: VerificationKeyV1,
    raw_pins: object,
) -> Epoch0RecoveryAuthorityPinsV1:
    root_info = os.fstat(root_fd)
    root_record = _issuer_root_record(root_fd)
    if (
        (root_info.st_dev, root_info.st_ino) != (ticket.root_dev, ticket.root_ino)
        or root_record.get("root_id") != ticket.root_id
        or root_record.get("root_manifest_sha256") != ticket.root_manifest_sha256
    ):
        raise ValueError("issuer recovery root identity")
    pins = Epoch0RecoveryAuthorityPinsV1.model_validate(raw_pins)
    if (
        pins.target_store_id != ticket.target_store_id
        or pins.root_id != ticket.root_id
        or pins.root_manifest_sha256 != ticket.root_manifest_sha256
        or (pins.target_parent_dev, pins.target_parent_ino)
        != (ticket.target_parent_dev, ticket.target_parent_ino)
        or pins.target_basename != ticket.target_basename
        or (pins.target_dev, pins.target_ino) != (ticket.target_dev, ticket.target_ino)
        or pins.issuer_sequence > ticket.maximum_issuer_sequence
    ):
        raise ValueError("issuer recovery ticket pins")
    _authenticate_epoch0_recovery_state_v1(
        parent_fd=parent_fd,
        target_fd=target_fd,
        verification_key=verification_key,
        expected=pins,
    )
    return pins


def _fixture_migration_lifecycle_issuer_main(
    socket_path: str,
    authorized_pid: int,
    handshake: Connection,
    provider_capability_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_verification_keys: tuple[VerificationKeyV1, ...],
    source_head_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_floor_pins: tuple[ProviderRevocationFloorPinV1, ...],
    source_floor_pins: tuple[OwnerPrivateSourceFloorPinV1, ...],
    expected_target_store_id: str,
    expected_semantic_source_sha256: str,
    expected_contract_sha256: str,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    key_id = "fixture-migration-lifecycle-issuer-v1-" + hashlib.sha256(public_key).hexdigest()[:24]
    verification_key = VerificationKeyV1(key_id=key_id, public_key_bytes=public_key)
    issuer_generation_nonce = secrets.token_hex(32)
    committed: SignedMigrationLifecycleStateV1 | None = None
    pending_candidate: bytes | None = None
    pending_state: SignedMigrationLifecycleStateV1 | None = None
    bound_root_fd: int | None = None
    bound_target_fd: int | None = None
    target_lease: sqlite3.Connection | None = None
    bound_identity: dict[str, object] | None = None
    recovery_ticket: SignedMigrationRecoveryTicketV1 | None = None
    recovery_admission_request: bytes | None = None
    recovery_admission: SignedEpoch0RecoveryAdmissionV1 | None = None
    copy_completed = False
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    process_watch = select.kqueue()
    try:
        process_watch.control(
            [
                select.kevent(
                    authorized_pid,
                    filter=select.KQ_FILTER_PROC,
                    flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE,
                    fflags=select.KQ_NOTE_EXIT | select.KQ_NOTE_FORK,
                )
            ],
            0,
            0,
        )
        listener.bind(socket_path)
        os.chmod(socket_path, 0o600)
        listener.listen(8)
        listener.settimeout(0.25)
        handshake.send((key_id, public_key))
        handshake.close()
        while True:
            if process_watch.control(None, 1, 0):
                return
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            descriptor: int | None = None
            received_descriptors: list[int] = []
            try:
                peer_pid = struct.unpack("i", connection.getsockopt(0, 2, 4))[0]
                connection.settimeout(0.1)
                while True:
                    try:
                        first, ancillary, flags, _ = connection.recvmsg(
                            _ISSUER_MAX_PACKET + 1,
                            socket.CMSG_SPACE(array("i").itemsize * 3),
                        )
                        if process_watch.control(None, 1, 0):
                            return
                        break
                    except TimeoutError:
                        if process_watch.control(None, 1, 0):
                            return
                received_descriptors = _issuer_received_descriptors(ancillary)
                if flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC):
                    raise ValueError("issuer truncated request")
                chunks = [first]
                total = len(first)
                while True:
                    try:
                        chunk = connection.recv(65_536)
                    except TimeoutError:
                        if process_watch.control(None, 1, 0):
                            return
                        continue
                    if not chunk:
                        break
                    if process_watch.control(None, 1, 0):
                        return
                    total += len(chunk)
                    if total > _ISSUER_MAX_PACKET:
                        raise ValueError("issuer request bound")
                    chunks.append(chunk)
                if process_watch.control(None, 1, 0):
                    return
                packet = b"".join(chunks)
                request = _parse_strict_json(packet, _ISSUER_MAX_PACKET)
                command = request.get("command")
                if peer_pid != authorized_pid and command != "recover_open":
                    raise ValueError("issuer peer pid")
                if command == "bind":
                    if (
                        bound_root_fd is not None
                        or bound_target_fd is not None
                        or set(request) != {"command", "target_basename"}
                        or len(received_descriptors) != 2
                        or type(request["target_basename"]) is not str
                    ):
                        raise ValueError("issuer bind envelope")
                    root_fd = received_descriptors.pop(0)
                    parent_fd = received_descriptors.pop(0)
                    independent_root_fd = -1
                    independent_target_fd = -1
                    try:
                        independent_root_fd = os.open(
                            ".",
                            os.O_RDONLY | os.O_DIRECTORY,
                            dir_fd=root_fd,
                        )
                        fcntl.flock(
                            independent_root_fd,
                            fcntl.LOCK_EX | fcntl.LOCK_NB,
                        )
                        root_record = _issuer_root_record(independent_root_fd)
                        if (
                            root_record.get("state") != "open"
                            or root_record.get("barrier_id") is not None
                        ):
                            raise ValueError("issuer bind root phase")
                        parent_identity = _migration_lifecycle_parent_identity(parent_fd)
                        bind_target_basename = request["target_basename"]
                        target_identity = _migration_lifecycle_entry_identity(
                            parent_fd, bind_target_basename
                        )
                        if target_identity is None:
                            raise ValueError("issuer bind target missing")
                        independent_target_fd = os.open(
                            bind_target_basename,
                            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=parent_fd,
                        )
                        target_opened = os.fstat(independent_target_fd)
                        if (target_opened.st_dev, target_opened.st_ino) != target_identity:
                            raise ValueError("issuer bind target identity")
                        bound_identity = {
                            "root_id": root_record["root_id"],
                            "root_manifest_sha256": root_record["root_manifest_sha256"],
                            "target_parent_dev": parent_identity[0],
                            "target_parent_ino": parent_identity[1],
                            "target_basename": bind_target_basename,
                            "target_dev": target_identity[0],
                            "target_ino": target_identity[1],
                        }
                        bound_root_fd = independent_root_fd
                        independent_root_fd = -1
                        bound_target_fd = independent_target_fd
                        independent_target_fd = -1
                        root_info = os.fstat(bound_root_fd)
                        ticket_material = {
                            "schema_version": 1,
                            "issuer_key_id": key_id,
                            "issuer_generation_nonce": issuer_generation_nonce,
                            "root_id": root_record["root_id"],
                            "root_dev": root_info.st_dev,
                            "root_ino": root_info.st_ino,
                            "root_manifest_sha256": root_record["root_manifest_sha256"],
                            "target_store_id": expected_target_store_id,
                            "target_parent_dev": parent_identity[0],
                            "target_parent_ino": parent_identity[1],
                            "target_basename": bind_target_basename,
                            "target_dev": target_identity[0],
                            "target_ino": target_identity[1],
                            "maximum_issuer_sequence": 4,
                            "ticket_nonce": secrets.token_hex(32),
                            "issued_at_ms": time.time_ns() // 1_000_000,
                        }
                        ticket_sha256 = hashlib.sha256(
                            _MIGRATION_RECOVERY_TICKET_DOMAIN + _canonical_json(ticket_material)
                        ).hexdigest()
                        recovery_ticket = SignedMigrationRecoveryTicketV1.model_validate(
                            {
                                **ticket_material,
                                "ticket_sha256": ticket_sha256,
                                "signature_ed25519": private_key.sign(
                                    _MIGRATION_RECOVERY_TICKET_SIGNATURE_DOMAIN
                                    + bytes.fromhex(ticket_sha256)
                                ),
                            }
                        )
                        _issuer_response(
                            connection,
                            b"B"
                            + _canonical_json(
                                {
                                    **recovery_ticket.model_dump(
                                        mode="python", exclude={"signature_ed25519"}
                                    ),
                                    "signature_ed25519": recovery_ticket.signature_ed25519.hex(),
                                }
                            ),
                        )
                    finally:
                        if independent_root_fd >= 0:
                            os.close(independent_root_fd)
                        if independent_target_fd >= 0:
                            os.close(independent_target_fd)
                        if root_fd >= 0:
                            os.close(root_fd)
                        os.close(parent_fd)
                    continue
                if command == "recover_open":
                    if (
                        recovery_ticket is None
                        or set(request)
                        != {
                            "command",
                            "ticket_sha256",
                            "issuer_generation_nonce",
                            "caller_boot_nonce",
                            "handle_nonce",
                            "authority_pins",
                        }
                        or len(received_descriptors) != 3
                        or request["ticket_sha256"] != recovery_ticket.ticket_sha256
                        or request["issuer_generation_nonce"]
                        != recovery_ticket.issuer_generation_nonce
                        or type(request["caller_boot_nonce"]) is not str
                        or type(request["handle_nonce"]) is not str
                        or type(request["authority_pins"]) is not dict
                    ):
                        raise ValueError("issuer recovery open envelope")
                    request_bytes = _canonical_json(request)
                    recovery_root_fd = received_descriptors.pop(0)
                    recovery_parent_fd = received_descriptors.pop(0)
                    recovery_target_fd = received_descriptors.pop(0)
                    try:
                        pins = _issuer_authenticate_recovery_descriptors(
                            root_fd=recovery_root_fd,
                            parent_fd=recovery_parent_fd,
                            target_fd=recovery_target_fd,
                            ticket=recovery_ticket,
                            verification_key=verification_key,
                            raw_pins=request["authority_pins"],
                        )
                    finally:
                        os.close(recovery_root_fd)
                        os.close(recovery_parent_fd)
                        os.close(recovery_target_fd)
                    if recovery_admission_request is not None:
                        if (
                            request_bytes != recovery_admission_request
                            or recovery_admission is None
                            or peer_pid != recovery_admission.authenticated_peer_pid
                        ):
                            raise ValueError("issuer recovery admission replay")
                    else:
                        admission_material = {
                            "schema_version": 1,
                            "issuer_key_id": key_id,
                            "issuer_generation_nonce": issuer_generation_nonce,
                            "ticket_sha256": recovery_ticket.ticket_sha256,
                            "authenticated_peer_pid": peer_pid,
                            "caller_boot_nonce": request["caller_boot_nonce"],
                            "handle_nonce": request["handle_nonce"],
                            "descriptor_mode": "target",
                            "authority_pins": pins.model_dump(mode="json"),
                            "issued_at_ms": time.time_ns() // 1_000_000,
                        }
                        admission_sha256 = hashlib.sha256(
                            _MIGRATION_RECOVERY_ADMISSION_DOMAIN
                            + _canonical_json(admission_material)
                        ).hexdigest()
                        recovery_admission = SignedEpoch0RecoveryAdmissionV1.model_validate(
                            {
                                **admission_material,
                                "admission_sha256": admission_sha256,
                                "signature_ed25519": private_key.sign(
                                    _MIGRATION_RECOVERY_ADMISSION_SIGNATURE_DOMAIN
                                    + bytes.fromhex(admission_sha256)
                                ),
                            }
                        )
                        recovery_admission_request = request_bytes
                    if recovery_admission is None:
                        raise ValueError("issuer recovery admission missing")
                    _issuer_response(
                        connection,
                        b"R"
                        + _canonical_json(
                            {
                                **recovery_admission.model_dump(
                                    mode="python", exclude={"signature_ed25519"}
                                ),
                                "signature_ed25519": recovery_admission.signature_ed25519.hex(),
                            }
                        ),
                    )
                    continue
                if command == "close":
                    if received_descriptors:
                        raise ValueError("issuer close descriptor")
                    _issuer_response(connection, b"C")
                    return
                if command == "copy_epoch0":
                    if (
                        bound_root_fd is None
                        or bound_target_fd is None
                        or committed is None
                        or pending_state is not None
                        or received_descriptors
                        or set(request)
                        != {
                            "command",
                            "prepared_state_sha256",
                            "test_post_commit_pause_ms",
                        }
                        or request["prepared_state_sha256"] != committed.state_sha256
                        or committed.lifecycle_phase != "copy_prepared"
                        or type(request["test_post_commit_pause_ms"]) is not int
                        or not 0 <= request["test_post_commit_pause_ms"] <= 1_000
                    ):
                        raise ValueError("issuer copy command state")
                    with _issuer_transition_lock(bound_root_fd):
                        if target_lease is None:
                            target_lease = _issuer_acquire_target_lease(bound_target_fd)
                        compatible = _issuer_compatible_root_record(
                            bound_root_fd, committed.lifecycle_phase
                        )
                        corpus = _collect_sealed_corpus(
                            _issuer_root_path(bound_root_fd), compatible
                        )
                        if (
                            committed.source_manifest_sha256 != corpus.source_manifest_sha256
                            or committed.copy_audit_sha256 is None
                        ):
                            raise ValueError("issuer copy command corpus")
                        first_execution = not copy_completed
                        try:
                            audit, _ = _reconcile_copy_prepared_target_v1(
                                target_lease,
                                corpus=corpus,
                                expected_copy_audit_sha256=committed.copy_audit_sha256,
                                target_store_id=committed.target_store_id,
                                semantic_source_sha256=expected_semantic_source_sha256,
                                contract_sha256=expected_contract_sha256,
                                provider_capability_verification_keys=provider_capability_verification_keys,
                                provider_revocation_verification_keys=provider_revocation_verification_keys,
                                source_head_verification_keys=source_head_verification_keys,
                                provider_revocation_floor_pins=provider_revocation_floor_pins,
                                source_floor_pins=source_floor_pins,
                            )
                            target_lease.execute("COMMIT")
                            copy_completed = True
                            pause_ms = request["test_post_commit_pause_ms"]
                            if pause_ms:
                                target_lease.execute("PRAGMA busy_timeout=50")
                                time.sleep(pause_ms / 1_000)
                            target_lease.execute("BEGIN IMMEDIATE")
                            confirmed, confirmed_copied = _reconcile_copy_prepared_target_v1(
                                target_lease,
                                corpus=corpus,
                                expected_copy_audit_sha256=committed.copy_audit_sha256,
                                target_store_id=committed.target_store_id,
                                semantic_source_sha256=expected_semantic_source_sha256,
                                contract_sha256=expected_contract_sha256,
                                provider_capability_verification_keys=provider_capability_verification_keys,
                                provider_revocation_verification_keys=provider_revocation_verification_keys,
                                source_head_verification_keys=source_head_verification_keys,
                                provider_revocation_floor_pins=provider_revocation_floor_pins,
                                source_floor_pins=source_floor_pins,
                            )
                            has_corpus_rows = any(
                                getattr(corpus, table_name)
                                for table_name in (
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
                            )
                            if confirmed != audit or (has_corpus_rows and confirmed_copied):
                                raise ValueError("issuer copy command confirmation")
                            copied = first_execution
                        except BaseException:
                            with suppress(sqlite3.Error):
                                target_lease.execute("ROLLBACK")
                            if not target_lease.in_transaction:
                                try:
                                    target_lease.execute("BEGIN IMMEDIATE")
                                except BaseException:
                                    target_lease.close()
                                    target_lease = None
                            raise
                    _issuer_response(
                        connection,
                        b"Y"
                        + _copy_audit_sha256(audit).encode("ascii")
                        + (b"1" if copied else b"0"),
                    )
                    continue
                if command == "reserve":
                    if (
                        bound_root_fd is None
                        or bound_identity is None
                        or received_descriptors
                        or set(request) != {"command", "candidate"}
                    ):
                        raise ValueError("issuer reserve envelope")
                    candidate = request["candidate"]
                    if type(candidate) is not dict or set(candidate) != _ISSUER_CANDIDATE_FIELDS:
                        raise ValueError("issuer candidate fields")
                    candidate_bytes = _canonical_json(candidate)
                    if pending_candidate is not None:
                        if candidate_bytes != pending_candidate or pending_state is None:
                            raise ValueError("issuer pending equivocation")
                        with _issuer_transition_lock(bound_root_fd):
                            compatible = _issuer_compatible_root_record(
                                bound_root_fd, pending_state.lifecycle_phase
                            )
                            if pending_state.lifecycle_phase != "schema_only" and (
                                pending_state.barrier_id != compatible.get("barrier_id")
                                or pending_state.freeze_nonce != compatible.get("freeze_nonce")
                            ):
                                raise ValueError("issuer pending root authority")
                            if pending_state.lifecycle_phase in {
                                "sources_sealed",
                                "copy_prepared",
                                "copied_epoch0",
                            }:
                                corpus = _collect_sealed_corpus(
                                    _issuer_root_path(bound_root_fd), compatible
                                )
                                if (
                                    pending_state.source_manifest_sha256
                                    != corpus.source_manifest_sha256
                                ):
                                    raise ValueError("issuer pending source manifest")
                                if pending_state.lifecycle_phase in {
                                    "copy_prepared",
                                    "copied_epoch0",
                                }:
                                    if bound_target_fd is None:
                                        raise ValueError("issuer pending target custody")
                                    if target_lease is None:
                                        if pending_state.lifecycle_phase != "copied_epoch0":
                                            raise ValueError("issuer pending target lease")
                                        target_lease = _issuer_acquire_target_lease(bound_target_fd)
                                    copy_measure = (
                                        _issuer_copy_intent
                                        if pending_state.lifecycle_phase == "copy_prepared"
                                        else _issuer_observed_copy
                                    )
                                    expected_audit = copy_measure(
                                        target_fd=bound_target_fd,
                                        target_lease=target_lease,
                                        corpus=corpus,
                                        provider_capability_verification_keys=provider_capability_verification_keys,
                                        provider_revocation_verification_keys=provider_revocation_verification_keys,
                                        source_head_verification_keys=source_head_verification_keys,
                                        provider_revocation_floor_pins=provider_revocation_floor_pins,
                                        source_floor_pins=source_floor_pins,
                                        expected_target_store_id=pending_state.target_store_id,
                                        expected_semantic_source_sha256=expected_semantic_source_sha256,
                                        expected_contract_sha256=expected_contract_sha256,
                                    )
                                    if pending_state.copy_audit_sha256 != expected_audit:
                                        raise ValueError("issuer pending copy intent")
                        _issuer_response(
                            connection,
                            b"S" + _migration_lifecycle_state_document(pending_state),
                        )
                        continue
                    if any(
                        candidate.get(field) != expected
                        for field, expected in bound_identity.items()
                    ):
                        raise ValueError("issuer candidate bound identity")
                    phase = candidate.get("lifecycle_phase")
                    with _issuer_transition_lock(bound_root_fd):
                        root_record = _issuer_compatible_root_record(bound_root_fd, phase)
                        if phase == "schema_only":
                            witness_sha256 = None
                        else:
                            if candidate.get("barrier_id") != root_record.get(
                                "barrier_id"
                            ) or candidate.get("freeze_nonce") != root_record.get("freeze_nonce"):
                                raise ValueError("issuer barrier root phase")
                            if phase in {
                                "sources_sealed",
                                "copy_prepared",
                                "copied_epoch0",
                            }:
                                corpus = _collect_sealed_corpus(
                                    _issuer_root_path(bound_root_fd), root_record
                                )
                                if (
                                    candidate.get("source_manifest_sha256")
                                    != corpus.source_manifest_sha256
                                ):
                                    raise ValueError("issuer source manifest")
                                if phase in {"copy_prepared", "copied_epoch0"}:
                                    if bound_target_fd is None:
                                        raise ValueError("issuer target custody")
                                    if phase == "copy_prepared":
                                        if target_lease is not None:
                                            raise ValueError("issuer target lease state")
                                        target_lease = _issuer_acquire_target_lease(bound_target_fd)
                                    elif target_lease is None:
                                        target_lease = _issuer_acquire_target_lease(bound_target_fd)
                                    copy_measure = (
                                        _issuer_copy_intent
                                        if phase == "copy_prepared"
                                        else _issuer_observed_copy
                                    )
                                    expected_audit = copy_measure(
                                        target_fd=bound_target_fd,
                                        target_lease=target_lease,
                                        corpus=corpus,
                                        provider_capability_verification_keys=provider_capability_verification_keys,
                                        provider_revocation_verification_keys=provider_revocation_verification_keys,
                                        source_head_verification_keys=source_head_verification_keys,
                                        provider_revocation_floor_pins=provider_revocation_floor_pins,
                                        source_floor_pins=source_floor_pins,
                                        expected_target_store_id=str(candidate["target_store_id"]),
                                        expected_semantic_source_sha256=expected_semantic_source_sha256,
                                        expected_contract_sha256=expected_contract_sha256,
                                    )
                                    if candidate.get("copy_audit_sha256") != expected_audit:
                                        raise ValueError("issuer copy intent")
                            witness_sha256 = _issuer_witness_sha256(
                                root_record=root_record,
                                target_parent_identity=(
                                    cast(int, bound_identity["target_parent_dev"]),
                                    cast(int, bound_identity["target_parent_ino"]),
                                ),
                                target_basename=str(bound_identity["target_basename"]),
                                target_identity=(
                                    cast(int, bound_identity["target_dev"]),
                                    cast(int, bound_identity["target_ino"]),
                                ),
                            )
                            if committed is not None and committed.witness_sha256 is not None:
                                witness_sha256 = committed.witness_sha256
                    material = {
                        **candidate,
                        "witness_sha256": witness_sha256,
                        "issuer_key_id": key_id,
                    }
                    state_sha256 = _migration_lifecycle_state_sha256(material)
                    material["state_sha256"] = state_sha256
                    material["signature_ed25519"] = private_key.sign(
                        _MIGRATION_LIFECYCLE_SIGNATURE_DOMAIN + bytes.fromhex(state_sha256)
                    )
                    state = SignedMigrationLifecycleStateV1.model_validate(material)
                    if committed is None:
                        _verify_migration_lifecycle_genesis(state, verification_key)
                    else:
                        _verify_migration_lifecycle_transition(committed, state, verification_key)
                    pending_candidate = candidate_bytes
                    pending_state = state
                    _issuer_response(connection, b"S" + _migration_lifecycle_state_document(state))
                    continue
                if command == "commit":
                    if set(request) != {
                        "command",
                        "state_sha256",
                        "target_basename",
                    }:
                        raise ValueError("issuer commit envelope")
                    if len(received_descriptors) != 1:
                        raise ValueError("issuer descriptor roster")
                    descriptor = received_descriptors.pop()
                    requested_hash = request["state_sha256"]
                    target_basename = request["target_basename"]
                    if type(requested_hash) is not str or type(target_basename) is not str:
                        raise ValueError("issuer commit values")
                    if bound_root_fd is None:
                        raise ValueError("issuer unbound commit")
                    state_for_commit = pending_state if pending_state is not None else committed
                    if state_for_commit is None:
                        raise ValueError("issuer commit without state")
                    release_copy_lease = False
                    with _issuer_transition_lock(bound_root_fd):
                        compatible = _issuer_compatible_root_record(
                            bound_root_fd, state_for_commit.lifecycle_phase
                        )
                        if state_for_commit.lifecycle_phase != "schema_only" and (
                            state_for_commit.barrier_id != compatible.get("barrier_id")
                            or state_for_commit.freeze_nonce != compatible.get("freeze_nonce")
                        ):
                            raise ValueError("issuer commit root authority")
                        if state_for_commit.lifecycle_phase in {
                            "sources_sealed",
                            "copy_prepared",
                            "copied_epoch0",
                        }:
                            corpus = _collect_sealed_corpus(
                                _issuer_root_path(bound_root_fd), compatible
                            )
                            if (
                                state_for_commit.source_manifest_sha256
                                != corpus.source_manifest_sha256
                            ):
                                raise ValueError("issuer commit source manifest")
                            if state_for_commit.lifecycle_phase in {
                                "copy_prepared",
                                "copied_epoch0",
                            }:
                                if bound_target_fd is None:
                                    raise ValueError("issuer commit target custody")
                                if target_lease is None:
                                    if pending_state is not None:
                                        raise ValueError("issuer commit target lease")
                                    target_lease = _issuer_acquire_target_lease(bound_target_fd)
                                copy_measure = (
                                    _issuer_copy_intent
                                    if state_for_commit.lifecycle_phase == "copy_prepared"
                                    and not copy_completed
                                    else _issuer_observed_copy
                                )
                                expected_audit = copy_measure(
                                    target_fd=bound_target_fd,
                                    target_lease=target_lease,
                                    corpus=corpus,
                                    provider_capability_verification_keys=provider_capability_verification_keys,
                                    provider_revocation_verification_keys=provider_revocation_verification_keys,
                                    source_head_verification_keys=source_head_verification_keys,
                                    provider_revocation_floor_pins=provider_revocation_floor_pins,
                                    source_floor_pins=source_floor_pins,
                                    expected_target_store_id=state_for_commit.target_store_id,
                                    expected_semantic_source_sha256=expected_semantic_source_sha256,
                                    expected_contract_sha256=expected_contract_sha256,
                                )
                                if state_for_commit.copy_audit_sha256 != expected_audit:
                                    raise ValueError("issuer commit copy intent")
                        durable = _read_signed_migration_lifecycle_state(
                            parent_fd=descriptor,
                            target_basename=target_basename,
                            verification_key=verification_key,
                        )
                        if pending_state is None:
                            if committed is None or requested_hash != committed.state_sha256:
                                raise ValueError("issuer commit without pending")
                            if durable != committed:
                                raise ValueError("issuer committed replay mismatch")
                        else:
                            if (
                                requested_hash != pending_state.state_sha256
                                or durable != pending_state
                            ):
                                raise ValueError("issuer durable commit mismatch")
                            committed = pending_state
                            pending_candidate = None
                            pending_state = None
                        release_copy_lease = state_for_commit.lifecycle_phase == "copied_epoch0"
                    if release_copy_lease:
                        if target_lease is None:
                            raise ValueError("issuer committed target lease")
                        _issuer_release_target_lease(target_lease)
                        target_lease = None
                    _issuer_response(connection, b"A" + requested_hash.encode("ascii"))
                    continue
                raise ValueError("issuer command")
            except Exception:
                if (
                    target_lease is not None
                    and pending_state is None
                    and (committed is None or committed.lifecycle_phase != "copy_prepared")
                ):
                    _issuer_release_target_lease(target_lease)
                    target_lease = None
                _issuer_response(connection, b"E")
            finally:
                if descriptor is not None:
                    os.close(descriptor)
                for unexpected_descriptor in received_descriptors:
                    os.close(unexpected_descriptor)
                connection.close()
    finally:
        handshake.close()
        process_watch.close()
        if target_lease is not None:
            _issuer_release_target_lease(target_lease)
        if bound_root_fd is not None:
            fcntl.flock(bound_root_fd, fcntl.LOCK_UN)
            os.close(bound_root_fd)
        if bound_target_fd is not None:
            os.close(bound_target_fd)
        listener.close()
        Path(socket_path).unlink(missing_ok=True)


class FixtureMigrationLifecycleIssuerV1:
    _boot_nonce: bytes
    _creator_pid: int
    _lock: threading.Lock
    _process: BaseProcess
    _socket_path: str
    _socket_root: Path
    recovery_ticket: SignedMigrationRecoveryTicketV1
    verification_key: VerificationKeyV1

    __slots__ = (
        "_boot_nonce",
        "_creator_pid",
        "_lock",
        "_process",
        "_socket_path",
        "_socket_root",
        "recovery_ticket",
        "verification_key",
    )

    def __init_subclass__(cls, **kwargs: object) -> Never:
        del cls, kwargs
        raise TypeError("fixture migration lifecycle issuer is final")

    @classmethod
    def spawn(
        cls,
        *,
        root_fd: int,
        parent_fd: int,
        target_basename: str,
        provider_capability_verification_keys: tuple[VerificationKeyV1, ...],
        provider_revocation_verification_keys: tuple[VerificationKeyV1, ...],
        source_head_verification_keys: tuple[VerificationKeyV1, ...],
        provider_revocation_floor_pins: tuple[ProviderRevocationFloorPinV1, ...],
        source_floor_pins: tuple[OwnerPrivateSourceFloorPinV1, ...],
        expected_target_store_id: str,
        expected_semantic_source_sha256: str,
        expected_contract_sha256: str,
    ) -> FixtureMigrationLifecycleIssuerV1:
        context = multiprocessing.get_context("spawn")
        receive_handshake, send_handshake = context.Pipe(duplex=False)
        socket_root = Path(tempfile.mkdtemp(prefix="antiek-issuer-"))
        socket_root.chmod(0o700)
        socket_path = os.fspath(socket_root / _ISSUER_WITNESS_SOCKET_NAME)
        process = context.Process(
            target=_fixture_migration_lifecycle_issuer_main,
            args=(
                socket_path,
                os.getpid(),
                send_handshake,
                provider_capability_verification_keys,
                provider_revocation_verification_keys,
                source_head_verification_keys,
                provider_revocation_floor_pins,
                source_floor_pins,
                expected_target_store_id,
                expected_semantic_source_sha256,
                expected_contract_sha256,
            ),
            daemon=True,
        )
        try:
            process.start()
            send_handshake.close()
            if not receive_handshake.poll(5):
                raise TimeoutError("issuer handshake timeout")
            handshake = receive_handshake.recv()
            if (
                type(handshake) is not tuple
                or len(handshake) != 2
                or type(handshake[0]) is not str
                or type(handshake[1]) is not bytes
            ):
                raise ValueError("issuer handshake")
            key_id, public_key = handshake
            if len(public_key) != 32:
                raise ValueError("issuer public key")
        except Exception:
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
            (socket_root / _ISSUER_WITNESS_SOCKET_NAME).unlink(missing_ok=True)
            socket_root.rmdir()
            raise
        finally:
            receive_handshake.close()
            send_handshake.close()
        issuer = object.__new__(cls)
        object.__setattr__(issuer, "_boot_nonce", secrets.token_bytes(32))
        object.__setattr__(issuer, "_creator_pid", os.getpid())
        object.__setattr__(issuer, "_lock", threading.Lock())
        object.__setattr__(issuer, "_process", process)
        object.__setattr__(issuer, "_socket_path", socket_path)
        object.__setattr__(issuer, "_socket_root", socket_root)
        object.__setattr__(
            issuer,
            "verification_key",
            VerificationKeyV1(key_id=key_id, public_key_bytes=public_key),
        )
        bind_request = _canonical_json({"command": "bind", "target_basename": target_basename})
        try:
            bind_response = issuer._request(bind_request, (root_fd, parent_fd))
            if bind_response[:1] != b"B":
                raise ValueError("issuer bind response")
            parsed_ticket = _parse_strict_json(bind_response[1:], _ISSUER_MAX_PACKET)
            signature_hex = parsed_ticket.get("signature_ed25519")
            if type(signature_hex) is not str:
                raise ValueError("issuer recovery ticket signature")
            recovery_ticket = SignedMigrationRecoveryTicketV1.model_validate(
                {**parsed_ticket, "signature_ed25519": bytes.fromhex(signature_hex)}
            )
            _verify_signed_migration_recovery_ticket(recovery_ticket, issuer.verification_key)
        except Exception:
            issuer.close()
            raise
        object.__setattr__(issuer, "recovery_ticket", recovery_ticket)
        return issuer

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise AttributeError("fixture migration lifecycle issuer is immutable")

    def __reduce__(self) -> Never:
        raise TypeError("fixture migration lifecycle issuer is process-bound")

    def __copy__(self) -> Never:
        raise TypeError("fixture migration lifecycle issuer cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("fixture migration lifecycle issuer cannot be copied")

    def _validate_client(self) -> None:
        if self._creator_pid != os.getpid() or len(self._boot_nonce) != 32:
            raise ValueError("issuer client process mismatch")

    @property
    def process_id(self) -> int:
        self._validate_client()
        pid = self._process.pid
        if type(pid) is not int:
            raise ValueError("issuer process unavailable")
        return pid

    def _request(self, request: bytes, descriptors: tuple[int, ...] = ()) -> bytes:
        self._validate_client()
        if len(request) > _ISSUER_MAX_PACKET or len(descriptors) > 3:
            raise ValueError("issuer request bound")
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(5.0)
        try:
            connection.connect(self._socket_path)
            issuer_pid = self._process.pid
            if (
                type(issuer_pid) is not int
                or struct.unpack("i", connection.getsockopt(0, 2, 4))[0] != issuer_pid
            ):
                raise ValueError("issuer server pid mismatch")
            ancillary: list[tuple[int, int, bytes]] = []
            if descriptors:
                rights = array("i", descriptors)
                ancillary.append((socket.SOL_SOCKET, socket.SCM_RIGHTS, rights.tobytes()))
            sent = connection.sendmsg([request], ancillary)
            if sent != len(request):
                raise OSError("short issuer request")
            connection.shutdown(socket.SHUT_WR)
            response_parts: list[bytes] = []
            total = 0
            while chunk := connection.recv(65_536):
                total += len(chunk)
                if total > _ISSUER_MAX_PACKET:
                    raise ValueError("issuer response bound")
                response_parts.append(chunk)
            response = b"".join(response_parts)
        finally:
            connection.close()
        if not response or response[:1] == b"E":
            raise ValueError("fixture migration lifecycle issuer rejected")
        return response

    def reserve(self, candidate: Mapping[str, object]) -> SignedMigrationLifecycleStateV1:
        self._validate_client()
        if set(candidate) != _ISSUER_CANDIDATE_FIELDS:
            raise ValueError("issuer candidate fields")
        request = _canonical_json({"command": "reserve", "candidate": dict(candidate)})
        if len(request) > _ISSUER_MAX_PACKET:
            raise ValueError("issuer request bound")
        with self._lock:
            response = self._request(request)
        if response[:1] != b"S":
            raise ValueError("issuer reserve response")
        state = _parse_migration_lifecycle_state_document(response[1:], self.verification_key)
        returned_candidate = state.model_dump(
            mode="python",
            exclude={
                "issuer_key_id",
                "state_sha256",
                "signature_ed25519",
                "witness_sha256",
            },
        )
        if returned_candidate != dict(candidate):
            raise ValueError("issuer reserve correlation mismatch")
        return state

    def commit(self, *, state: SignedMigrationLifecycleStateV1, parent_fd: int) -> None:
        self._validate_client()
        if type(state) is not SignedMigrationLifecycleStateV1:
            raise ValueError("issuer commit state")
        request = _canonical_json(
            {
                "command": "commit",
                "state_sha256": state.state_sha256,
                "target_basename": state.target_basename,
            }
        )
        with self._lock:
            response = self._request(request, (parent_fd,))
        if response != b"A" + state.state_sha256.encode("ascii"):
            raise ValueError("issuer commit response")

    def copy_epoch0(
        self,
        *,
        prepared_state: SignedMigrationLifecycleStateV1,
        test_post_commit_pause_ms: int = 0,
    ) -> bool:
        self._validate_client()
        if (
            type(prepared_state) is not SignedMigrationLifecycleStateV1
            or prepared_state.lifecycle_phase != "copy_prepared"
            or prepared_state.copy_audit_sha256 is None
            or type(test_post_commit_pause_ms) is not int
            or not 0 <= test_post_commit_pause_ms <= 1_000
        ):
            raise ValueError("issuer copy prepared state")
        request = _canonical_json(
            {
                "command": "copy_epoch0",
                "prepared_state_sha256": prepared_state.state_sha256,
                "test_post_commit_pause_ms": test_post_commit_pause_ms,
            }
        )
        with self._lock:
            response = self._request(request)
        expected_prefix = b"Y" + prepared_state.copy_audit_sha256.encode("ascii")
        if response not in {expected_prefix + b"0", expected_prefix + b"1"}:
            raise ValueError("issuer copy response")
        return response[-1:] == b"1"

    def recover_open(
        self,
        *,
        root_fd: int,
        parent_fd: int,
        target_fd: int,
        authority_pins: Epoch0RecoveryAuthorityPinsV1,
        caller_boot_nonce: str,
        handle_nonce: str,
    ) -> SignedEpoch0RecoveryAdmissionV1:
        self._validate_client()
        if (
            type(authority_pins) is not Epoch0RecoveryAuthorityPinsV1
            or not re.fullmatch(r"[0-9a-f]{64}", caller_boot_nonce)
            or not re.fullmatch(r"[0-9a-f]{64}", handle_nonce)
        ):
            raise ValueError("issuer recovery open values")
        request = _canonical_json(
            {
                "command": "recover_open",
                "ticket_sha256": self.recovery_ticket.ticket_sha256,
                "issuer_generation_nonce": self.recovery_ticket.issuer_generation_nonce,
                "caller_boot_nonce": caller_boot_nonce,
                "handle_nonce": handle_nonce,
                "authority_pins": authority_pins.model_dump(mode="json"),
            }
        )
        with self._lock:
            response = self._request(request, (root_fd, parent_fd, target_fd))
        if response[:1] != b"R":
            raise ValueError("issuer recovery admission response")
        parsed = _parse_strict_json(response[1:], _ISSUER_MAX_PACKET)
        signature_hex = parsed.get("signature_ed25519")
        if type(signature_hex) is not str:
            raise ValueError("issuer recovery admission signature")
        admission = SignedEpoch0RecoveryAdmissionV1.model_validate(
            {**parsed, "signature_ed25519": bytes.fromhex(signature_hex)}
        )
        _verify_signed_epoch0_recovery_admission(admission, self.verification_key)
        if (
            admission.ticket_sha256 != self.recovery_ticket.ticket_sha256
            or admission.issuer_generation_nonce != self.recovery_ticket.issuer_generation_nonce
            or admission.authenticated_peer_pid != os.getpid()
            or admission.caller_boot_nonce != caller_boot_nonce
            or admission.handle_nonce != handle_nonce
            or admission.authority_pins != authority_pins
        ):
            raise ValueError("issuer recovery admission correlation")
        return admission

    def close(self) -> None:
        self._validate_client()
        with self._lock:
            try:
                if self._process.is_alive():
                    response = self._request(_canonical_json({"command": "close"}))
                    if response != b"C":
                        raise ValueError("issuer close response")
            finally:
                self._process.join(timeout=5)
                if self._process.is_alive():
                    self._process.terminate()
                    self._process.join(timeout=5)
                (self._socket_root / _ISSUER_WITNESS_SOCKET_NAME).unlink(missing_ok=True)
                self._socket_root.rmdir()


_MIGRATION_ROW_MODELS: dict[str, type[BaseModel]] = {
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
_MIGRATION_ROW_KEY_FIELDS = {
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


def _child_path(root: Path, role: str) -> Path:
    return root / "children" / f"{role}.sqlite3"


def _contract_role(role: str) -> str:
    return role.replace("-", "_")


def _owned_child_tables(role: str) -> tuple[str, ...]:
    return tuple(
        table
        for table in _MIGRATION_ROLE_SCHEMA_TABLES[_contract_role(role)]
        if table not in {"adapter_state", "mutator_attempts"}
    )


def _initialize_child_adapters(
    root: Path, *, typed_rows: dict[str, tuple[BaseModel, ...]] | None = None
) -> dict[str, object]:
    supplied = {} if typed_rows is None else dict(typed_rows)
    if set(supplied) - set(_MIGRATION_ROW_MODELS):
        raise ValueError("unknown typed migration collection")
    children = root / "children"
    children.mkdir(mode=0o700)
    result: dict[str, object] = {}
    for role in _CHILD_ROLES:
        path = _child_path(root, role)
        if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise ValueError("child adapter sidecar remains")
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA user_version=1")
            connection.executescript(_migration_role_schema_sql(_contract_role(role)))
            connection.execute("INSERT INTO adapter_state VALUES(1,1,1,0,0,1)")
            for table in _owned_child_tables(role):
                connection.execute(
                    f'INSERT INTO "{table}"(id,payload) VALUES(?,?)',
                    ("__sentinel__", b"sentinel"),
                )
                model_type = _MIGRATION_ROW_MODELS.get(table)
                if model_type is None:
                    if supplied.get(table):
                        raise ValueError("non-migration table rows supplied")
                    continue
                rows = supplied.get(table, ())
                key_fields = _MIGRATION_ROW_KEY_FIELDS[table]
                typed = tuple(model_type.model_validate(row) for row in rows)
                keys = tuple(tuple(getattr(row, field) for field in key_fields) for row in typed)
                if keys != tuple(sorted(set(keys))):
                    raise ValueError("typed migration rows not canonical")
                for row in typed:
                    connection.execute(
                        f'INSERT INTO "{table}"(id,payload) VALUES(?,?)',
                        (
                            _migration_row_sha256(table, row),
                            _canonical_json(_migration_encode(row)),
                        ),
                    )
            connection.commit()
        finally:
            connection.close()
        path.chmod(0o600)
        result[role] = os.fspath(path.relative_to(root))
    return result


def _decode_child_rows(connection: sqlite3.Connection, table: str) -> tuple[BaseModel, ...]:
    model_type = _MIGRATION_ROW_MODELS[table]
    key_fields = _MIGRATION_ROW_KEY_FIELDS[table]
    decoded: list[BaseModel] = []
    for stored_id, payload in connection.execute(
        f'SELECT id,payload FROM "{table}" WHERE id != ?', ("__sentinel__",)
    ):
        if type(stored_id) is not str or type(payload) is not bytes:
            raise ValueError("typed child row storage mismatch")

        def decode(value: object) -> object:
            if (
                type(value) is list
                and len(value) == 2
                and value[0] == "blob"
                and type(value[1]) is str
            ):
                return bytes.fromhex(value[1])
            if type(value) is list:
                return [decode(item) for item in value]
            if type(value) is dict:
                return {str(key): decode(item) for key, item in value.items()}
            return value

        row = model_type.model_validate(decode(json.loads(payload)))
        if payload != _canonical_json(_migration_encode(row)):
            raise ValueError("typed child row encoding mismatch")
        if stored_id != _migration_row_sha256(table, row):
            raise ValueError("typed child row id mismatch")
        decoded.append(row)
    rows = tuple(sorted(decoded, key=lambda row: tuple(getattr(row, key) for key in key_fields)))
    keys = tuple(tuple(getattr(row, field) for field in key_fields) for row in rows)
    if keys != tuple(sorted(set(keys))):
        raise ValueError("typed child row key collision")
    return rows


def _extract_child_migration_rows(root: Path) -> dict[str, tuple[BaseModel, ...]]:
    extracted: dict[str, tuple[BaseModel, ...]] = {}
    for role in _CHILD_ROLES:
        connection = sqlite3.connect(
            f"file:{_child_path(root, role)}?mode=ro&immutable=1", uri=True
        )
        try:
            for table in _owned_child_tables(role):
                if table in _MIGRATION_ROW_MODELS:
                    extracted[table] = _decode_child_rows(connection, table)
        finally:
            connection.close()
    if set(extracted) != set(_MIGRATION_ROW_MODELS):
        raise ValueError("typed child collection roster mismatch")
    return extracted


def _measure_child_adapters(root: Path) -> dict[str, object]:
    measurements: dict[str, object] = {}
    for role in _CHILD_ROLES:
        path = _child_path(root, role)
        if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise ValueError("child adapter sidecar remains")
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or info.st_mode & 0o777 != 0o600
        ):
            raise ValueError("child adapter identity mismatch")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            header = os.read(descriptor, 20)
        finally:
            os.close(descriptor)
        if len(header) != 20 or header[18:20] != b"\x02\x02":
            raise ValueError("child adapter WAL pragma mismatch")
        uri = f"file:{path}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            if connection.execute("PRAGMA user_version").fetchone() != (1,):
                raise ValueError("child adapter user version mismatch")
            sql = [
                list(row)
                for row in connection.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master "
                    "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
                )
            ]
            state_row = connection.execute(
                "SELECT admission_enabled,writer_enabled,active_invocations,"
                "open_accounting_cents,version FROM adapter_state WHERE singleton=1"
            ).fetchone()
            state = None if state_row is None else list(state_row)
            probes = [
                list(row)
                for row in connection.execute(
                    "SELECT name,planted_at FROM mutator_attempts ORDER BY name"
                )
            ]
            row_counts = []
            ordered_role_rows: list[list[str]] = []
            for table in _owned_child_tables(role):
                if table in _MIGRATION_ROW_MODELS:
                    rows = _decode_child_rows(connection, table)
                    row_counts.append([table, len(rows)])
                    ordered_role_rows.extend(
                        [table, _migration_row_sha256(table, row)] for row in rows
                    )
                else:
                    count_row = connection.execute(
                        f'SELECT COUNT(*) FROM "{table}" WHERE id != ?', ("__sentinel__",)
                    ).fetchone()
                    if count_row is None:
                        raise ValueError("child row count unavailable")
                    row_counts.append([table, int(count_row[0])])
            actual_schema_sha256 = _migration_role_schema_sha256_from_connection(
                connection,
                _contract_role(role),
                required_pragmas={
                    "foreign_keys": 1,
                    "journal_mode": "wal",
                    "trusted_schema": 0,
                    "user_version": 1,
                },
            )
        finally:
            connection.close()
        contract_role = _contract_role(role)
        if actual_schema_sha256 != _migration_role_schema_sha256(contract_role):
            raise ValueError("child adapter schema drift")
        role_bytes = contract_role.encode()
        ordered_rows_sha256 = hashlib.sha256(
            _SOURCE_STORE_ROWS_DOMAIN
            + len(role_bytes).to_bytes(4, "big")
            + role_bytes
            + _canonical_json(ordered_role_rows)
        ).hexdigest()
        material = {
            "role": role,
            "sql": sql,
            "state": state,
            "probes": probes,
            "schema_sha256": actual_schema_sha256,
            "final_version": None if state is None else state[4],
            "row_counts": row_counts,
            "ordered_rows_sha256": ordered_rows_sha256,
        }
        measurements[role] = {
            **material,
            "measurement_sha256": hashlib.sha256(_canonical_json(material)).hexdigest(),
        }
    return measurements


def _audit_child_phase(record: dict[str, object], measured: dict[str, object]) -> None:
    state = record.get("state")
    versions = {
        "open": 1,
        "quiesced": 1,
        "admission_denied": 2,
        "drained": 3,
        "writers_revoked": 4,
        "writers_verified": 5,
        "sealed": 6,
        "legacy_read_only": 6,
    }
    expected_version = versions.get(state) if isinstance(state, str) else None
    if expected_version is None:
        return
    for role in _CHILD_ROLES:
        role_measurement = measured.get(role)
        if type(role_measurement) is not dict:
            raise ValueError("child phase measurement missing")
        child_state = role_measurement.get("state")
        expected_admission = 0 if role == "paid-lane-fixture-v1" and expected_version >= 2 else 1
        expected_writer = 0 if expected_version >= 4 else 1
        if child_state != [expected_admission, expected_writer, 0, 0, expected_version]:
            raise ValueError("child phase state mismatch")


def _durable_write_json(path: Path, value: dict[str, object]) -> None:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short durable write")
            view = view[written:]
        os.fsync(descriptor)
        os.replace(temporary, path)
    finally:
        os.close(descriptor)
        temporary.unlink(missing_ok=True)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _secure_support_root(path: Path, *, create: bool) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("support root must be absolute and nonsymlinked")
    if create:
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
    resolved = path.resolve(strict=True)
    root_info = resolved.stat()
    if resolved != path or (root_info.st_mode & 0o777) != 0o700 or root_info.st_uid != os.getuid():
        raise ValueError("support root identity or mode mismatch")
    for orphan in resolved.glob(".*.tmp"):
        info = orphan.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("invalid crash temporary")
        orphan.unlink()
    return resolved


def _read_json_audited(path: Path) -> dict[str, object]:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or (info.st_mode & 0o777) != 0o600
        or info.st_uid != os.getuid()
    ):
        raise ValueError("durable state file identity mismatch")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError("durable state changed during open")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 65536):
            chunks.append(chunk)
        value = json.loads(b"".join(chunks).decode("utf-8"))
    finally:
        os.close(descriptor)
    if type(value) is not dict:
        raise ValueError("durable state shape mismatch")
    return value


def _append_transition_evidence(
    record: dict[str, object], *, operation: str, prior_state: str, next_state: str
) -> None:
    evidence = record.get("transition_evidence")
    if type(evidence) is not list:
        raise ValueError("transition evidence mismatch")
    prior_hash = "0" * 64 if not evidence else evidence[-1]["evidence_sha256"]
    material = {
        "root_manifest_sha256": record["root_manifest_sha256"],
        "inventory_sha256": record["inventory_sha256"],
        "barrier_id": record["barrier_id"],
        "freeze_nonce": record["freeze_nonce"],
        "operation": operation,
        "prior_state": prior_state,
        "next_state": next_state,
        "prior_evidence_sha256": prior_hash,
        "writer_inventory": record["writer_inventory"],
        "source_store_identities": record["source_store_identities"],
        "measured_state_sha256": hashlib.sha256(
            _canonical_json(record["child_adapter_evidence"])
        ).hexdigest(),
    }
    evidence.append(
        {
            **material,
            "evidence_sha256": hashlib.sha256(_canonical_json(material)).hexdigest(),
        }
    )


def _audit_transition_evidence(record: dict[str, object]) -> None:
    evidence = record.get("transition_evidence")
    if type(evidence) is not list:
        raise ValueError("transition evidence shape")
    legal = (
        ("acquire_writer_barrier", "open", "quiesced"),
        ("deny_new_admission", "quiesced", "admission_denied"),
        ("drain_terminal_only", "admission_denied", "drained"),
        ("close_and_revoke_all_writers", "drained", "writers_revoked"),
        ("checkpoint_and_plant_test_all_mutators", "writers_revoked", "writers_verified"),
        ("seal_and_collect", "writers_verified", "sealed"),
        ("revalidate_sealed_sources", "sealed", "sealed"),
        ("mark_legacy_read_only", "sealed", "legacy_read_only"),
    )
    prior_hash = "0" * 64
    expected_index = 0
    for index, item in enumerate(evidence):
        if type(item) is not dict:
            raise ValueError("transition evidence item")
        material = {key: value for key, value in item.items() if key != "evidence_sha256"}
        expected = hashlib.sha256(_canonical_json(material)).hexdigest()
        if (
            material.get("prior_evidence_sha256") != prior_hash
            or item.get("evidence_sha256") != expected
            or material.get("root_manifest_sha256") != record.get("root_manifest_sha256")
            or material.get("inventory_sha256") != record.get("inventory_sha256")
            or material.get("barrier_id") != record.get("barrier_id")
            or material.get("freeze_nonce") != record.get("freeze_nonce")
        ):
            raise ValueError("transition evidence hash")
        operation = material.get("operation")
        transition = (
            operation,
            material.get("prior_state"),
            material.get("next_state"),
        )
        abort_release = (
            index == len(evidence) - 1
            and operation == "release_after_authenticated_abort"
            and transition[1] == ("open" if expected_index == 0 else legal[expected_index - 1][2])
            and transition[2] == "released"
        )
        ready_release = (
            expected_index == len(legal)
            and index == len(evidence) - 1
            and operation == "release_after_ready"
            and transition[1:] == ("legacy_read_only", "released")
        )
        if expected_index < len(legal) and transition == legal[expected_index]:
            expected_index += 1
        elif abort_release or ready_release:
            pass
        else:
            raise ValueError("illegal transition evidence sequence")
        prior_hash = expected
    expected_state = "open" if not evidence else evidence[-1]["next_state"]
    if record.get("state") != expected_state:
        raise ValueError("durable state/evidence mismatch")
    if (
        evidence
        and evidence[-1].get("measured_state_sha256")
        != hashlib.sha256(_canonical_json(record.get("child_adapter_evidence"))).hexdigest()
    ):
        raise ValueError("terminal transition measurement mismatch")
    revalidated = expected_index >= 7
    if record.get("sealed_sources_revalidated") is not revalidated:
        raise ValueError("sealed revalidation flag mismatch")
    if record.get("migration_aborted") is True and (
        not evidence or evidence[-1].get("operation") != "release_after_authenticated_abort"
    ):
        raise ValueError("abort release evidence mismatch")


def _execute_synthetic_transition(root: Path, record: dict[str, object], operation: str) -> None:
    evidence = record.get("child_adapter_evidence")
    if type(evidence) is not dict:
        raise ValueError("child adapter evidence missing")
    paths = tuple(_child_path(root, role) for role in _CHILD_ROLES)
    if operation == "deny_new_admission":
        for role, path in zip(_CHILD_ROLES, paths, strict=True):
            connection = sqlite3.connect(path)
            try:
                if role == "paid-lane-fixture-v1":
                    changed = connection.execute(
                        "UPDATE adapter_state SET admission_enabled=0,version=version+1 "
                        "WHERE singleton=1 AND admission_enabled=1"
                    ).rowcount
                    if changed != 1:
                        raise ValueError("admission already denied")
                    try:
                        connection.execute(
                            "INSERT INTO paid_admissions(id,payload) VALUES('denied',X'00')"
                        )
                    except sqlite3.IntegrityError as error:
                        if "admission denied" not in str(error):
                            raise
                    else:
                        raise ValueError("denied admission accepted")
                else:
                    connection.execute(
                        "UPDATE adapter_state SET version=version+1 WHERE singleton=1"
                    )
                connection.commit()
            finally:
                connection.close()
        evidence["admission_denied"] = True
    elif operation == "drain_terminal_only":
        for role, path in zip(_CHILD_ROLES, paths, strict=True):
            connection = sqlite3.connect(path)
            try:
                row = connection.execute(
                    "SELECT active_invocations,open_accounting_cents FROM adapter_state"
                ).fetchone()
                zero_only_rows = 0
                if role == "paid-lane-fixture-v1":
                    result = connection.execute(
                        "SELECT COUNT(*) FROM paid_admissions WHERE id != ?", ("__sentinel__",)
                    ).fetchone()
                    if result is None:
                        raise ValueError("paid admission drain count unavailable")
                    zero_only_rows = int(result[0])
                if row == (0, 0) and zero_only_rows == 0:
                    connection.execute(
                        "UPDATE adapter_state SET version=version+1 WHERE singleton=1"
                    )
                    connection.commit()
            finally:
                connection.close()
            if row != (0, 0) or zero_only_rows != 0:
                raise ValueError("child work not drained")
        evidence["drain_verified"] = True
    elif operation == "close_and_revoke_all_writers":
        for path in paths:
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "UPDATE adapter_state SET writer_enabled=0,version=version+1 "
                    "WHERE singleton=1 AND writer_enabled=1"
                )
                connection.commit()
            finally:
                connection.close()
        evidence["writers_revoked"] = True
    elif operation == "checkpoint_and_plant_test_all_mutators":
        rejected: list[str] = []
        for role, path in zip(_CHILD_ROLES, paths, strict=True):
            connection = sqlite3.connect(path)
            try:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                for table in _owned_child_tables(role):
                    mutations = (
                        (
                            "insert",
                            f'INSERT INTO "{table}"(id,payload) VALUES(?,?)',
                            ("plant", b"plant"),
                        ),
                        (
                            "update",
                            f'UPDATE "{table}" SET payload=? WHERE id=?',
                            (b"changed", "__sentinel__"),
                        ),
                        ("delete", f'DELETE FROM "{table}" WHERE id=?', ("__sentinel__",)),
                    )
                    for mutation, sql, parameters in mutations:
                        try:
                            connection.execute(sql, parameters)
                        except sqlite3.IntegrityError as error:
                            if "writer revoked" not in str(error):
                                raise
                            rejected.append(f"{role}:{table}:{mutation}")
                        else:
                            raise ValueError("revoked child mutator accepted")
                connection.execute("UPDATE adapter_state SET version=version+1 WHERE singleton=1")
                connection.commit()
            finally:
                connection.close()
        evidence["planted_mutator_rejections"] = rejected
    elif operation == "seal_and_collect":
        expected_rejections = [
            f"{role}:{table}:{mutation}"
            for role in _CHILD_ROLES
            for table in _owned_child_tables(role)
            for mutation in ("insert", "update", "delete")
        ]
        if evidence.get("planted_mutator_rejections") != expected_rejections:
            raise ValueError("child mutator proof roster mismatch")
        for path in paths:
            connection = sqlite3.connect(path)
            try:
                checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                state = connection.execute(
                    "SELECT admission_enabled,writer_enabled,active_invocations,"
                    "open_accounting_cents FROM adapter_state WHERE singleton=1"
                ).fetchone()
                probes = connection.execute("SELECT COUNT(*) FROM mutator_attempts").fetchone()
                version = connection.execute(
                    "SELECT version FROM adapter_state WHERE singleton=1"
                ).fetchone()
                if version != (_MIGRATION_CHILD_FINAL_VERSION - 1,):
                    raise ValueError("child adapter pre-seal version mismatch")
                connection.execute("UPDATE adapter_state SET version=version+1 WHERE singleton=1")
                connection.commit()
            finally:
                connection.close()
            if checkpoint != (0, 0, 0) or state is None or state[1:] != (0, 0, 0) or probes != (0,):
                raise ValueError("child adapter is not sealed")
            if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
                raise ValueError("child adapter sidecar remains")
        evidence["sealed_measurements"] = _measure_child_adapters(root)


@contextmanager
def _exclusive_root_lock(root: Path, *, timeout_ms: int = 5000) -> Iterator[None]:
    lock_path = root / ".migration.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or (info.st_mode & 0o777) != 0o600
            or info.st_uid != os.getuid()
        ):
            raise ValueError("lock identity mismatch")
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("migration lock acquisition timed out") from None
                time.sleep(0.005)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


class QuarantinedSyntheticWriterBarrierV1:
    _boot_nonce: bytes
    _creator_pid: int
    _root_path: Path
    acquired_at_ms: int
    barrier_id: str
    freeze_nonce: str
    inventory_sha256: str
    root_id: str
    root_manifest_sha256: str
    schema_version: Literal[1]
    state: str

    __slots__ = (
        "_boot_nonce",
        "_creator_pid",
        "_root_path",
        "acquired_at_ms",
        "barrier_id",
        "freeze_nonce",
        "inventory_sha256",
        "root_id",
        "root_manifest_sha256",
        "schema_version",
        "state",
    )

    _NEXT = {
        "quiesced": ("deny_new_admission", "admission_denied"),
        "admission_denied": ("drain_terminal_only", "drained"),
        "drained": ("close_and_revoke_all_writers", "writers_revoked"),
        "writers_revoked": (
            "checkpoint_and_plant_test_all_mutators",
            "writers_verified",
        ),
        "writers_verified": ("seal_and_collect", "sealed"),
        "sealed": ("mark_legacy_read_only", "legacy_read_only"),
        "legacy_read_only": ("release_after_ready", "released"),
    }

    def __init_subclass__(cls, **kwargs: object) -> Never:
        del cls, kwargs
        raise TypeError("synthetic writer barrier is final")

    def __init__(self, *, root_path: Path, record: dict[str, object]) -> None:
        acquired_at_ms = record["acquired_at_ms"]
        if type(acquired_at_ms) is not int:
            raise ValueError("barrier acquisition timestamp mismatch")
        object.__setattr__(self, "_root_path", root_path)
        object.__setattr__(self, "_creator_pid", os.getpid())
        object.__setattr__(self, "_boot_nonce", secrets.token_bytes(32))
        object.__setattr__(self, "schema_version", 1)
        object.__setattr__(self, "acquired_at_ms", acquired_at_ms)
        object.__setattr__(self, "root_id", str(record["root_id"]))
        object.__setattr__(self, "root_manifest_sha256", str(record["root_manifest_sha256"]))
        object.__setattr__(self, "barrier_id", str(record["barrier_id"]))
        object.__setattr__(self, "inventory_sha256", str(record["inventory_sha256"]))
        object.__setattr__(self, "freeze_nonce", str(record["freeze_nonce"]))
        object.__setattr__(self, "state", str(record["state"]))

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise AttributeError("synthetic writer barrier is immutable")

    def __reduce__(self) -> Never:
        raise TypeError("synthetic writer barrier is process-bound")

    def _transition(self, operation: str) -> None:
        if self._creator_pid != os.getpid() or len(self._boot_nonce) != 32:
            raise ValueError("barrier process mismatch")
        expected = self._NEXT.get(self.state)
        if expected is None or expected[0] != operation:
            raise ValueError("barrier transition mismatch")
        state_path = self._root_path / _SUPPORT_ROOT_STATE
        with _exclusive_root_lock(self._root_path):
            record = _read_json_audited(state_path)
            if record["state"] != self.state or record["barrier_id"] != self.barrier_id:
                raise ValueError("durable barrier mismatch")
            _audit_transition_evidence(record)
            _execute_synthetic_transition(self._root_path, record, operation)
            _append_transition_evidence(
                record, operation=operation, prior_state=self.state, next_state=expected[1]
            )
            record["state"] = expected[1]
            _durable_write_json(state_path, record)
        object.__setattr__(self, "state", expected[1])

    def deny_new_admission(self) -> None:
        self._transition("deny_new_admission")

    def drain_terminal_only(self) -> None:
        self._transition("drain_terminal_only")

    def close_and_revoke_all_writers(self) -> None:
        self._transition("close_and_revoke_all_writers")

    def checkpoint_and_plant_test_all_mutators(self) -> None:
        self._transition("checkpoint_and_plant_test_all_mutators")

    def seal_and_collect(self) -> FrozenPaidLaneMigrationCorpusV1:
        self._transition("seal_and_collect")
        record = _read_json_audited(self._root_path / _SUPPORT_ROOT_STATE)
        return _collect_sealed_corpus(self._root_path, record)

    def revalidate_sealed_sources(self) -> None:
        if self.state != "sealed" or self._creator_pid != os.getpid():
            raise ValueError("sealed source revalidation mismatch")
        path = self._root_path / _SUPPORT_ROOT_STATE
        with _exclusive_root_lock(self._root_path):
            record = _read_json_audited(path)
            if record["state"] != "sealed" or record.get("sealed_sources_revalidated") is True:
                raise ValueError("sealed source durable state mismatch")
            evidence = record.get("child_adapter_evidence")
            if type(evidence) is not dict:
                raise ValueError("sealed child evidence missing")
            measured = _measure_child_adapters(self._root_path)
            if measured != evidence.get("sealed_measurements"):
                raise ValueError("sealed source measurement drift")
            record["sealed_sources_revalidated"] = True
            evidence["source_revalidation_sha256"] = hashlib.sha256(
                _canonical_json(measured)
            ).hexdigest()
            _append_transition_evidence(
                record,
                operation="revalidate_sealed_sources",
                prior_state="sealed",
                next_state="sealed",
            )
            _durable_write_json(path, record)

    def mark_legacy_read_only(self) -> None:
        record = _read_json_audited(self._root_path / _SUPPORT_ROOT_STATE)
        if record.get("sealed_sources_revalidated") is not True:
            raise ValueError("sources not revalidated")
        evidence = record.get("child_adapter_evidence")
        if type(evidence) is not dict:
            raise ValueError("sealed child evidence missing")
        measured = _measure_child_adapters(self._root_path)
        _audit_child_phase(record, measured)
        if measured != evidence.get("sealed_measurements"):
            raise ValueError("sealed source measurement drift")
        self._transition("mark_legacy_read_only")

    def release_after_ready(
        self,
        *,
        pinned_store: PrivatePaidLaneEligibilityCheckpointStoreV1,
        external_pin_store: QuarantinedSyntheticExternalPinStoreV1,
        expected_target_store_id: str,
        expected_pin_sha256: str,
        expected_ready_sha256: str,
        expected_root_manifest_sha256: str,
        expected_barrier_id: str,
        expected_freeze_nonce: str,
        expected_source_manifest_sha256: str,
        expected_copy_audit_sha256: str,
        expected_cutover_marker_sha256: str,
        expected_semantic_source_sha256: str,
        expected_contract_sha256: str,
    ) -> None:
        if (
            type(pinned_store) is not PrivatePaidLaneEligibilityCheckpointStoreV1
            or pinned_store.open_mode != "pinned_epoch1"
            or pinned_store.store_id != expected_target_store_id
            or pinned_store.semantic_source_sha256 != expected_semantic_source_sha256
            or pinned_store.contract_sha256 != expected_contract_sha256
        ):
            raise ValueError("genuine pinned runtime required")
        with pinned_store._connect():
            pass
        pin, ready = external_pin_store.load()
        durable = _read_json_audited(self._root_path / _SUPPORT_ROOT_STATE)
        if (
            pin is None
            or ready is None
            or pin.target_store_id != expected_target_store_id
            or pin.pin_sha256 != expected_pin_sha256
            or ready.pin_sha256 != pin.pin_sha256
            or ready.ready_sha256 != expected_ready_sha256
            or ready.legacy_root_id != self.root_id
            or durable["root_manifest_sha256"] != expected_root_manifest_sha256
            or durable["barrier_id"] != expected_barrier_id
            or durable["freeze_nonce"] != expected_freeze_nonce
            or pin.source_manifest_sha256 != expected_source_manifest_sha256
            or pin.copy_audit_sha256 != expected_copy_audit_sha256
            or pin.cutover_marker_sha256 != expected_cutover_marker_sha256
            or pin.semantic_source_sha256 != expected_semantic_source_sha256
            or pin.contract_sha256 != expected_contract_sha256
            or pin.installed_at_ms > ready.ready_at_ms
        ):
            raise ValueError("authenticated readiness mismatch")
        self._transition("release_after_ready")

    def release_after_authenticated_abort(
        self,
        *,
        abort_result: QuarantinedAbortUncutResultV1,
        expected_target_store_id: str,
        expected_target_database_path: Path,
    ) -> None:
        if type(abort_result) is not QuarantinedAbortUncutResultV1:
            raise ValueError("exact abort result required")
        if abort_result.store_id != expected_target_store_id:
            raise ValueError("abort result target mismatch")
        path = self._root_path / _SUPPORT_ROOT_STATE
        with _exclusive_root_lock(self._root_path):
            record = _read_json_audited(path)
            proof = record.get("authenticated_abort_completion")
            expected_proof = {
                "root_id": self.root_id,
                "root_manifest_sha256": self.root_manifest_sha256,
                "barrier_id": self.barrier_id,
                "freeze_nonce": self.freeze_nonce,
                "target_store_id": expected_target_store_id,
                "target_database_path": os.fspath(expected_target_database_path),
                "target_absent": True,
                "sidecars_absent": True,
                "parent_fsynced": True,
                "sources_unchanged": True,
            }
            if (
                self.state == "released"
                or proof != expected_proof
                or expected_target_database_path.exists()
                or any(
                    Path(str(expected_target_database_path) + suffix).exists()
                    for suffix in ("-wal", "-shm", "-journal")
                )
            ):
                raise ValueError("authenticated abort completion unavailable")
            _append_transition_evidence(
                record,
                operation="release_after_authenticated_abort",
                prior_state=self.state,
                next_state="released",
            )
            record["migration_aborted"] = True
            record["state"] = "released"
            _durable_write_json(path, record)
            object.__setattr__(self, "state", "released")


class QuarantinedSyntheticLegacyRootV1:
    __slots__ = ("_boot_nonce", "_creator_pid", "root_path")

    def __init_subclass__(cls, **kwargs: object) -> Never:
        del cls, kwargs
        raise TypeError("synthetic legacy root is final")

    def __init__(self, root_path: Path) -> None:
        self.root_path = root_path
        self._creator_pid = os.getpid()
        self._boot_nonce = secrets.token_bytes(32)

    @classmethod
    def create_new(
        cls,
        *,
        root_path: Path,
        root_id: str,
        writer_inventory: tuple[str, ...],
        source_store_identities: tuple[str, ...],
        now_ms: int,
        typed_rows: dict[str, tuple[BaseModel, ...]] | None = None,
    ) -> QuarantinedSyntheticLegacyRootV1:
        if writer_inventory != _CHILD_ROLES:
            raise ValueError("writer inventory must exactly name child roles")
        if source_store_identities != _CHILD_ROLES:
            raise ValueError("source store identities must exactly name child roles")
        root = _secure_support_root(root_path, create=True)
        inventory_sha256 = hashlib.sha256(_canonical_json(writer_inventory)).hexdigest()
        manifest = {
            "root_id": root_id,
            "writer_inventory": writer_inventory,
            "source_store_identities": source_store_identities,
            "created_at_ms": now_ms,
        }
        record: dict[str, object] = {
            **manifest,
            "inventory_sha256": inventory_sha256,
            "root_manifest_sha256": hashlib.sha256(_canonical_json(manifest)).hexdigest(),
            "barrier_id": None,
            "freeze_nonce": None,
            "state": "open",
            "transition_evidence": [],
            "sealed_sources_revalidated": False,
            "child_adapters": _initialize_child_adapters(root, typed_rows=typed_rows),
            "child_adapter_evidence": {
                "admission_denied": False,
                "drain_verified": False,
                "writers_revoked": False,
                "planted_mutator_rejections": [],
                "sealed_measurements": None,
            },
        }
        _durable_write_json(root / _SUPPORT_ROOT_STATE, record)
        return cls(root)

    @classmethod
    def open_existing(
        cls,
        *,
        root_path: Path,
        expected_root_id: str,
        expected_root_manifest_sha256: str,
        expected_inventory_sha256: str,
    ) -> QuarantinedSyntheticLegacyRootV1:
        root = _secure_support_root(root_path, create=False)
        record = _read_json_audited(root / _SUPPORT_ROOT_STATE)
        _audit_transition_evidence(record)
        expected_children = {
            role: os.fspath(_child_path(root, role).relative_to(root)) for role in _CHILD_ROLES
        }
        if record.get("child_adapters") != expected_children:
            raise ValueError("child adapter roster mismatch")
        measured_children = _measure_child_adapters(root)
        _audit_child_phase(record, measured_children)
        child_evidence = record.get("child_adapter_evidence")
        if type(child_evidence) is not dict:
            raise ValueError("child adapter evidence shape mismatch")
        sealed_measurements = child_evidence.get("sealed_measurements")
        if sealed_measurements is not None and measured_children != sealed_measurements:
            raise ValueError("reopened child measurement drift")
        inventory = record.get("writer_inventory")
        source_identities = record.get("source_store_identities")
        created_at_ms = record.get("created_at_ms")
        if type(inventory) is not list or type(source_identities) is not list:
            raise ValueError("legacy root inventory shape mismatch")
        manifest = {
            "root_id": record.get("root_id"),
            "writer_inventory": inventory,
            "source_store_identities": source_identities,
            "created_at_ms": created_at_ms,
        }
        if (
            record["root_id"] != expected_root_id
            or record["root_manifest_sha256"] != expected_root_manifest_sha256
            or record["inventory_sha256"] != expected_inventory_sha256
            or record["inventory_sha256"] != hashlib.sha256(_canonical_json(inventory)).hexdigest()
            or record["root_manifest_sha256"]
            != hashlib.sha256(_canonical_json(manifest)).hexdigest()
        ):
            raise ValueError("legacy root identity mismatch")
        return cls(root)

    def acquire_writer_barrier(
        self,
        *,
        expected_root_id: str,
        expected_root_manifest_sha256: str,
        expected_inventory_sha256: str,
        timeout_ms: int = 5000,
    ) -> QuarantinedSyntheticWriterBarrierV1:
        if self._creator_pid != os.getpid() or not 0 < timeout_ms <= 5000:
            raise ValueError("legacy root process or timeout mismatch")
        path = self.root_path / _SUPPORT_ROOT_STATE
        with _exclusive_root_lock(self.root_path, timeout_ms=timeout_ms):
            record = _read_json_audited(path)
            if (
                record["state"] != "open"
                or record["root_id"] != expected_root_id
                or record["root_manifest_sha256"] != expected_root_manifest_sha256
                or record["inventory_sha256"] != expected_inventory_sha256
            ):
                raise ValueError("barrier acquisition mismatch")
            record["freeze_nonce"] = secrets.token_hex(32)
            record["barrier_id"] = _migration_barrier_id(str(record["freeze_nonce"]))
            created_at_ms = record["created_at_ms"]
            if type(created_at_ms) is not int:
                raise ValueError("root creation timestamp mismatch")
            record["acquired_at_ms"] = created_at_ms
            _append_transition_evidence(
                record,
                operation="acquire_writer_barrier",
                prior_state="open",
                next_state="quiesced",
            )
            record["state"] = "quiesced"
            _durable_write_json(path, record)
        return QuarantinedSyntheticWriterBarrierV1(root_path=self.root_path, record=record)

    def _audit_unchanged_for_abort(self) -> tuple[str, str, str]:
        if self._creator_pid != os.getpid() or len(self._boot_nonce) != 32:
            raise ValueError("legacy root process mismatch")
        record = _read_json_audited(self.root_path / _SUPPORT_ROOT_STATE)
        _audit_transition_evidence(record)
        measured = _measure_child_adapters(self.root_path)
        _audit_child_phase(record, measured)
        if record.get("state") != "open" or record.get("barrier_id") is not None:
            raise ValueError("legacy root is no longer unchanged")
        return (
            str(record["root_id"]),
            str(record["root_manifest_sha256"]),
            str(record["inventory_sha256"]),
        )

    def reacquire_cutover_barrier(
        self,
        *,
        expected_root_id: str,
        expected_root_manifest_sha256: str,
        expected_barrier_id: str,
        expected_freeze_nonce: str,
        expected_durable_state: str,
        timeout_ms: int = 5000,
    ) -> QuarantinedSyntheticWriterBarrierV1:
        if self._creator_pid != os.getpid() or not 0 < timeout_ms <= 5000:
            raise ValueError("legacy root process or timeout mismatch")
        record = _read_json_audited(self.root_path / _SUPPORT_ROOT_STATE)
        _audit_transition_evidence(record)
        allowed = {
            "quiesced",
            "admission_denied",
            "drained",
            "writers_revoked",
            "writers_verified",
            "sealed",
            "legacy_read_only",
        }
        if (
            expected_durable_state not in allowed
            or record["root_id"] != expected_root_id
            or record["root_manifest_sha256"] != expected_root_manifest_sha256
            or record["barrier_id"] != expected_barrier_id
            or record["freeze_nonce"] != expected_freeze_nonce
            or record["state"] != expected_durable_state
        ):
            raise ValueError("barrier reacquisition mismatch")
        return QuarantinedSyntheticWriterBarrierV1(root_path=self.root_path, record=record)


class QuarantinedSyntheticExternalPinStoreV1:
    __slots__ = ("_boot_nonce", "_creator_pid", "pin_store_id", "root_path")

    def __init__(self, *, root_path: Path, pin_store_id: str) -> None:
        self.root_path = root_path
        self.pin_store_id = pin_store_id
        self._creator_pid = os.getpid()
        self._boot_nonce = secrets.token_bytes(32)

    def __init_subclass__(cls, **kwargs: object) -> Never:
        del cls, kwargs
        raise TypeError("synthetic external pin store is final")

    @property
    def store_id(self) -> str:
        return self.pin_store_id

    @property
    def pin_sha256(self) -> str | None:
        pin, _ = self.load()
        return None if pin is None else pin.pin_sha256

    @property
    def ready_sha256(self) -> str | None:
        _, ready = self.load()
        return None if ready is None else ready.ready_sha256

    def _check_process(self) -> None:
        if self._creator_pid != os.getpid() or len(self._boot_nonce) != 32:
            raise ValueError("pin store process mismatch")

    @classmethod
    def create_new(
        cls, *, root_path: Path, pin_store_id: str
    ) -> QuarantinedSyntheticExternalPinStoreV1:
        root = _secure_support_root(root_path, create=True)
        _durable_write_json(
            root / _SUPPORT_PIN_STATE,
            {"pin_store_id": pin_store_id, "pin": None, "ready": None},
        )
        return cls(root_path=root, pin_store_id=pin_store_id)

    @classmethod
    def open_existing(
        cls, *, root_path: Path, expected_pin_store_id: str
    ) -> QuarantinedSyntheticExternalPinStoreV1:
        root = _secure_support_root(root_path, create=False)
        record = _read_json_audited(root / _SUPPORT_PIN_STATE)
        if record["pin_store_id"] != expected_pin_store_id:
            raise ValueError("pin store identity mismatch")
        instance = cls(root_path=root, pin_store_id=expected_pin_store_id)
        instance.load()
        return instance

    def load(
        self,
    ) -> tuple[
        QuarantinedSyntheticExternalPinRecordV1 | None,
        QuarantinedSyntheticReadyRecordV1 | None,
    ]:
        self._check_process()
        record = _read_json_audited(self.root_path / _SUPPORT_PIN_STATE)
        pin = (
            None
            if record["pin"] is None
            else QuarantinedSyntheticExternalPinRecordV1.model_validate(record["pin"])
        )
        ready = (
            None
            if record["ready"] is None
            else QuarantinedSyntheticReadyRecordV1.model_validate(record["ready"])
        )
        if (
            pin is not None
            and pin.pin_store_id != self.pin_store_id
            or ready is not None
            and (
                pin is None
                or ready.pin_sha256 != pin.pin_sha256
                or ready.ready_at_ms < pin.installed_at_ms
            )
        ):
            raise ValueError("pin ready relationship mismatch")
        return pin, ready

    def install_once(
        self, *, expected_absent: Literal[True], record: QuarantinedSyntheticExternalPinRecordV1
    ) -> None:
        self._check_process()
        if expected_absent is not True or record.pin_store_id != self.pin_store_id:
            raise ValueError("pin install identity mismatch")
        path = self.root_path / _SUPPORT_PIN_STATE
        with _exclusive_root_lock(self.root_path):
            durable = _read_json_audited(path)
            if durable["pin"] is not None:
                raise ValueError("pin already installed")
            durable["pin"] = record.model_dump(mode="json")
            _durable_write_json(path, durable)

    def mark_ready(
        self, *, expected_pin_sha256: str, ready_record: QuarantinedSyntheticReadyRecordV1
    ) -> None:
        self._check_process()
        path = self.root_path / _SUPPORT_PIN_STATE
        with _exclusive_root_lock(self.root_path):
            durable = _read_json_audited(path)
            pin_value = durable["pin"]
            if (
                type(pin_value) is not dict
                or pin_value.get("pin_sha256") != expected_pin_sha256
                or ready_record.pin_sha256 != expected_pin_sha256
                or durable["ready"] is not None
            ):
                raise ValueError("ready CAS mismatch")
            durable["ready"] = ready_record.model_dump(mode="json")
            _durable_write_json(path, durable)


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

CAPABILITY_KEY_ID = "fixture-capability-key"
REVOCATION_KEY_ID = "fixture-revocation-key"
SOURCE_HEAD_KEY_ID = "fixture-source-head-key"

CAPABILITY_PRIVATE_KEY = bytes.fromhex("51" * 32)
REVOCATION_PRIVATE_KEY = bytes.fromhex("52" * 32)
SOURCE_HEAD_PRIVATE_KEY = bytes.fromhex("53" * 32)

OWNER_PATH_DISCRIMINATOR = "opspd1_" + "a1" * 32
STORE_ID = "mpstore1_" + "b2" * 32
SOURCE_KEY_VERSION = "moskv1_source-fixture-v1"
OWNER_KEY_VERSION = "mpkv1_owner-fixture-v1"

CAPABILITY_REGISTRY_ID = "fixture-capability-registry"
REVOCATION_REGISTRY_ID = "fixture-revocation-registry"
SOURCE_REGISTRY_ID = "opsreg1_" + "d4" * 32

REVOCATION_FLOOR_HEAD = "00" * 32
REVOCATION_FLOOR_EPOCH = 0
SOURCE_FLOOR_HEAD = "00" * 32
SOURCE_FLOOR_EPOCH = 0


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------


def capability_public_key() -> bytes:
    return (
        Ed25519PrivateKey.from_private_bytes(CAPABILITY_PRIVATE_KEY).public_key().public_bytes_raw()
    )


def revocation_public_key() -> bytes:
    return (
        Ed25519PrivateKey.from_private_bytes(REVOCATION_PRIVATE_KEY).public_key().public_bytes_raw()
    )


def source_head_public_key() -> bytes:
    return (
        Ed25519PrivateKey.from_private_bytes(SOURCE_HEAD_PRIVATE_KEY)
        .public_key()
        .public_bytes_raw()
    )


def capability_verification_keys() -> tuple[VerificationKeyV1, ...]:
    return (VerificationKeyV1(key_id=CAPABILITY_KEY_ID, public_key_bytes=capability_public_key()),)


def revocation_verification_keys() -> tuple[VerificationKeyV1, ...]:
    return (VerificationKeyV1(key_id=REVOCATION_KEY_ID, public_key_bytes=revocation_public_key()),)


def source_head_verification_keys() -> tuple[VerificationKeyV1, ...]:
    return (
        VerificationKeyV1(key_id=SOURCE_HEAD_KEY_ID, public_key_bytes=source_head_public_key()),
    )


def cutover_verification_keys() -> tuple[VerificationKeyV1, ...]:
    return ()


def provider_revocation_floor_pins() -> tuple[ProviderRevocationFloorPinV1, ...]:
    genesis = fixture_revocation_head(epoch=0, issued_at_ms=0)
    return (
        ProviderRevocationFloorPinV1(
            registry_id=REVOCATION_REGISTRY_ID,
            owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
            floor_head_sha256=genesis.head_sha256,
            floor_epoch=REVOCATION_FLOOR_EPOCH,
        ),
    )


def source_floor_pins() -> tuple[OwnerPrivateSourceFloorPinV1, ...]:
    genesis = fixture_source_head(epoch=0, previous_head_sha256="0" * 64, issued_at_ms=0)
    return (
        OwnerPrivateSourceFloorPinV1(
            registry_id=SOURCE_REGISTRY_ID,
            owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
            floor_head_sha256=genesis.head_sha256,
            floor_epoch=SOURCE_FLOOR_EPOCH,
        ),
    )


# ---------------------------------------------------------------------------
# Signing helpers
# ---------------------------------------------------------------------------


def _sign_capability_v4(cap: SignedProviderCapabilityV4FixtureV1) -> str:
    return (
        Ed25519PrivateKey.from_private_bytes(CAPABILITY_PRIVATE_KEY)
        .sign(_CAPABILITY_V4_SIGNATURE_DOMAIN + bytes.fromhex(cap.capability_sha256))
        .hex()
    )


def _sign_revocation_head(head: SignedProviderRevocationHeadFixtureV1) -> str:
    return (
        Ed25519PrivateKey.from_private_bytes(REVOCATION_PRIVATE_KEY)
        .sign(_REVOCATION_SIGNATURE_DOMAIN + bytes.fromhex(head.head_sha256))
        .hex()
    )


def _sign_source_head(head: SignedSourceHeadFixtureV1) -> str:
    return (
        Ed25519PrivateKey.from_private_bytes(SOURCE_HEAD_PRIVATE_KEY)
        .sign(_SOURCE_SIGNATURE_DOMAIN + bytes.fromhex(head.head_sha256))
        .hex()
    )


# ---------------------------------------------------------------------------
# Fixture factories
# ---------------------------------------------------------------------------


def fixture_capability_v4(
    *,
    capability_id: str = "fixture-capability-1",
    revocation_registry_id: str = REVOCATION_REGISTRY_ID,
    issued_at_ms: int = 1_000,
    expires_at_ms: int = 10_000,
    revocation_trusted_floor_sha256: str = REVOCATION_FLOOR_HEAD,
    approved_max_cents: int = 100,
    maximum_output_bytes: int = 4096,
    router_role: Literal["planner", "gatherer", "verifier", "synthesizer"] = "gatherer",
) -> SignedProviderCapabilityV4FixtureV1:
    account_blind = b"\x01" * 32
    project_blind = b"\x02" * 32
    material: dict[str, object] = {
        "schema_version": 4,
        "capability_id": capability_id,
        "owner_path_discriminator": OWNER_PATH_DISCRIMINATOR,
        "revocation_registry_id": revocation_registry_id,
        "revocation_trusted_floor_sha256": revocation_trusted_floor_sha256,
        "provider": "fixture.provider",
        "model": "fixture.model",
        "route": "fixture.route",
        "api_mode": "fixture",
        "processing_region": "local",
        "output_schema": "fixture.output.v1",
        "account_scope_blind_id": account_blind,
        "project_scope_blind_id": project_blind,
        "router_role": router_role,
        "policy_sha256": "aa" * 32,
        "core_sha256": "bb" * 32,
        "receipt_contract_sha256": "cc" * 32,
        "envelope_contract_sha256": "dd" * 32,
        "approved_max_cents": approved_max_cents,
        "maximum_output_bytes": maximum_output_bytes,
        "issued_at_ms": issued_at_ms,
        "expires_at_ms": expires_at_ms,
        "key_id": CAPABILITY_KEY_ID,
        "issuer_role": "private_provider_capability_v4_fixture_issuer",
        "key_purpose": "private_provider_capability_v4_fixture_v1",
        "signature_scheme": "ed25519",
        "synthetic_fixture_eligibility_only": True,
        "live_migration_verified": False,
        "user_accounting_effect": False,
        "transport_reachable": False,
        "confers_execution_authority": False,
        "confers_checkpoint_authority": False,
        "confers_sink_authority": False,
        "confers_transition_authority": False,
        "production_consumer_enabled": False,
    }
    cap_hash = _capability_v4_document_sha256(material)
    cap = SignedProviderCapabilityV4FixtureV1.model_validate(
        {**material, "capability_sha256": cap_hash, "signature_ed25519": "00" * 64}
    )
    return SignedProviderCapabilityV4FixtureV1.model_validate(
        {**material, "capability_sha256": cap_hash, "signature_ed25519": _sign_capability_v4(cap)}
    )


def fixture_revocation_head(
    *,
    registry_id: str = REVOCATION_REGISTRY_ID,
    epoch: int = 0,
    predecessor_head_sha256: str | None = None,
    issued_at_ms: int = 1_000,
    revoked_capability_sha256s: tuple[str, ...] = (),
) -> SignedProviderRevocationHeadFixtureV1:
    material: dict[str, object] = {
        "schema_version": 1,
        "registry_id": registry_id,
        "owner_path_discriminator": OWNER_PATH_DISCRIMINATOR,
        "epoch": epoch,
        "predecessor_head_sha256": predecessor_head_sha256,
        "issued_at_ms": issued_at_ms,
        "revoked_capability_sha256s": revoked_capability_sha256s,
        "key_id": REVOCATION_KEY_ID,
        "issuer_role": "private_provider_revocation_fixture_issuer",
        "key_purpose": "private_provider_revocation_fixture_v1",
        "signature_scheme": "ed25519",
        "synthetic_fixture_eligibility_only": True,
        "live_migration_verified": False,
        "user_accounting_effect": False,
        "transport_reachable": False,
        "confers_execution_authority": False,
        "confers_checkpoint_authority": False,
        "confers_sink_authority": False,
        "confers_transition_authority": False,
        "production_consumer_enabled": False,
    }
    head_hash = _revocation_head_document_sha256(material)
    head = SignedProviderRevocationHeadFixtureV1.model_validate(
        {**material, "head_sha256": head_hash, "signature_ed25519": "00" * 64}
    )
    return SignedProviderRevocationHeadFixtureV1.model_validate(
        {**material, "head_sha256": head_hash, "signature_ed25519": _sign_revocation_head(head)}
    )


def fixture_source_head(
    *,
    epoch: int = 0,
    previous_head_sha256: str = "0" * 64,
    issued_at_ms: int = 1_000,
    active_revisions: tuple[OpaqueSourceBundleRevisionV1, ...] = (),
) -> SignedSourceHeadFixtureV1:
    # Compute snapshot hash without the hash field first
    snapshot_no_hash: dict[str, object] = {
        "schema_version": 1,
        "registry_id": SOURCE_REGISTRY_ID,
        "owner_path_discriminator": OWNER_PATH_DISCRIMINATOR,
        "epoch": epoch,
        "issued_at_ms": issued_at_ms,
        "active_bundle_revisions": tuple(r.model_dump(mode="json") for r in active_revisions),
        "tombstoned_bundle_ids": (),
        "confers_execution_authority": False,
        "confers_checkpoint_authority": False,
        "confers_sink_authority": False,
        "confers_transition_authority": False,
        "production_consumer_enabled": False,
    }
    snapshot_hash = _source_snapshot_sha256(snapshot_no_hash)
    snapshot_material = {**snapshot_no_hash, "snapshot_sha256": snapshot_hash}
    OwnerPrivateSourceAuthoritySnapshotV1.model_validate(snapshot_material)

    head_material: dict[str, object] = {
        "schema_version": 1,
        "registry_id": SOURCE_REGISTRY_ID,
        "owner_path_discriminator": OWNER_PATH_DISCRIMINATOR,
        "epoch": epoch,
        "issued_at_ms": issued_at_ms,
        "previous_head_sha256": previous_head_sha256,
        "snapshot": snapshot_material,
        "key_id": SOURCE_HEAD_KEY_ID,
        "issuer_role": "owner_private_source_head_issuer",
        "key_purpose": "owner_private_source_head_issuer_v1",
        "signature_scheme": "ed25519",
        "confers_execution_authority": False,
        "confers_checkpoint_authority": False,
        "confers_sink_authority": False,
        "confers_transition_authority": False,
        "production_consumer_enabled": False,
    }
    head_hash = _source_head_document_sha256(head_material)
    head = SignedSourceHeadFixtureV1.model_validate(
        {**head_material, "head_sha256": head_hash, "signature_ed25519": "00" * 64}
    )
    return SignedSourceHeadFixtureV1.model_validate(
        {**head_material, "head_sha256": head_hash, "signature_ed25519": _sign_source_head(head)}
    )


# ---------------------------------------------------------------------------
# Owner authority
# ---------------------------------------------------------------------------


class OpaqueOwnerPathAuthority:
    __slots__ = ()

    def __repr__(self) -> str:
        return "OpaqueOwnerPathAuthority(redacted=True)"

    def __reduce__(self) -> Never:
        raise TypeError("owner path authority is process-local")


# ---------------------------------------------------------------------------
# Key provider (test fixture)
# ---------------------------------------------------------------------------


class _HMACKeyContext(AbstractContextManager[bytearray]):
    def __init__(self, key: bytes) -> None:
        self._key = key
        self._opened: bytearray | None = None

    def __enter__(self) -> bytearray:
        buf = bytearray(self._key)
        self._opened = buf
        return buf

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._opened is not None:
            self._opened[:] = b"\x00" * len(self._opened)
        self._opened = None


class _AESKeyContext(AbstractContextManager[bytearray]):
    def __init__(self, key: bytes) -> None:
        self._key = key
        self._opened: bytearray | None = None

    def __enter__(self) -> bytearray:
        buf = bytearray(self._key)
        self._opened = buf
        return buf

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._opened is not None:
            self._opened[:] = b"\x00" * len(self._opened)
        self._opened = None


class _AuthContext(AbstractContextManager[None]):
    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        pass


@dataclass(slots=True)
class FixtureOwnerKeyProvider:
    expected_authority: object
    hmac_keys: dict[str, bytes] = field(
        default_factory=lambda: {
            "consent_v1": bytes([0x10]) * 32,
            "cursor_v1": bytes([0x11]) * 32,
            "account_v1": bytes([0x12]) * 32,
            "project_v1": bytes([0x13]) * 32,
            "request_v1": bytes([0x14]) * 32,
            "idempotency_v1": bytes([0x15]) * 32,
            "effect_v1": bytes([0x16]) * 32,
            "test_claim_v1": bytes([0x17]) * 32,
        }
    )
    aes_keys: dict[tuple[str, str], bytes] = field(default_factory=dict)
    auth_calls: list[tuple[int, str]] = field(default_factory=list)
    hmac_calls: list[tuple[int, str, str]] = field(default_factory=list)

    def authenticate_owner_path(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
    ) -> AbstractContextManager[None]:
        if owner_path_authority is not self.expected_authority:
            raise ValueError("wrong authority")
        if owner_path_discriminator != OWNER_PATH_DISCRIMINATOR:
            raise ValueError("wrong discriminator")
        self.auth_calls.append((id(owner_path_authority), owner_path_discriminator))
        return _AuthContext()

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
    ) -> AbstractContextManager[bytearray]:
        if owner_path_authority is not self.expected_authority:
            raise ValueError("wrong authority")
        if owner_path_discriminator != OWNER_PATH_DISCRIMINATOR:
            raise ValueError("wrong discriminator")
        key = self.hmac_keys.get(purpose)
        if key is None:
            raise ValueError("wrong purpose")
        self.hmac_calls.append((id(owner_path_authority), owner_path_discriminator, purpose))
        return _HMACKeyContext(key)

    def open_aes256gcm_key(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        key_version: str,
        purpose: Literal["admission_candidate_v1", "attempt_evidence_v1"],
    ) -> AbstractContextManager[bytearray]:
        if owner_path_authority is not self.expected_authority:
            raise ValueError("wrong authority")
        return _AESKeyContext(secrets.token_bytes(32))


class FixtureSourceKeyProvider:
    def __init__(self) -> None:
        self.keys: dict[tuple[str, str], bytes] = {
            (OWNER_PATH_DISCRIMINATOR, SOURCE_KEY_VERSION): bytes([0x31]) * 32
        }
        self.calls: list[tuple[int, str, str]] = []
        self.opened_buffers: list[bytearray] = []

    def open_aes256gcm_key(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        key_version: str,
    ) -> AbstractContextManager[bytearray]:
        key = self.keys.get((owner_path_discriminator, key_version))
        if key is None:
            raise ValueError("source key unavailable")
        self.calls.append((id(owner_path_authority), owner_path_discriminator, key_version))
        return _AESKeyContext(key)


# ---------------------------------------------------------------------------
# Store case factory
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PrivatePaidLaneCheckpointCase:
    authority: OpaqueOwnerPathAuthority
    owner_key_provider: FixtureOwnerKeyProvider
    source_key_provider: FixtureSourceKeyProvider
    store: PrivatePaidLaneEligibilityCheckpointStoreV1
    genesis_source_head: SignedSourceHeadFixtureV1
    uses_quarantined_raw_sql_genesis_scaffolding: Literal[True]


def fixture_genesis_migration_rows() -> dict[str, tuple[BaseModel, ...]]:
    revocation = fixture_revocation_head(epoch=0, issued_at_ms=0)
    source = fixture_source_head(epoch=0, previous_head_sha256="0" * 64, issued_at_ms=0)
    return {
        "provider_revocation_heads": (
            ProviderRevocationHeadMigrationRowV1(
                head_sha256=revocation.head_sha256,
                registry_id=revocation.registry_id,
                owner_path_discriminator=revocation.owner_path_discriminator,
                epoch=revocation.epoch,
                predecessor_head_sha256=revocation.predecessor_head_sha256,
                issued_at_ms=revocation.issued_at_ms,
                revoked_capability_hashes_json=_canonical_json(
                    list(revocation.revoked_capability_sha256s)
                ),
                key_id=revocation.key_id,
                document_json=_canonical_json(revocation.model_dump(mode="json")),
                signature_ed25519=bytes.fromhex(revocation.signature_ed25519),
            ),
        ),
        "provider_revocation_current": (
            ProviderRevocationCurrentMigrationRowV1(
                registry_id=revocation.registry_id,
                owner_path_discriminator=revocation.owner_path_discriminator,
                head_sha256=revocation.head_sha256,
                epoch=0,
                state_version=1,
                updated_at_ms=0,
            ),
        ),
        "source_heads": (
            SourceHeadMigrationRowV1(
                head_sha256=source.head_sha256,
                registry_id=source.registry_id,
                owner_path_discriminator=source.owner_path_discriminator,
                epoch=source.epoch,
                previous_head_sha256=source.previous_head_sha256,
                issued_at_ms=source.issued_at_ms,
                active_bundle_revisions_json=_canonical_json(
                    [row.model_dump(mode="json") for row in source.snapshot.active_bundle_revisions]
                ),
                snapshot_json=_canonical_json(source.snapshot.model_dump(mode="json")),
                key_id=source.key_id,
                document_json=_canonical_json(source.model_dump(mode="json")),
                signature_ed25519=bytes.fromhex(source.signature_ed25519),
            ),
        ),
        "source_current": (
            SourceCurrentMigrationRowV1(
                registry_id=source.registry_id,
                owner_path_discriminator=source.owner_path_discriminator,
                head_sha256=source.head_sha256,
                epoch=0,
                state_version=1,
                updated_at_ms=0,
            ),
        ),
    }


def fixture_store_case(
    root: Path, *, synthetic_legacy_root: _OpenLegacyRootV1 | None = None
) -> PrivatePaidLaneCheckpointCase:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    authority = OpaqueOwnerPathAuthority()
    owner_key_provider = FixtureOwnerKeyProvider(authority)
    source_key_provider = FixtureSourceKeyProvider()

    # Create genesis source head (epoch 0, predecessor all-zeros)
    genesis_source_head = fixture_source_head(
        epoch=0,
        previous_head_sha256="0" * 64,
        issued_at_ms=0,
    )

    # Create genesis revocation head
    genesis_revocation_head = fixture_revocation_head(epoch=0, issued_at_ms=0)

    # Build floor pins pointing at the genesis heads
    rfp = ProviderRevocationFloorPinV1(
        registry_id=REVOCATION_REGISTRY_ID,
        owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
        floor_head_sha256=genesis_revocation_head.head_sha256,
        floor_epoch=0,
    )
    sfp = OwnerPrivateSourceFloorPinV1(
        registry_id=SOURCE_REGISTRY_ID,
        owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
        floor_head_sha256=genesis_source_head.head_sha256,
        floor_epoch=0,
    )

    # Compute expected identities
    semantic = compute_private_paid_lane_semantic_sha256()
    contract = compute_private_paid_lane_contract_sha256(
        semantic_sha256=semantic,
        sql=_SCHEMA_SQL_V1,
        predecessor_cycle33_contract=_PREDECESSOR_CYCLE33_CONTRACT_SHA256,
        predecessor_cycle32_source=_PREDECESSOR_CYCLE32_SOURCE_SHA256,
        predecessor_cycle30_capability=_PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
    )

    production_epoch0_store = PrivatePaidLaneEligibilityCheckpointStoreV1.open(
        database_path=root / "paid-lane.sqlite3",
        open_mode="create_epoch0",
        expected_store_id=STORE_ID,
        expected_schema_version=1,
        expected_migration_epoch=0,
        expected_cutover_marker_sha256=None,
        expected_source_manifest_sha256=None,
        expected_copy_audit_sha256=None,
        expected_external_pin_store_id=STORE_ID,
        expected_semantic_source_sha256=semantic,
        expected_contract_sha256=contract,
        provider_capability_verification_keys=capability_verification_keys(),
        provider_revocation_verification_keys=revocation_verification_keys(),
        source_head_verification_keys=source_head_verification_keys(),
        cutover_verification_keys=cutover_verification_keys(),
        provider_revocation_floor_pins=(rfp,),
        source_floor_pins=(sfp,),
        source_bundle_key_provider=source_key_provider,
        owner_key_provider=owner_key_provider,
        synthetic_legacy_root=(
            _OpenLegacyRootV1() if synthetic_legacy_root is None else synthetic_legacy_root
        ),
        synthetic_external_pin_store=_OpenExternalPinStoreV1(store_id=STORE_ID),
    )
    # Quarantined support composition scaffolding only. Cycle34A defines no public genesis
    # bootstrap, and these rows are not evidence of epoch-zero writer authority.

    with sqlite3.connect(production_epoch0_store.database_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        # Insert genesis revocation head
        revoked_json = _canonical_json(sorted(genesis_revocation_head.revoked_capability_sha256s))
        head_doc = _canonical_json(genesis_revocation_head.model_dump(mode="json"))
        conn.execute(
            "INSERT INTO provider_revocation_heads "
            "(head_sha256, registry_id, owner_path_discriminator, epoch, "
            "predecessor_head_sha256, issued_at_ms, revoked_capability_hashes_json, "
            "key_id, document_json, signature_ed25519) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                genesis_revocation_head.head_sha256,
                genesis_revocation_head.registry_id,
                genesis_revocation_head.owner_path_discriminator,
                0,
                None,
                0,
                revoked_json,
                genesis_revocation_head.key_id,
                head_doc,
                genesis_revocation_head.signature_ed25519,
            ),
        )
        conn.execute(
            "INSERT INTO provider_revocation_current "
            "(registry_id, owner_path_discriminator, head_sha256, epoch, "
            "state_version, updated_at_ms) "
            "VALUES (?,?,?,?,?,?)",
            (
                REVOCATION_REGISTRY_ID,
                OWNER_PATH_DISCRIMINATOR,
                genesis_revocation_head.head_sha256,
                0,
                1,
                0,
            ),
        )
        # Insert genesis source head
        snapshot_doc = _canonical_json(genesis_source_head.snapshot.model_dump(mode="json"))
        revisions_json = _canonical_json(
            [
                r.model_dump(mode="json")
                for r in genesis_source_head.snapshot.active_bundle_revisions
            ]
        )
        source_head_doc = _canonical_json(genesis_source_head.model_dump(mode="json"))
        conn.execute(
            "INSERT INTO source_heads "
            "(head_sha256, registry_id, owner_path_discriminator, epoch, "
            "previous_head_sha256, issued_at_ms, active_bundle_revisions_json, "
            "snapshot_json, key_id, document_json, signature_ed25519) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                genesis_source_head.head_sha256,
                genesis_source_head.registry_id,
                genesis_source_head.owner_path_discriminator,
                0,
                "0" * 64,
                0,
                revisions_json,
                snapshot_doc,
                genesis_source_head.key_id,
                source_head_doc,
                genesis_source_head.signature_ed25519,
            ),
        )
        conn.execute(
            "INSERT INTO source_current "
            "(registry_id, owner_path_discriminator, head_sha256, epoch, "
            "state_version, updated_at_ms) "
            "VALUES (?,?,?,?,?,?)",
            (
                SOURCE_REGISTRY_ID,
                OWNER_PATH_DISCRIMINATOR,
                genesis_source_head.head_sha256,
                0,
                1,
                0,
            ),
        )
        conn.commit()

    return PrivatePaidLaneCheckpointCase(
        authority=authority,
        owner_key_provider=owner_key_provider,
        source_key_provider=source_key_provider,
        store=production_epoch0_store,
        genesis_source_head=genesis_source_head,
        uses_quarantined_raw_sql_genesis_scaffolding=True,
    )


__all__ = [
    "CAPABILITY_KEY_ID",
    "CAPABILITY_PRIVATE_KEY",
    "OWNER_PATH_DISCRIMINATOR",
    "REVOCATION_KEY_ID",
    "REVOCATION_REGISTRY_ID",
    "SOURCE_HEAD_KEY_ID",
    "SOURCE_KEY_VERSION",
    "SOURCE_REGISTRY_ID",
    "STORE_ID",
    "FixtureOwnerKeyProvider",
    "FixtureMigrationLifecycleIssuerV1",
    "FixtureSourceKeyProvider",
    "OpaqueOwnerPathAuthority",
    "PrivatePaidLaneCheckpointCase",
    "QuarantinedSyntheticExternalPinStoreV1",
    "QuarantinedSyntheticLegacyRootV1",
    "QuarantinedSyntheticWriterBarrierV1",
    "capability_verification_keys",
    "fixture_capability_v4",
    "fixture_revocation_head",
    "fixture_source_head",
    "fixture_store_case",
    "provider_revocation_floor_pins",
    "revocation_verification_keys",
    "source_floor_pins",
    "source_head_verification_keys",
]
