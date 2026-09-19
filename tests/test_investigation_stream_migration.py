from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import substrate.investigation_stream_migration as migration_operations
from substrate.event_log import (
    append_event_once_authorized,
    prepare_typed_event,
    seal_investigation_authorized,
    trajectory_authorized,
)
from substrate.investigation_stream_migration import (
    MigrationLimits,
    migrate_legacy_to_composite,
    resume_composite_to_legacy,
    resume_legacy_to_composite,
    rollback_composite_to_legacy,
)
from substrate.investigation_streams import (
    StreamStorageState,
    initialize_composite_stream,
    list_operator_investigation_authorities,
    resolve_investigation_stream,
)
from substrate.investigation_tenancy import (
    InvestigationAuthority,
    InvestigationOwnershipConflict,
    bind_legacy_stream_lease,
    legacy_lease_storage_state,
)
from substrate.schemas.events import DispatchCallPayload


def _event(investigation_id: str, event_id: str, prompt_hash: str):
    return prepare_typed_event(
        investigation_id,
        DispatchCallPayload(
            provider="provider",
            model="model",
            tier="flash",
            target_role="researcher",
            input_tokens=10,
            output_tokens=20,
            cost_usd=0.01,
            latency_ms=100,
            prompt_hash=prompt_hash,
        ),
        event_id=event_id,
    )


def _legacy_authority(tmp_path, investigation_id: str = "private-display"):
    authority = InvestigationAuthority("alice", investigation_id, root=tmp_path)
    bind_legacy_stream_lease(authority)
    return authority


def test_forward_jsonl_migration_flips_last_and_receipt_is_redacted(tmp_path):
    authority = _legacy_authority(tmp_path)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-1", "secret"))
    checkpoints: list[str] = []

    receipt = migrate_legacy_to_composite(authority, checkpoint=checkpoints.append)

    assert checkpoints.index("metadata_published") < checkpoints.index("lease_flipped")
    assert checkpoints.index("lease_flipped") < checkpoints.index("legacy_archived")
    assert legacy_lease_storage_state(authority) == "composite"
    resolved = resolve_investigation_stream(authority)
    assert resolved.state is StreamStorageState.COMPOSITE
    assert [row["event_id"] for row in trajectory_authorized(authority)] == ["evt-1"]
    encoded = json.dumps(receipt.as_dict(), sort_keys=True)
    assert authority.investigation_id not in encoded
    assert authority.account_id not in encoded
    assert "secret" not in encoded
    assert receipt.row_count == 1
    assert len(receipt.source_digest) == len(receipt.stream_digest) == 64


def test_forward_preserves_sealed_prefix_and_later_live_tail(tmp_path):
    authority = _legacy_authority(tmp_path)
    append_event_once_authorized(
        authority, _event(authority.investigation_id, "evt-prefix", "prefix")
    )
    sealed = seal_investigation_authorized(authority)
    assert sealed is not None
    append_event_once_authorized(
        authority, _event(authority.investigation_id, "evt-tail", "tail")
    )

    receipt = migrate_legacy_to_composite(authority)

    assert receipt.row_count == 2
    resolved = resolve_investigation_stream(authority)
    assert [
        row["event_id"]
        for row in migration_operations._parse_parquet(
            authority, resolved.parquet_path.read_bytes()
        )
    ] == ["evt-prefix"]
    assert [
        json.loads(line)["event_id"]
        for line in resolved.jsonl_path.read_text(encoding="utf-8").splitlines()
    ] == ["evt-tail"]


def test_malformed_source_is_rejected_before_authority_flip(tmp_path):
    authority = _legacy_authority(tmp_path)
    legacy = tmp_path / f"{authority.investigation_id}.jsonl"
    legacy.write_text("{\n", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed JSON"):
        migrate_legacy_to_composite(authority)

    assert legacy_lease_storage_state(authority) == "legacy"
    with pytest.raises(InvestigationOwnershipConflict, match="operator recovery"):
        resolve_investigation_stream(authority)


def test_conflicting_event_id_is_rejected_before_authority_flip(tmp_path):
    authority = _legacy_authority(tmp_path)
    first = _event(authority.investigation_id, "evt-collision", "first")
    second = _event(authority.investigation_id, "evt-collision", "second")
    legacy = tmp_path / f"{authority.investigation_id}.jsonl"
    legacy.write_text(
        json.dumps(first.model_dump(mode="json"))
        + "\n"
        + json.dumps(second.model_dump(mode="json"))
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="event id collision"):
        migrate_legacy_to_composite(authority)

    assert legacy_lease_storage_state(authority) == "legacy"


def test_partial_composite_metadata_is_inert_until_lease_flip_and_resumable(tmp_path):
    authority = _legacy_authority(tmp_path)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-1", "one"))

    def crash_after_metadata(name: str) -> None:
        if name == "metadata_published":
            raise RuntimeError("injected crash")

    with pytest.raises(RuntimeError, match="injected crash"):
        migrate_legacy_to_composite(authority, checkpoint=crash_after_metadata)

    assert legacy_lease_storage_state(authority) == "legacy"
    with pytest.raises(InvestigationOwnershipConflict, match="operator recovery"):
        resolve_investigation_stream(authority)

    receipt = migrate_legacy_to_composite(authority)
    assert receipt.disposition == "migrated"
    assert resolve_investigation_stream(authority).state is StreamStorageState.COMPOSITE


def test_rollback_refreshes_legacy_with_post_cutover_events_before_flip(tmp_path):
    authority = _legacy_authority(tmp_path)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-before", "before"))
    migrate_legacy_to_composite(authority)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-after", "after"))
    (tmp_path / f"{authority.investigation_id}.jsonl").write_text(
        json.dumps(_event(authority.investigation_id, "evt-stale", "stale").model_dump(mode="json"))
        + "\n",
        encoding="utf-8",
    )
    checkpoints: list[str] = []

    receipt = rollback_composite_to_legacy(authority, checkpoint=checkpoints.append)

    assert checkpoints[-2:] == ["rollback_data_verified", "rollback_lease_flipped"]
    assert receipt.disposition == "rolled_back"
    assert legacy_lease_storage_state(authority) == "legacy"
    assert resolve_investigation_stream(authority).state is StreamStorageState.LEGACY
    assert [row["event_id"] for row in trajectory_authorized(authority)] == [
        "evt-before",
        "evt-after",
    ]
    rollback_journal = next(
        (tmp_path / ".tenancy" / "stream-migrations").glob("*.rollback.json")
    )
    assert json.loads(rollback_journal.read_text(encoding="utf-8"))["phase"] == "complete"


def test_forward_limits_fail_before_flip(tmp_path):
    authority = _legacy_authority(tmp_path)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-1", "one"))
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-2", "two"))

    with pytest.raises(ValueError, match="row limit"):
        migrate_legacy_to_composite(
            authority,
            limits=MigrationLimits(
                max_rows=1,
                max_file_bytes=1024 * 1024,
                max_total_bytes=1024 * 1024,
            ),
        )

    assert legacy_lease_storage_state(authority) == "legacy"


def test_forward_resume_after_flip_never_reads_legacy(tmp_path):
    authority = _legacy_authority(tmp_path)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-1", "one"))

    def crash_after_flip(name: str) -> None:
        if name == "lease_flipped":
            raise RuntimeError("injected post-flip crash")

    with pytest.raises(RuntimeError, match="post-flip crash"):
        migrate_legacy_to_composite(authority, checkpoint=crash_after_flip)
    assert legacy_lease_storage_state(authority) == "composite"
    (tmp_path / f"{authority.investigation_id}.jsonl").write_text(
        "not-json\n", encoding="utf-8"
    )

    receipt = resume_legacy_to_composite(authority)

    assert receipt.disposition == "resumed_after_flip"
    assert receipt.row_count == 1
    assert [row["event_id"] for row in trajectory_authorized(authority)] == ["evt-1"]


def test_rollback_resume_after_flip_verifies_refreshed_legacy(tmp_path):
    authority = _legacy_authority(tmp_path)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-1", "one"))
    migrate_legacy_to_composite(authority)

    def crash_after_flip(name: str) -> None:
        if name == "rollback_lease_flipped":
            raise RuntimeError("injected rollback post-flip crash")

    with pytest.raises(RuntimeError, match="rollback post-flip crash"):
        rollback_composite_to_legacy(authority, checkpoint=crash_after_flip)
    assert legacy_lease_storage_state(authority) == "legacy"

    receipt = resume_composite_to_legacy(authority)

    assert receipt.disposition == "resumed_after_flip"
    assert [row["event_id"] for row in trajectory_authorized(authority)] == ["evt-1"]


def test_migration_journals_are_redacted_and_quarantine_uses_reason_code(tmp_path):
    authority = _legacy_authority(tmp_path)
    private_payload = "payload-that-must-not-appear"
    append_event_once_authorized(
        authority,
        _event(authority.investigation_id, "evt-private", private_payload),
    )
    migrate_legacy_to_composite(authority)

    journals = list((tmp_path / ".tenancy" / "stream-migrations").glob("*.json"))
    assert len(journals) == 1
    encoded = journals[0].read_text(encoding="utf-8")
    assert authority.account_id not in encoded
    assert authority.investigation_id not in encoded
    assert private_payload not in encoded
    record = json.loads(encoded)
    assert record["phase"] == "complete"
    assert record["content_digest"]


def test_foreign_migration_authority_fails_before_any_mutation(tmp_path):
    owner = _legacy_authority(tmp_path)
    append_event_once_authorized(owner, _event(owner.investigation_id, "evt-1", "one"))
    foreign = InvestigationAuthority("bob", owner.investigation_id, root=tmp_path)
    before = {
        path.relative_to(tmp_path): (
            path.read_bytes() if path.is_file() and not path.is_symlink() else None
        )
        for path in tmp_path.rglob("*")
    }

    with pytest.raises(InvestigationOwnershipConflict):
        migrate_legacy_to_composite(foreign)

    after = {
        path.relative_to(tmp_path): (
            path.read_bytes() if path.is_file() and not path.is_symlink() else None
        )
        for path in tmp_path.rglob("*")
    }
    assert after == before


def test_global_enumeration_accepts_only_verified_inert_legacy_backup(tmp_path):
    authority = _legacy_authority(tmp_path)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-1", "one"))
    migrate_legacy_to_composite(authority)
    operator = InvestigationAuthority("__operator__", "__global__", root=tmp_path)

    assert [
        (item.account_id, item.investigation_id)
        for item in list_operator_investigation_authorities(operator)
    ] == [("alice", authority.investigation_id)]

    rollback_composite_to_legacy(authority)
    with pytest.raises(InvestigationOwnershipConflict, match="legacy migration"):
        list_operator_investigation_authorities(operator)


def test_migrated_historic_display_id_no_longer_blocks_another_account(tmp_path):
    historic = _legacy_authority(tmp_path, investigation_id="shared-display")
    append_event_once_authorized(historic, _event("shared-display", "evt-historic", "old"))
    migrate_legacy_to_composite(historic)

    newcomer = InvestigationAuthority("bob", "shared-display", root=tmp_path)
    initialized = initialize_composite_stream(newcomer)
    append_event_once_authorized(newcomer, _event("shared-display", "evt-new", "new"))

    assert initialized.jsonl_path != resolve_investigation_stream(historic).jsonl_path
    assert resolve_investigation_stream(newcomer).state is StreamStorageState.COMPOSITE
    assert [row["event_id"] for row in trajectory_authorized(historic)] == [
        "evt-historic"
    ]
    assert [row["event_id"] for row in trajectory_authorized(newcomer)] == ["evt-new"]


@pytest.mark.parametrize(
    "crash_point",
    [
        "source_snapshotted",
        "parquet_temp_fsynced",
        "parquet_temp_verified",
        "parquet_published",
        "jsonl_temp_fsynced",
        "jsonl_temp_verified",
        "jsonl_published",
        "data_verified",
        "metadata_published",
    ],
)
def test_forward_preflip_crash_matrix_resumes_from_legacy(tmp_path, crash_point):
    authority = _legacy_authority(tmp_path)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-prefix", "one"))
    assert seal_investigation_authorized(authority) is not None
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-tail", "two"))

    def inject(name: str) -> None:
        if name == crash_point:
            raise RuntimeError(f"crash:{name}")

    with pytest.raises(RuntimeError, match="crash:"):
        migrate_legacy_to_composite(authority, checkpoint=inject)
    assert legacy_lease_storage_state(authority) == "legacy"
    with pytest.raises(InvestigationOwnershipConflict, match="operator recovery"):
        resolve_investigation_stream(authority)

    receipt = resume_legacy_to_composite(authority)

    assert receipt.row_count == 2
    assert resolve_investigation_stream(authority).state is StreamStorageState.COMPOSITE
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize(
    "crash_point",
    [
        "rollback_source_snapshotted",
        "rollback_parquet_temp_fsynced",
        "rollback_parquet_temp_verified",
        "rollback_parquet_published",
        "rollback_jsonl_temp_fsynced",
        "rollback_jsonl_temp_verified",
        "rollback_jsonl_published",
        "rollback_data_verified",
    ],
)
def test_rollback_preflip_crash_matrix_resumes_from_composite(tmp_path, crash_point):
    authority = _legacy_authority(tmp_path)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-prefix", "one"))
    assert seal_investigation_authorized(authority) is not None
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-tail", "two"))
    migrate_legacy_to_composite(authority)

    def inject(name: str) -> None:
        if name == crash_point:
            raise RuntimeError(f"crash:{name}")

    with pytest.raises(RuntimeError, match="crash:"):
        rollback_composite_to_legacy(authority, checkpoint=inject)
    assert legacy_lease_storage_state(authority) == "composite"
    with pytest.raises(InvestigationOwnershipConflict, match="operator recovery"):
        resolve_investigation_stream(authority)

    receipt = resume_composite_to_legacy(authority)

    assert receipt.row_count == 2
    assert resolve_investigation_stream(authority).state is StreamStorageState.LEGACY
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("operation", ["append", "seal"])
def test_migration_excludes_concurrent_runtime_io_without_deadlock(tmp_path, operation):
    authority = _legacy_authority(tmp_path)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-before", "before"))
    migration_locked = threading.Event()
    release_migration = threading.Event()
    operation_started = threading.Event()

    def checkpoint(name: str) -> None:
        if name == "source_snapshotted":
            migration_locked.set()
            assert release_migration.wait(timeout=5)

    def concurrent_operation():
        operation_started.set()
        if operation == "append":
            return append_event_once_authorized(
                authority,
                _event(authority.investigation_id, "evt-after", "after"),
            )
        return seal_investigation_authorized(authority)

    with ThreadPoolExecutor(max_workers=2) as pool:
        migration = pool.submit(
            migrate_legacy_to_composite,
            authority,
            checkpoint=checkpoint,
        )
        assert migration_locked.wait(timeout=5)
        runtime_io = pool.submit(concurrent_operation)
        assert operation_started.wait(timeout=5)
        assert not runtime_io.done()
        release_migration.set()
        assert migration.result(timeout=5).disposition == "migrated"
        runtime_io.result(timeout=5)

    event_ids = [row["event_id"] for row in trajectory_authorized(authority)]
    assert "evt-before" in event_ids
    if operation == "append":
        assert "evt-after" in event_ids


def test_forward_rollback_forward_replaces_existing_opaque_backup(tmp_path):
    authority = _legacy_authority(tmp_path)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-1", "one"))
    migrate_legacy_to_composite(authority)
    rollback_composite_to_legacy(authority)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-2", "two"))

    receipt = migrate_legacy_to_composite(authority)

    assert receipt.row_count == 2
    assert [row["event_id"] for row in trajectory_authorized(authority)] == [
        "evt-1",
        "evt-2",
    ]
    backups = list((tmp_path / ".tenancy" / "legacy-stream-backups").rglob("*.jsonl"))
    assert len(backups) == 1


def test_tampered_journal_operation_digest_denies_resolution_and_resume(tmp_path):
    authority = _legacy_authority(tmp_path)
    append_event_once_authorized(authority, _event(authority.investigation_id, "evt-1", "one"))
    migrate_legacy_to_composite(authority)
    journal = next((tmp_path / ".tenancy" / "stream-migrations").glob("*.forward.json"))
    record = json.loads(journal.read_text(encoding="utf-8"))
    record["operation_digest"] = "forged"
    journal.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(InvestigationOwnershipConflict, match="journal is invalid"):
        resolve_investigation_stream(authority)
    with pytest.raises(InvestigationOwnershipConflict, match="journal is invalid"):
        resume_legacy_to_composite(authority)
