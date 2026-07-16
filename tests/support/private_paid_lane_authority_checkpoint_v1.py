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
from collections.abc import Callable, Iterator, Mapping
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
    _COPY_TABLE_ORDER_FIELDS,
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
    CopyAuditV1,
    EncryptedSourceBundleMigrationRowV1,
    Epoch0RecoveryAbortPreparationCompletionV1,
    Epoch0RecoveryAbortPreparedAuthorityPinsV1,
    Epoch0RecoveryAbortRenameCompletionV1,
    Epoch0RecoveryAbortRenamedAuthorityPinsV1,
    Epoch0RecoveryAuthorityPinsV1,
    Epoch0RecoveryBarrierAcquisitionCompletionV1,
    Epoch0RecoveryCopyCompletionV1,
    Epoch0RecoveryCopyPreparationCompletionV1,
    Epoch0RecoverySourceSealingCompletionV1,
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
    _authenticate_epoch0_recovery_abort_prepared_state_for_rename_v1,
    _authenticate_epoch0_recovery_abort_renamed_state_v1,
    _authenticate_epoch0_recovery_state_v1,
    _canonical_json,
    _capability_v4_document_sha256,
    _confirm_signed_migration_lifecycle_state_durable,
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
    _persist_signed_migration_lifecycle_state,
    _read_signed_migration_lifecycle_state,
    _reconcile_copy_prepared_target_v1,
    _rename_migration_target_to_tombstone_exclusive,
    _revocation_head_document_sha256,
    _source_head_document_sha256,
    _source_snapshot_sha256,
    _verify_epoch0_recovery_abort_preparation_completion_v1,
    _verify_epoch0_recovery_abort_rename_completion_v1,
    _verify_epoch0_recovery_barrier_acquisition_completion_v1,
    _verify_epoch0_recovery_copy_completion_v1,
    _verify_epoch0_recovery_copy_preparation_completion_v1,
    _verify_epoch0_recovery_source_sealing_completion_v1,
    _verify_migration_abort_post_rename_target_layout,
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
_RecoveryFaultBoundary = Literal[
    "after_target_commit",
    "after_rename",
    "after_parent_fsync",
    "after_reread",
    "prepare_after_audit",
    "prepare_after_rename",
    "prepare_after_parent_fsync",
    "prepare_after_reread",
    "barrier_after_intent",
    "barrier_after_root_rename",
    "barrier_after_root_fsync",
    "barrier_after_root_reread",
    "barrier_after_journal_rename",
    "barrier_after_journal_parent_fsync",
    "barrier_after_journal_reread",
    "seal_deny_after_child_owner",
    "seal_deny_after_child_paid",
    "seal_deny_after_child_provider",
    "seal_drain_after_child_owner",
    "seal_drain_after_child_paid",
    "seal_drain_after_child_provider",
    "seal_revoke_after_child_owner",
    "seal_revoke_after_child_paid",
    "seal_revoke_after_child_provider",
    "seal_verify_after_child_owner",
    "seal_verify_after_child_paid",
    "seal_verify_after_child_provider",
    "seal_collect_after_child_owner",
    "seal_collect_after_child_paid",
    "seal_collect_after_child_provider",
    "seal_deny_after_root_rename",
    "seal_deny_after_root_fsync",
    "seal_deny_after_root_reread",
    "seal_drain_after_root_rename",
    "seal_drain_after_root_fsync",
    "seal_drain_after_root_reread",
    "seal_revoke_after_root_rename",
    "seal_revoke_after_root_fsync",
    "seal_revoke_after_root_reread",
    "seal_verify_after_root_rename",
    "seal_verify_after_root_fsync",
    "seal_verify_after_root_reread",
    "seal_collect_after_root_rename",
    "seal_collect_after_root_fsync",
    "seal_collect_after_root_reread",
    "seal_after_manifest_completion_cache",
    "seal_after_journal_rename",
    "seal_after_journal_parent_fsync",
    "seal_after_journal_reread",
    "abort_prepare_after_intent",
    "abort_prepare_after_rename",
    "abort_prepare_after_parent_fsync",
    "abort_prepare_after_reread",
    "abort_rename_after_intent",
    "abort_rename_after_target_rename",
    "abort_rename_after_post_target",
    "abort_rename_after_journal_rename",
    "abort_rename_after_journal_parent_fsync",
    "abort_rename_after_journal_reread",
]
_SUPPORT_PIN_STATE = "external-pin-state-v1.json"
_CHILD_ROLES = (
    "owner-private-source-v1",
    "paid-lane-fixture-v1",
    "provider-authority-v4",
)

_ISSUER_MAX_PACKET = 131_072
_ISSUER_WITNESS_SOCKET_NAME = "issuer-v1.sock"


class _InjectedRecoveryFault(RuntimeError):
    completion_document: bytes | None

    def __init__(self, message: str, *, completion_document: bytes | None = None) -> None:
        super().__init__(message)
        self.completion_document = completion_document


_ISSUER_SESSION_FRAME_MAGIC = b"ARS1"
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


def _issuer_session_frame(payload: bytes) -> bytes:
    if not payload or len(payload) > _ISSUER_MAX_PACKET:
        raise ValueError("issuer session frame bound")
    return _ISSUER_SESSION_FRAME_MAGIC + struct.pack("!I", len(payload)) + payload


def _issuer_session_receive_frame(
    socket_: socket.socket, initial: bytes = b"", *, idle_poll: bool = False
) -> bytes:
    framed = bytearray(initial)
    deadline = None if idle_poll and not framed else time.monotonic() + 5.0
    while len(framed) < 8:
        try:
            chunk = socket_.recv(8 - len(framed))
        except TimeoutError:
            if deadline is None:
                raise BlockingIOError("issuer session idle poll") from None
            if time.monotonic() >= deadline:
                raise
            continue
        if not chunk:
            raise ValueError("issuer session frame header")
        framed.extend(chunk)
        if deadline is None:
            deadline = time.monotonic() + 5.0
    if bytes(framed[:4]) != _ISSUER_SESSION_FRAME_MAGIC:
        raise ValueError("issuer session frame magic")
    length = struct.unpack("!I", framed[4:8])[0]
    if not 0 < length <= _ISSUER_MAX_PACKET:
        raise ValueError("issuer session frame bound")
    expected = 8 + length
    if len(framed) > expected:
        raise ValueError("issuer session frame trailing bytes")
    while len(framed) < expected:
        try:
            chunk = socket_.recv(expected - len(framed))
        except TimeoutError:
            if deadline is None or time.monotonic() >= deadline:
                raise
            continue
        if not chunk:
            raise ValueError("issuer session frame truncated")
        framed.extend(chunk)
    return bytes(framed[8:])


def _issuer_recovery_copy_completion_document(
    completion: Epoch0RecoveryCopyCompletionV1,
) -> bytes:
    material = completion.model_dump(mode="python")
    for state_field in ("prepared_state", "copied_state"):
        state = cast(dict[str, object], material[state_field])
        signature = state.get("signature_ed25519")
        if type(signature) is not bytes:
            raise ValueError("issuer recovery copy completion signature")
        state["signature_ed25519"] = signature.hex()
    encoded = _canonical_json(material)
    if len(encoded) > _ISSUER_MAX_PACKET:
        raise ValueError("issuer recovery copy completion bound")
    return encoded


def _parse_issuer_recovery_copy_completion_document(
    document: bytes,
) -> Epoch0RecoveryCopyCompletionV1:
    material = _parse_strict_json(document, _ISSUER_MAX_PACKET)
    for state_field in ("prepared_state", "copied_state"):
        state = material.get(state_field)
        if type(state) is not dict:
            raise ValueError("issuer recovery copy completion state")
        signature = state.get("signature_ed25519")
        if type(signature) is not str or not re.fullmatch(r"[0-9a-f]{128}", signature):
            raise ValueError("issuer recovery copy completion signature")
        state["signature_ed25519"] = bytes.fromhex(signature)
    copy_audit = material.get("copy_audit")
    if type(copy_audit) is not dict:
        raise ValueError("issuer recovery copy completion audit")
    ordered_hashes = copy_audit.get("ordered_table_row_sha256s")
    foreign_keys = copy_audit.get("foreign_key_check_rows")
    if type(ordered_hashes) is not list or type(foreign_keys) is not list:
        raise ValueError("issuer recovery copy completion audit tuples")
    copy_audit["ordered_table_row_sha256s"] = tuple(
        (entry[0], tuple(entry[1]))
        for entry in ordered_hashes
        if type(entry) is list and len(entry) == 2 and type(entry[1]) is list
    )
    copy_audit["foreign_key_check_rows"] = tuple(
        tuple(row) for row in foreign_keys if type(row) is list
    )
    completion = Epoch0RecoveryCopyCompletionV1.model_validate(material)
    if document != _issuer_recovery_copy_completion_document(completion):
        raise ValueError("issuer recovery copy completion canonical")
    return completion


def _issuer_recovery_copy_preparation_completion_document(
    completion: Epoch0RecoveryCopyPreparationCompletionV1,
) -> bytes:
    material = completion.model_dump(mode="python")
    for state_field in ("sealed_state", "prepared_state"):
        state = cast(dict[str, object], material[state_field])
        signature = state.get("signature_ed25519")
        if type(signature) is not bytes:
            raise ValueError("issuer recovery preparation completion signature")
        state["signature_ed25519"] = signature.hex()
    encoded = _canonical_json(material)
    if len(encoded) > _ISSUER_MAX_PACKET:
        raise ValueError("issuer recovery preparation completion bound")
    return encoded


def _parse_issuer_recovery_copy_preparation_completion_document(
    document: bytes,
) -> Epoch0RecoveryCopyPreparationCompletionV1:
    material = _parse_strict_json(document, _ISSUER_MAX_PACKET)
    for state_field in ("sealed_state", "prepared_state"):
        state = material.get(state_field)
        if type(state) is not dict:
            raise ValueError("issuer recovery preparation completion state")
        signature = state.get("signature_ed25519")
        if type(signature) is not str or not re.fullmatch(r"[0-9a-f]{128}", signature):
            raise ValueError("issuer recovery preparation completion signature")
        state["signature_ed25519"] = bytes.fromhex(signature)
    copy_audit = material.get("copy_audit")
    if type(copy_audit) is not dict:
        raise ValueError("issuer recovery preparation completion audit")
    ordered_hashes = copy_audit.get("ordered_table_row_sha256s")
    foreign_keys = copy_audit.get("foreign_key_check_rows")
    if type(ordered_hashes) is not list or type(foreign_keys) is not list:
        raise ValueError("issuer recovery preparation completion audit tuples")
    copy_audit["ordered_table_row_sha256s"] = tuple(
        (entry[0], tuple(entry[1]))
        for entry in ordered_hashes
        if type(entry) is list and len(entry) == 2 and type(entry[1]) is list
    )
    copy_audit["foreign_key_check_rows"] = tuple(
        tuple(row) for row in foreign_keys if type(row) is list
    )
    completion = Epoch0RecoveryCopyPreparationCompletionV1.model_validate(material)
    if document != _issuer_recovery_copy_preparation_completion_document(completion):
        raise ValueError("issuer recovery preparation completion canonical")
    return completion


def _issuer_recovery_barrier_acquisition_completion_document(
    completion: Epoch0RecoveryBarrierAcquisitionCompletionV1,
) -> bytes:
    material = completion.model_dump(mode="python")
    for state_field in ("schema_only_state", "barrier_acquired_state"):
        state = cast(dict[str, object], material[state_field])
        signature = state.get("signature_ed25519")
        if type(signature) is not bytes:
            raise ValueError("issuer recovery barrier acquisition completion signature")
        state["signature_ed25519"] = signature.hex()
    encoded = _canonical_json(material)
    if len(encoded) > _ISSUER_MAX_PACKET:
        raise ValueError("issuer recovery barrier acquisition completion bound")
    return encoded


def _parse_issuer_recovery_barrier_acquisition_completion_document(
    document: bytes,
) -> Epoch0RecoveryBarrierAcquisitionCompletionV1:
    material = _parse_strict_json(document, _ISSUER_MAX_PACKET)
    for state_field in ("schema_only_state", "barrier_acquired_state"):
        state = material.get(state_field)
        if type(state) is not dict:
            raise ValueError("issuer recovery barrier acquisition completion state")
        signature = state.get("signature_ed25519")
        if type(signature) is not str or not re.fullmatch(r"[0-9a-f]{128}", signature):
            raise ValueError("issuer recovery barrier acquisition completion signature")
        state["signature_ed25519"] = bytes.fromhex(signature)
    completion = Epoch0RecoveryBarrierAcquisitionCompletionV1.model_validate(material)
    if document != _issuer_recovery_barrier_acquisition_completion_document(completion):
        raise ValueError("issuer recovery barrier acquisition completion canonical")
    return completion


def _issuer_recovery_source_sealing_completion_document(
    completion: Epoch0RecoverySourceSealingCompletionV1,
) -> bytes:
    material = completion.model_dump(mode="python")
    for state_field in ("barrier_acquired_state", "sources_sealed_state"):
        state = cast(dict[str, object], material[state_field])
        signature = state.get("signature_ed25519")
        if type(signature) is not bytes:
            raise ValueError("issuer recovery source sealing completion signature")
        state["signature_ed25519"] = signature.hex()
    encoded = _canonical_json(material)
    if len(encoded) > _ISSUER_MAX_PACKET:
        raise ValueError("issuer recovery source sealing completion bound")
    return encoded


def _parse_issuer_recovery_source_sealing_completion_document(
    document: bytes,
) -> Epoch0RecoverySourceSealingCompletionV1:
    material = _parse_strict_json(document, _ISSUER_MAX_PACKET)
    for state_field in ("barrier_acquired_state", "sources_sealed_state"):
        state = material.get(state_field)
        if type(state) is not dict:
            raise ValueError("issuer recovery source sealing completion state")
        signature = state.get("signature_ed25519")
        if type(signature) is not str or not re.fullmatch(r"[0-9a-f]{128}", signature):
            raise ValueError("issuer recovery source sealing completion signature")
        state["signature_ed25519"] = bytes.fromhex(signature)
    completion = Epoch0RecoverySourceSealingCompletionV1.model_validate(material)
    if document != _issuer_recovery_source_sealing_completion_document(completion):
        raise ValueError("issuer recovery source sealing completion canonical")
    return completion


def _issuer_recovery_abort_preparation_completion_document(
    completion: Epoch0RecoveryAbortPreparationCompletionV1,
) -> bytes:
    material = completion.model_dump(mode="python")
    for state_field in ("origin_state", "abort_prepared_state"):
        state = cast(dict[str, object], material[state_field])
        signature = state.get("signature_ed25519")
        if type(signature) is not bytes:
            raise ValueError("issuer recovery abort preparation completion signature")
        state["signature_ed25519"] = signature.hex()
    encoded = _canonical_json(material)
    if len(encoded) > _ISSUER_MAX_PACKET:
        raise ValueError("issuer recovery abort preparation completion bound")
    return encoded


def _parse_issuer_recovery_abort_preparation_completion_document(
    document: bytes,
) -> Epoch0RecoveryAbortPreparationCompletionV1:
    material = _parse_strict_json(document, _ISSUER_MAX_PACKET)
    for state_field in ("origin_state", "abort_prepared_state"):
        state = material.get(state_field)
        if type(state) is not dict:
            raise ValueError("issuer recovery abort preparation completion state")
        signature = state.get("signature_ed25519")
        if type(signature) is not str or not re.fullmatch(r"[0-9a-f]{128}", signature):
            raise ValueError("issuer recovery abort preparation completion signature")
        state["signature_ed25519"] = bytes.fromhex(signature)
    completion = Epoch0RecoveryAbortPreparationCompletionV1.model_validate(material)
    if document != _issuer_recovery_abort_preparation_completion_document(completion):
        raise ValueError("issuer recovery abort preparation completion canonical")
    return completion


def _issuer_recovery_abort_rename_completion_document(
    completion: Epoch0RecoveryAbortRenameCompletionV1,
) -> bytes:
    material = completion.model_dump(mode="python")
    for state_field in ("abort_prepared_state", "abort_renamed_to_tombstone_state"):
        state = cast(dict[str, object], material[state_field])
        signature = state.get("signature_ed25519")
        if type(signature) is not bytes:
            raise ValueError("issuer recovery abort rename completion signature")
        state["signature_ed25519"] = signature.hex()
    encoded = _canonical_json(material)
    if len(encoded) > _ISSUER_MAX_PACKET:
        raise ValueError("issuer recovery abort rename completion bound")
    return encoded


def _parse_issuer_recovery_abort_rename_completion_document(
    document: bytes,
) -> Epoch0RecoveryAbortRenameCompletionV1:
    material = _parse_strict_json(document, _ISSUER_MAX_PACKET)
    for state_field in ("abort_prepared_state", "abort_renamed_to_tombstone_state"):
        state = material.get(state_field)
        if type(state) is not dict:
            raise ValueError("issuer recovery abort rename completion state")
        signature = state.get("signature_ed25519")
        if type(signature) is not str or not re.fullmatch(r"[0-9a-f]{128}", signature):
            raise ValueError("issuer recovery abort rename completion signature")
        state["signature_ed25519"] = bytes.fromhex(signature)
    completion = Epoch0RecoveryAbortRenameCompletionV1.model_validate(material)
    if document != _issuer_recovery_abort_rename_completion_document(completion):
        raise ValueError("issuer recovery abort rename completion canonical")
    return completion


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


def _issuer_authenticate_schema_recovery_root(
    root_fd: int,
    *,
    expected_root_id: str,
    expected_root_manifest_sha256: str,
    _allow_mixed_children: bool = False,
) -> dict[str, object]:
    root_path = _issuer_root_path(root_fd)
    record = _issuer_root_record(root_fd)
    if (
        record["root_id"] != expected_root_id
        or record["root_manifest_sha256"] != expected_root_manifest_sha256
    ):
        raise ValueError("issuer recovery schema root identity")
    expected_children = {
        role: os.fspath(_child_path(root_path, role).relative_to(root_path))
        for role in _CHILD_ROLES
    }
    if record.get("child_adapters") != expected_children:
        raise ValueError("issuer recovery child adapter roster")
    measured = _measure_child_adapters(root_path)
    if not _allow_mixed_children:
        _audit_child_phase(record, measured)
    inventory = record.get("writer_inventory")
    source_identities = record.get("source_store_identities")
    created_at_ms = record.get("created_at_ms")
    if (
        type(inventory) is not list
        or type(source_identities) is not list
        or type(created_at_ms) is not int
        or inventory != list(_CHILD_ROLES)
        or source_identities != list(_CHILD_ROLES)
    ):
        raise ValueError("issuer recovery inventory shape")
    manifest = {
        "root_id": record.get("root_id"),
        "writer_inventory": inventory,
        "source_store_identities": source_identities,
        "created_at_ms": created_at_ms,
    }
    if (
        record["inventory_sha256"] != hashlib.sha256(_canonical_json(inventory)).hexdigest()
        or record["root_manifest_sha256"] != hashlib.sha256(_canonical_json(manifest)).hexdigest()
    ):
        raise ValueError("issuer recovery inventory hash")
    return record


def _issuer_authenticate_barrier_recovery_root(
    root_fd: int,
    *,
    expected_root_id: str,
    expected_root_manifest_sha256: str,
    expected_barrier_id: str,
    expected_freeze_nonce: str,
) -> dict[str, object]:
    record = _issuer_authenticate_schema_recovery_root(
        root_fd,
        expected_root_id=expected_root_id,
        expected_root_manifest_sha256=expected_root_manifest_sha256,
        _allow_mixed_children=True,
    )
    state = record.get("state")
    if state not in {
        "quiesced",
        "admission_denied",
        "drained",
        "writers_revoked",
        "writers_verified",
        "sealed",
    }:
        raise ValueError("issuer recovery barrier root state")
    if (
        record.get("barrier_id") != expected_barrier_id
        or record.get("freeze_nonce") != expected_freeze_nonce
        or record.get("barrier_id") != _migration_barrier_id(expected_freeze_nonce)
    ):
        raise ValueError("issuer recovery barrier root pins")
    if state == "sealed":
        measured = _measure_child_adapters(_issuer_root_path(root_fd))
        _audit_child_phase(record, measured)
        evidence = record.get("child_adapter_evidence")
        if type(evidence) is not dict or evidence.get("sealed_measurements") != measured:
            raise ValueError("issuer recovery sealed root measurements")
    return record


def _issuer_durable_write_root_record(
    root_fd: int,
    record: dict[str, object],
    *,
    fault_hook: Callable[[Literal["after_rename", "after_parent_fsync"]], None] | None = None,
) -> None:
    root_info = os.fstat(root_fd)
    if (
        not stat.S_ISDIR(root_info.st_mode)
        or root_info.st_uid != os.getuid()
        or stat.S_IMODE(root_info.st_mode) != 0o700
    ):
        raise ValueError("issuer recovery root persistence identity")
    encoded = _canonical_json(record)
    if not 0 < len(encoded) <= 1_048_576:
        raise ValueError("issuer recovery root persistence bound")
    temporary = f".{_SUPPORT_ROOT_STATE}.recovery-{os.getpid()}-{secrets.token_hex(8)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=root_fd,
    )
    renamed = False
    try:
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short issuer recovery root write")
            view = view[written:]
        os.fsync(descriptor)
        os.replace(
            temporary,
            _SUPPORT_ROOT_STATE,
            src_dir_fd=root_fd,
            dst_dir_fd=root_fd,
        )
        renamed = True
        if fault_hook is not None:
            fault_hook("after_rename")
        os.fsync(root_fd)
        if fault_hook is not None:
            fault_hook("after_parent_fsync")
    finally:
        os.close(descriptor)
        if not renamed:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=root_fd)


def _issuer_barrier_material_for_schema_recovery(
    record: dict[str, object],
    *,
    root_ahead: bool,
    cached_barrier: tuple[str, str] | None = None,
) -> tuple[str, str, bool]:
    if root_ahead:
        barrier_id = record.get("barrier_id")
        freeze_nonce = record.get("freeze_nonce")
        evidence = record.get("transition_evidence")
        created_at_ms = record.get("created_at_ms")
        if (
            record.get("state") != "quiesced"
            or type(barrier_id) is not str
            or type(freeze_nonce) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", freeze_nonce)
            or barrier_id != _migration_barrier_id(freeze_nonce)
            or type(created_at_ms) is not int
            or record.get("acquired_at_ms") != created_at_ms
            or type(evidence) is not list
            or len(evidence) != 1
            or type(evidence[0]) is not dict
            or evidence[0].get("operation") != "acquire_writer_barrier"
            or evidence[0].get("prior_state") != "open"
            or evidence[0].get("next_state") != "quiesced"
        ):
            raise ValueError("issuer recovery root-ahead barrier")
        return barrier_id, freeze_nonce, False
    if (
        record.get("state") != "open"
        or record.get("barrier_id") is not None
        or record.get("freeze_nonce") is not None
        or "acquired_at_ms" in record
        or record.get("transition_evidence") != []
    ):
        raise ValueError("issuer recovery schema root state")
    if cached_barrier is None:
        freeze_nonce = secrets.token_hex(32)
        barrier_id = _migration_barrier_id(freeze_nonce)
    else:
        barrier_id, freeze_nonce = cached_barrier
        if barrier_id != _migration_barrier_id(freeze_nonce):
            raise ValueError("issuer recovery cached barrier identity")
    created_at_ms = record.get("created_at_ms")
    if type(created_at_ms) is not int:
        raise ValueError("issuer recovery root creation timestamp")
    record["freeze_nonce"] = freeze_nonce
    record["barrier_id"] = barrier_id
    record["acquired_at_ms"] = created_at_ms
    _append_transition_evidence(
        record,
        operation="acquire_writer_barrier",
        prior_state="open",
        next_state="quiesced",
    )
    record["state"] = "quiesced"
    return barrier_id, freeze_nonce, True


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


def _issuer_copy_intent_audit(
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
) -> CopyAuditV1:
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
    return audit


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
    return _copy_audit_sha256(
        _issuer_copy_intent_audit(
            target_fd=target_fd,
            target_lease=target_lease,
            corpus=corpus,
            provider_capability_verification_keys=provider_capability_verification_keys,
            provider_revocation_verification_keys=provider_revocation_verification_keys,
            source_head_verification_keys=source_head_verification_keys,
            provider_revocation_floor_pins=provider_revocation_floor_pins,
            source_floor_pins=source_floor_pins,
            expected_target_store_id=expected_target_store_id,
            expected_semantic_source_sha256=expected_semantic_source_sha256,
            expected_contract_sha256=expected_contract_sha256,
        )
    )


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


def _fixture_issuer_supervisor_main(handshake: Connection) -> None:
    try:
        handshake.send(os.getpid())
    finally:
        handshake.close()
    while True:
        time.sleep(60)


def _issuer_authenticate_recovery_descriptors(
    *,
    root_fd: int,
    parent_fd: int,
    target_fd: int,
    ticket: SignedMigrationRecoveryTicketV1,
    verification_key: VerificationKeyV1,
    raw_pins: object,
) -> (
    Epoch0RecoveryAuthorityPinsV1
    | Epoch0RecoveryAbortPreparedAuthorityPinsV1
    | Epoch0RecoveryAbortRenamedAuthorityPinsV1
):
    root_info = os.fstat(root_fd)
    root_record = _issuer_root_record(root_fd)
    if (
        (root_info.st_dev, root_info.st_ino) != (ticket.root_dev, ticket.root_ino)
        or root_record.get("root_id") != ticket.root_id
        or root_record.get("root_manifest_sha256") != ticket.root_manifest_sha256
    ):
        raise ValueError("issuer recovery root identity")
    if type(raw_pins) is not dict:
        raise ValueError("issuer recovery pins material")
    lifecycle_phase = raw_pins.get("lifecycle_phase")
    if lifecycle_phase == "abort_prepared":
        abort_pins = Epoch0RecoveryAbortPreparedAuthorityPinsV1.model_validate(raw_pins)
        if (
            abort_pins.target_store_id != ticket.target_store_id
            or abort_pins.root_id != ticket.root_id
            or abort_pins.root_manifest_sha256 != ticket.root_manifest_sha256
            or (abort_pins.target_parent_dev, abort_pins.target_parent_ino)
            != (ticket.target_parent_dev, ticket.target_parent_ino)
            or abort_pins.target_basename != ticket.target_basename
            or (abort_pins.target_dev, abort_pins.target_ino)
            != (ticket.target_dev, ticket.target_ino)
            or abort_pins.issuer_sequence > ticket.maximum_issuer_sequence
        ):
            raise ValueError("issuer recovery ticket abort pins")
        _authenticate_epoch0_recovery_abort_prepared_state_for_rename_v1(
            parent_fd=parent_fd,
            target_fd=target_fd,
            verification_key=verification_key,
            expected=abort_pins,
        )
        return abort_pins
    if lifecycle_phase == "abort_renamed_to_tombstone":
        renamed_pins = Epoch0RecoveryAbortRenamedAuthorityPinsV1.model_validate(raw_pins)
        if (
            renamed_pins.target_store_id != ticket.target_store_id
            or renamed_pins.root_id != ticket.root_id
            or renamed_pins.root_manifest_sha256 != ticket.root_manifest_sha256
            or (renamed_pins.target_parent_dev, renamed_pins.target_parent_ino)
            != (ticket.target_parent_dev, ticket.target_parent_ino)
            or renamed_pins.target_basename != ticket.target_basename
            or (renamed_pins.target_dev, renamed_pins.target_ino)
            != (ticket.target_dev, ticket.target_ino)
            or renamed_pins.issuer_sequence > ticket.maximum_issuer_sequence
        ):
            raise ValueError("issuer recovery ticket renamed abort pins")
        _authenticate_epoch0_recovery_abort_renamed_state_v1(
            parent_fd=parent_fd,
            target_fd=target_fd,
            verification_key=verification_key,
            expected=renamed_pins,
        )
        return renamed_pins
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


def _issuer_recovery_pins_from_state(
    state: SignedMigrationLifecycleStateV1,
) -> Epoch0RecoveryAuthorityPinsV1:
    return Epoch0RecoveryAuthorityPinsV1.model_validate(
        {name: getattr(state, name) for name in Epoch0RecoveryAuthorityPinsV1.model_fields}
    )


def _issuer_recovery_abort_prepared_pins_from_state(
    state: SignedMigrationLifecycleStateV1,
) -> Epoch0RecoveryAbortPreparedAuthorityPinsV1:
    return Epoch0RecoveryAbortPreparedAuthorityPinsV1.model_validate(
        {
            name: getattr(state, name)
            for name in Epoch0RecoveryAbortPreparedAuthorityPinsV1.model_fields
        }
    )


def _issuer_expected_abort_prepared_pins_from_origin(
    origin: Epoch0RecoveryAuthorityPinsV1,
    *,
    expected_abort_prepared_state_sha256: str,
) -> Epoch0RecoveryAbortPreparedAuthorityPinsV1:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_abort_prepared_state_sha256):
        raise ValueError("issuer expected abort prepared state hash")
    material = origin.model_dump(mode="python")
    material.update(
        {
            "lifecycle_phase": "abort_prepared",
            "phase_version": origin.phase_version + 1,
            "issuer_sequence": origin.issuer_sequence + 1,
            "state_sha256": expected_abort_prepared_state_sha256,
        }
    )
    return Epoch0RecoveryAbortPreparedAuthorityPinsV1.model_validate(material)


def _issuer_recovery_abort_renamed_pins_from_state(
    state: SignedMigrationLifecycleStateV1,
) -> Epoch0RecoveryAbortRenamedAuthorityPinsV1:
    return Epoch0RecoveryAbortRenamedAuthorityPinsV1.model_validate(
        {
            name: getattr(state, name)
            for name in Epoch0RecoveryAbortRenamedAuthorityPinsV1.model_fields
        }
    )


def _issuer_require_target_abort_sidecars_absent(
    *, parent_fd: int, target_basename: str, target_fd: int
) -> None:
    _issuer_require_child_sidecars_absent(_issuer_fd_path(target_fd))
    for suffix in ("-wal", "-shm", "-journal"):
        try:
            os.stat(
                f"{target_basename}{suffix}",
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            continue
        raise ValueError("issuer abort preparation sidecar present")


def _issuer_checkpoint_target_wal_and_release(
    target_lease: sqlite3.Connection | None,
) -> None:
    if target_lease is None:
        return
    _issuer_release_target_lease(target_lease)


def _issuer_validate_abort_target_schema_only(
    *,
    session_target_fd: int,
    target_lease: sqlite3.Connection | None,
    expected_target_store_id: str,
    expected_semantic_source_sha256: str,
    expected_contract_sha256: str,
) -> None:
    lease = target_lease
    acquired_locally = lease is None
    if lease is None:
        lease = _issuer_acquire_target_lease(session_target_fd)
    try:
        with _issuer_target_snapshot(session_target_fd, lease) as snapshot_path:
            conn = sqlite3.connect(f"{snapshot_path.as_uri()}?mode=ro", uri=True)
            try:
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute("PRAGMA temp_store=MEMORY")
                conn.execute(f"PRAGMA max_page_count={MAX_DB_PAGES}")
                conn.execute("BEGIN")
                try:
                    _audit_schema(conn)
                    singleton = conn.execute(
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
                        raise ValueError("issuer abort preparation schema-only singleton")
                    for table_name in _COPY_TABLE_ORDER_FIELDS:
                        if (
                            conn.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone()
                            is not None
                        ):
                            raise ValueError("issuer abort preparation schema-only has data rows")
                    conn.execute("COMMIT")
                except BaseException:
                    with suppress(sqlite3.Error):
                        conn.execute("ROLLBACK")
                    raise
            finally:
                conn.close()
    finally:
        if acquired_locally:
            _issuer_release_target_lease(lease)


def _issuer_validate_abort_origin_custody(
    *,
    session_root_fd: int,
    session_target_fd: int,
    origin: SignedMigrationLifecycleStateV1,
    target_lease: sqlite3.Connection | None,
    provider_capability_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_verification_keys: tuple[VerificationKeyV1, ...],
    source_head_verification_keys: tuple[VerificationKeyV1, ...],
    provider_revocation_floor_pins: tuple[ProviderRevocationFloorPinV1, ...],
    source_floor_pins: tuple[OwnerPrivateSourceFloorPinV1, ...],
    expected_semantic_source_sha256: str,
    expected_contract_sha256: str,
) -> None:
    phase = origin.lifecycle_phase
    if phase == "schema_only":
        root_record = _issuer_authenticate_schema_recovery_root(
            session_root_fd,
            expected_root_id=origin.root_id,
            expected_root_manifest_sha256=origin.root_manifest_sha256,
        )
        if (
            root_record.get("state") != "open"
            or root_record.get("barrier_id") is not None
            or root_record.get("freeze_nonce") is not None
        ):
            raise ValueError("issuer abort preparation schema root")
        _issuer_validate_abort_target_schema_only(
            session_target_fd=session_target_fd,
            target_lease=target_lease,
            expected_target_store_id=origin.target_store_id,
            expected_semantic_source_sha256=expected_semantic_source_sha256,
            expected_contract_sha256=expected_contract_sha256,
        )
        return
    if phase == "barrier_acquired":
        if origin.barrier_id is None or origin.freeze_nonce is None:
            raise ValueError("issuer abort preparation barrier pins")
        root_record = _issuer_authenticate_barrier_recovery_root(
            session_root_fd,
            expected_root_id=origin.root_id,
            expected_root_manifest_sha256=origin.root_manifest_sha256,
            expected_barrier_id=origin.barrier_id,
            expected_freeze_nonce=origin.freeze_nonce,
        )
        if root_record.get("state") not in {
            "quiesced",
            "admission_denied",
            "drained",
            "writers_revoked",
            "writers_verified",
        }:
            raise ValueError("issuer abort preparation barrier root")
        _issuer_validate_abort_target_schema_only(
            session_target_fd=session_target_fd,
            target_lease=target_lease,
            expected_target_store_id=origin.target_store_id,
            expected_semantic_source_sha256=expected_semantic_source_sha256,
            expected_contract_sha256=expected_contract_sha256,
        )
        return
    if phase not in {"sources_sealed", "copy_prepared", "copied_epoch0"}:
        raise ValueError("issuer abort preparation origin phase")
    compatible = _issuer_compatible_root_record(session_root_fd, phase)
    corpus = _collect_sealed_corpus(_issuer_root_path(session_root_fd), compatible)
    if corpus.source_manifest_sha256 != origin.source_manifest_sha256:
        raise ValueError("issuer abort preparation sealed corpus")
    if phase == "sources_sealed":
        _issuer_validate_abort_target_schema_only(
            session_target_fd=session_target_fd,
            target_lease=target_lease,
            expected_target_store_id=origin.target_store_id,
            expected_semantic_source_sha256=expected_semantic_source_sha256,
            expected_contract_sha256=expected_contract_sha256,
        )
        return
    if phase == "copy_prepared":
        if origin.copy_audit_sha256 is None:
            raise ValueError("issuer abort preparation audit pins")
        lease = target_lease
        acquired_locally = lease is None
        if lease is None:
            lease = _issuer_acquire_target_lease(session_target_fd)
        try:
            try:
                intent = _issuer_copy_intent_audit(
                    target_fd=session_target_fd,
                    target_lease=lease,
                    corpus=corpus,
                    provider_capability_verification_keys=provider_capability_verification_keys,
                    provider_revocation_verification_keys=provider_revocation_verification_keys,
                    source_head_verification_keys=source_head_verification_keys,
                    provider_revocation_floor_pins=provider_revocation_floor_pins,
                    source_floor_pins=source_floor_pins,
                    expected_target_store_id=origin.target_store_id,
                    expected_semantic_source_sha256=expected_semantic_source_sha256,
                    expected_contract_sha256=expected_contract_sha256,
                )
                observed_sha256 = _copy_audit_sha256(intent)
            except ValueError:
                observed_sha256 = _issuer_observed_copy(
                    target_fd=session_target_fd,
                    target_lease=lease,
                    corpus=corpus,
                    provider_capability_verification_keys=provider_capability_verification_keys,
                    provider_revocation_verification_keys=provider_revocation_verification_keys,
                    source_head_verification_keys=source_head_verification_keys,
                    provider_revocation_floor_pins=provider_revocation_floor_pins,
                    source_floor_pins=source_floor_pins,
                    expected_target_store_id=origin.target_store_id,
                    expected_semantic_source_sha256=expected_semantic_source_sha256,
                    expected_contract_sha256=expected_contract_sha256,
                )
        finally:
            if acquired_locally:
                _issuer_release_target_lease(lease)
        if observed_sha256 != origin.copy_audit_sha256:
            raise ValueError("issuer abort preparation target audit")
        return
    if phase == "copied_epoch0":
        if origin.copy_audit_sha256 is None:
            raise ValueError("issuer abort preparation audit pins")
        lease = target_lease
        if lease is None:
            lease = _issuer_acquire_target_lease(session_target_fd)
            try:
                observed_sha256 = _issuer_observed_copy(
                    target_fd=session_target_fd,
                    target_lease=lease,
                    corpus=corpus,
                    provider_capability_verification_keys=provider_capability_verification_keys,
                    provider_revocation_verification_keys=provider_revocation_verification_keys,
                    source_head_verification_keys=source_head_verification_keys,
                    provider_revocation_floor_pins=provider_revocation_floor_pins,
                    source_floor_pins=source_floor_pins,
                    expected_target_store_id=origin.target_store_id,
                    expected_semantic_source_sha256=expected_semantic_source_sha256,
                    expected_contract_sha256=expected_contract_sha256,
                )
            finally:
                if target_lease is None:
                    _issuer_release_target_lease(lease)
        else:
            observed_sha256 = _issuer_observed_copy(
                target_fd=session_target_fd,
                target_lease=lease,
                corpus=corpus,
                provider_capability_verification_keys=provider_capability_verification_keys,
                provider_revocation_verification_keys=provider_revocation_verification_keys,
                source_head_verification_keys=source_head_verification_keys,
                provider_revocation_floor_pins=provider_revocation_floor_pins,
                source_floor_pins=source_floor_pins,
                expected_target_store_id=origin.target_store_id,
                expected_semantic_source_sha256=expected_semantic_source_sha256,
                expected_contract_sha256=expected_contract_sha256,
            )
        if observed_sha256 != origin.copy_audit_sha256:
            raise ValueError("issuer abort preparation target audit")


def _fixture_migration_lifecycle_issuer_main(
    socket_path: str,
    supervisor_pid: int,
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
    recovery_fault_boundary: _RecoveryFaultBoundary | None,
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
    recovery_copy_completion: Epoch0RecoveryCopyCompletionV1 | None = None
    recovery_copy_preparation_completion: Epoch0RecoveryCopyPreparationCompletionV1 | None = None
    recovery_barrier_acquisition_completion: Epoch0RecoveryBarrierAcquisitionCompletionV1 | None = (
        None
    )
    recovery_source_sealing_completion: Epoch0RecoverySourceSealingCompletionV1 | None = None
    recovery_abort_preparation_completion: Epoch0RecoveryAbortPreparationCompletionV1 | None = None
    recovery_abort_rename_completion: Epoch0RecoveryAbortRenameCompletionV1 | None = None
    recovery_peer_exited = False
    recovery_peer_pid: int | None = None
    pending_recovery_peer_pid: int | None = None
    pending_recovery_peer_revoked = False
    rejected_recovery_peer_pids: set[int] = set()
    copy_completed = False
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    process_watch = select.kqueue()
    active_store_revoked = False
    pending_recovery_fault = recovery_fault_boundary

    def inject_recovery_fault(boundary: _RecoveryFaultBoundary) -> None:
        nonlocal pending_recovery_fault
        if pending_recovery_fault == boundary:
            pending_recovery_fault = None
            completion_document = None
            if (
                boundary.startswith("barrier_")
                and recovery_barrier_acquisition_completion is not None
            ):
                completion_document = _issuer_recovery_barrier_acquisition_completion_document(
                    recovery_barrier_acquisition_completion
                )
            elif boundary.startswith("seal_") and recovery_source_sealing_completion is not None:
                completion_document = _issuer_recovery_source_sealing_completion_document(
                    recovery_source_sealing_completion
                )
            elif (
                boundary.startswith("abort_prepare_")
                and recovery_abort_preparation_completion is not None
            ):
                completion_document = _issuer_recovery_abort_preparation_completion_document(
                    recovery_abort_preparation_completion
                )
            elif (
                boundary.startswith("abort_rename_")
                and recovery_abort_rename_completion is not None
            ):
                completion_document = _issuer_recovery_abort_rename_completion_document(
                    recovery_abort_rename_completion
                )
            raise _InjectedRecoveryFault(
                f"injected issuer recovery fault: {boundary}",
                completion_document=completion_document,
            )

    def inject_abort_prepare_persistence_fault(
        boundary: Literal["after_rename", "after_parent_fsync", "after_reread"],
    ) -> None:
        mapped = cast(
            _RecoveryFaultBoundary,
            {
                "after_rename": "abort_prepare_after_rename",
                "after_parent_fsync": "abort_prepare_after_parent_fsync",
                "after_reread": "abort_prepare_after_reread",
            }[boundary],
        )
        inject_recovery_fault(mapped)

    def inject_prepare_persistence_fault(
        boundary: Literal["after_rename", "after_parent_fsync", "after_reread"],
    ) -> None:
        mapped: _RecoveryFaultBoundary = cast(_RecoveryFaultBoundary, f"prepare_{boundary}")
        inject_recovery_fault(mapped)

    def inject_abort_rename_persistence_fault(
        boundary: Literal["after_rename", "after_parent_fsync", "after_reread"],
    ) -> None:
        mapped = cast(
            _RecoveryFaultBoundary,
            {
                "after_rename": "abort_rename_after_journal_rename",
                "after_parent_fsync": "abort_rename_after_journal_parent_fsync",
                "after_reread": "abort_rename_after_journal_reread",
            }[boundary],
        )
        inject_recovery_fault(mapped)

    def inject_barrier_root_persistence_fault(
        boundary: Literal["after_rename", "after_parent_fsync"],
    ) -> None:
        mapped = cast(
            _RecoveryFaultBoundary,
            {
                "after_rename": "barrier_after_root_rename",
                "after_parent_fsync": "barrier_after_root_fsync",
            }[boundary],
        )
        inject_recovery_fault(mapped)

    def inject_barrier_journal_persistence_fault(
        boundary: Literal["after_rename", "after_parent_fsync", "after_reread"],
    ) -> None:
        mapped = cast(
            _RecoveryFaultBoundary,
            {
                "after_rename": "barrier_after_journal_rename",
                "after_parent_fsync": "barrier_after_journal_parent_fsync",
                "after_reread": "barrier_after_journal_reread",
            }[boundary],
        )
        inject_recovery_fault(mapped)

    def inject_sealing_child_fault(operation: str, role: str | None) -> None:
        operation_token = {
            "deny_new_admission": "deny",
            "drain_terminal_only": "drain",
            "close_and_revoke_all_writers": "revoke",
            "checkpoint_and_plant_test_all_mutators": "verify",
            "seal_and_collect": "collect",
        }.get(operation)
        role_token = {
            "owner-private-source-v1": "owner",
            "paid-lane-fixture-v1": "paid",
            "provider-authority-v4": "provider",
            None: "all_children",
        }.get(role)
        if operation_token is None or role_token is None:
            raise ValueError("issuer sealing fault boundary")
        boundary = cast(
            _RecoveryFaultBoundary,
            f"seal_{operation_token}_after_"
            + (f"child_{role_token}" if role is not None else role_token),
        )
        inject_recovery_fault(boundary)

    def inject_sealing_root_fault(
        operation: str,
        boundary: Literal["after_rename", "after_parent_fsync", "after_reread"],
    ) -> None:
        operation_token = {
            "deny_new_admission": "deny",
            "drain_terminal_only": "drain",
            "close_and_revoke_all_writers": "revoke",
            "checkpoint_and_plant_test_all_mutators": "verify",
            "seal_and_collect": "collect",
        }.get(operation)
        boundary_token = {
            "after_rename": "rename",
            "after_parent_fsync": "fsync",
            "after_reread": "reread",
        }[boundary]
        if operation_token is None:
            raise ValueError("issuer sealing root fault boundary")
        inject_recovery_fault(
            cast(
                _RecoveryFaultBoundary,
                f"seal_{operation_token}_after_root_{boundary_token}",
            )
        )

    def inject_sealing_journal_fault(
        boundary: Literal["after_rename", "after_parent_fsync", "after_reread"],
    ) -> None:
        mapped = cast(
            _RecoveryFaultBoundary,
            {
                "after_rename": "seal_after_journal_rename",
                "after_parent_fsync": "seal_after_journal_parent_fsync",
                "after_reread": "seal_after_journal_reread",
            }[boundary],
        )
        inject_recovery_fault(mapped)

    def recover_schema_only_to_barrier_acquired(
        *,
        session_root_fd: int,
        session_parent_fd: int,
        session_target_fd: int,
        expected_schema_only_state_sha256: str,
        expected_pins: Epoch0RecoveryAuthorityPinsV1,
    ) -> Epoch0RecoveryBarrierAcquisitionCompletionV1:
        nonlocal committed, pending_candidate, pending_state
        nonlocal recovery_barrier_acquisition_completion
        del session_target_fd
        if (
            committed is None
            or expected_pins.lifecycle_phase != "schema_only"
            or expected_pins.state_sha256 != expected_schema_only_state_sha256
            or pending_state is not None
        ):
            raise ValueError("issuer recovery barrier acquisition phase")
        durable = _read_signed_migration_lifecycle_state(
            parent_fd=session_parent_fd,
            target_basename=expected_pins.target_basename,
            verification_key=verification_key,
        )
        if (
            recovery_barrier_acquisition_completion is not None
            and durable == recovery_barrier_acquisition_completion.barrier_acquired_state
        ):
            with _issuer_transition_lock(session_root_fd):
                durable = _confirm_signed_migration_lifecycle_state_durable(
                    parent_fd=session_parent_fd,
                    expected_state=recovery_barrier_acquisition_completion.barrier_acquired_state,
                    verification_key=verification_key,
                )
                os.fsync(session_root_fd)
                root_record = _issuer_authenticate_schema_recovery_root(
                    session_root_fd,
                    expected_root_id=expected_pins.root_id,
                    expected_root_manifest_sha256=expected_pins.root_manifest_sha256,
                )
                if (
                    root_record.get("state") != "quiesced"
                    or root_record.get("barrier_id")
                    != recovery_barrier_acquisition_completion.barrier_acquired_state.barrier_id
                    or root_record.get("freeze_nonce")
                    != recovery_barrier_acquisition_completion.barrier_acquired_state.freeze_nonce
                ):
                    raise ValueError("issuer recovery barrier acquisition replay root")
                committed = durable
                return recovery_barrier_acquisition_completion
        if (
            committed.lifecycle_phase != "schema_only"
            or committed.state_sha256 != expected_schema_only_state_sha256
            or durable != committed
        ):
            raise ValueError("issuer recovery schema journal")
        schema_only = committed
        with _issuer_transition_lock(session_root_fd):
            root_record = _issuer_authenticate_schema_recovery_root(
                session_root_fd,
                expected_root_id=schema_only.root_id,
                expected_root_manifest_sha256=schema_only.root_manifest_sha256,
            )
            root_ahead = (
                root_record.get("state") == "quiesced" and root_record.get("barrier_id") is not None
            )
            if root_ahead and root_record.get("state") != "quiesced":
                raise ValueError("issuer recovery schema root-ahead state")
            if not root_ahead and root_record.get("state") != "open":
                raise ValueError("issuer recovery schema root state")
            working_root = dict(root_record)
            barrier_id, freeze_nonce, mutate_root = _issuer_barrier_material_for_schema_recovery(
                working_root,
                root_ahead=root_ahead,
                cached_barrier=(
                    (
                        cast(
                            str,
                            recovery_barrier_acquisition_completion.barrier_acquired_state.barrier_id,
                        ),
                        cast(
                            str,
                            recovery_barrier_acquisition_completion.barrier_acquired_state.freeze_nonce,
                        ),
                    )
                    if recovery_barrier_acquisition_completion is not None and not root_ahead
                    else None
                ),
            )
            witness_sha256 = _issuer_witness_sha256(
                root_record=working_root,
                target_parent_identity=(
                    schema_only.target_parent_dev,
                    schema_only.target_parent_ino,
                ),
                target_basename=schema_only.target_basename,
                target_identity=(schema_only.target_dev, schema_only.target_ino),
            )
            if recovery_barrier_acquisition_completion is None:
                material = schema_only.model_dump(
                    mode="python",
                    exclude={"issuer_key_id", "state_sha256", "signature_ed25519"},
                )
                material.update(
                    {
                        "lifecycle_phase": "barrier_acquired",
                        "phase_version": 1,
                        "issuer_sequence": 1,
                        "updated_at_ms": max(
                            schema_only.updated_at_ms, time.time_ns() // 1_000_000
                        ),
                        "previous_state_sha256": schema_only.state_sha256,
                        "barrier_id": barrier_id,
                        "freeze_nonce": freeze_nonce,
                        "witness_sha256": witness_sha256,
                        "issuer_key_id": key_id,
                    }
                )
                state_sha256 = _migration_lifecycle_state_sha256(material)
                material["state_sha256"] = state_sha256
                material["signature_ed25519"] = private_key.sign(
                    _MIGRATION_LIFECYCLE_SIGNATURE_DOMAIN + bytes.fromhex(state_sha256)
                )
                barrier_acquired = SignedMigrationLifecycleStateV1.model_validate(material)
                recovery_barrier_acquisition_completion = (
                    Epoch0RecoveryBarrierAcquisitionCompletionV1(
                        schema_only_state=schema_only,
                        barrier_acquired_state=barrier_acquired,
                    )
                )
            else:
                if (
                    recovery_barrier_acquisition_completion.schema_only_state != schema_only
                    or recovery_barrier_acquisition_completion.barrier_acquired_state.barrier_id
                    != barrier_id
                    or recovery_barrier_acquisition_completion.barrier_acquired_state.freeze_nonce
                    != freeze_nonce
                    or recovery_barrier_acquisition_completion.barrier_acquired_state.witness_sha256
                    != witness_sha256
                ):
                    raise ValueError("issuer recovery barrier acquisition cached completion")
                barrier_acquired = recovery_barrier_acquisition_completion.barrier_acquired_state
            _verify_epoch0_recovery_barrier_acquisition_completion_v1(
                recovery_barrier_acquisition_completion,
                issuer_verification_key=verification_key,
                expected_schema_only_pins=expected_pins,
            )
            inject_recovery_fault("barrier_after_intent")
            if mutate_root:
                _issuer_durable_write_root_record(
                    session_root_fd,
                    working_root,
                    fault_hook=inject_barrier_root_persistence_fault,
                )
                reread_root = _issuer_authenticate_schema_recovery_root(
                    session_root_fd,
                    expected_root_id=schema_only.root_id,
                    expected_root_manifest_sha256=schema_only.root_manifest_sha256,
                )
                if (
                    reread_root.get("state") != "quiesced"
                    or reread_root.get("barrier_id") != barrier_id
                    or reread_root.get("freeze_nonce") != freeze_nonce
                    or len(cast(list[object], reread_root.get("transition_evidence"))) != 1
                ):
                    raise ValueError("issuer recovery barrier root reread")
                inject_recovery_fault("barrier_after_root_reread")
            else:
                os.fsync(session_root_fd)
                reread_root = _issuer_authenticate_schema_recovery_root(
                    session_root_fd,
                    expected_root_id=schema_only.root_id,
                    expected_root_manifest_sha256=schema_only.root_manifest_sha256,
                )
                if reread_root != working_root:
                    raise ValueError("issuer recovery barrier root durability adoption")
            _persist_signed_migration_lifecycle_state(
                parent_fd=session_parent_fd,
                state=barrier_acquired,
                verification_key=verification_key,
                expected_prior_state_sha256=schema_only.state_sha256,
                _fault_hook=inject_barrier_journal_persistence_fault,
            )
            reread = _read_signed_migration_lifecycle_state(
                parent_fd=session_parent_fd,
                target_basename=schema_only.target_basename,
                verification_key=verification_key,
            )
            if reread != barrier_acquired:
                raise ValueError("issuer recovery barrier journal reread")
            committed = barrier_acquired
            pending_candidate = None
            pending_state = None
            return recovery_barrier_acquisition_completion

    def recover_barrier_acquired_to_sources_sealed(
        *,
        session_root_fd: int,
        session_parent_fd: int,
        session_target_fd: int,
        expected_barrier_acquired_state_sha256: str,
        expected_pins: Epoch0RecoveryAuthorityPinsV1,
    ) -> Epoch0RecoverySourceSealingCompletionV1:
        nonlocal committed, pending_candidate, pending_state
        nonlocal recovery_source_sealing_completion
        del session_target_fd
        if (
            committed is None
            or expected_pins.lifecycle_phase != "barrier_acquired"
            or expected_pins.state_sha256 != expected_barrier_acquired_state_sha256
            or pending_state is not None
        ):
            raise ValueError("issuer recovery source sealing phase")
        durable = _read_signed_migration_lifecycle_state(
            parent_fd=session_parent_fd,
            target_basename=expected_pins.target_basename,
            verification_key=verification_key,
        )
        if (
            recovery_source_sealing_completion is not None
            and durable == recovery_source_sealing_completion.sources_sealed_state
        ):
            with _issuer_transition_lock(session_root_fd):
                durable = _confirm_signed_migration_lifecycle_state_durable(
                    parent_fd=session_parent_fd,
                    expected_state=recovery_source_sealing_completion.sources_sealed_state,
                    verification_key=verification_key,
                )
                root_record = _issuer_authenticate_barrier_recovery_root(
                    session_root_fd,
                    expected_root_id=expected_pins.root_id,
                    expected_root_manifest_sha256=expected_pins.root_manifest_sha256,
                    expected_barrier_id=cast(
                        str,
                        recovery_source_sealing_completion.sources_sealed_state.barrier_id,
                    ),
                    expected_freeze_nonce=cast(
                        str,
                        recovery_source_sealing_completion.sources_sealed_state.freeze_nonce,
                    ),
                )
                if root_record.get("state") != "sealed":
                    raise ValueError("issuer recovery source sealing replay root")
                compatible = dict(root_record)
                corpus = _collect_sealed_corpus(_issuer_root_path(session_root_fd), compatible)
                if (
                    corpus.source_manifest_sha256
                    != recovery_source_sealing_completion.sources_sealed_state.source_manifest_sha256
                ):
                    raise ValueError("issuer recovery source sealing replay manifest")
                committed = durable
                return recovery_source_sealing_completion
        if (
            committed.lifecycle_phase != "barrier_acquired"
            or committed.state_sha256 != expected_barrier_acquired_state_sha256
            or durable != committed
        ):
            raise ValueError("issuer recovery barrier acquired journal")
        barrier_acquired = committed
        with _issuer_transition_lock(session_root_fd):
            root_record = _issuer_authenticate_barrier_recovery_root(
                session_root_fd,
                expected_root_id=barrier_acquired.root_id,
                expected_root_manifest_sha256=barrier_acquired.root_manifest_sha256,
                expected_barrier_id=cast(str, barrier_acquired.barrier_id),
                expected_freeze_nonce=cast(str, barrier_acquired.freeze_nonce),
            )
            os.fsync(session_root_fd)
            confirmed_root_record = _issuer_authenticate_barrier_recovery_root(
                session_root_fd,
                expected_root_id=barrier_acquired.root_id,
                expected_root_manifest_sha256=barrier_acquired.root_manifest_sha256,
                expected_barrier_id=cast(str, barrier_acquired.barrier_id),
                expected_freeze_nonce=cast(str, barrier_acquired.freeze_nonce),
            )
            if confirmed_root_record != root_record:
                raise ValueError("issuer recovery sealing root durability adoption")
            working_root = dict(root_record)
            root_path = _issuer_root_path(session_root_fd)

            def _cache_source_sealing_completion(
                corpus: FrozenPaidLaneMigrationCorpusV1,
            ) -> SignedMigrationLifecycleStateV1:
                nonlocal recovery_source_sealing_completion
                if recovery_source_sealing_completion is None:
                    material = barrier_acquired.model_dump(
                        mode="python",
                        exclude={"issuer_key_id", "state_sha256", "signature_ed25519"},
                    )
                    material.update(
                        {
                            "lifecycle_phase": "sources_sealed",
                            "phase_version": 2,
                            "issuer_sequence": 2,
                            "updated_at_ms": max(
                                barrier_acquired.updated_at_ms,
                                time.time_ns() // 1_000_000,
                            ),
                            "previous_state_sha256": barrier_acquired.state_sha256,
                            "source_manifest_sha256": corpus.source_manifest_sha256,
                            "witness_sha256": barrier_acquired.witness_sha256,
                            "issuer_key_id": key_id,
                        }
                    )
                    state_sha256 = _migration_lifecycle_state_sha256(material)
                    material["state_sha256"] = state_sha256
                    material["signature_ed25519"] = private_key.sign(
                        _MIGRATION_LIFECYCLE_SIGNATURE_DOMAIN + bytes.fromhex(state_sha256)
                    )
                    sources_sealed = SignedMigrationLifecycleStateV1.model_validate(material)
                    recovery_source_sealing_completion = Epoch0RecoverySourceSealingCompletionV1(
                        barrier_acquired_state=barrier_acquired,
                        sources_sealed_state=sources_sealed,
                    )
                elif (
                    recovery_source_sealing_completion.barrier_acquired_state != barrier_acquired
                    or recovery_source_sealing_completion.sources_sealed_state.source_manifest_sha256
                    != corpus.source_manifest_sha256
                ):
                    raise ValueError("issuer recovery source sealing cached completion")
                return recovery_source_sealing_completion.sources_sealed_state

            if working_root.get("state") == "sealed":
                _cache_source_sealing_completion(_collect_sealed_corpus(root_path, working_root))
            else:
                subphase_order = (
                    "quiesced",
                    "admission_denied",
                    "drained",
                    "writers_revoked",
                    "writers_verified",
                    "sealed",
                )
                for operation, prior_state, next_state in _RECOVERY_ROOT_BARRIER_SUBPHASES:
                    current_state = working_root.get("state")
                    if type(current_state) is not str or current_state not in subphase_order:
                        raise ValueError("issuer recovery root subphase mismatch")
                    if subphase_order.index(current_state) >= subphase_order.index(next_state):
                        continue
                    if current_state != prior_state:
                        raise ValueError("issuer recovery root subphase mismatch")
                    _audit_transition_evidence(working_root)

                    def inject_current_root_fault(
                        boundary: Literal["after_rename", "after_parent_fsync"],
                        *,
                        current_operation: str = operation,
                    ) -> None:
                        inject_sealing_root_fault(current_operation, boundary)

                    if operation == "seal_and_collect":
                        _execute_barrier_child_operation(
                            root_path,
                            working_root,
                            operation,
                            recovery_mode=True,
                            fault_hook=inject_sealing_child_fault,
                        )
                        measured = _measure_child_adapters(root_path)
                        evidence = working_root.get("child_adapter_evidence")
                        if type(evidence) is not dict:
                            raise ValueError("issuer recovery sealed child evidence")
                        seal_working = dict(working_root)
                        seal_working["state"] = "sealed"
                        evidence_copy = dict(evidence)
                        evidence_copy["sealed_measurements"] = measured
                        seal_working["child_adapter_evidence"] = evidence_copy
                        _cache_source_sealing_completion(
                            _collect_sealed_corpus(root_path, seal_working)
                        )
                        assert recovery_source_sealing_completion is not None
                        _verify_epoch0_recovery_source_sealing_completion_v1(
                            recovery_source_sealing_completion,
                            issuer_verification_key=verification_key,
                            expected_barrier_acquired_pins=expected_pins,
                        )
                        inject_recovery_fault("seal_after_manifest_completion_cache")
                        evidence["sealed_measurements"] = measured
                        _append_transition_evidence(
                            working_root,
                            operation=operation,
                            prior_state=prior_state,
                            next_state=next_state,
                        )
                        working_root["state"] = next_state
                        _issuer_durable_write_root_record(
                            session_root_fd,
                            working_root,
                            fault_hook=inject_current_root_fault,
                        )
                        reread_root = _issuer_authenticate_barrier_recovery_root(
                            session_root_fd,
                            expected_root_id=barrier_acquired.root_id,
                            expected_root_manifest_sha256=barrier_acquired.root_manifest_sha256,
                            expected_barrier_id=cast(str, barrier_acquired.barrier_id),
                            expected_freeze_nonce=cast(str, barrier_acquired.freeze_nonce),
                        )
                        if reread_root.get("state") != "sealed":
                            raise ValueError("issuer recovery source sealing root reread")
                        inject_sealing_root_fault(operation, "after_reread")
                    else:
                        _execute_barrier_child_operation(
                            root_path,
                            working_root,
                            operation,
                            recovery_mode=True,
                            fault_hook=inject_sealing_child_fault,
                        )
                        _append_transition_evidence(
                            working_root,
                            operation=operation,
                            prior_state=prior_state,
                            next_state=next_state,
                        )
                        working_root["state"] = next_state
                        _issuer_durable_write_root_record(
                            session_root_fd,
                            working_root,
                            fault_hook=inject_current_root_fault,
                        )
                        reread_root = _issuer_authenticate_barrier_recovery_root(
                            session_root_fd,
                            expected_root_id=barrier_acquired.root_id,
                            expected_root_manifest_sha256=barrier_acquired.root_manifest_sha256,
                            expected_barrier_id=cast(str, barrier_acquired.barrier_id),
                            expected_freeze_nonce=cast(str, barrier_acquired.freeze_nonce),
                        )
                        if reread_root.get("state") != next_state:
                            raise ValueError("issuer recovery source sealing subphase reread")
                        inject_sealing_root_fault(operation, "after_reread")
                    working_root = dict(reread_root)
            if recovery_source_sealing_completion is None:
                raise ValueError("issuer recovery source sealing completion missing")
            sources_sealed = recovery_source_sealing_completion.sources_sealed_state
            _verify_epoch0_recovery_source_sealing_completion_v1(
                recovery_source_sealing_completion,
                issuer_verification_key=verification_key,
                expected_barrier_acquired_pins=expected_pins,
            )
            _persist_signed_migration_lifecycle_state(
                parent_fd=session_parent_fd,
                state=sources_sealed,
                verification_key=verification_key,
                expected_prior_state_sha256=barrier_acquired.state_sha256,
                _fault_hook=inject_sealing_journal_fault,
            )
            reread = _read_signed_migration_lifecycle_state(
                parent_fd=session_parent_fd,
                target_basename=barrier_acquired.target_basename,
                verification_key=verification_key,
            )
            if reread != sources_sealed:
                raise ValueError("issuer recovery source sealing journal reread")
            committed = sources_sealed
            pending_candidate = None
            pending_state = None
            return recovery_source_sealing_completion

    def recover_sources_sealed_to_copy_prepared(
        *,
        session_root_fd: int,
        session_parent_fd: int,
        session_target_fd: int,
        expected_sources_sealed_state_sha256: str,
        expected_pins: Epoch0RecoveryAuthorityPinsV1,
    ) -> Epoch0RecoveryCopyPreparationCompletionV1:
        nonlocal committed, pending_candidate, pending_state
        nonlocal recovery_copy_preparation_completion, target_lease
        if (
            committed is None
            or expected_pins.lifecycle_phase != "sources_sealed"
            or expected_pins.state_sha256 != expected_sources_sealed_state_sha256
            or pending_state is not None
        ):
            raise ValueError("issuer recovery preparation phase")
        durable = _read_signed_migration_lifecycle_state(
            parent_fd=session_parent_fd,
            target_basename=expected_pins.target_basename,
            verification_key=verification_key,
        )
        if (
            recovery_copy_preparation_completion is not None
            and durable == recovery_copy_preparation_completion.prepared_state
        ):
            with _issuer_transition_lock(session_root_fd):
                durable = _confirm_signed_migration_lifecycle_state_durable(
                    parent_fd=session_parent_fd,
                    expected_state=recovery_copy_preparation_completion.prepared_state,
                    verification_key=verification_key,
                )
                compatible = _issuer_compatible_root_record(
                    session_root_fd, durable.lifecycle_phase
                )
                corpus = _collect_sealed_corpus(_issuer_root_path(session_root_fd), compatible)
                if target_lease is None:
                    target_lease = _issuer_acquire_target_lease(session_target_fd)
                audit = _issuer_copy_intent_audit(
                    target_fd=session_target_fd,
                    target_lease=target_lease,
                    corpus=corpus,
                    provider_capability_verification_keys=(provider_capability_verification_keys),
                    provider_revocation_verification_keys=(provider_revocation_verification_keys),
                    source_head_verification_keys=source_head_verification_keys,
                    provider_revocation_floor_pins=provider_revocation_floor_pins,
                    source_floor_pins=source_floor_pins,
                    expected_target_store_id=durable.target_store_id,
                    expected_semantic_source_sha256=expected_semantic_source_sha256,
                    expected_contract_sha256=expected_contract_sha256,
                )
                if audit != recovery_copy_preparation_completion.copy_audit:
                    raise ValueError("issuer recovery preparation replay audit")
                committed = durable
                return recovery_copy_preparation_completion
        if (
            committed.lifecycle_phase != "sources_sealed"
            or committed.state_sha256 != expected_sources_sealed_state_sha256
            or durable != committed
        ):
            raise ValueError("issuer recovery sealed journal")
        sealed = committed
        with _issuer_transition_lock(session_root_fd):
            compatible = _issuer_compatible_root_record(session_root_fd, sealed.lifecycle_phase)
            corpus = _collect_sealed_corpus(_issuer_root_path(session_root_fd), compatible)
            if corpus.source_manifest_sha256 != sealed.source_manifest_sha256:
                raise ValueError("issuer recovery sealed corpus")
            if target_lease is None:
                target_lease = _issuer_acquire_target_lease(session_target_fd)
            audit = _issuer_copy_intent_audit(
                target_fd=session_target_fd,
                target_lease=target_lease,
                corpus=corpus,
                provider_capability_verification_keys=provider_capability_verification_keys,
                provider_revocation_verification_keys=provider_revocation_verification_keys,
                source_head_verification_keys=source_head_verification_keys,
                provider_revocation_floor_pins=provider_revocation_floor_pins,
                source_floor_pins=source_floor_pins,
                expected_target_store_id=sealed.target_store_id,
                expected_semantic_source_sha256=expected_semantic_source_sha256,
                expected_contract_sha256=expected_contract_sha256,
            )
            if recovery_copy_preparation_completion is None:
                material = sealed.model_dump(
                    mode="python",
                    exclude={"issuer_key_id", "state_sha256", "signature_ed25519"},
                )
                material.update(
                    {
                        "lifecycle_phase": "copy_prepared",
                        "phase_version": 3,
                        "issuer_sequence": 3,
                        "updated_at_ms": max(sealed.updated_at_ms, time.time_ns() // 1_000_000),
                        "previous_state_sha256": sealed.state_sha256,
                        "copy_audit_sha256": _copy_audit_sha256(audit),
                        "issuer_key_id": key_id,
                    }
                )
                state_sha256 = _migration_lifecycle_state_sha256(material)
                material["state_sha256"] = state_sha256
                material["signature_ed25519"] = private_key.sign(
                    _MIGRATION_LIFECYCLE_SIGNATURE_DOMAIN + bytes.fromhex(state_sha256)
                )
                prepared = SignedMigrationLifecycleStateV1.model_validate(material)
                recovery_copy_preparation_completion = Epoch0RecoveryCopyPreparationCompletionV1(
                    sealed_state=sealed,
                    prepared_state=prepared,
                    copy_audit=audit,
                )
            else:
                if (
                    recovery_copy_preparation_completion.sealed_state != sealed
                    or recovery_copy_preparation_completion.copy_audit != audit
                ):
                    raise ValueError("issuer recovery preparation cached completion")
                prepared = recovery_copy_preparation_completion.prepared_state
            _verify_epoch0_recovery_copy_preparation_completion_v1(
                recovery_copy_preparation_completion,
                issuer_verification_key=verification_key,
                expected_sealed_pins=expected_pins,
            )
            inject_recovery_fault("prepare_after_audit")
            _persist_signed_migration_lifecycle_state(
                parent_fd=session_parent_fd,
                state=prepared,
                verification_key=verification_key,
                expected_prior_state_sha256=sealed.state_sha256,
                _fault_hook=inject_prepare_persistence_fault,
            )
            reread = _read_signed_migration_lifecycle_state(
                parent_fd=session_parent_fd,
                target_basename=sealed.target_basename,
                verification_key=verification_key,
            )
            if reread != prepared:
                raise ValueError("issuer recovery prepared journal reread")
            committed = prepared
            pending_candidate = None
            pending_state = None
            return recovery_copy_preparation_completion

    def supervisor_exited() -> bool:
        nonlocal active_store_revoked, pending_recovery_peer_revoked, recovery_peer_exited
        supervisor_is_gone = False
        for event in process_watch.control(None, 8, 0):
            if event.ident == supervisor_pid and event.fflags & select.KQ_NOTE_EXIT:
                supervisor_is_gone = True
            if event.ident == authorized_pid and event.fflags & (
                select.KQ_NOTE_EXIT | select.KQ_NOTE_FORK
            ):
                active_store_revoked = True
            if (
                recovery_peer_pid is not None
                and event.ident == recovery_peer_pid
                and event.fflags & (select.KQ_NOTE_EXIT | select.KQ_NOTE_FORK)
            ):
                recovery_peer_exited = True
            if (
                pending_recovery_peer_pid is not None
                and event.ident == pending_recovery_peer_pid
                and event.fflags & (select.KQ_NOTE_EXIT | select.KQ_NOTE_FORK)
            ):
                pending_recovery_peer_revoked = True
        return supervisor_is_gone

    def recover_copy_prepared_epoch0(
        *,
        session_root_fd: int,
        session_parent_fd: int,
        session_target_fd: int,
        expected_prepared_state_sha256: str,
        expected_pins: Epoch0RecoveryAuthorityPinsV1,
    ) -> Epoch0RecoveryCopyCompletionV1:
        nonlocal committed, copy_completed, pending_candidate, pending_state
        nonlocal recovery_copy_completion, target_lease
        if (
            committed is None
            or bound_root_fd is None
            or bound_target_fd is None
            or pending_state is not None
            or expected_pins.lifecycle_phase != "copy_prepared"
            or expected_pins.state_sha256 != expected_prepared_state_sha256
        ):
            raise ValueError("issuer recovery copy phase")
        durable = _read_signed_migration_lifecycle_state(
            parent_fd=session_parent_fd,
            target_basename=expected_pins.target_basename,
            verification_key=verification_key,
        )
        if (
            recovery_copy_completion is not None
            and durable == recovery_copy_completion.copied_state
        ):
            with _issuer_transition_lock(session_root_fd):
                durable = _confirm_signed_migration_lifecycle_state_durable(
                    parent_fd=session_parent_fd,
                    expected_state=recovery_copy_completion.copied_state,
                    verification_key=verification_key,
                )
                if target_lease is None:
                    target_lease = _issuer_acquire_target_lease(session_target_fd)
                compatible = _issuer_compatible_root_record(
                    session_root_fd, durable.lifecycle_phase
                )
                corpus = _collect_sealed_corpus(_issuer_root_path(session_root_fd), compatible)
                observed_sha256 = _issuer_observed_copy(
                    target_fd=session_target_fd,
                    target_lease=target_lease,
                    corpus=corpus,
                    provider_capability_verification_keys=(provider_capability_verification_keys),
                    provider_revocation_verification_keys=(provider_revocation_verification_keys),
                    source_head_verification_keys=source_head_verification_keys,
                    provider_revocation_floor_pins=provider_revocation_floor_pins,
                    source_floor_pins=source_floor_pins,
                    expected_target_store_id=durable.target_store_id,
                    expected_semantic_source_sha256=expected_semantic_source_sha256,
                    expected_contract_sha256=expected_contract_sha256,
                )
                if observed_sha256 != durable.copy_audit_sha256:
                    raise ValueError("issuer recovery copied replay target")
                committed = durable
                _issuer_release_target_lease(target_lease)
                target_lease = None
                return recovery_copy_completion
        if (
            recovery_copy_completion is not None
            and durable != recovery_copy_completion.prepared_state
        ):
            raise ValueError("issuer recovery copied replay journal")
        if (
            committed.lifecycle_phase != "copy_prepared"
            or committed.state_sha256 != expected_prepared_state_sha256
            or durable != committed
        ):
            raise ValueError("issuer recovery prepared journal")
        prepared = committed
        with _issuer_transition_lock(session_root_fd):
            compatible = _issuer_compatible_root_record(session_root_fd, prepared.lifecycle_phase)
            corpus = _collect_sealed_corpus(_issuer_root_path(session_root_fd), compatible)
            if (
                corpus.source_manifest_sha256 != prepared.source_manifest_sha256
                or prepared.copy_audit_sha256 is None
            ):
                raise ValueError("issuer recovery prepared corpus")
            if target_lease is None:
                target_lease = _issuer_acquire_target_lease(session_target_fd)
            try:
                audit, copied = _reconcile_copy_prepared_target_v1(
                    target_lease,
                    corpus=corpus,
                    expected_copy_audit_sha256=prepared.copy_audit_sha256,
                    target_store_id=prepared.target_store_id,
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
                inject_recovery_fault("after_target_commit")
                target_lease.execute("BEGIN IMMEDIATE")
                confirmed, confirmed_copied = _reconcile_copy_prepared_target_v1(
                    target_lease,
                    corpus=corpus,
                    expected_copy_audit_sha256=prepared.copy_audit_sha256,
                    target_store_id=prepared.target_store_id,
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
                    raise ValueError("issuer recovery copy confirmation")
                del copied
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
            if recovery_copy_completion is None:
                material = prepared.model_dump(
                    mode="python",
                    exclude={"issuer_key_id", "state_sha256", "signature_ed25519"},
                )
                material.update(
                    {
                        "lifecycle_phase": "copied_epoch0",
                        "phase_version": 4,
                        "issuer_sequence": 4,
                        "updated_at_ms": max(prepared.updated_at_ms, time.time_ns() // 1_000_000),
                        "previous_state_sha256": prepared.state_sha256,
                        "issuer_key_id": key_id,
                    }
                )
                state_sha256 = _migration_lifecycle_state_sha256(material)
                material["state_sha256"] = state_sha256
                material["signature_ed25519"] = private_key.sign(
                    _MIGRATION_LIFECYCLE_SIGNATURE_DOMAIN + bytes.fromhex(state_sha256)
                )
                copied_state = SignedMigrationLifecycleStateV1.model_validate(material)
                _verify_migration_lifecycle_transition(prepared, copied_state, verification_key)
                recovery_copy_completion = Epoch0RecoveryCopyCompletionV1(
                    prepared_state=prepared,
                    copied_state=copied_state,
                    copy_audit=confirmed,
                )
            else:
                copied_state = recovery_copy_completion.copied_state
                if (
                    recovery_copy_completion.prepared_state != prepared
                    or recovery_copy_completion.copy_audit != confirmed
                ):
                    raise ValueError("issuer recovery copy cached completion")
            _verify_epoch0_recovery_copy_completion_v1(
                recovery_copy_completion,
                issuer_verification_key=verification_key,
                expected_prepared_pins=expected_pins,
            )
            _persist_signed_migration_lifecycle_state(
                parent_fd=session_parent_fd,
                state=copied_state,
                verification_key=verification_key,
                expected_prior_state_sha256=prepared.state_sha256,
                _fault_hook=inject_recovery_fault,
            )
            reread = _read_signed_migration_lifecycle_state(
                parent_fd=session_parent_fd,
                target_basename=prepared.target_basename,
                verification_key=verification_key,
            )
            if reread != copied_state:
                raise ValueError("issuer recovery copied journal reread")
            committed = copied_state
            pending_candidate = None
            pending_state = None
            _issuer_release_target_lease(target_lease)
            target_lease = None
            return recovery_copy_completion

    def recover_prepare_abort_uncut_epoch0(
        *,
        session_root_fd: int,
        session_parent_fd: int,
        session_target_fd: int,
        expected_origin_state_sha256: str,
        expected_origin_pins: Epoch0RecoveryAuthorityPinsV1,
    ) -> Epoch0RecoveryAbortPreparationCompletionV1:
        nonlocal committed, pending_candidate, pending_state
        nonlocal recovery_abort_preparation_completion, target_lease
        if (
            committed is None
            or pending_state is not None
            or expected_origin_pins.lifecycle_phase
            not in {
                "schema_only",
                "barrier_acquired",
                "sources_sealed",
                "copy_prepared",
                "copied_epoch0",
            }
            or expected_origin_pins.state_sha256 != expected_origin_state_sha256
        ):
            raise ValueError("issuer recovery abort preparation phase")
        durable = _read_signed_migration_lifecycle_state(
            parent_fd=session_parent_fd,
            target_basename=expected_origin_pins.target_basename,
            verification_key=verification_key,
        )
        if (
            recovery_abort_preparation_completion is not None
            and durable == recovery_abort_preparation_completion.abort_prepared_state
        ):
            with _issuer_transition_lock(session_root_fd):
                durable = _confirm_signed_migration_lifecycle_state_durable(
                    parent_fd=session_parent_fd,
                    expected_state=recovery_abort_preparation_completion.abort_prepared_state,
                    verification_key=verification_key,
                )
                try:
                    _issuer_validate_abort_origin_custody(
                        session_root_fd=session_root_fd,
                        session_target_fd=session_target_fd,
                        origin=recovery_abort_preparation_completion.origin_state,
                        target_lease=target_lease,
                        provider_capability_verification_keys=provider_capability_verification_keys,
                        provider_revocation_verification_keys=provider_revocation_verification_keys,
                        source_head_verification_keys=source_head_verification_keys,
                        provider_revocation_floor_pins=provider_revocation_floor_pins,
                        source_floor_pins=source_floor_pins,
                        expected_semantic_source_sha256=expected_semantic_source_sha256,
                        expected_contract_sha256=expected_contract_sha256,
                    )
                except BaseException:
                    if target_lease is not None:
                        _issuer_release_target_lease(target_lease)
                    target_lease = None
                    raise
                _issuer_checkpoint_target_wal_and_release(target_lease)
                target_lease = None
                _issuer_require_target_abort_sidecars_absent(
                    parent_fd=session_parent_fd,
                    target_basename=expected_origin_pins.target_basename,
                    target_fd=session_target_fd,
                )
                committed = durable
                return recovery_abort_preparation_completion
        if (
            committed.lifecycle_phase != expected_origin_pins.lifecycle_phase
            or committed.state_sha256 != expected_origin_state_sha256
            or durable != committed
        ):
            raise ValueError("issuer recovery abort preparation origin journal")
        origin = committed
        with _issuer_transition_lock(session_root_fd):
            try:
                _issuer_validate_abort_origin_custody(
                    session_root_fd=session_root_fd,
                    session_target_fd=session_target_fd,
                    origin=origin,
                    target_lease=target_lease,
                    provider_capability_verification_keys=provider_capability_verification_keys,
                    provider_revocation_verification_keys=provider_revocation_verification_keys,
                    source_head_verification_keys=source_head_verification_keys,
                    provider_revocation_floor_pins=provider_revocation_floor_pins,
                    source_floor_pins=source_floor_pins,
                    expected_semantic_source_sha256=expected_semantic_source_sha256,
                    expected_contract_sha256=expected_contract_sha256,
                )
            except BaseException:
                if target_lease is not None:
                    _issuer_release_target_lease(target_lease)
                target_lease = None
                raise
            _issuer_checkpoint_target_wal_and_release(target_lease)
            target_lease = None
            _issuer_require_target_abort_sidecars_absent(
                parent_fd=session_parent_fd,
                target_basename=origin.target_basename,
                target_fd=session_target_fd,
            )
            if recovery_abort_preparation_completion is None:
                material = origin.model_dump(
                    mode="python",
                    exclude={"issuer_key_id", "state_sha256", "signature_ed25519"},
                )
                next_version = origin.phase_version + 1
                material.update(
                    {
                        "lifecycle_phase": "abort_prepared",
                        "phase_version": next_version,
                        "issuer_sequence": next_version,
                        "updated_at_ms": max(origin.updated_at_ms, time.time_ns() // 1_000_000),
                        "previous_state_sha256": origin.state_sha256,
                        "issuer_key_id": key_id,
                    }
                )
                state_sha256 = _migration_lifecycle_state_sha256(material)
                material["state_sha256"] = state_sha256
                material["signature_ed25519"] = private_key.sign(
                    _MIGRATION_LIFECYCLE_SIGNATURE_DOMAIN + bytes.fromhex(state_sha256)
                )
                abort_prepared = SignedMigrationLifecycleStateV1.model_validate(material)
                recovery_abort_preparation_completion = Epoch0RecoveryAbortPreparationCompletionV1(
                    origin_state=origin,
                    abort_prepared_state=abort_prepared,
                )
            else:
                if recovery_abort_preparation_completion.origin_state != origin:
                    raise ValueError("issuer recovery abort preparation cached completion")
                abort_prepared = recovery_abort_preparation_completion.abort_prepared_state
            _verify_epoch0_recovery_abort_preparation_completion_v1(
                recovery_abort_preparation_completion,
                issuer_verification_key=verification_key,
                expected_origin_pins=expected_origin_pins,
            )
            inject_recovery_fault("abort_prepare_after_intent")
            _persist_signed_migration_lifecycle_state(
                parent_fd=session_parent_fd,
                state=abort_prepared,
                verification_key=verification_key,
                expected_prior_state_sha256=origin.state_sha256,
                _fault_hook=inject_abort_prepare_persistence_fault,
            )
            reread = _read_signed_migration_lifecycle_state(
                parent_fd=session_parent_fd,
                target_basename=origin.target_basename,
                verification_key=verification_key,
            )
            if reread != abort_prepared:
                raise ValueError("issuer recovery abort prepared journal reread")
            committed = abort_prepared
            pending_candidate = None
            pending_state = None
            return recovery_abort_preparation_completion

    def recover_abort_prepared_to_renamed_tombstone(
        *,
        session_root_fd: int,
        session_parent_fd: int,
        session_target_fd: int,
        expected_abort_prepared_state_sha256: str,
        expected_prepared_pins: Epoch0RecoveryAbortPreparedAuthorityPinsV1,
    ) -> Epoch0RecoveryAbortRenameCompletionV1:
        nonlocal committed, pending_candidate, pending_state
        nonlocal recovery_abort_rename_completion
        if (
            committed is None
            or expected_prepared_pins.lifecycle_phase != "abort_prepared"
            or expected_prepared_pins.state_sha256 != expected_abort_prepared_state_sha256
            or pending_state is not None
        ):
            raise ValueError("issuer recovery abort rename phase")
        durable = _read_signed_migration_lifecycle_state(
            parent_fd=session_parent_fd,
            target_basename=expected_prepared_pins.target_basename,
            verification_key=verification_key,
        )
        if (
            recovery_abort_rename_completion is not None
            and durable == recovery_abort_rename_completion.abort_renamed_to_tombstone_state
        ):
            with _issuer_transition_lock(session_root_fd):
                durable = _confirm_signed_migration_lifecycle_state_durable(
                    parent_fd=session_parent_fd,
                    expected_state=recovery_abort_rename_completion.abort_renamed_to_tombstone_state,
                    verification_key=verification_key,
                )
                renamed_pins = _issuer_recovery_abort_renamed_pins_from_state(durable)
                _authenticate_epoch0_recovery_abort_renamed_state_v1(
                    parent_fd=session_parent_fd,
                    target_fd=session_target_fd,
                    verification_key=verification_key,
                    expected=renamed_pins,
                )
                committed = durable
                return recovery_abort_rename_completion
        if (
            committed.lifecycle_phase != "abort_prepared"
            or committed.state_sha256 != expected_abort_prepared_state_sha256
            or durable != committed
        ):
            raise ValueError("issuer recovery abort rename prepared journal")
        abort_prepared = committed
        with _issuer_transition_lock(session_root_fd):
            locked_parent_fd = os.open(
                ".",
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=session_parent_fd,
            )
            try:
                fcntl.flock(locked_parent_fd, fcntl.LOCK_EX)
                abort_prepared, layout = (
                    _authenticate_epoch0_recovery_abort_prepared_state_for_rename_v1(
                        parent_fd=locked_parent_fd,
                        target_fd=session_target_fd,
                        verification_key=verification_key,
                        expected=expected_prepared_pins,
                    )
                )
                if recovery_abort_rename_completion is None:
                    material = abort_prepared.model_dump(
                        mode="python",
                        exclude={"issuer_key_id", "state_sha256", "signature_ed25519"},
                    )
                    next_version = abort_prepared.phase_version + 1
                    material.update(
                        {
                            "lifecycle_phase": "abort_renamed_to_tombstone",
                            "phase_version": next_version,
                            "issuer_sequence": next_version,
                            "updated_at_ms": max(
                                abort_prepared.updated_at_ms, time.time_ns() // 1_000_000
                            ),
                            "previous_state_sha256": abort_prepared.state_sha256,
                            "issuer_key_id": key_id,
                        }
                    )
                    state_sha256 = _migration_lifecycle_state_sha256(material)
                    material["state_sha256"] = state_sha256
                    material["signature_ed25519"] = private_key.sign(
                        _MIGRATION_LIFECYCLE_SIGNATURE_DOMAIN + bytes.fromhex(state_sha256)
                    )
                    renamed = SignedMigrationLifecycleStateV1.model_validate(material)
                    recovery_abort_rename_completion = Epoch0RecoveryAbortRenameCompletionV1(
                        abort_prepared_state=abort_prepared,
                        abort_renamed_to_tombstone_state=renamed,
                    )
                else:
                    if recovery_abort_rename_completion.abort_prepared_state != abort_prepared:
                        raise ValueError("issuer recovery abort rename cached completion")
                    renamed = recovery_abort_rename_completion.abort_renamed_to_tombstone_state
                _verify_epoch0_recovery_abort_rename_completion_v1(
                    recovery_abort_rename_completion,
                    issuer_verification_key=verification_key,
                    expected_prepared_pins=expected_prepared_pins,
                )
                inject_recovery_fault("abort_rename_after_intent")
                if layout == "pre_rename":
                    _rename_migration_target_to_tombstone_exclusive(
                        parent_fd=locked_parent_fd,
                        target_basename=abort_prepared.target_basename,
                        tombstone_basename=abort_prepared.tombstone_basename,
                    )
                    inject_recovery_fault("abort_rename_after_target_rename")
                _verify_migration_abort_post_rename_target_layout(
                    parent_fd=locked_parent_fd,
                    target_fd=session_target_fd,
                    target_basename=abort_prepared.target_basename,
                    tombstone_basename=abort_prepared.tombstone_basename,
                    expected_target_identity=(abort_prepared.target_dev, abort_prepared.target_ino),
                )
                inject_recovery_fault("abort_rename_after_post_target")
                _persist_signed_migration_lifecycle_state(
                    parent_fd=session_parent_fd,
                    state=renamed,
                    verification_key=verification_key,
                    expected_prior_state_sha256=abort_prepared.state_sha256,
                    _fault_hook=inject_abort_rename_persistence_fault,
                    locked_parent_fd=locked_parent_fd,
                )
                reread = _read_signed_migration_lifecycle_state(
                    parent_fd=locked_parent_fd,
                    target_basename=abort_prepared.target_basename,
                    verification_key=verification_key,
                )
                if reread != renamed:
                    raise ValueError("issuer recovery abort renamed journal reread")
                committed = renamed
                pending_candidate = None
                pending_state = None
                return recovery_abort_rename_completion
            finally:
                fcntl.flock(locked_parent_fd, fcntl.LOCK_UN)
                os.close(locked_parent_fd)

    try:
        process_watch.control(
            [
                select.kevent(
                    supervisor_pid,
                    filter=select.KQ_FILTER_PROC,
                    flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE,
                    fflags=select.KQ_NOTE_EXIT,
                ),
                select.kevent(
                    authorized_pid,
                    filter=select.KQ_FILTER_PROC,
                    flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE,
                    fflags=select.KQ_NOTE_EXIT | select.KQ_NOTE_FORK,
                ),
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
            if supervisor_exited():
                return
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            descriptor: int | None = None
            received_descriptors: list[int] = []
            session_framed = False
            try:
                peer_pid = struct.unpack("i", connection.getsockopt(0, 2, 4))[0]
                if peer_pid != authorized_pid and recovery_peer_pid is None:
                    pending_recovery_peer_pid = peer_pid
                    pending_recovery_peer_revoked = False
                    process_watch.control(
                        [
                            select.kevent(
                                peer_pid,
                                filter=select.KQ_FILTER_PROC,
                                flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE,
                                fflags=select.KQ_NOTE_EXIT | select.KQ_NOTE_FORK,
                            )
                        ],
                        0,
                        0,
                    )
                connection.settimeout(0.1)
                while True:
                    try:
                        first, ancillary, flags, _ = connection.recvmsg(
                            _ISSUER_MAX_PACKET + 1,
                            socket.CMSG_SPACE(array("i").itemsize * 3),
                        )
                        if supervisor_exited():
                            return
                        break
                    except TimeoutError:
                        if supervisor_exited():
                            return
                received_descriptors = _issuer_received_descriptors(ancillary)
                if flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC):
                    raise ValueError("issuer truncated request")
                session_framed = bool(first) and _ISSUER_SESSION_FRAME_MAGIC.startswith(first)
                if len(first) >= len(_ISSUER_SESSION_FRAME_MAGIC):
                    session_framed = first.startswith(_ISSUER_SESSION_FRAME_MAGIC)
                if session_framed:
                    packet = _issuer_session_receive_frame(connection, first)
                else:
                    chunks = [first]
                    total = len(first)
                    while True:
                        try:
                            chunk = connection.recv(65_536)
                        except TimeoutError:
                            if supervisor_exited():
                                return
                            continue
                        if not chunk:
                            break
                        if supervisor_exited():
                            return
                        total += len(chunk)
                        if total > _ISSUER_MAX_PACKET:
                            raise ValueError("issuer request bound")
                        chunks.append(chunk)
                    packet = b"".join(chunks)
                if supervisor_exited():
                    return
                request = _parse_strict_json(packet, _ISSUER_MAX_PACKET)
                command = request.get("command")
                if supervisor_exited():
                    return
                if (peer_pid != authorized_pid or active_store_revoked) and command not in {
                    "recover_open",
                    "recover_session_open",
                }:
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
                            "maximum_issuer_sequence": 11,
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
                if command in {"recover_open", "recover_session_open"}:
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
                        or (command == "recover_session_open") != session_framed
                        or (command == "recover_session_open" and not active_store_revoked)
                        or (command == "recover_session_open" and recovery_peer_exited)
                        or (
                            command == "recover_session_open"
                            and peer_pid in rejected_recovery_peer_pids
                        )
                    ):
                        raise ValueError("issuer recovery open envelope")
                    request_bytes = _canonical_json(request)
                    authentication_pins: object = request["authority_pins"]
                    if (
                        (
                            recovery_abort_rename_completion is not None
                            or recovery_abort_preparation_completion is not None
                            or recovery_copy_completion is not None
                            or recovery_copy_preparation_completion is not None
                            or recovery_source_sealing_completion is not None
                            or recovery_barrier_acquisition_completion is not None
                        )
                        and recovery_admission_request == request_bytes
                        and recovery_admission is not None
                        and peer_pid == recovery_admission.authenticated_peer_pid
                    ):
                        if recovery_abort_rename_completion is not None:
                            observed_recovery_state = _read_signed_migration_lifecycle_state(
                                parent_fd=received_descriptors[1],
                                target_basename=(
                                    recovery_abort_rename_completion.abort_prepared_state.target_basename
                                ),
                                verification_key=verification_key,
                            )
                            if observed_recovery_state not in (
                                recovery_abort_rename_completion.abort_prepared_state,
                                recovery_abort_rename_completion.abort_renamed_to_tombstone_state,
                            ):
                                raise ValueError("issuer recovery abort rename effective state")
                            effective_state = observed_recovery_state
                        elif recovery_abort_preparation_completion is not None:
                            observed_recovery_state = _read_signed_migration_lifecycle_state(
                                parent_fd=received_descriptors[1],
                                target_basename=(
                                    recovery_abort_preparation_completion.origin_state.target_basename
                                ),
                                verification_key=verification_key,
                            )
                            if observed_recovery_state not in (
                                recovery_abort_preparation_completion.origin_state,
                                recovery_abort_preparation_completion.abort_prepared_state,
                            ):
                                raise ValueError(
                                    "issuer recovery abort preparation effective state"
                                )
                            effective_state = observed_recovery_state
                        elif recovery_copy_completion is not None:
                            effective_state = recovery_copy_completion.copied_state
                        elif recovery_copy_preparation_completion is not None:
                            observed_recovery_state = _read_signed_migration_lifecycle_state(
                                parent_fd=received_descriptors[1],
                                target_basename=(
                                    recovery_copy_preparation_completion.sealed_state.target_basename
                                ),
                                verification_key=verification_key,
                            )
                            if observed_recovery_state not in (
                                recovery_copy_preparation_completion.sealed_state,
                                recovery_copy_preparation_completion.prepared_state,
                            ):
                                raise ValueError("issuer recovery preparation effective state")
                            effective_state = observed_recovery_state
                        elif recovery_source_sealing_completion is not None:
                            observed_recovery_state = _read_signed_migration_lifecycle_state(
                                parent_fd=received_descriptors[1],
                                target_basename=(
                                    recovery_source_sealing_completion.barrier_acquired_state.target_basename
                                ),
                                verification_key=verification_key,
                            )
                            if observed_recovery_state not in (
                                recovery_source_sealing_completion.barrier_acquired_state,
                                recovery_source_sealing_completion.sources_sealed_state,
                            ):
                                raise ValueError("issuer recovery source sealing effective state")
                            effective_state = observed_recovery_state
                        else:
                            assert recovery_barrier_acquisition_completion is not None
                            observed_recovery_state = _read_signed_migration_lifecycle_state(
                                parent_fd=received_descriptors[1],
                                target_basename=(
                                    recovery_barrier_acquisition_completion.schema_only_state.target_basename
                                ),
                                verification_key=verification_key,
                            )
                            if observed_recovery_state not in (
                                recovery_barrier_acquisition_completion.schema_only_state,
                                recovery_barrier_acquisition_completion.barrier_acquired_state,
                            ):
                                raise ValueError(
                                    "issuer recovery barrier acquisition effective state"
                                )
                            effective_state = observed_recovery_state
                        if effective_state.lifecycle_phase == "abort_renamed_to_tombstone":
                            authentication_pins = _issuer_recovery_abort_renamed_pins_from_state(
                                effective_state
                            ).model_dump(mode="json")
                        elif effective_state.lifecycle_phase == "abort_prepared":
                            authentication_pins = _issuer_recovery_abort_prepared_pins_from_state(
                                effective_state
                            ).model_dump(mode="json")
                        else:
                            authentication_pins = _issuer_recovery_pins_from_state(
                                effective_state
                            ).model_dump(mode="json")
                    recovery_root_fd = received_descriptors.pop(0)
                    recovery_parent_fd = received_descriptors.pop(0)
                    recovery_target_fd = received_descriptors.pop(0)
                    session_descriptors: list[int] = []
                    try:
                        pins = _issuer_authenticate_recovery_descriptors(
                            root_fd=recovery_root_fd,
                            parent_fd=recovery_parent_fd,
                            target_fd=recovery_target_fd,
                            ticket=recovery_ticket,
                            verification_key=verification_key,
                            raw_pins=authentication_pins,
                        )
                        if command == "recover_session_open":
                            for recovery_fd in (
                                recovery_root_fd,
                                recovery_parent_fd,
                                recovery_target_fd,
                            ):
                                session_descriptor = fcntl.fcntl(
                                    recovery_fd, fcntl.F_DUPFD_CLOEXEC, 0
                                )
                                session_descriptors.append(session_descriptor)
                                received_descriptors.append(session_descriptor)
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
                        admission_for_request = recovery_admission
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
                        admission_for_request = SignedEpoch0RecoveryAdmissionV1.model_validate(
                            {
                                **admission_material,
                                "admission_sha256": admission_sha256,
                                "signature_ed25519": private_key.sign(
                                    _MIGRATION_RECOVERY_ADMISSION_SIGNATURE_DOMAIN
                                    + bytes.fromhex(admission_sha256)
                                ),
                            }
                        )
                    if admission_for_request is None:
                        raise ValueError("issuer recovery admission missing")
                    if command == "recover_session_open":
                        if recovery_peer_pid is None:
                            supervisor_is_gone = supervisor_exited()
                            if pending_recovery_peer_revoked:
                                rejected_recovery_peer_pids.add(peer_pid)
                            if (
                                pending_recovery_peer_pid != peer_pid
                                or supervisor_is_gone
                                or pending_recovery_peer_revoked
                            ):
                                raise ValueError("issuer recovery peer preadmission lifetime")
                            recovery_peer_pid = peer_pid
                            pending_recovery_peer_pid = None
                        elif recovery_peer_pid != peer_pid or recovery_peer_exited:
                            raise ValueError("issuer recovery peer lifetime")
                        if supervisor_exited() or recovery_peer_exited:
                            return
                    if recovery_admission is None:
                        recovery_admission = admission_for_request
                        recovery_admission_request = request_bytes
                    admission_response = b"R" + _canonical_json(
                        {
                            **recovery_admission.model_dump(
                                mode="python", exclude={"signature_ed25519"}
                            ),
                            "signature_ed25519": recovery_admission.signature_ed25519.hex(),
                        }
                    )
                    if command == "recover_open":
                        _issuer_response(connection, admission_response)
                        continue
                    for session_descriptor in session_descriptors:
                        received_descriptors.remove(session_descriptor)
                    try:
                        if len(session_descriptors) != 3:
                            raise ValueError("issuer recovery session descriptors")
                        session_root_fd, session_parent_fd, session_target_fd = session_descriptors
                        connection.sendall(_issuer_session_frame(admission_response))
                        while True:
                            if supervisor_exited() or recovery_peer_exited:
                                return
                            try:
                                session_packet = _issuer_session_receive_frame(
                                    connection, idle_poll=True
                                )
                            except BlockingIOError:
                                continue
                            except (TimeoutError, ValueError):  # fmt: skip
                                break
                            if supervisor_exited() or recovery_peer_exited:
                                return
                            session_request = _parse_strict_json(session_packet, _ISSUER_MAX_PACKET)
                            session_command = session_request.get("command")
                            common_fields = {
                                "command",
                                "admission_sha256",
                                "handle_nonce",
                            }
                            if session_command == "session_recover_copy_prepared_epoch0":
                                expected_fields = common_fields | {"expected_prepared_state_sha256"}
                            elif (
                                session_command == "session_recover_sources_sealed_to_copy_prepared"
                            ):
                                expected_fields = common_fields | {
                                    "expected_sources_sealed_state_sha256"
                                }
                            elif (
                                session_command == "session_recover_schema_only_to_barrier_acquired"
                            ):
                                expected_fields = common_fields | {
                                    "expected_schema_only_state_sha256"
                                }
                            elif (
                                session_command
                                == "session_recover_barrier_acquired_to_sources_sealed"
                            ):
                                expected_fields = common_fields | {
                                    "expected_barrier_acquired_state_sha256"
                                }
                            elif session_command == "session_recover_prepare_abort_uncut_epoch0":
                                expected_fields = common_fields | {"expected_origin_state_sha256"}
                            elif (
                                session_command
                                == "session_recover_abort_prepared_to_renamed_tombstone"
                            ):
                                expected_fields = common_fields | {
                                    "expected_abort_prepared_state_sha256"
                                }
                            else:
                                expected_fields = common_fields
                            if set(session_request) != expected_fields or (
                                session_request["admission_sha256"]
                                != recovery_admission.admission_sha256
                                or session_request["handle_nonce"]
                                != recovery_admission.handle_nonce
                            ):
                                raise ValueError("issuer recovery session correlation")
                            if supervisor_exited() or recovery_peer_exited:
                                return
                            effective_descriptor_pins = pins
                            if recovery_abort_rename_completion is not None:
                                durable_recovery_state = _read_signed_migration_lifecycle_state(
                                    parent_fd=session_parent_fd,
                                    target_basename=(
                                        recovery_abort_rename_completion.abort_prepared_state.target_basename
                                    ),
                                    verification_key=verification_key,
                                )
                                if durable_recovery_state not in (
                                    recovery_abort_rename_completion.abort_prepared_state,
                                    recovery_abort_rename_completion.abort_renamed_to_tombstone_state,
                                ):
                                    raise ValueError("issuer recovery abort rename effective state")
                                if (
                                    durable_recovery_state.lifecycle_phase
                                    == "abort_renamed_to_tombstone"
                                ):
                                    effective_descriptor_pins = (
                                        _issuer_recovery_abort_renamed_pins_from_state(
                                            durable_recovery_state
                                        )
                                    )
                                else:
                                    effective_descriptor_pins = (
                                        _issuer_recovery_abort_prepared_pins_from_state(
                                            durable_recovery_state
                                        )
                                    )
                            elif recovery_abort_preparation_completion is not None:
                                durable_recovery_state = _read_signed_migration_lifecycle_state(
                                    parent_fd=session_parent_fd,
                                    target_basename=(
                                        recovery_abort_preparation_completion.origin_state.target_basename
                                    ),
                                    verification_key=verification_key,
                                )
                                if durable_recovery_state not in (
                                    recovery_abort_preparation_completion.origin_state,
                                    recovery_abort_preparation_completion.abort_prepared_state,
                                ):
                                    raise ValueError(
                                        "issuer recovery abort preparation effective state"
                                    )
                                if durable_recovery_state.lifecycle_phase == "abort_prepared":
                                    effective_descriptor_pins = (
                                        _issuer_recovery_abort_prepared_pins_from_state(
                                            durable_recovery_state
                                        )
                                    )
                                else:
                                    effective_descriptor_pins = _issuer_recovery_pins_from_state(
                                        durable_recovery_state
                                    )
                            elif recovery_copy_completion is not None:
                                effective_descriptor_pins = _issuer_recovery_pins_from_state(
                                    recovery_copy_completion.copied_state
                                )
                            elif recovery_copy_preparation_completion is not None:
                                durable_recovery_state = _read_signed_migration_lifecycle_state(
                                    parent_fd=session_parent_fd,
                                    target_basename=(
                                        recovery_copy_preparation_completion.sealed_state.target_basename
                                    ),
                                    verification_key=verification_key,
                                )
                                if durable_recovery_state not in (
                                    recovery_copy_preparation_completion.sealed_state,
                                    recovery_copy_preparation_completion.prepared_state,
                                ):
                                    raise ValueError("issuer recovery preparation effective state")
                                effective_descriptor_pins = _issuer_recovery_pins_from_state(
                                    durable_recovery_state
                                )
                            elif recovery_source_sealing_completion is not None:
                                durable_recovery_state = _read_signed_migration_lifecycle_state(
                                    parent_fd=session_parent_fd,
                                    target_basename=(
                                        recovery_source_sealing_completion.barrier_acquired_state.target_basename
                                    ),
                                    verification_key=verification_key,
                                )
                                if durable_recovery_state not in (
                                    recovery_source_sealing_completion.barrier_acquired_state,
                                    recovery_source_sealing_completion.sources_sealed_state,
                                ):
                                    raise ValueError(
                                        "issuer recovery source sealing effective state"
                                    )
                                effective_descriptor_pins = _issuer_recovery_pins_from_state(
                                    durable_recovery_state
                                )
                            elif recovery_barrier_acquisition_completion is not None:
                                durable_recovery_state = _read_signed_migration_lifecycle_state(
                                    parent_fd=session_parent_fd,
                                    target_basename=(
                                        recovery_barrier_acquisition_completion.schema_only_state.target_basename
                                    ),
                                    verification_key=verification_key,
                                )
                                if durable_recovery_state not in (
                                    recovery_barrier_acquisition_completion.schema_only_state,
                                    recovery_barrier_acquisition_completion.barrier_acquired_state,
                                ):
                                    raise ValueError(
                                        "issuer recovery barrier acquisition effective state"
                                    )
                                effective_descriptor_pins = _issuer_recovery_pins_from_state(
                                    durable_recovery_state
                                )
                            if session_command == "session_ping":
                                _issuer_authenticate_recovery_descriptors(
                                    root_fd=session_root_fd,
                                    parent_fd=session_parent_fd,
                                    target_fd=session_target_fd,
                                    ticket=recovery_ticket,
                                    verification_key=verification_key,
                                    raw_pins=effective_descriptor_pins.model_dump(mode="json"),
                                )
                                if supervisor_exited() or recovery_peer_exited:
                                    return
                                connection.sendall(
                                    _issuer_session_frame(
                                        b"P" + recovery_admission.admission_sha256.encode("ascii")
                                    )
                                )
                                continue
                            if session_command == "session_recover_schema_only_to_barrier_acquired":
                                expected_schema_only_state_sha256 = session_request.get(
                                    "expected_schema_only_state_sha256"
                                )
                                if type(
                                    expected_schema_only_state_sha256
                                ) is not str or not re.fullmatch(
                                    r"[0-9a-f]{64}", expected_schema_only_state_sha256
                                ):
                                    raise ValueError("issuer recovery barrier expected state")
                                try:
                                    _issuer_authenticate_recovery_descriptors(
                                        root_fd=session_root_fd,
                                        parent_fd=session_parent_fd,
                                        target_fd=session_target_fd,
                                        ticket=recovery_ticket,
                                        verification_key=verification_key,
                                        raw_pins=effective_descriptor_pins.model_dump(mode="json"),
                                    )
                                    barrier_completion = recover_schema_only_to_barrier_acquired(
                                        session_root_fd=session_root_fd,
                                        session_parent_fd=session_parent_fd,
                                        session_target_fd=session_target_fd,
                                        expected_schema_only_state_sha256=(
                                            expected_schema_only_state_sha256
                                        ),
                                        expected_pins=recovery_admission.authority_pins,
                                    )
                                    if supervisor_exited() or recovery_peer_exited:
                                        return
                                except _InjectedRecoveryFault as error:
                                    connection.sendall(
                                        _issuer_session_frame(
                                            b"E" + (error.completion_document or b"")
                                        )
                                    )
                                    continue
                                except Exception:
                                    connection.sendall(_issuer_session_frame(b"E"))
                                    continue
                                connection.sendall(
                                    _issuer_session_frame(
                                        b"Y"
                                        + _issuer_recovery_barrier_acquisition_completion_document(
                                            barrier_completion
                                        )
                                    )
                                )
                                continue
                            if (
                                session_command
                                == "session_recover_barrier_acquired_to_sources_sealed"
                            ):
                                expected_barrier_acquired_state_sha256 = session_request.get(
                                    "expected_barrier_acquired_state_sha256"
                                )
                                if type(
                                    expected_barrier_acquired_state_sha256
                                ) is not str or not re.fullmatch(
                                    r"[0-9a-f]{64}", expected_barrier_acquired_state_sha256
                                ):
                                    raise ValueError("issuer recovery sealing expected state")
                                try:
                                    _issuer_authenticate_recovery_descriptors(
                                        root_fd=session_root_fd,
                                        parent_fd=session_parent_fd,
                                        target_fd=session_target_fd,
                                        ticket=recovery_ticket,
                                        verification_key=verification_key,
                                        raw_pins=effective_descriptor_pins.model_dump(mode="json"),
                                    )
                                    sealing_completion = recover_barrier_acquired_to_sources_sealed(
                                        session_root_fd=session_root_fd,
                                        session_parent_fd=session_parent_fd,
                                        session_target_fd=session_target_fd,
                                        expected_barrier_acquired_state_sha256=(
                                            expected_barrier_acquired_state_sha256
                                        ),
                                        expected_pins=recovery_admission.authority_pins,
                                    )
                                    if supervisor_exited() or recovery_peer_exited:
                                        return
                                except _InjectedRecoveryFault as error:
                                    connection.sendall(
                                        _issuer_session_frame(
                                            b"E" + (error.completion_document or b"")
                                        )
                                    )
                                    continue
                                except Exception:
                                    connection.sendall(_issuer_session_frame(b"E"))
                                    continue
                                connection.sendall(
                                    _issuer_session_frame(
                                        b"Y"
                                        + _issuer_recovery_source_sealing_completion_document(
                                            sealing_completion
                                        )
                                    )
                                )
                                continue
                            if session_command == "session_recover_sources_sealed_to_copy_prepared":
                                if (
                                    type(effective_descriptor_pins)
                                    is not Epoch0RecoveryAuthorityPinsV1
                                ):
                                    raise ValueError("issuer recovery preparation effective pins")
                                expected_sealed_state_sha256 = session_request.get(
                                    "expected_sources_sealed_state_sha256"
                                )
                                if type(
                                    expected_sealed_state_sha256
                                ) is not str or not re.fullmatch(
                                    r"[0-9a-f]{64}", expected_sealed_state_sha256
                                ):
                                    raise ValueError("issuer recovery preparation expected state")
                                try:
                                    _issuer_authenticate_recovery_descriptors(
                                        root_fd=session_root_fd,
                                        parent_fd=session_parent_fd,
                                        target_fd=session_target_fd,
                                        ticket=recovery_ticket,
                                        verification_key=verification_key,
                                        raw_pins=effective_descriptor_pins.model_dump(mode="json"),
                                    )
                                    preparation_completion = (
                                        recover_sources_sealed_to_copy_prepared(
                                            session_root_fd=session_root_fd,
                                            session_parent_fd=session_parent_fd,
                                            session_target_fd=session_target_fd,
                                            expected_sources_sealed_state_sha256=(
                                                expected_sealed_state_sha256
                                            ),
                                            expected_pins=effective_descriptor_pins,
                                        )
                                    )
                                    if supervisor_exited() or recovery_peer_exited:
                                        return
                                except Exception:
                                    connection.sendall(_issuer_session_frame(b"E"))
                                    continue
                                connection.sendall(
                                    _issuer_session_frame(
                                        b"Y"
                                        + _issuer_recovery_copy_preparation_completion_document(
                                            preparation_completion
                                        )
                                    )
                                )
                                continue
                            if session_command == "session_recover_copy_prepared_epoch0":
                                expected_prepared_state_sha256 = session_request.get(
                                    "expected_prepared_state_sha256"
                                )
                                if type(
                                    expected_prepared_state_sha256
                                ) is not str or not re.fullmatch(
                                    r"[0-9a-f]{64}", expected_prepared_state_sha256
                                ):
                                    raise ValueError("issuer recovery copy expected state")
                                try:
                                    _issuer_authenticate_recovery_descriptors(
                                        root_fd=session_root_fd,
                                        parent_fd=session_parent_fd,
                                        target_fd=session_target_fd,
                                        ticket=recovery_ticket,
                                        verification_key=verification_key,
                                        raw_pins=effective_descriptor_pins.model_dump(mode="json"),
                                    )
                                    prepared_pins = (
                                        _issuer_recovery_pins_from_state(
                                            recovery_copy_preparation_completion.prepared_state
                                        )
                                        if recovery_copy_preparation_completion is not None
                                        else recovery_admission.authority_pins
                                    )
                                    copy_completion = recover_copy_prepared_epoch0(
                                        session_root_fd=session_root_fd,
                                        session_parent_fd=session_parent_fd,
                                        session_target_fd=session_target_fd,
                                        expected_prepared_state_sha256=(
                                            expected_prepared_state_sha256
                                        ),
                                        expected_pins=prepared_pins,
                                    )
                                    if supervisor_exited() or recovery_peer_exited:
                                        return
                                except Exception:
                                    connection.sendall(_issuer_session_frame(b"E"))
                                    continue
                                connection.sendall(
                                    _issuer_session_frame(
                                        b"Y"
                                        + _issuer_recovery_copy_completion_document(copy_completion)
                                    )
                                )
                                continue
                            if session_command == "session_recover_prepare_abort_uncut_epoch0":
                                expected_origin_state_sha256 = session_request.get(
                                    "expected_origin_state_sha256"
                                )
                                if type(
                                    expected_origin_state_sha256
                                ) is not str or not re.fullmatch(
                                    r"[0-9a-f]{64}", expected_origin_state_sha256
                                ):
                                    raise ValueError(
                                        "issuer recovery abort preparation expected state"
                                    )
                                if recovery_admission.authority_pins.lifecycle_phase not in {
                                    "schema_only",
                                    "barrier_acquired",
                                    "sources_sealed",
                                    "copy_prepared",
                                    "copied_epoch0",
                                }:
                                    raise ValueError("issuer recovery abort preparation admission")
                                try:
                                    _issuer_authenticate_recovery_descriptors(
                                        root_fd=session_root_fd,
                                        parent_fd=session_parent_fd,
                                        target_fd=session_target_fd,
                                        ticket=recovery_ticket,
                                        verification_key=verification_key,
                                        raw_pins=effective_descriptor_pins.model_dump(mode="json"),
                                    )
                                    abort_completion = recover_prepare_abort_uncut_epoch0(
                                        session_root_fd=session_root_fd,
                                        session_parent_fd=session_parent_fd,
                                        session_target_fd=session_target_fd,
                                        expected_origin_state_sha256=expected_origin_state_sha256,
                                        expected_origin_pins=recovery_admission.authority_pins,
                                    )
                                    if supervisor_exited() or recovery_peer_exited:
                                        return
                                except _InjectedRecoveryFault as error:
                                    connection.sendall(
                                        _issuer_session_frame(
                                            b"E" + (error.completion_document or b"")
                                        )
                                    )
                                    continue
                                except Exception:
                                    connection.sendall(_issuer_session_frame(b"E"))
                                    continue
                                connection.sendall(
                                    _issuer_session_frame(
                                        b"Y"
                                        + _issuer_recovery_abort_preparation_completion_document(
                                            abort_completion
                                        )
                                    )
                                )
                                continue
                            if (
                                session_command
                                == "session_recover_abort_prepared_to_renamed_tombstone"
                            ):
                                expected_abort_prepared_state_sha256 = session_request.get(
                                    "expected_abort_prepared_state_sha256"
                                )
                                if type(
                                    expected_abort_prepared_state_sha256
                                ) is not str or not re.fullmatch(
                                    r"[0-9a-f]{64}", expected_abort_prepared_state_sha256
                                ):
                                    raise ValueError("issuer recovery abort rename expected state")
                                expected_prepared_pins = (
                                    _issuer_expected_abort_prepared_pins_from_origin(
                                        recovery_admission.authority_pins,
                                        expected_abort_prepared_state_sha256=(
                                            expected_abort_prepared_state_sha256
                                        ),
                                    )
                                )
                                try:
                                    _issuer_authenticate_recovery_descriptors(
                                        root_fd=session_root_fd,
                                        parent_fd=session_parent_fd,
                                        target_fd=session_target_fd,
                                        ticket=recovery_ticket,
                                        verification_key=verification_key,
                                        raw_pins=effective_descriptor_pins.model_dump(mode="json"),
                                    )
                                    rename_completion = recover_abort_prepared_to_renamed_tombstone(
                                        session_root_fd=session_root_fd,
                                        session_parent_fd=session_parent_fd,
                                        session_target_fd=session_target_fd,
                                        expected_abort_prepared_state_sha256=(
                                            expected_abort_prepared_state_sha256
                                        ),
                                        expected_prepared_pins=expected_prepared_pins,
                                    )
                                    if supervisor_exited() or recovery_peer_exited:
                                        return
                                except _InjectedRecoveryFault as error:
                                    connection.sendall(
                                        _issuer_session_frame(
                                            b"E" + (error.completion_document or b"")
                                        )
                                    )
                                    continue
                                except Exception:
                                    connection.sendall(_issuer_session_frame(b"E"))
                                    continue
                                connection.sendall(
                                    _issuer_session_frame(
                                        b"Y"
                                        + _issuer_recovery_abort_rename_completion_document(
                                            rename_completion
                                        )
                                    )
                                )
                                continue
                            if session_command == "session_close":
                                if supervisor_exited() or recovery_peer_exited:
                                    return
                                connection.sendall(
                                    _issuer_session_frame(
                                        b"C" + recovery_admission.admission_sha256.encode("ascii")
                                    )
                                )
                                break
                            raise ValueError("issuer recovery session command")
                    finally:
                        for session_descriptor in session_descriptors:
                            os.close(session_descriptor)
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
                    and recovery_copy_preparation_completion is None
                    and (committed is None or committed.lifecycle_phase != "copy_prepared")
                ):
                    _issuer_release_target_lease(target_lease)
                    target_lease = None
                if session_framed:
                    with suppress(OSError, ValueError):
                        connection.sendall(_issuer_session_frame(b"E"))
                else:
                    _issuer_response(connection, b"E")
            finally:
                if pending_recovery_peer_pid is not None:
                    with suppress(OSError):
                        process_watch.control(
                            [
                                select.kevent(
                                    pending_recovery_peer_pid,
                                    filter=select.KQ_FILTER_PROC,
                                    flags=select.KQ_EV_DELETE,
                                )
                            ],
                            0,
                            0,
                        )
                    pending_recovery_peer_pid = None
                    pending_recovery_peer_revoked = False
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


class FixtureMigrationRecoverySessionV1:
    _admission: SignedEpoch0RecoveryAdmissionV1
    _boot_nonce: bytes
    _closed: bool
    _connection: socket.socket
    _creator_pid: int
    _descriptors: tuple[int, int, int]
    _handle_nonce: str
    _lock: threading.Lock
    _abort_preparation_completion: Epoch0RecoveryAbortPreparationCompletionV1 | None
    _abort_rename_completion: Epoch0RecoveryAbortRenameCompletionV1 | None
    _barrier_acquisition_completion: Epoch0RecoveryBarrierAcquisitionCompletionV1 | None
    _preparation_completion: Epoch0RecoveryCopyPreparationCompletionV1 | None
    _source_sealing_completion: Epoch0RecoverySourceSealingCompletionV1 | None
    _ticket: SignedMigrationRecoveryTicketV1
    _verification_key: VerificationKeyV1

    __slots__ = (
        "_abort_preparation_completion",
        "_abort_rename_completion",
        "_admission",
        "_barrier_acquisition_completion",
        "_boot_nonce",
        "_closed",
        "_connection",
        "_creator_pid",
        "_descriptors",
        "_handle_nonce",
        "_lock",
        "_preparation_completion",
        "_source_sealing_completion",
        "_ticket",
        "_verification_key",
    )

    def __init_subclass__(cls, **kwargs: object) -> Never:
        del cls, kwargs
        raise TypeError("fixture migration recovery session is final")

    @classmethod
    def open(
        cls,
        *,
        socket_path: str,
        expected_issuer_pid: int,
        recovery_ticket: SignedMigrationRecoveryTicketV1,
        verification_key: VerificationKeyV1,
        root_fd: int,
        parent_fd: int,
        target_fd: int,
        authority_pins: Epoch0RecoveryAuthorityPinsV1,
        _exact_admission: SignedEpoch0RecoveryAdmissionV1 | None = None,
    ) -> FixtureMigrationRecoverySessionV1:
        if (
            type(socket_path) is not str
            or type(expected_issuer_pid) is not int
            or type(recovery_ticket) is not SignedMigrationRecoveryTicketV1
            or type(verification_key) is not VerificationKeyV1
            or type(authority_pins) is not Epoch0RecoveryAuthorityPinsV1
            or (
                _exact_admission is not None
                and type(_exact_admission) is not SignedEpoch0RecoveryAdmissionV1
            )
        ):
            raise ValueError("fixture recovery session open values")
        _verify_signed_migration_recovery_ticket(recovery_ticket, verification_key)
        if _exact_admission is None:
            caller_boot_nonce = secrets.token_hex(32)
            handle_nonce = secrets.token_hex(32)
        else:
            _verify_signed_epoch0_recovery_admission(_exact_admission, verification_key)
            if (
                _exact_admission.ticket_sha256 != recovery_ticket.ticket_sha256
                or _exact_admission.issuer_generation_nonce
                != recovery_ticket.issuer_generation_nonce
                or _exact_admission.authenticated_peer_pid != os.getpid()
                or _exact_admission.authority_pins != authority_pins
            ):
                raise ValueError("fixture recovery session exact admission")
            caller_boot_nonce = _exact_admission.caller_boot_nonce
            handle_nonce = _exact_admission.handle_nonce
        request = _canonical_json(
            {
                "command": "recover_session_open",
                "ticket_sha256": recovery_ticket.ticket_sha256,
                "issuer_generation_nonce": recovery_ticket.issuer_generation_nonce,
                "caller_boot_nonce": caller_boot_nonce,
                "handle_nonce": handle_nonce,
                "authority_pins": authority_pins.model_dump(mode="json"),
            }
        )
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        duplicates: list[int] = []
        try:
            for descriptor in (root_fd, parent_fd, target_fd):
                duplicates.append(fcntl.fcntl(descriptor, fcntl.F_DUPFD_CLOEXEC, 0))
            connection.settimeout(5.0)
            connection.connect(socket_path)
            peer_pid = struct.unpack("i", connection.getsockopt(0, 2, 4))[0]
            if peer_pid != expected_issuer_pid:
                raise ValueError("fixture recovery session issuer pid")
            framed = _issuer_session_frame(request)
            rights = array("i", duplicates)
            if connection.sendmsg(
                [framed],
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights.tobytes())],
            ) != len(framed):
                raise OSError("short recovery session request")
            response = _issuer_session_receive_frame(connection)
            if response[:1] != b"R":
                raise ValueError(
                    "fixture recovery session admission response: "
                    + response.decode("utf-8", errors="replace")
                )
            parsed = _parse_strict_json(response[1:], _ISSUER_MAX_PACKET)
            signature_hex = parsed.get("signature_ed25519")
            if type(signature_hex) is not str:
                raise ValueError("fixture recovery session admission signature")
            admission = SignedEpoch0RecoveryAdmissionV1.model_validate(
                {**parsed, "signature_ed25519": bytes.fromhex(signature_hex)}
            )
            _verify_signed_epoch0_recovery_admission(admission, verification_key)
            if (
                admission.ticket_sha256 != recovery_ticket.ticket_sha256
                or admission.issuer_generation_nonce != recovery_ticket.issuer_generation_nonce
                or admission.authenticated_peer_pid != os.getpid()
                or admission.caller_boot_nonce != caller_boot_nonce
                or admission.handle_nonce != handle_nonce
                or admission.descriptor_mode != "target"
                or admission.authority_pins != authority_pins
                or (_exact_admission is not None and admission != _exact_admission)
            ):
                raise ValueError("fixture recovery session admission correlation")
            connection.settimeout(5.0)
        except Exception:
            connection.close()
            for duplicate in duplicates:
                os.close(duplicate)
            raise
        if len(duplicates) != 3:
            raise AssertionError("fixture recovery session descriptors")
        session = object.__new__(cls)
        object.__setattr__(session, "_admission", admission)
        object.__setattr__(session, "_boot_nonce", bytes.fromhex(caller_boot_nonce))
        object.__setattr__(session, "_closed", False)
        object.__setattr__(session, "_connection", connection)
        object.__setattr__(session, "_creator_pid", os.getpid())
        object.__setattr__(session, "_descriptors", tuple(duplicates))
        object.__setattr__(session, "_handle_nonce", handle_nonce)
        object.__setattr__(session, "_lock", threading.Lock())
        object.__setattr__(session, "_abort_preparation_completion", None)
        object.__setattr__(session, "_abort_rename_completion", None)
        object.__setattr__(session, "_barrier_acquisition_completion", None)
        object.__setattr__(session, "_preparation_completion", None)
        object.__setattr__(session, "_source_sealing_completion", None)
        object.__setattr__(session, "_ticket", recovery_ticket)
        object.__setattr__(session, "_verification_key", verification_key)
        return session

    @classmethod
    def reopen_exact(
        cls,
        *,
        socket_path: str,
        expected_issuer_pid: int,
        recovery_ticket: SignedMigrationRecoveryTicketV1,
        admission: SignedEpoch0RecoveryAdmissionV1,
        verification_key: VerificationKeyV1,
        root_fd: int,
        parent_fd: int,
        target_fd: int,
    ) -> FixtureMigrationRecoverySessionV1:
        return cls.open(
            socket_path=socket_path,
            expected_issuer_pid=expected_issuer_pid,
            recovery_ticket=recovery_ticket,
            verification_key=verification_key,
            root_fd=root_fd,
            parent_fd=parent_fd,
            target_fd=target_fd,
            authority_pins=admission.authority_pins,
            _exact_admission=admission,
        )

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise AttributeError("fixture migration recovery session is immutable")

    def __reduce__(self) -> Never:
        raise TypeError("fixture migration recovery session is process-bound")

    def __copy__(self) -> Never:
        raise TypeError("fixture migration recovery session cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("fixture migration recovery session cannot be copied")

    def _validate(self) -> None:
        if (
            self._creator_pid != os.getpid()
            or len(self._boot_nonce) != 32
            or self._handle_nonce != self._admission.handle_nonce
            or self._closed
        ):
            raise ValueError("fixture recovery session unavailable")

    @property
    def admission(self) -> SignedEpoch0RecoveryAdmissionV1:
        self._validate()
        return self._admission

    @property
    def authority_pins(self) -> Epoch0RecoveryAuthorityPinsV1:
        self._validate()
        return self._admission.authority_pins

    def _close_local(self) -> None:
        if self._closed:
            return
        object.__setattr__(self, "_closed", True)
        self._connection.close()
        for descriptor in self._descriptors:
            with suppress(OSError):
                os.close(descriptor)

    def _live_request(self, command: Literal["session_ping", "session_close"]) -> bytes:
        request = _canonical_json(
            {
                "command": command,
                "admission_sha256": self._admission.admission_sha256,
                "handle_nonce": self._handle_nonce,
            }
        )
        self._connection.sendall(_issuer_session_frame(request))
        return _issuer_session_receive_frame(self._connection)

    def ping(self) -> None:
        self._validate()
        with self._lock:
            try:
                response = self._live_request("session_ping")
                if response != b"P" + self._admission.admission_sha256.encode("ascii"):
                    raise ValueError("fixture recovery session ping response")
            except Exception:
                self._close_local()
                raise

    def recover_schema_only_to_barrier_acquired(
        self, *, expected_schema_only_state_sha256: str
    ) -> Epoch0RecoveryBarrierAcquisitionCompletionV1:
        self._validate()
        schema_pins = self._admission.authority_pins
        if (
            not re.fullmatch(r"[0-9a-f]{64}", expected_schema_only_state_sha256)
            or schema_pins.lifecycle_phase != "schema_only"
            or schema_pins.state_sha256 != expected_schema_only_state_sha256
        ):
            raise ValueError("fixture recovery schema-only state")
        request = _canonical_json(
            {
                "command": "session_recover_schema_only_to_barrier_acquired",
                "admission_sha256": self._admission.admission_sha256,
                "handle_nonce": self._handle_nonce,
                "expected_schema_only_state_sha256": expected_schema_only_state_sha256,
            }
        )
        with self._lock:
            try:
                self._connection.sendall(_issuer_session_frame(request))
                response = _issuer_session_receive_frame(self._connection)
            except Exception:
                self._close_local()
                raise
            if response[:1] == b"E":
                try:
                    if response[1:]:
                        fault_completion = (
                            _parse_issuer_recovery_barrier_acquisition_completion_document(
                                response[1:]
                            )
                        )
                        _verify_epoch0_recovery_barrier_acquisition_completion_v1(
                            fault_completion,
                            issuer_verification_key=self._verification_key,
                            expected_schema_only_pins=schema_pins,
                        )
                        object.__setattr__(
                            self,
                            "_barrier_acquisition_completion",
                            fault_completion,
                        )
                except Exception:
                    self._close_local()
                    raise
                raise ValueError("fixture recovery barrier acquisition rejected")
            try:
                if response[:1] != b"Y":
                    raise ValueError("fixture recovery barrier acquisition response")
                completion = _parse_issuer_recovery_barrier_acquisition_completion_document(
                    response[1:]
                )
                _verify_epoch0_recovery_barrier_acquisition_completion_v1(
                    completion,
                    issuer_verification_key=self._verification_key,
                    expected_schema_only_pins=schema_pins,
                )
                if (
                    self._barrier_acquisition_completion is not None
                    and completion != self._barrier_acquisition_completion
                ):
                    raise ValueError("fixture recovery barrier acquisition replay")
                object.__setattr__(self, "_barrier_acquisition_completion", completion)
            except Exception:
                self._close_local()
                raise
            return completion

    def recover_barrier_acquired_to_sources_sealed(
        self, *, expected_barrier_acquired_state_sha256: str
    ) -> Epoch0RecoverySourceSealingCompletionV1:
        self._validate()
        barrier_pins = self._admission.authority_pins
        if (
            not re.fullmatch(r"[0-9a-f]{64}", expected_barrier_acquired_state_sha256)
            or barrier_pins.lifecycle_phase != "barrier_acquired"
            or barrier_pins.state_sha256 != expected_barrier_acquired_state_sha256
        ):
            raise ValueError("fixture recovery barrier acquired state")
        request = _canonical_json(
            {
                "command": "session_recover_barrier_acquired_to_sources_sealed",
                "admission_sha256": self._admission.admission_sha256,
                "handle_nonce": self._handle_nonce,
                "expected_barrier_acquired_state_sha256": (expected_barrier_acquired_state_sha256),
            }
        )
        with self._lock:
            try:
                self._connection.sendall(_issuer_session_frame(request))
                response = _issuer_session_receive_frame(self._connection)
            except Exception:
                self._close_local()
                raise
            if response[:1] == b"E":
                try:
                    if response[1:]:
                        fault_completion = (
                            _parse_issuer_recovery_source_sealing_completion_document(response[1:])
                        )
                        _verify_epoch0_recovery_source_sealing_completion_v1(
                            fault_completion,
                            issuer_verification_key=self._verification_key,
                            expected_barrier_acquired_pins=barrier_pins,
                        )
                        object.__setattr__(
                            self,
                            "_source_sealing_completion",
                            fault_completion,
                        )
                except Exception:
                    self._close_local()
                    raise
                raise ValueError("fixture recovery source sealing rejected")
            try:
                if response[:1] != b"Y":
                    raise ValueError("fixture recovery source sealing response")
                completion = _parse_issuer_recovery_source_sealing_completion_document(response[1:])
                _verify_epoch0_recovery_source_sealing_completion_v1(
                    completion,
                    issuer_verification_key=self._verification_key,
                    expected_barrier_acquired_pins=barrier_pins,
                )
                if (
                    self._source_sealing_completion is not None
                    and completion != self._source_sealing_completion
                ):
                    raise ValueError("fixture recovery source sealing replay")
                object.__setattr__(self, "_source_sealing_completion", completion)
            except Exception:
                self._close_local()
                raise
            return completion

    def recover_copy_prepared_epoch0(
        self, *, expected_prepared_state_sha256: str
    ) -> Epoch0RecoveryCopyCompletionV1:
        self._validate()
        prepared_pins = self._admission.authority_pins
        if self._preparation_completion is not None:
            prepared_pins = _issuer_recovery_pins_from_state(
                self._preparation_completion.prepared_state
            )
        if (
            not re.fullmatch(r"[0-9a-f]{64}", expected_prepared_state_sha256)
            or prepared_pins.lifecycle_phase != "copy_prepared"
            or (prepared_pins.state_sha256 != expected_prepared_state_sha256)
        ):
            raise ValueError("fixture recovery copy prepared state")
        request = _canonical_json(
            {
                "command": "session_recover_copy_prepared_epoch0",
                "admission_sha256": self._admission.admission_sha256,
                "handle_nonce": self._handle_nonce,
                "expected_prepared_state_sha256": expected_prepared_state_sha256,
            }
        )
        with self._lock:
            try:
                self._connection.sendall(_issuer_session_frame(request))
                response = _issuer_session_receive_frame(self._connection)
            except Exception:
                self._close_local()
                raise
            if response == b"E":
                raise ValueError("fixture recovery copy rejected")
            try:
                if response[:1] != b"Y":
                    raise ValueError("fixture recovery copy response")
                completion = _parse_issuer_recovery_copy_completion_document(response[1:])
                _verify_epoch0_recovery_copy_completion_v1(
                    completion,
                    issuer_verification_key=self._verification_key,
                    expected_prepared_pins=prepared_pins,
                )
            except Exception:
                self._close_local()
                raise
            return completion

    def recover_sources_sealed_to_copy_prepared(
        self, *, expected_sources_sealed_state_sha256: str
    ) -> Epoch0RecoveryCopyPreparationCompletionV1:
        self._validate()
        sealed_pins = self._admission.authority_pins
        if self._source_sealing_completion is not None:
            sealed_pins = _issuer_recovery_pins_from_state(
                self._source_sealing_completion.sources_sealed_state
            )
        if (
            not re.fullmatch(r"[0-9a-f]{64}", expected_sources_sealed_state_sha256)
            or sealed_pins.lifecycle_phase != "sources_sealed"
            or sealed_pins.state_sha256 != expected_sources_sealed_state_sha256
        ):
            raise ValueError("fixture recovery sealed state")
        request = _canonical_json(
            {
                "command": "session_recover_sources_sealed_to_copy_prepared",
                "admission_sha256": self._admission.admission_sha256,
                "handle_nonce": self._handle_nonce,
                "expected_sources_sealed_state_sha256": (expected_sources_sealed_state_sha256),
            }
        )
        with self._lock:
            try:
                self._connection.sendall(_issuer_session_frame(request))
                response = _issuer_session_receive_frame(self._connection)
            except Exception:
                self._close_local()
                raise
            if response == b"E":
                raise ValueError("fixture recovery preparation rejected")
            try:
                if response[:1] != b"Y":
                    raise ValueError("fixture recovery preparation response")
                completion = _parse_issuer_recovery_copy_preparation_completion_document(
                    response[1:]
                )
                _verify_epoch0_recovery_copy_preparation_completion_v1(
                    completion,
                    issuer_verification_key=self._verification_key,
                    expected_sealed_pins=sealed_pins,
                )
                if (
                    self._preparation_completion is not None
                    and completion != self._preparation_completion
                ):
                    raise ValueError("fixture recovery preparation replay")
                object.__setattr__(self, "_preparation_completion", completion)
            except Exception:
                self._close_local()
                raise
            return completion

    def recover_prepare_abort_uncut_epoch0(
        self, *, expected_origin_state_sha256: str
    ) -> Epoch0RecoveryAbortPreparationCompletionV1:
        self._validate()
        origin_pins = self._admission.authority_pins
        if (
            not re.fullmatch(r"[0-9a-f]{64}", expected_origin_state_sha256)
            or origin_pins.lifecycle_phase
            not in {
                "schema_only",
                "barrier_acquired",
                "sources_sealed",
                "copy_prepared",
                "copied_epoch0",
            }
            or origin_pins.state_sha256 != expected_origin_state_sha256
        ):
            raise ValueError("fixture recovery abort preparation origin state")
        request = _canonical_json(
            {
                "command": "session_recover_prepare_abort_uncut_epoch0",
                "admission_sha256": self._admission.admission_sha256,
                "handle_nonce": self._handle_nonce,
                "expected_origin_state_sha256": expected_origin_state_sha256,
            }
        )
        with self._lock:
            try:
                self._connection.sendall(_issuer_session_frame(request))
                response = _issuer_session_receive_frame(self._connection)
            except Exception:
                self._close_local()
                raise
            if response[:1] == b"E":
                try:
                    if response[1:]:
                        fault_completion = (
                            _parse_issuer_recovery_abort_preparation_completion_document(
                                response[1:]
                            )
                        )
                        _verify_epoch0_recovery_abort_preparation_completion_v1(
                            fault_completion,
                            issuer_verification_key=self._verification_key,
                            expected_origin_pins=origin_pins,
                        )
                        object.__setattr__(
                            self,
                            "_abort_preparation_completion",
                            fault_completion,
                        )
                except Exception:
                    self._close_local()
                    raise
                raise ValueError("fixture recovery abort preparation rejected")
            try:
                if response[:1] != b"Y":
                    raise ValueError("fixture recovery abort preparation response")
                completion = _parse_issuer_recovery_abort_preparation_completion_document(
                    response[1:]
                )
                _verify_epoch0_recovery_abort_preparation_completion_v1(
                    completion,
                    issuer_verification_key=self._verification_key,
                    expected_origin_pins=origin_pins,
                )
                if (
                    self._abort_preparation_completion is not None
                    and completion != self._abort_preparation_completion
                ):
                    raise ValueError("fixture recovery abort preparation replay")
                object.__setattr__(self, "_abort_preparation_completion", completion)
            except Exception:
                self._close_local()
                raise
            return completion

    def recover_abort_prepared_to_renamed_tombstone(
        self, *, expected_abort_prepared_state_sha256: str
    ) -> Epoch0RecoveryAbortRenameCompletionV1:
        self._validate()
        prepared_pins = _issuer_expected_abort_prepared_pins_from_origin(
            self._admission.authority_pins,
            expected_abort_prepared_state_sha256=expected_abort_prepared_state_sha256,
        )
        if (
            self._abort_preparation_completion is not None
            and self._abort_preparation_completion.abort_prepared_state.state_sha256
            != expected_abort_prepared_state_sha256
        ):
            raise ValueError("fixture recovery abort prepared state")
        request = _canonical_json(
            {
                "command": "session_recover_abort_prepared_to_renamed_tombstone",
                "admission_sha256": self._admission.admission_sha256,
                "handle_nonce": self._handle_nonce,
                "expected_abort_prepared_state_sha256": expected_abort_prepared_state_sha256,
            }
        )
        with self._lock:
            try:
                self._connection.sendall(_issuer_session_frame(request))
                response = _issuer_session_receive_frame(self._connection)
            except Exception:
                self._close_local()
                raise
            if response[:1] == b"E":
                try:
                    if response[1:]:
                        fault_completion = _parse_issuer_recovery_abort_rename_completion_document(
                            response[1:]
                        )
                        _verify_epoch0_recovery_abort_rename_completion_v1(
                            fault_completion,
                            issuer_verification_key=self._verification_key,
                            expected_prepared_pins=prepared_pins,
                        )
                        object.__setattr__(self, "_abort_rename_completion", fault_completion)
                except Exception:
                    self._close_local()
                    raise
                raise ValueError("fixture recovery abort rename rejected")
            try:
                if response[:1] != b"Y":
                    raise ValueError("fixture recovery abort rename response")
                completion = _parse_issuer_recovery_abort_rename_completion_document(response[1:])
                _verify_epoch0_recovery_abort_rename_completion_v1(
                    completion,
                    issuer_verification_key=self._verification_key,
                    expected_prepared_pins=prepared_pins,
                )
                if (
                    self._abort_rename_completion is not None
                    and completion != self._abort_rename_completion
                ):
                    raise ValueError("fixture recovery abort rename replay")
                object.__setattr__(self, "_abort_rename_completion", completion)
            except Exception:
                self._close_local()
                raise
            return completion

    def close(self) -> None:
        if self._closed:
            return
        if self._creator_pid != os.getpid():
            self._close_local()
            return
        with self._lock:
            try:
                response = self._live_request("session_close")
                if response != b"C" + self._admission.admission_sha256.encode("ascii"):
                    raise ValueError("fixture recovery session close response")
            except (OSError, TimeoutError, ValueError):  # fmt: skip
                pass
            finally:
                self._close_local()

    def __del__(self) -> None:
        with suppress(AttributeError, OSError):
            self._close_local()


class FixtureMigrationLifecycleIssuerV1:
    _boot_nonce: bytes
    _creator_pid: int
    _lock: threading.Lock
    _process: BaseProcess
    _socket_path: str
    _socket_root: Path
    _supervisor_process: BaseProcess
    recovery_ticket: SignedMigrationRecoveryTicketV1
    verification_key: VerificationKeyV1

    __slots__ = (
        "_boot_nonce",
        "_creator_pid",
        "_lock",
        "_process",
        "_socket_path",
        "_socket_root",
        "_supervisor_process",
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
        recovery_fault_boundary: _RecoveryFaultBoundary | None = None,
    ) -> FixtureMigrationLifecycleIssuerV1:
        if recovery_fault_boundary not in {
            None,
            "after_target_commit",
            "after_rename",
            "after_parent_fsync",
            "after_reread",
            "prepare_after_audit",
            "prepare_after_rename",
            "prepare_after_parent_fsync",
            "prepare_after_reread",
            "barrier_after_intent",
            "barrier_after_root_rename",
            "barrier_after_root_fsync",
            "barrier_after_root_reread",
            "barrier_after_journal_rename",
            "barrier_after_journal_parent_fsync",
            "barrier_after_journal_reread",
            "seal_deny_after_child_owner",
            "seal_deny_after_child_paid",
            "seal_deny_after_child_provider",
            "seal_drain_after_child_owner",
            "seal_drain_after_child_paid",
            "seal_drain_after_child_provider",
            "seal_revoke_after_child_owner",
            "seal_revoke_after_child_paid",
            "seal_revoke_after_child_provider",
            "seal_verify_after_child_owner",
            "seal_verify_after_child_paid",
            "seal_verify_after_child_provider",
            "seal_collect_after_child_owner",
            "seal_collect_after_child_paid",
            "seal_collect_after_child_provider",
            "seal_deny_after_root_rename",
            "seal_deny_after_root_fsync",
            "seal_deny_after_root_reread",
            "seal_drain_after_root_rename",
            "seal_drain_after_root_fsync",
            "seal_drain_after_root_reread",
            "seal_revoke_after_root_rename",
            "seal_revoke_after_root_fsync",
            "seal_revoke_after_root_reread",
            "seal_verify_after_root_rename",
            "seal_verify_after_root_fsync",
            "seal_verify_after_root_reread",
            "seal_collect_after_root_rename",
            "seal_collect_after_root_fsync",
            "seal_collect_after_root_reread",
            "seal_after_manifest_completion_cache",
            "seal_after_journal_rename",
            "seal_after_journal_parent_fsync",
            "seal_after_journal_reread",
            "abort_prepare_after_intent",
            "abort_prepare_after_rename",
            "abort_prepare_after_parent_fsync",
            "abort_prepare_after_reread",
            "abort_rename_after_intent",
            "abort_rename_after_target_rename",
            "abort_rename_after_post_target",
            "abort_rename_after_journal_rename",
            "abort_rename_after_journal_parent_fsync",
            "abort_rename_after_journal_reread",
        }:
            raise ValueError("issuer recovery fault boundary")
        context = multiprocessing.get_context("spawn")
        supervisor_receive, supervisor_send = context.Pipe(duplex=False)
        supervisor_process = context.Process(
            target=_fixture_issuer_supervisor_main,
            args=(supervisor_send,),
            daemon=False,
        )
        try:
            supervisor_process.start()
            supervisor_send.close()
            if not supervisor_receive.poll(5):
                raise TimeoutError("issuer supervisor handshake timeout")
            supervisor_pid = supervisor_receive.recv()
            if type(supervisor_pid) is not int or supervisor_pid != supervisor_process.pid:
                raise ValueError("issuer supervisor handshake")
        except Exception:
            supervisor_send.close()
            supervisor_receive.close()
            if supervisor_process.pid is not None:
                if supervisor_process.is_alive():
                    supervisor_process.terminate()
                supervisor_process.join(timeout=5)
            raise
        finally:
            supervisor_receive.close()
            supervisor_send.close()
        receive_handshake: Connection | None = None
        send_handshake: Connection | None = None
        socket_root: Path | None = None
        socket_path: str | None = None
        process: BaseProcess | None = None
        try:
            receive_handshake, send_handshake = context.Pipe(duplex=False)
            socket_root = Path(tempfile.mkdtemp(prefix="antiek-issuer-"))
            socket_root.chmod(0o700)
            socket_path = os.fspath(socket_root / _ISSUER_WITNESS_SOCKET_NAME)
            process = context.Process(
                target=_fixture_migration_lifecycle_issuer_main,
                args=(
                    socket_path,
                    supervisor_pid,
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
                    recovery_fault_boundary,
                ),
                daemon=True,
            )
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
            if process is not None and process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
            if socket_root is not None:
                (socket_root / _ISSUER_WITNESS_SOCKET_NAME).unlink(missing_ok=True)
                with suppress(OSError):
                    socket_root.rmdir()
            if supervisor_process.is_alive():
                supervisor_process.terminate()
            supervisor_process.join(timeout=5)
            raise
        finally:
            if receive_handshake is not None:
                receive_handshake.close()
            if send_handshake is not None:
                send_handshake.close()
        assert process is not None
        assert socket_path is not None
        assert socket_root is not None
        issuer = object.__new__(cls)
        object.__setattr__(issuer, "_boot_nonce", secrets.token_bytes(32))
        object.__setattr__(issuer, "_creator_pid", os.getpid())
        object.__setattr__(issuer, "_lock", threading.Lock())
        object.__setattr__(issuer, "_process", process)
        object.__setattr__(issuer, "_socket_path", socket_path)
        object.__setattr__(issuer, "_socket_root", socket_root)
        object.__setattr__(issuer, "_supervisor_process", supervisor_process)
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
                    try:
                        response = self._request(_canonical_json({"command": "close"}))
                        if response != b"C":
                            raise ValueError("issuer close response")
                    except (OSError, ValueError):  # fmt: skip
                        pass
            finally:
                if self._supervisor_process.is_alive():
                    self._supervisor_process.terminate()
                self._supervisor_process.join(timeout=5)
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


_CHILD_BARRIER_OPERATION_VERSIONS: dict[str, tuple[int, int]] = {
    "deny_new_admission": (1, 2),
    "drain_terminal_only": (2, 3),
    "close_and_revoke_all_writers": (3, 4),
    "checkpoint_and_plant_test_all_mutators": (4, 5),
    "seal_and_collect": (5, 6),
}

_RECOVERY_ROOT_BARRIER_SUBPHASES: tuple[tuple[str, str, str], ...] = (
    ("deny_new_admission", "quiesced", "admission_denied"),
    ("drain_terminal_only", "admission_denied", "drained"),
    ("close_and_revoke_all_writers", "drained", "writers_revoked"),
    ("checkpoint_and_plant_test_all_mutators", "writers_revoked", "writers_verified"),
    ("seal_and_collect", "writers_verified", "sealed"),
)


def _expected_child_adapter_state(role: str, version: int) -> list[int] | None:
    if version < 1 or version > _MIGRATION_CHILD_FINAL_VERSION:
        return None
    admission = 0 if role == "paid-lane-fixture-v1" and version >= 2 else 1
    writer = 0 if version >= 4 else 1
    return [admission, writer, 0, 0, version]


def _read_child_adapter_state(path: Path) -> list[int]:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT admission_enabled,writer_enabled,active_invocations,"
            "open_accounting_cents,version FROM adapter_state WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise ValueError("child adapter state missing")
        return list(row)
    finally:
        connection.close()


def _child_barrier_operation_pre_satisfied(role: str, path: Path, operation: str) -> bool:
    pre_version, _ = _CHILD_BARRIER_OPERATION_VERSIONS[operation]
    state = _read_child_adapter_state(path)
    expected = _expected_child_adapter_state(role, pre_version)
    if state != expected:
        return False
    if operation == "drain_terminal_only":
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
        finally:
            connection.close()
        return row == (0, 0) and zero_only_rows == 0
    if operation == "seal_and_collect":
        connection = sqlite3.connect(path)
        try:
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            adapter = connection.execute(
                "SELECT admission_enabled,writer_enabled,active_invocations,"
                "open_accounting_cents FROM adapter_state WHERE singleton=1"
            ).fetchone()
            probes = connection.execute("SELECT COUNT(*) FROM mutator_attempts").fetchone()
        finally:
            connection.close()
        return (
            checkpoint == (0, 0, 0)
            and adapter is not None
            and adapter[1:] == (0, 0, 0)
            and probes == (0,)
            and not any(
                Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")
            )
        )
    return True


def _child_barrier_operation_post_satisfied(
    role: str, path: Path, operation: str, *, evidence: Mapping[str, object]
) -> bool:
    _, post_version = _CHILD_BARRIER_OPERATION_VERSIONS[operation]
    state = _read_child_adapter_state(path)
    expected = _expected_child_adapter_state(role, post_version)
    if state != expected:
        return False
    if operation == "checkpoint_and_plant_test_all_mutators":
        # Version 5 is committed only after every mutator probe for this child rejects.
        # The root proof roster is reconstructed once all children reach this marker.
        return True
    if operation == "seal_and_collect":
        connection = sqlite3.connect(path)
        try:
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            adapter = connection.execute(
                "SELECT admission_enabled,writer_enabled,active_invocations,"
                "open_accounting_cents FROM adapter_state WHERE singleton=1"
            ).fetchone()
            probes = connection.execute("SELECT COUNT(*) FROM mutator_attempts").fetchone()
        finally:
            connection.close()
        return (
            checkpoint == (0, 0, 0)
            and adapter is not None
            and adapter[1:] == (0, 0, 0)
            and probes == (0,)
            and not any(
                Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")
            )
        )
    return True


def _classify_child_barrier_operation(
    role: str, path: Path, operation: str, *, evidence: Mapping[str, object]
) -> Literal["pre", "post", "mismatch"]:
    if operation not in _CHILD_BARRIER_OPERATION_VERSIONS:
        raise ValueError("child barrier operation unknown")
    if _child_barrier_operation_post_satisfied(role, path, operation, evidence=evidence):
        return "post"
    if _child_barrier_operation_pre_satisfied(role, path, operation):
        return "pre"
    return "mismatch"


def _apply_child_barrier_operation(
    role: str, path: Path, operation: str, *, rejected: list[str] | None = None
) -> None:
    if operation == "deny_new_admission":
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
                connection.execute("UPDATE adapter_state SET version=version+1 WHERE singleton=1")
            connection.commit()
        finally:
            connection.close()
        return
    if operation == "drain_terminal_only":
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
            if row != (0, 0) or zero_only_rows != 0:
                raise ValueError("child work not drained")
            connection.execute("UPDATE adapter_state SET version=version+1 WHERE singleton=1")
            connection.commit()
        finally:
            connection.close()
        return
    if operation == "close_and_revoke_all_writers":
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "UPDATE adapter_state SET writer_enabled=0,version=version+1 "
                "WHERE singleton=1 AND writer_enabled=1"
            )
            connection.commit()
        finally:
            connection.close()
        return
    if operation == "checkpoint_and_plant_test_all_mutators":
        if rejected is None:
            raise ValueError("child mutator rejection roster required")
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
        return
    if operation == "seal_and_collect":
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
        return
    raise ValueError("child barrier operation unknown")


def _verify_child_barrier_operation(
    role: str, path: Path, operation: str, *, evidence: Mapping[str, object]
) -> None:
    if _classify_child_barrier_operation(role, path, operation, evidence=evidence) != "post":
        raise ValueError("child barrier operation verify mismatch")


def _execute_barrier_child_operation(
    root: Path,
    record: dict[str, object],
    operation: str,
    *,
    recovery_mode: bool,
    fault_hook: Callable[[str, str | None], None] | None = None,
) -> bool:
    evidence = record.get("child_adapter_evidence")
    if type(evidence) is not dict:
        raise ValueError("child adapter evidence missing")
    applied = False
    rejected: list[str] = []
    classifications = tuple(
        (
            role,
            _child_path(root, role),
            _classify_child_barrier_operation(
                role,
                _child_path(root, role),
                operation,
                evidence=evidence,
            ),
        )
        for role in _CHILD_ROLES
    )
    if any(classification == "mismatch" for _, _, classification in classifications):
        raise ValueError("child barrier operation classification mismatch")
    if not recovery_mode and any(
        classification == "post" for _, _, classification in classifications
    ):
        raise ValueError("child barrier operation post unexpected")
    for role, path, classification in classifications:
        if classification == "post":
            pass
        elif classification == "pre":
            if operation == "checkpoint_and_plant_test_all_mutators":
                _apply_child_barrier_operation(role, path, operation, rejected=rejected)
            else:
                _apply_child_barrier_operation(role, path, operation)
            applied = True
        _verify_child_barrier_operation(role, path, operation, evidence=evidence)
        if classification == "pre" and fault_hook is not None:
            fault_hook(operation, role)
    if operation == "deny_new_admission":
        evidence["admission_denied"] = True
    elif operation == "drain_terminal_only":
        evidence["drain_verified"] = True
    elif operation == "close_and_revoke_all_writers":
        evidence["writers_revoked"] = True
    elif operation == "checkpoint_and_plant_test_all_mutators":
        expected_rejections = [
            f"{role}:{table}:{mutation}"
            for role in _CHILD_ROLES
            for table in _owned_child_tables(role)
            for mutation in ("insert", "update", "delete")
        ]
        evidence["planted_mutator_rejections"] = expected_rejections
        if evidence.get("planted_mutator_rejections") != expected_rejections:
            raise ValueError("child mutator proof roster mismatch")
    elif operation == "seal_and_collect":
        measured = _measure_child_adapters(root)
        existing_measurements = evidence.get("sealed_measurements")
        if existing_measurements is not None and existing_measurements != measured:
            raise ValueError("sealed source measurement drift")
        evidence["sealed_measurements"] = measured
    return applied


def _execute_synthetic_transition(root: Path, record: dict[str, object], operation: str) -> None:
    _execute_barrier_child_operation(root, record, operation, recovery_mode=False)


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
