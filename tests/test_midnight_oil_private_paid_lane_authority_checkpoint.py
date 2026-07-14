"""Cycle34A tests for private_paid_lane_authority_checkpoint."""

from __future__ import annotations

import ast
import copy
import fcntl
import hashlib
import hmac
import inspect
import json
import multiprocessing
import os
import pickle
import sqlite3
import textwrap
import weakref
from pathlib import Path
from typing import Any

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import substrate.midnight_oil.private_paid_lane_authority_checkpoint as checkpoint_module
import tests.support.private_paid_lane_authority_checkpoint_v1 as support_checkpoint
from substrate.midnight_oil.private_paid_lane_authority_checkpoint import (
    _BLIND_DOMAINS,
    _EXPECTED_AUTOINDEX_NAMES,
    _EXPECTED_INDEX_SET,
    _EXPECTED_TABLE_SET,
    _EXTERNAL_PIN_DOMAIN,
    _PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
    _PREDECESSOR_CYCLE32_SOURCE_SHA256,
    _PREDECESSOR_CYCLE33_CONTRACT_SHA256,
    _READY_DOMAIN,
    _SCHEMA_SQL_V1,
    FixtureBudgetResultV1,
    FixtureCapabilityResultV1,
    FixtureConsentPutV1,
    FixtureConsentResultV1,
    FixtureHeadResultV1,
    FixtureOwnerOperationPutV1,
    FixtureOwnerOperationResultV1,
    FixtureQueueLeaseResultV1,
    FrozenPaidLaneMigrationCorpusV1,
    MigrationSourceStoreV1,
    PrivatePaidLaneEligibilityCheckpointRejected,
    PrivatePaidLaneEligibilityCheckpointStoreV1,
    QuarantinedSyntheticExternalPinRecordV1,
    QuarantinedSyntheticExternalPinStoreV1,
    QuarantinedSyntheticLegacyRootV1,
    QuarantinedSyntheticReadyRecordV1,
    _canonical_json,
    _capability_v4_document_sha256,
    _compact_sql,
    _revocation_head_document_sha256,
    _source_head_document_sha256,
    compute_private_paid_lane_contract_sha256,
    compute_private_paid_lane_semantic_sha256,
)
from tests.support.private_paid_lane_authority_checkpoint_v1 import (
    OWNER_PATH_DISCRIMINATOR,
    SOURCE_KEY_VERSION,
    STORE_ID,
    OpaqueOwnerPathAuthority,
    capability_verification_keys,
    cutover_verification_keys,
    fixture_capability_v4,
    fixture_revocation_head,
    fixture_source_head,
    fixture_store_case,
    provider_revocation_floor_pins,
    revocation_verification_keys,
    source_floor_pins,
    source_head_verification_keys,
)
from tests.support.private_paid_lane_authority_checkpoint_v1 import (
    QuarantinedSyntheticExternalPinStoreV1 as SupportExternalPinStoreV1,
)
from tests.support.private_paid_lane_authority_checkpoint_v1 import (
    QuarantinedSyntheticLegacyRootV1 as SupportLegacyRootV1,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _schema_row_count(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COUNT(*) FROM paid_lane_schema").fetchone()
    assert row is not None
    return int(row[0])


def _empty_migration_source_stores() -> tuple[MigrationSourceStoreV1, ...]:
    domain = b"antiek.midnight-oil.private-paid-source-store-ordered-rows.v1\0"
    stores = []
    for index, role in enumerate(
        ("owner_private_source_v1", "paid_lane_fixture_v1", "provider_authority_v4"),
        start=1,
    ):
        role_bytes = role.encode()
        digest = hashlib.sha256(
            domain + len(role_bytes).to_bytes(4, "big") + role_bytes + _canonical_json([])
        ).hexdigest()
        stores.append(
            MigrationSourceStoreV1(
                store_kind=role,
                store_id=f"legacy-{index}",
                schema_sha256=checkpoint_module._migration_role_schema_sha256(role),
                native_writer_barrier_id=checkpoint_module._migration_barrier_id("33" * 32),
                final_version=checkpoint_module._MIGRATION_CHILD_FINAL_VERSION,
                row_count=0,
                ordered_rows_sha256=digest,
            )
        )
    return tuple(stores)


def _reopen_precutover(case: Any) -> PrivatePaidLaneEligibilityCheckpointStoreV1:
    semantic = compute_private_paid_lane_semantic_sha256()
    return PrivatePaidLaneEligibilityCheckpointStoreV1.open(
        database_path=case.store.database_path,
        open_mode="precutover_epoch0",
        expected_store_id=STORE_ID,
        expected_schema_version=1,
        expected_migration_epoch=0,
        expected_cutover_marker_sha256=None,
        expected_source_manifest_sha256=None,
        expected_copy_audit_sha256=None,
        expected_external_pin_store_id=STORE_ID,
        expected_semantic_source_sha256=semantic,
        expected_contract_sha256=compute_private_paid_lane_contract_sha256(
            semantic_sha256=semantic,
            sql=_SCHEMA_SQL_V1,
            predecessor_cycle33_contract=_PREDECESSOR_CYCLE33_CONTRACT_SHA256,
            predecessor_cycle32_source=_PREDECESSOR_CYCLE32_SOURCE_SHA256,
            predecessor_cycle30_capability=_PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
        ),
        provider_capability_verification_keys=capability_verification_keys(),
        provider_revocation_verification_keys=revocation_verification_keys(),
        source_head_verification_keys=source_head_verification_keys(),
        cutover_verification_keys=cutover_verification_keys(),
        provider_revocation_floor_pins=provider_revocation_floor_pins(),
        source_floor_pins=source_floor_pins(),
        source_bundle_key_provider=case.source_key_provider,
        owner_key_provider=case.owner_key_provider,
        synthetic_legacy_root=QuarantinedSyntheticLegacyRootV1(),
        synthetic_external_pin_store=QuarantinedSyntheticExternalPinStoreV1(store_id=STORE_ID),
    )


def _all_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }


def _all_explicit_indexes(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name NOT LIKE 'sqlite_autoindex_%'"
        ).fetchall()
    }


def _all_autoindexes(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'sqlite_autoindex_%'"
        ).fetchall()
    }


def _table_sql(connection: sqlite3.Connection, name: str) -> str | None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return str(row[0]) if row else None


def _expected_blind(key: bytes | bytearray, purpose: str, parts: tuple[bytes, ...]) -> bytes:
    msg = bytearray(_BLIND_DOMAINS[purpose])
    for part in parts:
        msg.extend(len(part).to_bytes(4, "big"))
        msg.extend(part)
    return hmac.new(bytes(key), bytes(msg), hashlib.sha256).digest()


def _mp_install_pin(root: str, record: dict[str, object], queue: Any) -> None:
    try:
        store = SupportExternalPinStoreV1.open_existing(
            root_path=Path(root), expected_pin_store_id="pin-store-mp"
        )
        store.install_once(
            expected_absent=True,
            record=QuarantinedSyntheticExternalPinRecordV1.model_validate(record),
        )
        queue.put("won")
    except Exception:
        queue.put("lost")


def _mp_use_barrier(barrier: Any, queue: Any) -> None:
    try:
        barrier.deny_new_admission()
        queue.put("accepted")
    except Exception:
        queue.put("rejected")


def _mp_acquire_barrier(root: str, manifest: str, inventory: str, queue: Any) -> None:
    try:
        legacy = SupportLegacyRootV1.open_existing(
            root_path=Path(root),
            expected_root_id="legacy-mp",
            expected_root_manifest_sha256=manifest,
            expected_inventory_sha256=inventory,
        )
        barrier = legacy.acquire_writer_barrier(
            expected_root_id="legacy-mp",
            expected_root_manifest_sha256=manifest,
            expected_inventory_sha256=inventory,
        )
        queue.put(("won", barrier.barrier_id, barrier.freeze_nonce))
    except Exception:
        queue.put(("lost", None, None))


def _mp_hold_lock(root: str, ready: Any, release: Any) -> None:
    descriptor = os.open(Path(root) / ".migration.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        ready.set()
        release.wait(10)
    finally:
        os.close(descriptor)


# ---------------------------------------------------------------------------
# Schema/identity tests
# ---------------------------------------------------------------------------


class TestSchemaAudit:
    @pytest.mark.parametrize(
        ("size_delta", "accepted"),
        ((-1, True), (0, True), (1, False)),
    )
    def test_document_byte_bound_n_edges(self, size_delta: int, accepted: bool) -> None:
        value = b"x" * (checkpoint_module.MAX_DOCUMENT_BYTES + size_delta)
        if accepted:
            checkpoint_module._require_bounded_bytes(
                value, bound=checkpoint_module.MAX_DOCUMENT_BYTES
            )
        else:
            with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
                checkpoint_module._require_bounded_bytes(
                    value, bound=checkpoint_module.MAX_DOCUMENT_BYTES
                )

    def test_direct_constructor_and_mode_forgery_cannot_create_writer_authority(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            PrivatePaidLaneEligibilityCheckpointStoreV1()
        with pytest.raises(TypeError):
            type(
                "ForbiddenCheckpointSubclass",
                (PrivatePaidLaneEligibilityCheckpointStoreV1,),
                {},
            )
        case = fixture_store_case(tmp_path / "constructor-harness")
        assert type(case.store) is PrivatePaidLaneEligibilityCheckpointStoreV1
        assert not hasattr(
            PrivatePaidLaneEligibilityCheckpointStoreV1,
            "_enable_quarantined_fixture_writer_harness",
        )
        assert not any(
            "harness" in name.lower() or "activate" in name.lower()
            for name in checkpoint_module.__dict__
        )
        assert not hasattr(
            PrivatePaidLaneEligibilityCheckpointStoreV1,
            "_initialize_from_open",
        )
        uninitialized = object.__new__(PrivatePaidLaneEligibilityCheckpointStoreV1)
        with pytest.raises(AttributeError):
            object.__getattribute__(uninitialized, "_initialize_from_open")
        object.__setattr__(uninitialized, "open_mode", "pinned_epoch1")
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            uninitialized.put_fixture_owner_operation(
                owner_path_authority=case.authority,
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                value=FixtureOwnerOperationPutV1(
                    operation_id="uninitialized",
                    job_id="uninitialized-job",
                    execution_id="uninitialized-execution",
                    stage_id="uninitialized-stage",
                    state="queued",
                ),
                now_ms=1,
            )
        production_store = PrivatePaidLaneEligibilityCheckpointStoreV1.open(
            database_path=tmp_path / "production-epoch0" / "paid-lane.sqlite3",
            open_mode="create_epoch0",
            expected_store_id=STORE_ID,
            expected_schema_version=1,
            expected_migration_epoch=0,
            expected_cutover_marker_sha256=None,
            expected_source_manifest_sha256=None,
            expected_copy_audit_sha256=None,
            expected_external_pin_store_id=STORE_ID,
            expected_semantic_source_sha256=compute_private_paid_lane_semantic_sha256(),
            expected_contract_sha256=checkpoint_module.PRIVATE_PAID_LANE_CHECKPOINT_CONTRACT_SHA256_V1,
            provider_capability_verification_keys=capability_verification_keys(),
            provider_revocation_verification_keys=revocation_verification_keys(),
            source_head_verification_keys=source_head_verification_keys(),
            cutover_verification_keys=cutover_verification_keys(),
            provider_revocation_floor_pins=provider_revocation_floor_pins(),
            source_floor_pins=source_floor_pins(),
            source_bundle_key_provider=case.source_key_provider,
            owner_key_provider=case.owner_key_provider,
            synthetic_legacy_root=QuarantinedSyntheticLegacyRootV1(),
            synthetic_external_pin_store=QuarantinedSyntheticExternalPinStoreV1(store_id=STORE_ID),
        )
        assert type(production_store) is PrivatePaidLaneEligibilityCheckpointStoreV1
        foreign_open: Any = PrivatePaidLaneEligibilityCheckpointStoreV1.__dict__["open"].__func__
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            foreign_open(
                object,
                database_path=tmp_path / "foreign-class" / "paid-lane.sqlite3",
                open_mode="create_epoch0",
                expected_store_id=STORE_ID,
                expected_schema_version=1,
                expected_migration_epoch=0,
                expected_cutover_marker_sha256=None,
                expected_source_manifest_sha256=None,
                expected_copy_audit_sha256=None,
                expected_external_pin_store_id=STORE_ID,
                expected_semantic_source_sha256=compute_private_paid_lane_semantic_sha256(),
                expected_contract_sha256=(
                    checkpoint_module.PRIVATE_PAID_LANE_CHECKPOINT_CONTRACT_SHA256_V1
                ),
                provider_capability_verification_keys=capability_verification_keys(),
                provider_revocation_verification_keys=revocation_verification_keys(),
                source_head_verification_keys=source_head_verification_keys(),
                cutover_verification_keys=cutover_verification_keys(),
                provider_revocation_floor_pins=provider_revocation_floor_pins(),
                source_floor_pins=source_floor_pins(),
                source_bundle_key_provider=case.source_key_provider,
                owner_key_provider=case.owner_key_provider,
                synthetic_legacy_root=QuarantinedSyntheticLegacyRootV1(),
                synthetic_external_pin_store=QuarantinedSyntheticExternalPinStoreV1(
                    store_id=STORE_ID
                ),
            )
        object.__setattr__(production_store, "open_mode", "pinned_epoch1")
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            production_store.put_fixture_owner_operation(
                owner_path_authority=case.authority,
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                value=FixtureOwnerOperationPutV1(
                    operation_id="forged",
                    job_id="forged-job",
                    execution_id="forged-execution",
                    stage_id="forged-stage",
                    state="queued",
                ),
                now_ms=1,
            )

    @pytest.mark.parametrize(
        "gate_name",
        (
            "require_private_source_authority_module_source",
            "require_private_source_head_store_module_source",
            "require_private_source_bundle_store_module_source",
        ),
    )
    def test_open_requires_exact_predecessor_runtime_attestations(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gate_name: str
    ) -> None:
        def reject() -> None:
            raise RuntimeError("mutated predecessor")

        monkeypatch.setattr(checkpoint_module, gate_name, reject)
        target = tmp_path / gate_name / "paid-lane.sqlite3"
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            fixture_store_case(target.parent)
        assert not target.exists()

    @pytest.mark.parametrize(
        "gate_name",
        (
            "require_private_source_authority_module_source",
            "require_private_source_head_store_module_source",
            "require_private_source_bundle_store_module_source",
        ),
    )
    def test_authority_read_rechecks_predecessor_runtime_attestations(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gate_name: str
    ) -> None:
        case = fixture_store_case(tmp_path / f"runtime-{gate_name}")

        def reject() -> None:
            raise RuntimeError("mutated predecessor")

        monkeypatch.setattr(checkpoint_module, gate_name, reject)
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            case.store.put_fixture_owner_operation(
                owner_path_authority=case.authority,
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                value=FixtureOwnerOperationPutV1(
                    operation_id="attestation",
                    job_id="attestation-job",
                    execution_id="attestation-execution",
                    stage_id="attestation-stage",
                    state="queued",
                ),
                now_ms=1,
            )
        with sqlite3.connect(case.store.database_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM owner_operations").fetchone() == (0,)

    def test_mutable_row_bound_accepts_n_minus_one_and_n_then_rejects_n_plus_one(
        self, tmp_path: Path
    ) -> None:
        case = fixture_store_case(tmp_path / "mutable-row-bound")
        bound = checkpoint_module.MAX_MUTABLE_CURRENT_ROWS
        with sqlite3.connect(case.store.database_path) as connection:
            connection.execute(
                "WITH RECURSIVE seq(value) AS (VALUES(0) UNION ALL "
                "SELECT value+1 FROM seq WHERE value<?) "
                "INSERT INTO owner_operations "
                "(owner_path_discriminator,operation_id,job_id,execution_id,stage_id,state,"
                "state_version,cancel_requested,cancellation_version,created_at_ms,updated_at_ms) "
                "SELECT ?,printf('capacity-op-%d',value),printf('capacity-job-%d',value),"
                "printf('capacity-exec-%d',value),printf('capacity-stage-%d',value),"
                "'queued',1,0,0,0,0 FROM seq",
                (bound - 2, OWNER_PATH_DISCRIMINATOR),
            )
            connection.commit()
            assert connection.execute("SELECT COUNT(*) FROM owner_operations").fetchone() == (
                bound - 1,
            )
            checkpoint_module._audit_34a_row_bounds(connection)
        with sqlite3.connect(case.store.database_path) as connection:
            connection.execute(
                "INSERT INTO owner_operations VALUES (?,?,?,?,?,'queued',1,0,0,0,0)",
                (
                    OWNER_PATH_DISCRIMINATOR,
                    "capacity-n",
                    "capacity-job-n",
                    "capacity-exec-n",
                    "capacity-stage-n",
                ),
            )
            connection.commit()
            checkpoint_module._audit_34a_row_bounds(connection)
            connection.execute(
                "INSERT INTO owner_operations VALUES (?,?,?,?,?,'queued',1,0,0,0,0)",
                (
                    OWNER_PATH_DISCRIMINATOR,
                    "raw-n-plus-one",
                    "raw-job-n-plus-one",
                    "raw-exec-n-plus-one",
                    "raw-stage-n-plus-one",
                ),
            )
            connection.commit()
            with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
                checkpoint_module._audit_34a_row_bounds(connection)

    def test_schema_has_18_tables(self, tmp_path: Path) -> None:
        case = fixture_store_case(tmp_path / "t18")
        with sqlite3.connect(case.store.database_path) as conn:
            tables = _all_tables(conn)
        assert len(tables) == 18
        assert tables == _EXPECTED_TABLE_SET

    def test_schema_has_13_explicit_indexes(self, tmp_path: Path) -> None:
        case = fixture_store_case(tmp_path / "t13")
        with sqlite3.connect(case.store.database_path) as conn:
            indexes = _all_explicit_indexes(conn)
        assert len(indexes) == 13
        assert indexes == _EXPECTED_INDEX_SET

    def test_schema_has_46_autoindexes(self, tmp_path: Path) -> None:
        case = fixture_store_case(tmp_path / "t46")
        with sqlite3.connect(case.store.database_path) as conn:
            auto = _all_autoindexes(conn)
        assert len(auto) == 46
        assert auto == _EXPECTED_AUTOINDEX_NAMES

    def test_schema_singleton(self, tmp_path: Path) -> None:
        case = fixture_store_case(tmp_path / "ts")
        with sqlite3.connect(case.store.database_path) as conn:
            row = conn.execute(
                "SELECT schema_version, migration_epoch, store_id, semantic_source_sha256, "
                "contract_sha256, cutover_marker_sha256 FROM paid_lane_schema WHERE singleton=1"
            ).fetchone()
        assert row is not None
        assert row[0] == 1  # schema_version
        assert row[1] == 0  # migration_epoch
        assert row[2] == STORE_ID
        assert row[3] == case.store.semantic_source_sha256
        assert row[4] == case.store.contract_sha256
        assert row[5] is None

    def test_schema_sql_matches_normative(self) -> None:
        """Verify _SCHEMA_SQL_V1 parses to exactly the expected objects."""
        tables, indexes = _parse_schema_sql(_SCHEMA_SQL_V1)
        assert len(tables) == 18
        assert len(indexes) == 13
        table_names = [name for name, _ in tables]
        index_names = [name for name, _ in indexes]
        assert set(table_names) == _EXPECTED_TABLE_SET
        assert set(index_names) == _EXPECTED_INDEX_SET

    def test_compact_sql_normalization(self) -> None:
        a = _compact_sql("CREATE TABLE foo (id INTEGER NOT NULL)")
        b = _compact_sql("CREATE  TABLE  FOO  (  ID  INTEGER  NOT  NULL  )")
        assert a == b

    def test_authorizer_denies_delete(self, tmp_path: Path) -> None:
        case = fixture_store_case(tmp_path / "tauth")
        with (
            pytest.raises((PrivatePaidLaneEligibilityCheckpointRejected, sqlite3.DatabaseError)),
            sqlite3.connect(case.store.database_path) as conn,
        ):
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.set_authorizer(checkpoint_module._authorizer)
            conn.execute("DELETE FROM paid_lane_schema WHERE singleton=1")

    def test_precutover_reopen_audits_without_rerunning_ddl(self, tmp_path: Path) -> None:
        case = fixture_store_case(tmp_path / "treopen")
        reopened = PrivatePaidLaneEligibilityCheckpointStoreV1.open(
            database_path=case.store.database_path,
            open_mode="precutover_epoch0",
            expected_store_id=STORE_ID,
            expected_schema_version=1,
            expected_migration_epoch=0,
            expected_cutover_marker_sha256=None,
            expected_source_manifest_sha256=None,
            expected_copy_audit_sha256=None,
            expected_external_pin_store_id=STORE_ID,
            expected_semantic_source_sha256=case.store.semantic_source_sha256,
            expected_contract_sha256=case.store.contract_sha256,
            provider_capability_verification_keys=capability_verification_keys(),
            provider_revocation_verification_keys=revocation_verification_keys(),
            source_head_verification_keys=source_head_verification_keys(),
            cutover_verification_keys=cutover_verification_keys(),
            provider_revocation_floor_pins=provider_revocation_floor_pins(),
            source_floor_pins=source_floor_pins(),
            source_bundle_key_provider=case.source_key_provider,
            owner_key_provider=case.owner_key_provider,
            synthetic_legacy_root=QuarantinedSyntheticLegacyRootV1(),
            synthetic_external_pin_store=QuarantinedSyntheticExternalPinStoreV1(store_id=STORE_ID),
        )
        assert reopened.database_path == case.store.database_path

    def test_reopen_rejects_extra_schema_object(self, tmp_path: Path) -> None:
        case = fixture_store_case(tmp_path / "tschemadrift")
        with sqlite3.connect(case.store.database_path) as conn:
            conn.execute("CREATE TABLE injected_schema_drift (id INTEGER) STRICT")
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            PrivatePaidLaneEligibilityCheckpointStoreV1.open(
                database_path=case.store.database_path,
                open_mode="precutover_epoch0",
                expected_store_id=STORE_ID,
                expected_schema_version=1,
                expected_migration_epoch=0,
                expected_cutover_marker_sha256=None,
                expected_source_manifest_sha256=None,
                expected_copy_audit_sha256=None,
                expected_external_pin_store_id=STORE_ID,
                expected_semantic_source_sha256=case.store.semantic_source_sha256,
                expected_contract_sha256=case.store.contract_sha256,
                provider_capability_verification_keys=capability_verification_keys(),
                provider_revocation_verification_keys=revocation_verification_keys(),
                source_head_verification_keys=source_head_verification_keys(),
                cutover_verification_keys=cutover_verification_keys(),
                provider_revocation_floor_pins=provider_revocation_floor_pins(),
                source_floor_pins=source_floor_pins(),
                source_bundle_key_provider=case.source_key_provider,
                owner_key_provider=case.owner_key_provider,
                synthetic_legacy_root=QuarantinedSyntheticLegacyRootV1(),
                synthetic_external_pin_store=QuarantinedSyntheticExternalPinStoreV1(
                    store_id=STORE_ID
                ),
            )

    def test_create_epoch0_authenticates_then_rejects_normal_fixture_writer(
        self, tmp_path: Path
    ) -> None:
        authority = OpaqueOwnerPathAuthority()
        from tests.support.private_paid_lane_authority_checkpoint_v1 import (
            FixtureOwnerKeyProvider,
            FixtureSourceKeyProvider,
        )

        semantic = compute_private_paid_lane_semantic_sha256()
        owner_key_provider = FixtureOwnerKeyProvider(authority)
        store = PrivatePaidLaneEligibilityCheckpointStoreV1.open(
            database_path=tmp_path / "epoch0" / "paid-lane.sqlite3",
            open_mode="create_epoch0",
            expected_store_id=STORE_ID,
            expected_schema_version=1,
            expected_migration_epoch=0,
            expected_cutover_marker_sha256=None,
            expected_source_manifest_sha256=None,
            expected_copy_audit_sha256=None,
            expected_external_pin_store_id=STORE_ID,
            expected_semantic_source_sha256=semantic,
            expected_contract_sha256=compute_private_paid_lane_contract_sha256(
                semantic_sha256=semantic,
                sql=_SCHEMA_SQL_V1,
                predecessor_cycle33_contract=_PREDECESSOR_CYCLE33_CONTRACT_SHA256,
                predecessor_cycle32_source=_PREDECESSOR_CYCLE32_SOURCE_SHA256,
                predecessor_cycle30_capability=_PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
            ),
            provider_capability_verification_keys=capability_verification_keys(),
            provider_revocation_verification_keys=revocation_verification_keys(),
            source_head_verification_keys=source_head_verification_keys(),
            cutover_verification_keys=cutover_verification_keys(),
            provider_revocation_floor_pins=provider_revocation_floor_pins(),
            source_floor_pins=source_floor_pins(),
            source_bundle_key_provider=FixtureSourceKeyProvider(),
            owner_key_provider=owner_key_provider,
            synthetic_legacy_root=QuarantinedSyntheticLegacyRootV1(),
            synthetic_external_pin_store=QuarantinedSyntheticExternalPinStoreV1(store_id=STORE_ID),
        )
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            store.put_fixture_owner_operation(
                owner_path_authority=authority,
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                value=FixtureOwnerOperationPutV1(
                    operation_id="op:epoch0",
                    job_id="job:epoch0",
                    execution_id="exec:epoch0",
                    stage_id="stage:epoch0",
                    state="queued",
                ),
                now_ms=1,
            )
        assert store.open_mode == "create_epoch0"
        assert len(owner_key_provider.auth_calls) == 1
        with sqlite3.connect(store.database_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM owner_operations").fetchone() == (0,)

    def test_pinned_epoch1_fails_closed_without_exact_34d_ceremony(self, tmp_path: Path) -> None:
        case = fixture_store_case(tmp_path / "tpinready")
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            PrivatePaidLaneEligibilityCheckpointStoreV1.open(
                database_path=case.store.database_path,
                open_mode="pinned_epoch1",
                expected_store_id=STORE_ID,
                expected_schema_version=1,
                expected_migration_epoch=1,
                expected_cutover_marker_sha256="33" * 32,
                expected_source_manifest_sha256="11" * 32,
                expected_copy_audit_sha256="22" * 32,
                expected_external_pin_store_id=STORE_ID,
                expected_semantic_source_sha256=case.store.semantic_source_sha256,
                expected_contract_sha256=case.store.contract_sha256,
                provider_capability_verification_keys=capability_verification_keys(),
                provider_revocation_verification_keys=revocation_verification_keys(),
                source_head_verification_keys=source_head_verification_keys(),
                cutover_verification_keys=cutover_verification_keys(),
                provider_revocation_floor_pins=provider_revocation_floor_pins(),
                source_floor_pins=source_floor_pins(),
                source_bundle_key_provider=case.source_key_provider,
                owner_key_provider=case.owner_key_provider,
                synthetic_legacy_root=None,
                synthetic_external_pin_store=QuarantinedSyntheticExternalPinStoreV1(
                    store_id=STORE_ID,
                    pin_sha256="44" * 32,
                    ready_sha256=None,
                ),
            )

    def test_supplied_symlink_alias_rejects_before_resolution(self, tmp_path: Path) -> None:
        real_root = tmp_path / "real"
        real_root.mkdir(mode=0o700)
        alias = tmp_path / "alias"
        alias.symlink_to(real_root, target_is_directory=True)
        authority = OpaqueOwnerPathAuthority()
        from tests.support.private_paid_lane_authority_checkpoint_v1 import (
            FixtureOwnerKeyProvider,
            FixtureSourceKeyProvider,
        )

        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            PrivatePaidLaneEligibilityCheckpointStoreV1.open(
                database_path=alias / "paid-lane.sqlite3",
                open_mode="create_epoch0",
                expected_store_id=STORE_ID,
                expected_schema_version=1,
                expected_migration_epoch=0,
                expected_cutover_marker_sha256=None,
                expected_source_manifest_sha256=None,
                expected_copy_audit_sha256=None,
                expected_external_pin_store_id=STORE_ID,
                expected_semantic_source_sha256=compute_private_paid_lane_semantic_sha256(),
                expected_contract_sha256=compute_private_paid_lane_contract_sha256(
                    semantic_sha256=compute_private_paid_lane_semantic_sha256(),
                    sql=_SCHEMA_SQL_V1,
                    predecessor_cycle33_contract=_PREDECESSOR_CYCLE33_CONTRACT_SHA256,
                    predecessor_cycle32_source=_PREDECESSOR_CYCLE32_SOURCE_SHA256,
                    predecessor_cycle30_capability=_PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
                ),
                provider_capability_verification_keys=capability_verification_keys(),
                provider_revocation_verification_keys=revocation_verification_keys(),
                source_head_verification_keys=source_head_verification_keys(),
                cutover_verification_keys=cutover_verification_keys(),
                provider_revocation_floor_pins=provider_revocation_floor_pins(),
                source_floor_pins=source_floor_pins(),
                source_bundle_key_provider=FixtureSourceKeyProvider(),
                owner_key_provider=FixtureOwnerKeyProvider(authority),
                synthetic_legacy_root=QuarantinedSyntheticLegacyRootV1(),
                synthetic_external_pin_store=QuarantinedSyntheticExternalPinStoreV1(
                    store_id=STORE_ID
                ),
            )

    def test_duplicate_verification_key_ids_reject_before_open(self, tmp_path: Path) -> None:
        authority = OpaqueOwnerPathAuthority()
        from tests.support.private_paid_lane_authority_checkpoint_v1 import (
            FixtureOwnerKeyProvider,
            FixtureSourceKeyProvider,
            capability_verification_keys,
        )

        duplicate_capability_keys = (
            capability_verification_keys()[0],
            capability_verification_keys()[0],
        )
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            PrivatePaidLaneEligibilityCheckpointStoreV1.open(
                database_path=tmp_path / "dup" / "paid-lane.sqlite3",
                open_mode="create_epoch0",
                expected_store_id=STORE_ID,
                expected_schema_version=1,
                expected_migration_epoch=0,
                expected_cutover_marker_sha256=None,
                expected_source_manifest_sha256=None,
                expected_copy_audit_sha256=None,
                expected_external_pin_store_id=STORE_ID,
                expected_semantic_source_sha256=compute_private_paid_lane_semantic_sha256(),
                expected_contract_sha256=compute_private_paid_lane_contract_sha256(
                    semantic_sha256=compute_private_paid_lane_semantic_sha256(),
                    sql=_SCHEMA_SQL_V1,
                    predecessor_cycle33_contract=_PREDECESSOR_CYCLE33_CONTRACT_SHA256,
                    predecessor_cycle32_source=_PREDECESSOR_CYCLE32_SOURCE_SHA256,
                    predecessor_cycle30_capability=_PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
                ),
                provider_capability_verification_keys=duplicate_capability_keys,
                provider_revocation_verification_keys=revocation_verification_keys(),
                source_head_verification_keys=source_head_verification_keys(),
                cutover_verification_keys=cutover_verification_keys(),
                provider_revocation_floor_pins=provider_revocation_floor_pins(),
                source_floor_pins=source_floor_pins(),
                source_bundle_key_provider=FixtureSourceKeyProvider(),
                owner_key_provider=FixtureOwnerKeyProvider(authority),
                synthetic_legacy_root=QuarantinedSyntheticLegacyRootV1(),
                synthetic_external_pin_store=QuarantinedSyntheticExternalPinStoreV1(
                    store_id=STORE_ID
                ),
            )


class TestResultDtoShapes:
    _LITERALS = (
        "synthetic_fixture_eligibility_only",
        "live_migration_verified",
        "user_accounting_effect",
        "transport_reachable",
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    )

    def test_six_result_dtos_have_exact_fields(self) -> None:
        expected: dict[Any, tuple[str, ...]] = {
            FixtureOwnerOperationResultV1: (
                "applied",
                "replayed",
                "owner_path_discriminator",
                "operation_id",
                "state",
                "state_version",
                "cancel_requested",
                "cancellation_version",
                *self._LITERALS,
            ),
            FixtureConsentResultV1: (
                "applied",
                "replayed",
                "owner_path_discriminator",
                "consent_blind_id",
                "state",
                "version",
                "expires_at_ms",
                *self._LITERALS,
            ),
            FixtureQueueLeaseResultV1: (
                "applied",
                "replayed",
                "owner_path_discriminator",
                "queue_operation_id",
                "lease_owner",
                "generation",
                "cursor_blind_id",
                "row_version",
                "exclusive_until_ms",
                *self._LITERALS,
            ),
            FixtureBudgetResultV1: (
                "applied",
                "replayed",
                "owner_path_discriminator",
                "account_scope_blind_id",
                "project_scope_blind_id",
                "approved_ceiling_cents",
                "confirmed_cents",
                "open_cents",
                "unknown_cents",
                "row_version",
                *self._LITERALS,
            ),
            FixtureCapabilityResultV1: (
                "applied",
                "replayed",
                "owner_path_discriminator",
                "capability_id",
                "capability_sha256",
                "revocation_registry_id",
                "revocation_trusted_floor_sha256",
                "expires_at_ms",
                *self._LITERALS,
            ),
            FixtureHeadResultV1: (
                "applied",
                "replayed",
                "head_kind",
                "owner_path_discriminator",
                "registry_id",
                "current_head_sha256",
                "current_epoch",
                "state_version",
                *self._LITERALS,
            ),
        }
        for model, fields in expected.items():
            assert tuple(model.model_fields) == fields


def _parse_schema_sql(sql: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    tables: list[tuple[str, str]] = []
    indexes: list[tuple[str, str]] = []
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
                tables.append((str(row_name), str(row_sql)))
            elif row_type == "index" and not str(row_name).startswith("sqlite_autoindex"):
                indexes.append((str(row_name), str(row_sql)))
    finally:
        conn.close()
    return tables, indexes


# ---------------------------------------------------------------------------
# Identity tests
# ---------------------------------------------------------------------------


class TestIdentities:
    @staticmethod
    def _contract() -> str:
        return compute_private_paid_lane_contract_sha256(
            semantic_sha256=compute_private_paid_lane_semantic_sha256(),
            sql=_SCHEMA_SQL_V1,
            predecessor_cycle33_contract=_PREDECESSOR_CYCLE33_CONTRACT_SHA256,
            predecessor_cycle32_source=_PREDECESSOR_CYCLE32_SOURCE_SHA256,
            predecessor_cycle30_capability=_PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
        )

    def test_semantic_hash_deterministic(self) -> None:
        h1 = compute_private_paid_lane_semantic_sha256()
        h2 = compute_private_paid_lane_semantic_sha256()
        assert h1 == h2
        assert len(h1) == 64

    def test_contract_hash_deterministic(self) -> None:
        s = compute_private_paid_lane_semantic_sha256()
        c1 = compute_private_paid_lane_contract_sha256(
            semantic_sha256=s,
            sql=_SCHEMA_SQL_V1,
            predecessor_cycle33_contract=_PREDECESSOR_CYCLE33_CONTRACT_SHA256,
            predecessor_cycle32_source=_PREDECESSOR_CYCLE32_SOURCE_SHA256,
            predecessor_cycle30_capability=_PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
        )
        c2 = compute_private_paid_lane_contract_sha256(
            semantic_sha256=s,
            sql=_SCHEMA_SQL_V1,
            predecessor_cycle33_contract=_PREDECESSOR_CYCLE33_CONTRACT_SHA256,
            predecessor_cycle32_source=_PREDECESSOR_CYCLE32_SOURCE_SHA256,
            predecessor_cycle30_capability=_PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
        )
        assert c1 == c2
        assert len(c1) == 64

    def test_semantic_excludes_identity_assignments(self) -> None:
        """Removing the identity assignment lines should not change the hash."""
        source_file = inspect.getfile(PrivatePaidLaneEligibilityCheckpointStoreV1)
        with open(source_file, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=source_file)
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
                (
                    ast.Import,
                    ast.ImportFrom,
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                ),
            ):
                parts.append(ast.dump(node))
        combined = "\n".join(parts)
        expected = hashlib.sha256(
            checkpoint_module._SEMANTIC_SOURCE_DOMAIN + combined.encode("utf-8")
        ).hexdigest()
        assert compute_private_paid_lane_semantic_sha256() == expected

    def test_capability_v4_hash_domain(self) -> None:
        cap = fixture_capability_v4()
        h = _capability_v4_document_sha256(cap)
        assert h == cap.capability_sha256

    def test_revocation_head_hash_domain(self) -> None:
        head = fixture_revocation_head(epoch=0)
        h = _revocation_head_document_sha256(head)
        assert h == head.head_sha256

    def test_source_head_hash_domain(self) -> None:
        head = fixture_source_head(epoch=0)
        h = _source_head_document_sha256(head)
        assert h == head.head_sha256

    def test_exported_semantic_matches_computed(self) -> None:
        assert (
            compute_private_paid_lane_semantic_sha256()
            == checkpoint_module.PRIVATE_PAID_LANE_CHECKPOINT_SEMANTIC_SHA256_V1
        )

    def test_exported_contract_matches_computed(self) -> None:
        assert (
            compute_private_paid_lane_contract_sha256(
                semantic_sha256=compute_private_paid_lane_semantic_sha256(),
                sql=_SCHEMA_SQL_V1,
                predecessor_cycle33_contract=_PREDECESSOR_CYCLE33_CONTRACT_SHA256,
                predecessor_cycle32_source=_PREDECESSOR_CYCLE32_SOURCE_SHA256,
                predecessor_cycle30_capability=_PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
            )
            == checkpoint_module.PRIVATE_PAID_LANE_CHECKPOINT_CONTRACT_SHA256_V1
        )

    def test_contract_identity_changes_with_sql_and_predecessor_inputs(self) -> None:
        baseline = self._contract()
        assert (
            compute_private_paid_lane_contract_sha256(
                semantic_sha256=compute_private_paid_lane_semantic_sha256(),
                sql=_SCHEMA_SQL_V1 + "\n ",
                predecessor_cycle33_contract=_PREDECESSOR_CYCLE33_CONTRACT_SHA256,
                predecessor_cycle32_source=_PREDECESSOR_CYCLE32_SOURCE_SHA256,
                predecessor_cycle30_capability=_PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
            )
            != baseline
        )
        assert (
            compute_private_paid_lane_contract_sha256(
                semantic_sha256=compute_private_paid_lane_semantic_sha256(),
                sql=_SCHEMA_SQL_V1,
                predecessor_cycle33_contract="0" * 64,
                predecessor_cycle32_source=_PREDECESSOR_CYCLE32_SOURCE_SHA256,
                predecessor_cycle30_capability=_PREDECESSOR_CYCLE30_CAPABILITY_SHA256,
            )
            != baseline
        )

    def test_contract_identity_changes_with_domain_and_bound(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = self._contract()
        with monkeypatch.context() as patcher:
            patcher.setitem(
                checkpoint_module._BLIND_DOMAINS,
                "consent_v1",
                b"antiek.midnight-oil.private-paid-blind.consent.mutated.v1\x00",
            )
            assert self._contract() != baseline
        monkeypatch.setattr(checkpoint_module, "MAX_ACTIVE_HANDLES", 63)
        assert self._contract() != baseline

    def test_contract_identity_changes_with_model_schema(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = self._contract()
        monkeypatch.setattr(
            FixtureConsentPutV1,
            "model_json_schema",
            classmethod(lambda cls: {"title": cls.__name__, "mutated": True}),
        )
        assert self._contract() != baseline

    def test_contract_identity_changes_with_public_and_provider_signatures(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = self._contract()
        public_method: Any = PrivatePaidLaneEligibilityCheckpointStoreV1.put_fixture_consent
        with monkeypatch.context() as patcher:
            patcher.setattr(
                public_method,
                "__signature__",
                inspect.Signature([inspect.Parameter("mutated", inspect.Parameter.KEYWORD_ONLY)]),
                raising=False,
            )
            assert self._contract() != baseline
        provider_method: Any = (
            checkpoint_module.PrivatePaidLaneOwnerKeyProviderV1.open_hmac_sha256_key
        )
        monkeypatch.setattr(
            provider_method,
            "__signature__",
            inspect.Signature([inspect.Parameter("mutated", inspect.Parameter.KEYWORD_ONLY)]),
            raising=False,
        )
        assert self._contract() != baseline


# ---------------------------------------------------------------------------
# HMAC blind identity tests
# ---------------------------------------------------------------------------


class TestBlindIdentities:
    def test_no_module_level_unkeyed_or_arbitrary_key_blind_api(self) -> None:
        assert "blind_v1" not in checkpoint_module.__dict__
        assert "_blind_v1_with_provider_key" not in checkpoint_module.__dict__

    def test_private_keyed_blind_returns_32_bytes(self) -> None:
        result = _expected_blind(bytearray(b"k" * 32), "consent_v1", (b"part1", b"part2"))
        assert isinstance(result, bytes)
        assert len(result) == 32

    def test_blind_v1_deterministic(self) -> None:
        key = bytearray(b"k" * 32)
        a = _expected_blind(key, "consent_v1", (b"a",))
        b = _expected_blind(key, "consent_v1", (b"a",))
        assert a == b

    def test_blind_v1_different_purpose_different_result(self) -> None:
        key = bytearray(b"k" * 32)
        a = _expected_blind(key, "consent_v1", (b"a",))
        b = _expected_blind(key, "cursor_v1", (b"a",))
        assert a != b

    def test_blind_v1_different_parts_different_result(self) -> None:
        key = bytearray(b"k" * 32)
        a = _expected_blind(key, "consent_v1", (b"a",))
        b = _expected_blind(key, "consent_v1", (b"b",))
        assert a != b

    def test_blind_v1_different_keys_different_result(self) -> None:
        a = _expected_blind(bytearray(b"a" * 32), "consent_v1", (b"x",))
        b = _expected_blind(bytearray(b"b" * 32), "consent_v1", (b"x",))
        assert a != b

    def test_store_uses_provider_hmac_key_not_domain(self, tmp_path: Path) -> None:
        case = fixture_store_case(tmp_path / "thmac")
        blind_id = case.store._blind_consent(
            case.authority,
            OWNER_PATH_DISCRIMINATOR,
            b"receipt",
            b"config",
        )
        assert blind_id == _expected_blind(
            bytearray(case.owner_key_provider.hmac_keys["consent_v1"]),
            "consent_v1",
            (b"receipt", b"config"),
        )
        legacy_domain_keyed = hmac.new(
            _BLIND_DOMAINS["consent_v1"],
            (7).to_bytes(4, "big") + b"receipt" + (6).to_bytes(4, "big") + b"config",
            hashlib.sha256,
        ).digest()
        assert blind_id != legacy_domain_keyed
        assert case.owner_key_provider.hmac_calls[-1][2] == "consent_v1"

    def test_shared_hmac_subkeys_reject_before_sql(self, tmp_path: Path) -> None:
        case = fixture_store_case(tmp_path / "tsharedhmac")
        case.owner_key_provider.hmac_keys["effect_v1"] = case.owner_key_provider.hmac_keys[
            "consent_v1"
        ]
        case.store._blind_effect(
            case.authority,
            OWNER_PATH_DISCRIMINATOR,
            "op",
            "job",
            "exec",
            "stage",
            "gatherer",
            "provider",
            "model",
            "route",
            b"request",
        )
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            case.store.put_fixture_consent(
                owner_path_authority=case.authority,
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                value=FixtureConsentPutV1(
                    consent_receipt_material=b"receipt",
                    consent_config_material=b"config",
                    approved_ceiling_cents=25,
                    issued_at_ms=1,
                    expires_at_ms=100,
                ),
                now_ms=2,
            )
        with sqlite3.connect(case.store.database_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM consent_claims").fetchone() == (0,)
        assert len(case.owner_key_provider.auth_calls) == 1

    def test_five_34a_and_three_deferred_34b_algorithms_use_exact_keys_and_tuples(
        self, tmp_path: Path
    ) -> None:
        case = fixture_store_case(tmp_path / "tallblind")
        expected = {
            "consent_v1": (
                case.store._blind_consent(case.authority, OWNER_PATH_DISCRIMINATOR, b"r", b"c"),
                (b"r", b"c"),
            ),
            "cursor_v1": (
                case.store._blind_cursor(case.authority, OWNER_PATH_DISCRIMINATOR, "qop", b"cur"),
                (b"qop", b"cur"),
            ),
            "account_v1": (
                case.store._blind_account(case.authority, OWNER_PATH_DISCRIMINATOR, b"acct"),
                (b"acct",),
            ),
            "project_v1": (
                case.store._blind_project(case.authority, OWNER_PATH_DISCRIMINATOR, b"proj"),
                (b"proj",),
            ),
            "request_v1": (
                case.store._blind_request(case.authority, OWNER_PATH_DISCRIMINATOR, b"req"),
                (b"req",),
            ),
            "idempotency_v1": (
                case.store._blind_idempotency(
                    case.authority, OWNER_PATH_DISCRIMINATOR, "prov", "model", "route", b"idem"
                ),
                (b"prov", b"model", b"route", b"idem"),
            ),
            "effect_v1": (
                case.store._blind_effect(
                    case.authority,
                    OWNER_PATH_DISCRIMINATOR,
                    "op",
                    "job",
                    "exec",
                    "stage",
                    "gatherer",
                    "prov",
                    "model",
                    "route",
                    b"req",
                ),
                (
                    OWNER_PATH_DISCRIMINATOR.encode("utf-8"),
                    b"op",
                    b"job",
                    b"exec",
                    b"stage",
                    b"gatherer",
                    b"prov",
                    b"model",
                    b"route",
                    b"req",
                ),
            ),
            "test_claim_v1": (
                case.store._blind_test_claim(
                    case.authority, OWNER_PATH_DISCRIMINATOR, b"r", b"c", b"effect"
                ),
                (b"r", b"c", b"effect"),
            ),
        }
        for purpose, (actual, parts) in expected.items():
            assert actual == _expected_blind(
                bytearray(case.owner_key_provider.hmac_keys[purpose]),
                purpose,
                parts,
            )
        other_owner_effect = _expected_blind(
            bytearray(case.owner_key_provider.hmac_keys["effect_v1"]),
            "effect_v1",
            (("opspd1_" + "0" * 64).encode("utf-8"), *expected["effect_v1"][1][1:]),
        )
        assert expected["effect_v1"][0] != other_owner_effect
        assert {call[2] for call in case.owner_key_provider.hmac_calls} >= set(_BLIND_DOMAINS)

    def test_all_8_purposes_have_domains(self) -> None:
        expected_purposes = {
            "consent_v1",
            "cursor_v1",
            "account_v1",
            "project_v1",
            "request_v1",
            "idempotency_v1",
            "effect_v1",
            "test_claim_v1",
        }
        assert set(_BLIND_DOMAINS.keys()) == expected_purposes
        for _purpose, domain in _BLIND_DOMAINS.items():
            assert isinstance(domain, bytes)
            assert domain.endswith(b"\x00")
            assert len(domain) > 10


# ---------------------------------------------------------------------------
# Owner operation tests
# ---------------------------------------------------------------------------


class TestProductionWritersDeferred:
    """Epoch-zero stores expose only quarantined root-ceremony authority."""

    def test_production_writers_are_bound_and_fail_closed(self, tmp_path: Path) -> None:
        case = fixture_store_case(tmp_path / "deferred-writers")
        assert type(case.store) is PrivatePaidLaneEligibilityCheckpointStoreV1
        calls = (
            lambda: case.store.put_fixture_owner_operation(
                owner_path_authority=case.authority,
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                value=FixtureOwnerOperationPutV1(
                    operation_id="op",
                    job_id="job",
                    execution_id="exec",
                    stage_id="stage",
                    state="queued",
                ),
                now_ms=1,
            ),
            lambda: case.store.seal_frozen_fixture_corpus(None, None, None, 1),  # type: ignore[arg-type]
            lambda: case.store.copy_sealed_fixture_corpus(None, None, 1),  # type: ignore[arg-type]
            lambda: case.store.abort_uncut_checkpoint_root(None, None, None, 1),  # type: ignore[arg-type]
            lambda: case.store.recover_and_abort_uncut_checkpoint_root_after_restart(),
            lambda: case.store.commit_fixture_cutover(),
            lambda: case.store.resume_fixture_cutover_forward_only(),
        )
        for call in calls:
            with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
                call()

    def test_create_empty_checkpoint_root_issues_one_process_handle(self, tmp_path: Path) -> None:
        case = fixture_store_case(tmp_path / "create-root-handle")
        handle = case.store.create_empty_checkpoint_root(now_ms=7)
        assert type(handle) is checkpoint_module.QuarantinedPrecutoverHandleV1
        assert handle.store_id == case.store.store_id
        assert handle.created_at_ms == 7
        assert handle._process_id == os.getpid()
        assert handle._boot_nonce == case.store._boot_nonce
        assert handle._consumed is False
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            case.store.create_empty_checkpoint_root(now_ms=8)
        with pytest.raises(TypeError):
            copy.copy(handle)
        with pytest.raises(TypeError):
            pickle.dumps(handle)

    def test_unbound_public_apis_reject_fabricated_receiver(self) -> None:
        class FabricatedReceiver:
            pass

        fabricated = FabricatedReceiver()
        fabricated_any: Any = fabricated
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            PrivatePaidLaneEligibilityCheckpointStoreV1.create_empty_checkpoint_root(
                fabricated_any,
                now_ms=1,
            )
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            PrivatePaidLaneEligibilityCheckpointStoreV1.put_fixture_owner_operation(
                fabricated_any,
                owner_path_authority=object(),
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                value=FixtureOwnerOperationPutV1(
                    operation_id="op",
                    job_id="job",
                    execution_id="exec",
                    stage_id="stage",
                    state="queued",
                ),
                now_ms=1,
            )

    def test_object_new_receiver_is_not_validated(self) -> None:
        fabricated = object.__new__(PrivatePaidLaneEligibilityCheckpointStoreV1)
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            fabricated.create_empty_checkpoint_root(now_ms=1)

    def test_public_dispatch_has_no_original_callable_escape(self) -> None:
        public_instance_apis = (
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
        for name in public_instance_apis:
            method = getattr(PrivatePaidLaneEligibilityCheckpointStoreV1, name)
            assert not hasattr(method, "__wrapped__")
            assert method.__closure__ is None
            assert method.__name__ == name
            function = PrivatePaidLaneEligibilityCheckpointStoreV1.__dict__[name]
            definition = ast.parse(textwrap.dedent(inspect.getsource(function))).body[0]
            assert isinstance(definition, ast.FunctionDef)
            body = definition.body
            first = body[0]
            assert isinstance(first, ast.Expr)
            assert isinstance(first.value, ast.Call)
            assert isinstance(first.value.func, ast.Attribute)
            assert first.value.func.attr == "_validate_exact_open_instance"
        open_method: Any = PrivatePaidLaneEligibilityCheckpointStoreV1.open
        open_function = open_method.__func__
        assert not hasattr(open_function, "__wrapped__")
        assert open_function.__closure__ is None

    def test_34e_authority_lifecycle_stays_syntactically_fail_closed(self) -> None:
        deferred = (
            "seal_frozen_fixture_corpus",
            "copy_sealed_fixture_corpus",
            "abort_uncut_checkpoint_root",
            "recover_and_abort_uncut_checkpoint_root_after_restart",
            "commit_fixture_cutover",
            "resume_fixture_cutover_forward_only",
        )
        for name in deferred:
            function = PrivatePaidLaneEligibilityCheckpointStoreV1.__dict__[name]
            definition = ast.parse(textwrap.dedent(inspect.getsource(function))).body[0]
            assert isinstance(definition, ast.FunctionDef)
            assert len(definition.body) in (2, 3)
            assert isinstance(definition.body[0], ast.Expr)
            terminal = definition.body[-1]
            assert isinstance(terminal, ast.Raise)
            assert isinstance(terminal.exc, ast.Call)
            assert isinstance(terminal.exc.func, ast.Name)
            assert terminal.exc.func.id == "PrivatePaidLaneEligibilityCheckpointRejected"
            assert not any(
                isinstance(node, (ast.With, ast.Try, ast.Return)) for node in ast.walk(definition)
            )

    def test_module_exposes_no_issuance_capability_and_mutation_cannot_authorize(self) -> None:
        assert not any(
            isinstance(value, weakref.WeakSet) for value in checkpoint_module.__dict__.values()
        )
        assert "_VALIDATED_OPEN_STORES" not in checkpoint_module.__dict__
        assert "_issue_exact_store_from_open" not in checkpoint_module.__dict__
        assert "_exact_store_api" not in checkpoint_module.__dict__

        fabricated = object.__new__(PrivatePaidLaneEligibilityCheckpointStoreV1)
        checkpoint_module.__dict__["_VALIDATED_OPEN_STORES"] = {fabricated}
        checkpoint_module.__dict__["_issue_exact_store_from_open"] = lambda value: value
        try:
            with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
                fabricated.create_empty_checkpoint_root(now_ms=1)
        finally:
            del checkpoint_module.__dict__["_VALIDATED_OPEN_STORES"]
            del checkpoint_module.__dict__["_issue_exact_store_from_open"]

    def test_shallow_copy_and_slot_clone_cannot_authorize(self, tmp_path: Path) -> None:
        case = fixture_store_case(tmp_path / "copy-forgery")
        with pytest.raises(TypeError):
            copy.copy(case.store)
        with pytest.raises(TypeError):
            copy.deepcopy(case.store)

        forged = object.__new__(PrivatePaidLaneEligibilityCheckpointStoreV1)
        for slot in PrivatePaidLaneEligibilityCheckpointStoreV1.__slots__:
            if slot != "__weakref__":
                object.__setattr__(forged, slot, object.__getattribute__(case.store, slot))
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            forged.create_empty_checkpoint_root(now_ms=1)

    def test_support_contains_no_writer_delegate_or_production_stamp(self) -> None:
        support_path = Path(support_checkpoint.__file__)
        source = support_path.read_text(encoding="utf-8")
        assert not hasattr(support_checkpoint, "QuarantinedFixtureWriterCompositionV1")
        assert "PrivatePaidLaneEligibilityCheckpointStoreV1.put_fixture_" not in source
        assert "support_composition_identity" not in source


class TestMigrationPrerequisites:
    def test_cutover_marker_requires_explicit_correct_verification_key(self) -> None:
        private_key = Ed25519PrivateKey.from_private_bytes(b"m" * 32)
        material = {
            "schema_version": 1,
            "target_store_id": STORE_ID,
            "prior_migration_epoch": 0,
            "migration_epoch": 1,
            "freeze_nonce": "11" * 32,
            "source_manifest_sha256": "22" * 32,
            "copy_audit_sha256": "33" * 32,
            "semantic_source_sha256": "44" * 32,
            "contract_sha256": "55" * 32,
            "sealed_at_ms": 10,
            "marker_committed_at_ms": 11,
            "key_id": "cutover-key",
            "issuer_role": "private_paid_cutover_fixture_issuer",
            "purpose": "private_paid_cutover_fixture_v1",
            "scheme": "ed25519",
        }
        marker_sha256 = hashlib.sha256(
            checkpoint_module._CUTOVER_MARKER_DOMAIN + _canonical_json(material)
        ).hexdigest()
        marker = checkpoint_module.SignedCutoverMarkerV1.model_validate(
            {
                **material,
                "marker_sha256": marker_sha256,
                "signature_ed25519": private_key.sign(
                    checkpoint_module._CUTOVER_MARKER_SIGNATURE_DOMAIN
                    + bytes.fromhex(marker_sha256)
                ),
            }
        )
        key = checkpoint_module.VerificationKeyV1(
            key_id="cutover-key", public_key_bytes=private_key.public_key().public_bytes_raw()
        )
        checkpoint_module._verify_signed_cutover_marker(marker, (key,))
        wrong = checkpoint_module.VerificationKeyV1(
            key_id="cutover-key",
            public_key_bytes=Ed25519PrivateKey.from_private_bytes(b"w" * 32)
            .public_key()
            .public_bytes_raw(),
        )
        with pytest.raises(InvalidSignature):
            checkpoint_module._verify_signed_cutover_marker(marker, (wrong,))

    def test_critic_false_accepts_reject(self) -> None:
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            checkpoint_module.QuarantinedPrecutoverHandleV1(store_id="", created_at_ms=-1)
        with pytest.raises(ValueError):
            MigrationSourceStoreV1(
                store_kind="",
                store_id="",
                schema_sha256="x",
                native_writer_barrier_id="",
                final_version=0,
                row_count=0,
                ordered_rows_sha256="y",
            )
        with pytest.raises(ValueError):
            checkpoint_module.SignedCutoverMarkerV1(
                target_store_id="",
                freeze_nonce="",
                source_manifest_sha256="x",
                copy_audit_sha256="x",
                semantic_source_sha256="x",
                contract_sha256="x",
                sealed_at_ms=10,
                marker_committed_at_ms=1,
                key_id="",
                marker_sha256="x",
                signature_ed25519=b"",
            )
        pin_material = {
            "schema_version": 1,
            "pin_store_id": "",
            "target_store_id": "",
            "migration_epoch": 1,
            "cutover_marker_sha256": "11" * 32,
            "source_manifest_sha256": "22" * 32,
            "copy_audit_sha256": "33" * 32,
            "semantic_source_sha256": "44" * 32,
            "contract_sha256": "55" * 32,
            "installed_at_ms": 1,
        }
        with pytest.raises(ValueError):
            QuarantinedSyntheticExternalPinRecordV1.model_validate(
                {
                    **pin_material,
                    "pin_sha256": hashlib.sha256(
                        _EXTERNAL_PIN_DOMAIN + _canonical_json(pin_material)
                    ).hexdigest(),
                }
            )

    def test_contract_states_reflection_is_not_security_boundary(self) -> None:
        policy = checkpoint_module.CONSTRUCTION_POLICY_V1
        assert policy["same_process_reflection_is_security_boundary"] is False
        assert policy["stronger_same_process_boundary_requirement"] == "native-or-external"

    def test_closed_corpus_model_has_exact_top_level_fields(self) -> None:
        assert tuple(FrozenPaidLaneMigrationCorpusV1.model_fields) == (
            "schema_version",
            "target_migration_epoch",
            "freeze_nonce",
            "quiesced_at_ms",
            "drained_at_ms",
            "sealed_at_ms",
            "source_stores",
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
            "source_manifest_sha256",
        )
        draft = FrozenPaidLaneMigrationCorpusV1.model_construct(
            freeze_nonce="33" * 32,
            quiesced_at_ms=1,
            drained_at_ms=2,
            sealed_at_ms=3,
            source_stores=_empty_migration_source_stores(),
            source_manifest_sha256="0" * 64,
        )
        corpus = FrozenPaidLaneMigrationCorpusV1.model_validate(
            {
                **draft.model_dump(mode="python"),
                "source_manifest_sha256": checkpoint_module._migration_source_manifest_sha256(
                    draft
                ),
            }
        )
        assert corpus.target_migration_epoch == 1
        with pytest.raises(ValueError):
            FrozenPaidLaneMigrationCorpusV1.model_validate(
                {**corpus.model_dump(mode="python"), "drained_at_ms": 0}
            )
        with pytest.raises(ValueError):
            FrozenPaidLaneMigrationCorpusV1.model_validate(
                {**corpus.model_dump(mode="python"), "source_manifest_sha256": "ff" * 32}
            )

    def test_encrypted_migration_row_rejects_framing_mismatch(self) -> None:
        with pytest.raises(ValueError):
            checkpoint_module.EncryptedSourceBundleMigrationRowV1(
                opaque_source_bundle_id="opsbs1_" + "11" * 32,
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                key_version=SOURCE_KEY_VERSION,
                nonce=b"short",
                aad_json=b"{}",
                ciphertext_schema="owner_private_encrypted_source_bundle_v1_json",
                ciphertext_type="application/json",
                ciphertext_length=16,
                ciphertext=b"x" * 16,
            )

    def test_migration_binary_encoding_and_exact_source_aad(self) -> None:
        assert checkpoint_module._bounded_migration_bytes(b"\x80\xff", bound=20) == (
            b'["blob","80ff"]'
        )
        with pytest.raises(ValueError):
            checkpoint_module._bounded_migration_bytes(b"\x80\xff", bound=14)
        bundle_id = "opsbs1_" + "11" * 32
        aad = _canonical_json(
            {
                "aead_suite": "aes-256-gcm",
                "categorical_state": "sealed",
                "ciphertext_length": 16,
                "ciphertext_schema": "owner_private_encrypted_source_bundle_v1_json",
                "ciphertext_type": "application/json",
                "key_version": SOURCE_KEY_VERSION,
                "nonce_length": 12,
                "opaque_source_bundle_id": bundle_id,
                "owner_path_discriminator": OWNER_PATH_DISCRIMINATOR,
                "row_revision": 1,
                "schema_version": 1,
            }
        )
        row = checkpoint_module.EncryptedSourceBundleMigrationRowV1(
            opaque_source_bundle_id=bundle_id,
            owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
            key_version=SOURCE_KEY_VERSION,
            nonce=b"\x80" * 12,
            aad_json=aad,
            ciphertext_schema="owner_private_encrypted_source_bundle_v1_json",
            ciphertext_type="application/json",
            ciphertext_length=16,
            ciphertext=b"\xff" * 16,
        )
        assert row.ciphertext == b"\xff" * 16
        with pytest.raises(ValueError):
            row.model_copy(update={"aad_json": b"{}"}).__class__.model_validate(
                {**row.model_dump(mode="python"), "aad_json": b"{}"}
            )

    def test_migration_limit_oracles_cover_n_minus_one_n_n_plus_one(self) -> None:
        for length in (
            checkpoint_module.MAX_CORPUS_BYTES - 1,
            checkpoint_module.MAX_CORPUS_BYTES,
        ):
            checkpoint_module._require_migration_byte_length(length)
        with pytest.raises(ValueError, match="migration corpus byte bound"):
            checkpoint_module._require_migration_byte_length(checkpoint_module.MAX_CORPUS_BYTES + 1)
        for count in (
            checkpoint_module.MAX_MIGRATION_ROWS - 1,
            checkpoint_module.MAX_MIGRATION_ROWS,
        ):
            checkpoint_module._require_migration_collection_count(count)
        with pytest.raises(ValueError, match="migration collection row bound"):
            checkpoint_module._require_migration_collection_count(
                checkpoint_module.MAX_MIGRATION_ROWS + 1
            )

    def test_migration_target_row_predicates_are_exact(self) -> None:
        with pytest.raises(ValueError):
            checkpoint_module.OwnerOperationMigrationRowV1(
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                operation_id="operation-1",
                job_id="job-1",
                execution_id="execution-1",
                stage_id="stage-1",
                state="terminal",
                state_version=1,
                cancel_requested=1,
                cancellation_version=1,
                created_at_ms=1,
                updated_at_ms=2,
            )
        with pytest.raises(ValueError):
            checkpoint_module.OwnerOperationMigrationRowV1(
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                operation_id="operation-1",
                job_id="job-1",
                execution_id="execution-1",
                stage_id="stage-1",
                state="cancelled",
                state_version=1,
                cancel_requested=0,
                cancellation_version=0,
                created_at_ms=1,
                updated_at_ms=2,
            )
        with pytest.raises(ValueError):
            checkpoint_module.ConsentClaimMigrationRowV1(
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                consent_blind_id=b"c" * 32,
                approved_ceiling_cents=0,
                version=1,
                issued_at_ms=1,
                expires_at_ms=2,
                state="open",
                updated_at_ms=1,
            )
        with pytest.raises(ValueError):
            checkpoint_module.QueueLeaseMigrationRowV1(
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                queue_operation_id="queue-1",
                lease_owner="owner-1",
                generation=1,
                cursor_blind_id=b"q" * 32,
                row_version=1,
                acquired_at_ms=2,
                exclusive_until_ms=2,
                updated_at_ms=2,
            )
        with pytest.raises(ValueError):
            checkpoint_module.BudgetAccountMigrationRowV1(
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                account_scope_blind_id=b"a" * 32,
                project_scope_blind_id=b"p" * 32,
                approved_ceiling_cents=0,
                row_version=1,
                updated_at_ms=1,
            )

    def test_support_barrier_is_durable_one_shot_and_ordered(self, tmp_path: Path) -> None:
        root = SupportLegacyRootV1.create_new(
            root_path=tmp_path / "legacy",
            root_id="legacy-root-1",
            writer_inventory=support_checkpoint._CHILD_ROLES,
            source_store_identities=support_checkpoint._CHILD_ROLES,
            now_ms=1,
        )
        durable = json.loads(
            (root.root_path / "legacy-root-state-v1.json").read_text(encoding="utf-8")
        )
        barrier = root.acquire_writer_barrier(
            expected_root_id="legacy-root-1",
            expected_root_manifest_sha256=durable["root_manifest_sha256"],
            expected_inventory_sha256=durable["inventory_sha256"],
        )
        barrier = root.reacquire_cutover_barrier(
            expected_root_id="legacy-root-1",
            expected_root_manifest_sha256=durable["root_manifest_sha256"],
            expected_barrier_id=barrier.barrier_id,
            expected_freeze_nonce=barrier.freeze_nonce,
            expected_durable_state="quiesced",
        )
        with pytest.raises(ValueError):
            barrier.drain_terminal_only()
        barrier.deny_new_admission()
        barrier.drain_terminal_only()
        barrier.close_and_revoke_all_writers()
        barrier.checkpoint_and_plant_test_all_mutators()
        corpus = barrier.seal_and_collect()
        assert type(corpus) is checkpoint_module.FrozenPaidLaneMigrationCorpusV1
        assert corpus.freeze_nonce == barrier.freeze_nonce
        assert len(corpus.source_stores) == 3
        assert all(store.row_count == 0 for store in corpus.source_stores)
        assert all(
            getattr(corpus, name) == ()
            for name in (
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
        barrier.revalidate_sealed_sources()
        barrier.mark_legacy_read_only()
        wrong_store_abort = checkpoint_module.QuarantinedAbortUncutResultV1(
            store_id="other-store",
            aborted_at_ms=1,
        )
        with pytest.raises(ValueError, match="abort result target mismatch"):
            barrier.release_after_authenticated_abort(
                abort_result=wrong_store_abort,
                expected_target_store_id=STORE_ID,
                expected_target_database_path=tmp_path / "target.sqlite3",
            )
        with pytest.raises(TypeError):
            release_without_ready: Any = barrier.release_after_ready
            release_without_ready()
        reopened = json.loads(
            (root.root_path / "legacy-root-state-v1.json").read_text(encoding="utf-8")
        )
        assert reopened["state"] == "legacy_read_only"
        assert reopened["sealed_sources_revalidated"] is True

    def test_support_barrier_extracts_typed_genesis_from_owning_children(
        self, tmp_path: Path
    ) -> None:
        typed_rows = support_checkpoint.fixture_genesis_migration_rows()
        root = SupportLegacyRootV1.create_new(
            root_path=tmp_path / "legacy-typed-genesis",
            root_id="legacy-typed-genesis",
            writer_inventory=support_checkpoint._CHILD_ROLES,
            source_store_identities=support_checkpoint._CHILD_ROLES,
            now_ms=1,
            typed_rows=typed_rows,
        )
        durable = json.loads(
            (root.root_path / "legacy-root-state-v1.json").read_text(encoding="utf-8")
        )
        barrier = root.acquire_writer_barrier(
            expected_root_id="legacy-typed-genesis",
            expected_root_manifest_sha256=durable["root_manifest_sha256"],
            expected_inventory_sha256=durable["inventory_sha256"],
        )
        barrier.deny_new_admission()
        barrier.drain_terminal_only()
        barrier.close_and_revoke_all_writers()
        barrier.checkpoint_and_plant_test_all_mutators()
        corpus = barrier.seal_and_collect()

        assert corpus.provider_revocation_heads == typed_rows["provider_revocation_heads"]
        assert corpus.provider_revocation_current == typed_rows["provider_revocation_current"]
        assert corpus.source_heads == typed_rows["source_heads"]
        assert corpus.source_current == typed_rows["source_current"]
        assert {row.store_kind: row.row_count for row in corpus.source_stores} == {
            "owner_private_source_v1": 2,
            "paid_lane_fixture_v1": 0,
            "provider_authority_v4": 2,
        }
        assert corpus.source_manifest_sha256 == checkpoint_module._migration_source_manifest_sha256(
            corpus
        )

    def test_typed_child_genesis_rejects_unknown_collection_and_noncanonical_rows(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="unknown typed migration collection"):
            SupportLegacyRootV1.create_new(
                root_path=tmp_path / "legacy-unknown-typed",
                root_id="legacy-unknown-typed",
                writer_inventory=support_checkpoint._CHILD_ROLES,
                source_store_identities=support_checkpoint._CHILD_ROLES,
                now_ms=1,
                typed_rows={"not_a_collection": ()},
            )
        rows = support_checkpoint.fixture_genesis_migration_rows()
        duplicate = rows["source_heads"] * 2
        with pytest.raises(ValueError, match="typed migration rows not canonical"):
            SupportLegacyRootV1.create_new(
                root_path=tmp_path / "legacy-duplicate-typed",
                root_id="legacy-duplicate-typed",
                writer_inventory=support_checkpoint._CHILD_ROLES,
                source_store_identities=support_checkpoint._CHILD_ROLES,
                now_ms=1,
                typed_rows={**rows, "source_heads": duplicate},
            )

    def test_seal_rejects_nonempty_zero_only_paid_admission_history(self, tmp_path: Path) -> None:
        root = SupportLegacyRootV1.create_new(
            root_path=tmp_path / "legacy-live-admission",
            root_id="legacy-live-admission",
            writer_inventory=support_checkpoint._CHILD_ROLES,
            source_store_identities=support_checkpoint._CHILD_ROLES,
            now_ms=1,
            typed_rows=support_checkpoint.fixture_genesis_migration_rows(),
        )
        paid_child = root.root_path / "children" / "paid-lane-fixture-v1.sqlite3"
        with sqlite3.connect(paid_child) as connection:
            connection.execute(
                "INSERT INTO paid_admissions(id,payload) VALUES(?,?)",
                ("existing-live-admission", b"must-not-be-omitted"),
            )
        durable = json.loads(
            (root.root_path / "legacy-root-state-v1.json").read_text(encoding="utf-8")
        )
        barrier = root.acquire_writer_barrier(
            expected_root_id="legacy-live-admission",
            expected_root_manifest_sha256=durable["root_manifest_sha256"],
            expected_inventory_sha256=durable["inventory_sha256"],
        )
        barrier.deny_new_admission()
        with pytest.raises(ValueError, match="child work not drained"):
            barrier.drain_terminal_only()

    def test_barrier_rejects_rewritten_state_and_post_seal_child_mutation(
        self, tmp_path: Path
    ) -> None:
        root = SupportLegacyRootV1.create_new(
            root_path=tmp_path / "legacy-corrupt",
            root_id="legacy-corrupt",
            writer_inventory=support_checkpoint._CHILD_ROLES,
            source_store_identities=support_checkpoint._CHILD_ROLES,
            now_ms=1,
        )
        state_path = root.root_path / "legacy-root-state-v1.json"
        durable = json.loads(state_path.read_text())
        durable["state"] = "sealed"
        state_path.write_text(json.dumps(durable))
        state_path.chmod(0o600)
        with pytest.raises(ValueError):
            SupportLegacyRootV1.open_existing(
                root_path=root.root_path,
                expected_root_id="legacy-corrupt",
                expected_root_manifest_sha256=durable["root_manifest_sha256"],
                expected_inventory_sha256=durable["inventory_sha256"],
            )

        root = SupportLegacyRootV1.create_new(
            root_path=tmp_path / "legacy-mutated",
            root_id="legacy-mutated",
            writer_inventory=support_checkpoint._CHILD_ROLES,
            source_store_identities=support_checkpoint._CHILD_ROLES,
            now_ms=1,
        )
        durable = json.loads((root.root_path / "legacy-root-state-v1.json").read_text())
        barrier = root.acquire_writer_barrier(
            expected_root_id="legacy-mutated",
            expected_root_manifest_sha256=durable["root_manifest_sha256"],
            expected_inventory_sha256=durable["inventory_sha256"],
        )
        barrier.deny_new_admission()
        barrier.drain_terminal_only()
        barrier.close_and_revoke_all_writers()
        barrier.checkpoint_and_plant_test_all_mutators()
        barrier.seal_and_collect()
        child = root.root_path / "children" / "owner-private-source-v1.sqlite3"
        connection = sqlite3.connect(child)
        connection.execute("UPDATE adapter_state SET version=version+1")
        connection.commit()
        connection.close()
        with pytest.raises(ValueError):
            barrier.revalidate_sealed_sources()

    def test_external_pin_install_once_then_ready_is_durable(self, tmp_path: Path) -> None:
        store = SupportExternalPinStoreV1.create_new(
            root_path=tmp_path / "pins", pin_store_id="pin-store-1"
        )
        pin_material = {
            "schema_version": 1,
            "pin_store_id": "pin-store-1",
            "target_store_id": STORE_ID,
            "migration_epoch": 1,
            "cutover_marker_sha256": "11" * 32,
            "source_manifest_sha256": "22" * 32,
            "copy_audit_sha256": "33" * 32,
            "semantic_source_sha256": "44" * 32,
            "contract_sha256": "55" * 32,
            "installed_at_ms": 10,
        }
        pin = QuarantinedSyntheticExternalPinRecordV1.model_validate(
            {
                **pin_material,
                "pin_sha256": hashlib.sha256(
                    _EXTERNAL_PIN_DOMAIN + _canonical_json(pin_material)
                ).hexdigest(),
            }
        )
        store.install_once(expected_absent=True, record=pin)
        with pytest.raises(ValueError):
            store.install_once(expected_absent=True, record=pin)
        ready_material = {
            "schema_version": 1,
            "pin_sha256": pin.pin_sha256,
            "legacy_root_id": "legacy-root-1",
            "legacy_read_only": True,
            "new_runtime_ready": True,
            "ready_at_ms": 11,
        }
        ready = QuarantinedSyntheticReadyRecordV1.model_validate(
            {
                **ready_material,
                "ready_sha256": hashlib.sha256(
                    _READY_DOMAIN + _canonical_json(ready_material)
                ).hexdigest(),
            }
        )
        store.mark_ready(expected_pin_sha256=pin.pin_sha256, ready_record=ready)
        reopened = SupportExternalPinStoreV1.open_existing(
            root_path=store.root_path, expected_pin_store_id="pin-store-1"
        )
        assert reopened.load() == (pin, ready)
        with pytest.raises(ValueError):
            reopened.mark_ready(expected_pin_sha256=pin.pin_sha256, ready_record=ready)
        reopened._creator_pid += 1
        with pytest.raises(ValueError):
            reopened.load()
        reopened._creator_pid = os.getpid()
        orphan = store.root_path / ".external-pin-state-v1.json.crash.tmp"
        orphan.write_bytes(b"partial")
        orphan.chmod(0o600)
        SupportExternalPinStoreV1.open_existing(
            root_path=store.root_path, expected_pin_store_id="pin-store-1"
        )
        assert not orphan.exists()
        state_path = store.root_path / "external-pin-state-v1.json"
        corrupted = json.loads(state_path.read_text(encoding="utf-8"))
        corrupted["ready"]["ready_sha256"] = "ff" * 32
        state_path.write_text(json.dumps(corrupted), encoding="utf-8")
        state_path.chmod(0o600)
        with pytest.raises(ValueError):
            SupportExternalPinStoreV1.open_existing(
                root_path=store.root_path, expected_pin_store_id="pin-store-1"
            ).load()

    def test_multiprocess_pin_cas_and_barrier_process_binding(self, tmp_path: Path) -> None:
        context = multiprocessing.get_context("spawn")
        store = SupportExternalPinStoreV1.create_new(
            root_path=tmp_path / "pins-mp", pin_store_id="pin-store-mp"
        )
        material = {
            "schema_version": 1,
            "pin_store_id": "pin-store-mp",
            "target_store_id": STORE_ID,
            "migration_epoch": 1,
            "cutover_marker_sha256": "11" * 32,
            "source_manifest_sha256": "22" * 32,
            "copy_audit_sha256": "33" * 32,
            "semantic_source_sha256": "44" * 32,
            "contract_sha256": "55" * 32,
            "installed_at_ms": 10,
        }
        record = {
            **material,
            "pin_sha256": hashlib.sha256(
                _EXTERNAL_PIN_DOMAIN + _canonical_json(material)
            ).hexdigest(),
        }
        queue = context.Queue()
        processes = [
            context.Process(target=_mp_install_pin, args=(str(store.root_path), record, queue))
            for _ in range(2)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            assert process.exitcode == 0
        assert sorted(queue.get(timeout=2) for _ in processes) == ["lost", "won"]

        root = SupportLegacyRootV1.create_new(
            root_path=tmp_path / "legacy-mp",
            root_id="legacy-mp",
            writer_inventory=support_checkpoint._CHILD_ROLES,
            source_store_identities=support_checkpoint._CHILD_ROLES,
            now_ms=1,
        )
        durable = json.loads(
            (root.root_path / "legacy-root-state-v1.json").read_text(encoding="utf-8")
        )
        barrier_processes = [
            context.Process(
                target=_mp_acquire_barrier,
                args=(
                    str(root.root_path),
                    durable["root_manifest_sha256"],
                    durable["inventory_sha256"],
                    queue,
                ),
            )
            for _ in range(2)
        ]
        for process in barrier_processes:
            process.start()
        for process in barrier_processes:
            process.join(10)
            assert process.exitcode == 0
        outcomes = [queue.get(timeout=2) for _ in barrier_processes]
        assert sorted(outcome[0] for outcome in outcomes) == ["lost", "won"]
        winner = next(outcome for outcome in outcomes if outcome[0] == "won")
        barrier = root.reacquire_cutover_barrier(
            expected_root_id="legacy-mp",
            expected_root_manifest_sha256=durable["root_manifest_sha256"],
            expected_barrier_id=winner[1],
            expected_freeze_nonce=winner[2],
            expected_durable_state="quiesced",
        )
        child = context.Process(target=_mp_use_barrier, args=(barrier, queue))
        with pytest.raises(TypeError):
            child.start()

    def test_barrier_lock_timeout_uses_monotonic_deadline(self, tmp_path: Path) -> None:
        context = multiprocessing.get_context("spawn")
        root = SupportLegacyRootV1.create_new(
            root_path=tmp_path / "legacy-timeout",
            root_id="legacy-timeout",
            writer_inventory=support_checkpoint._CHILD_ROLES,
            source_store_identities=support_checkpoint._CHILD_ROLES,
            now_ms=1,
        )
        durable = json.loads(
            (root.root_path / "legacy-root-state-v1.json").read_text(encoding="utf-8")
        )
        ready = context.Event()
        release = context.Event()
        holder = context.Process(target=_mp_hold_lock, args=(str(root.root_path), ready, release))
        holder.start()
        assert ready.wait(5)
        with pytest.raises(TimeoutError):
            root.acquire_writer_barrier(
                expected_root_id="legacy-timeout",
                expected_root_manifest_sha256=durable["root_manifest_sha256"],
                expected_inventory_sha256=durable["inventory_sha256"],
                timeout_ms=20,
            )
        release.set()
        holder.join(10)
        assert holder.exitcode == 0

    def test_authenticated_abort_from_quiesced_reopens_as_released(self, tmp_path: Path) -> None:
        root = SupportLegacyRootV1.create_new(
            root_path=tmp_path / "legacy-abort",
            root_id="legacy-abort",
            writer_inventory=support_checkpoint._CHILD_ROLES,
            source_store_identities=support_checkpoint._CHILD_ROLES,
            now_ms=1,
        )
        state_path = root.root_path / "legacy-root-state-v1.json"
        durable = json.loads(state_path.read_text())
        barrier = root.acquire_writer_barrier(
            expected_root_id="legacy-abort",
            expected_root_manifest_sha256=durable["root_manifest_sha256"],
            expected_inventory_sha256=durable["inventory_sha256"],
        )
        target_path = tmp_path / "absent-target.sqlite3"
        durable = json.loads(state_path.read_text())
        durable["authenticated_abort_completion"] = {
            "root_id": barrier.root_id,
            "root_manifest_sha256": barrier.root_manifest_sha256,
            "barrier_id": barrier.barrier_id,
            "freeze_nonce": barrier.freeze_nonce,
            "target_store_id": STORE_ID,
            "target_database_path": os.fspath(target_path),
            "target_absent": True,
            "sidecars_absent": True,
            "parent_fsynced": True,
            "sources_unchanged": True,
        }
        support_checkpoint._durable_write_json(state_path, durable)
        barrier.release_after_authenticated_abort(
            abort_result=checkpoint_module.QuarantinedAbortUncutResultV1(
                store_id=STORE_ID,
                aborted_at_ms=2,
            ),
            expected_target_store_id=STORE_ID,
            expected_target_database_path=target_path,
        )
        reopened = SupportLegacyRootV1.open_existing(
            root_path=root.root_path,
            expected_root_id="legacy-abort",
            expected_root_manifest_sha256=durable["root_manifest_sha256"],
            expected_inventory_sha256=durable["inventory_sha256"],
        )
        assert reopened.root_path == root.root_path
        assert json.loads(state_path.read_text())["state"] == "released"

    def test_reopen_rejects_revocation_retained_in_wal(self, tmp_path: Path) -> None:
        root = SupportLegacyRootV1.create_new(
            root_path=tmp_path / "legacy-wal",
            root_id="legacy-wal",
            writer_inventory=support_checkpoint._CHILD_ROLES,
            source_store_identities=support_checkpoint._CHILD_ROLES,
            now_ms=1,
        )
        state_path = root.root_path / "legacy-root-state-v1.json"
        durable = json.loads(state_path.read_text())
        barrier = root.acquire_writer_barrier(
            expected_root_id="legacy-wal",
            expected_root_manifest_sha256=durable["root_manifest_sha256"],
            expected_inventory_sha256=durable["inventory_sha256"],
        )
        barrier.deny_new_admission()
        barrier.drain_terminal_only()
        child_path = root.root_path / "children" / "owner-private-source-v1.sqlite3"
        reader = sqlite3.connect(child_path)
        try:
            reader.execute("BEGIN")
            reader.execute("SELECT * FROM adapter_state").fetchall()
            barrier.close_and_revoke_all_writers()
            assert Path(str(child_path) + "-wal").exists()
            with pytest.raises(ValueError, match="child adapter sidecar remains"):
                SupportLegacyRootV1.open_existing(
                    root_path=root.root_path,
                    expected_root_id="legacy-wal",
                    expected_root_manifest_sha256=durable["root_manifest_sha256"],
                    expected_inventory_sha256=durable["inventory_sha256"],
                )
        finally:
            reader.close()


# ---------------------------------------------------------------------------
# Rejection exception tests
# ---------------------------------------------------------------------------


class TestRejection:
    def test_exception_message(self) -> None:
        exc = PrivatePaidLaneEligibilityCheckpointRejected()
        assert "rejected" in str(exc)

    def test_exception_repr(self) -> None:
        exc = PrivatePaidLaneEligibilityCheckpointRejected()
        assert "PrivatePaidLaneEligibilityCheckpointRejected" in repr(exc)

    def test_exception_is_value_error(self) -> None:
        assert issubclass(PrivatePaidLaneEligibilityCheckpointRejected, ValueError)


# ---------------------------------------------------------------------------
# DB/WAL leakage tests
# ---------------------------------------------------------------------------


class TestNoPlaintextLeakage:
    def test_db_no_plaintext_canary(self, tmp_path: Path) -> None:
        """Verify no raw secret material appears in DB pages."""
        case = fixture_store_case(tmp_path / "tleak")
        with pytest.raises(PrivatePaidLaneEligibilityCheckpointRejected):
            case.store.put_fixture_owner_operation(
                owner_path_authority=case.authority,
                owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
                value=FixtureOwnerOperationPutV1(
                    operation_id="op:1",
                    job_id="job:1",
                    execution_id="exec:1",
                    stage_id="stage:1",
                    state="queued",
                ),
                now_ms=1_000,
            )
        # Read raw DB bytes
        db_bytes = case.store.database_path.read_bytes()
        source_key = case.source_key_provider.keys[(OWNER_PATH_DISCRIMINATOR, SOURCE_KEY_VERSION)]
        assert source_key not in db_bytes
        # Verify no raw plaintext request material
        assert b"request-plaintext-canary" not in db_bytes
