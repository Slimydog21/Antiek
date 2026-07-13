from __future__ import annotations

import copy
import multiprocessing
import os
import pickle
import secrets
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Never

import pytest

import substrate.midnight_oil.private_source_bundle_store as bundle_store
from substrate.midnight_oil.private_source_bundle_store import (
    MAX_SOURCE_RECEIPT_PAIRS,
    OWNER_PRIVATE_SOURCE_EXACT_CURRENT_RESOLVER_CONTRACT_SHA256,
    PENDING_SELECTOR_TTL_MS,
    PRIVATE_SOURCE_BUNDLE_STORE_MODULE_SOURCE_SHA256,
    OwnerPrivateEncryptedSourceBundleStoreV1,
    OwnerPrivateSourceStoreRejected,
    PendingOpaqueSourceSelectorV1,
    private_source_bundle_store_module_source_sha256,
    require_private_source_bundle_store_module_source,
)
from substrate.midnight_oil.private_source_head_store import (
    OwnerPrivateSourceAuthorityHeadV1,
    _SourceHeadRepositoryV1,
)
from tests.support.owner_private_source_authority_v1 import encoded_private_needles
from tests.support.owner_private_source_bundle_store_v1 import (
    KEY_VERSION,
    WRONG_DATA_KEY,
    OpaqueOwnerPathAuthority,
    OwnerPrivateSourceBundleStoreCase,
    owner_private_source_bundle_store_case,
)
from tests.support.owner_private_source_head_v1 import bundle_revision, successor

NOW_MS = 2_002
ROOT = Path(__file__).resolve().parents[1]


def test_bundle_store_module_semantic_source_identity_is_pinned() -> None:
    assert (
        private_source_bundle_store_module_source_sha256()
        == PRIVATE_SOURCE_BUNDLE_STORE_MODULE_SOURCE_SHA256
    )
    require_private_source_bundle_store_module_source()


def _admit_floor(case: OwnerPrivateSourceBundleStoreCase) -> None:
    result = case.store.admit_trusted_floor(head=case.floor, now_ms=NOW_MS)
    assert result.applied is True
    assert result.current_head_sha256 == case.floor.head_sha256
    assert result.current_epoch == 0


def _reopen_store(
    case: OwnerPrivateSourceBundleStoreCase,
) -> OwnerPrivateEncryptedSourceBundleStoreV1:
    return OwnerPrivateEncryptedSourceBundleStoreV1(
        case.store.path,
        owner_path_discriminator=case.store.owner_path_discriminator,
        registry_id=case.store.registry_id,
        trusted_floor_sha256=case.floor.head_sha256,
        creation_anchor_verification_keys=case.store._anchor_keys,
        source_head_verification_keys=case.store._head_repository.verification_keys,
        key_provider=case.key_provider,
    )


def _pending_and_successor(
    case: OwnerPrivateSourceBundleStoreCase,
    *,
    now_ms: int = NOW_MS,
) -> tuple[PendingOpaqueSourceSelectorV1, OwnerPrivateSourceAuthorityHeadV1]:
    pending = case.store.mint_pending_selector(
        owner_path_authority=case.authority,
        expected_current_head_sha256=case.floor.head_sha256,
        expected_current_epoch=case.floor.epoch,
        now_ms=now_ms,
    )
    next_head = successor(
        case.floor,
        issued_at_ms=now_ms,
        active=(bundle_revision(pending.opaque_source_bundle_id),),
    )
    return pending, next_head


def _seal(
    case: OwnerPrivateSourceBundleStoreCase,
    *,
    now_ms: int = NOW_MS,
) -> tuple[PendingOpaqueSourceSelectorV1, OwnerPrivateSourceAuthorityHeadV1]:
    pending, next_head = _pending_and_successor(case, now_ms=now_ms)
    result = case.store.seal_bundle_current(
        owner_path_authority=case.authority,
        pending_selector=pending,
        bundle=case.bundle,
        expected_current_head_sha256=case.floor.head_sha256,
        expected_absent_row_revision=0,
        next_head=next_head,
        key_version=KEY_VERSION,
        now_ms=now_ms,
    )
    assert result.applied is True and result.replayed is False
    assert result.opaque_source_bundle_id == pending.opaque_source_bundle_id
    assert result.current_head_sha256 == next_head.head_sha256
    assert result.current_epoch == 1
    return pending, next_head


def _stored_row(case: OwnerPrivateSourceBundleStoreCase) -> tuple[object, ...]:
    with sqlite3.connect(case.store.path) as connection:
        row = connection.execute(
            "SELECT opaque_source_bundle_id, nonce, ciphertext, row_revision "
            "FROM owner_private_encrypted_source_bundles"
        ).fetchone()
    assert row is not None
    return tuple(row)


def test_floor_pending_atomic_seal_exact_resolve_and_replay_no_rewrite(
    tmp_path: Path,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "store")
    _admit_floor(case)
    pending, next_head = _seal(case)
    before = _stored_row(case)
    witness = case.store.resolve_exact_current(
        owner_path_authority=case.authority,
        opaque_source_bundle_id=pending.opaque_source_bundle_id,
        expected_current_head_sha256=next_head.head_sha256,
        expected_row_revision=1,
        expected_receipt_pairs=case.receipt_pairs,
        now_ms=NOW_MS,
        required_until_ms=case.bundle.required_until_ms,
    )
    assert witness.exact_match is True
    assert witness.confers_execution_authority is False
    assert witness.confers_checkpoint_authority is False
    assert witness.confers_sink_authority is False
    assert witness.confers_transition_authority is False
    assert witness.production_consumer_enabled is False
    assert (
        witness.resolver_contract_sha256
        == OWNER_PRIVATE_SOURCE_EXACT_CURRENT_RESOLVER_CONTRACT_SHA256
    )
    assert "opsbs1_" not in repr(witness)
    for operation in (
        lambda: copy.copy(witness),
        lambda: copy.deepcopy(witness),
        lambda: pickle.dumps(witness),
    ):
        with pytest.raises(TypeError):
            operation()
    with pytest.raises(AttributeError):
        witness._current_epoch = 9
    replay = case.store.replay_bundle_current(
        owner_path_authority=case.authority,
        opaque_source_bundle_id=pending.opaque_source_bundle_id,
        bundle=case.bundle,
        expected_current_head_sha256=next_head.head_sha256,
        expected_row_revision=1,
        now_ms=NOW_MS,
    )
    assert replay.applied is False and replay.replayed is True
    assert _stored_row(case) == before
    with sqlite3.connect(case.store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_encrypted_source_bundles"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_source_authority_heads"
        ).fetchone() == (2,)
    case.key_provider.assert_all_opened_keys_cleared()


def test_planner_zero_roster_seals_and_resolves_with_empty_pairs(tmp_path: Path) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "planner", planner=True)
    assert case.receipt_pairs == ()
    _admit_floor(case)
    pending, next_head = _seal(case)
    witness = case.store.resolve_exact_current(
        owner_path_authority=case.authority,
        opaque_source_bundle_id=pending.opaque_source_bundle_id,
        expected_current_head_sha256=next_head.head_sha256,
        expected_row_revision=1,
        expected_receipt_pairs=(),
        now_ms=NOW_MS,
        required_until_ms=case.bundle.required_until_ms,
    )
    assert witness.exact_match is True
    case.key_provider.assert_all_opened_keys_cleared()


def test_floor_replay_is_idempotent_without_rewrite(tmp_path: Path) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "floor")
    _admit_floor(case)
    with sqlite3.connect(case.store.path) as connection:
        before = connection.execute(
            "SELECT head_sha256, document_json FROM owner_private_source_authority_heads"
        ).fetchall()
    replay = case.store.admit_trusted_floor(head=case.floor, now_ms=NOW_MS)
    assert replay.applied is False
    with sqlite3.connect(case.store.path) as connection:
        after = connection.execute(
            "SELECT head_sha256, document_json FROM owner_private_source_authority_heads"
        ).fetchall()
    assert after == before


def test_floor_replay_rejects_after_current_has_advanced(tmp_path: Path) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "advanced-floor")
    _admit_floor(case)
    _seal(case)
    with pytest.raises(OwnerPrivateSourceStoreRejected):
        case.store.admit_trusted_floor(head=case.floor, now_ms=NOW_MS)


def test_restart_preserves_resolution_and_rejects_pre_restart_pending(
    tmp_path: Path,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "restart")
    _admit_floor(case)
    pending, next_head = _seal(case)
    reopened = _reopen_store(case)
    witness = reopened.resolve_exact_current(
        owner_path_authority=case.authority,
        opaque_source_bundle_id=pending.opaque_source_bundle_id,
        expected_current_head_sha256=next_head.head_sha256,
        expected_row_revision=1,
        expected_receipt_pairs=case.receipt_pairs,
        now_ms=NOW_MS,
        required_until_ms=case.bundle.required_until_ms,
    )
    assert witness.current_head_sha256 == next_head.head_sha256

    fresh_case = owner_private_source_bundle_store_case(tmp_path / "pending-restart")
    _admit_floor(fresh_case)
    stale_pending, stale_next = _pending_and_successor(fresh_case)
    restarted = _reopen_store(fresh_case)
    with pytest.raises(OwnerPrivateSourceStoreRejected):
        restarted.seal_bundle_current(
            owner_path_authority=fresh_case.authority,
            pending_selector=stale_pending,
            bundle=fresh_case.bundle,
            expected_current_head_sha256=fresh_case.floor.head_sha256,
            expected_absent_row_revision=0,
            next_head=stale_next,
            key_version=KEY_VERSION,
            now_ms=NOW_MS,
        )


def test_concurrent_successors_have_exactly_one_winner(tmp_path: Path) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "concurrent")
    _admit_floor(case)
    second = _reopen_store(case)
    first_pending = case.store.mint_pending_selector(
        owner_path_authority=case.authority,
        expected_current_head_sha256=case.floor.head_sha256,
        expected_current_epoch=0,
        now_ms=NOW_MS,
    )
    second_pending = second.mint_pending_selector(
        owner_path_authority=case.authority,
        expected_current_head_sha256=case.floor.head_sha256,
        expected_current_epoch=0,
        now_ms=NOW_MS,
    )
    first_head = successor(
        case.floor,
        issued_at_ms=NOW_MS,
        active=(bundle_revision(first_pending.opaque_source_bundle_id),),
    )
    second_head = successor(
        case.floor,
        issued_at_ms=NOW_MS,
        active=(bundle_revision(second_pending.opaque_source_bundle_id),),
    )

    def attempt(
        store: OwnerPrivateEncryptedSourceBundleStoreV1,
        pending: PendingOpaqueSourceSelectorV1,
        head: OwnerPrivateSourceAuthorityHeadV1,
    ) -> bool:
        try:
            return store.seal_bundle_current(
                owner_path_authority=case.authority,
                pending_selector=pending,
                bundle=case.bundle,
                expected_current_head_sha256=case.floor.head_sha256,
                expected_absent_row_revision=0,
                next_head=head,
                key_version=KEY_VERSION,
                now_ms=NOW_MS,
            ).applied
        except OwnerPrivateSourceStoreRejected:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(
            executor.map(
                lambda arguments: attempt(*arguments),
                (
                    (case.store, first_pending, first_head),
                    (second, second_pending, second_head),
                ),
            )
        )
    assert sorted(outcomes) == [False, True]
    with sqlite3.connect(case.store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_encrypted_source_bundles"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_source_authority_heads"
        ).fetchone() == (2,)


def test_separate_process_successors_have_exactly_one_winner(tmp_path: Path) -> None:
    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("requires fork for inherited closed test fixtures")
    case = owner_private_source_bundle_store_case(tmp_path / "multiprocess")
    _admit_floor(case)
    context = multiprocessing.get_context("fork")
    barrier: Any = context.Barrier(2)
    outcomes: Any = context.Queue()

    def worker() -> None:
        store = _reopen_store(case)
        pending = store.mint_pending_selector(
            owner_path_authority=case.authority,
            expected_current_head_sha256=case.floor.head_sha256,
            expected_current_epoch=0,
            now_ms=NOW_MS,
        )
        next_head = successor(
            case.floor,
            issued_at_ms=NOW_MS,
            active=(bundle_revision(pending.opaque_source_bundle_id),),
        )
        barrier.wait(timeout=10)
        try:
            store.seal_bundle_current(
                owner_path_authority=case.authority,
                pending_selector=pending,
                bundle=case.bundle,
                expected_current_head_sha256=case.floor.head_sha256,
                expected_absent_row_revision=0,
                next_head=next_head,
                key_version=KEY_VERSION,
                now_ms=NOW_MS,
            )
        except OwnerPrivateSourceStoreRejected:
            outcomes.put(False)
        else:
            outcomes.put(True)

    processes = tuple(context.Process(target=worker) for _ in range(2))
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)
    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    assert [process.exitcode for process in processes] == [0, 0]
    assert sorted((outcomes.get(timeout=2), outcomes.get(timeout=2))) == [False, True]


def test_abrupt_process_exit_after_insert_recovers_floor_only_state(tmp_path: Path) -> None:
    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("requires fork for inherited closed test fixtures")
    case = owner_private_source_bundle_store_case(tmp_path / "crash-recovery")
    _admit_floor(case)
    context = multiprocessing.get_context("fork")

    def worker() -> None:
        store = _reopen_store(case)
        pending = store.mint_pending_selector(
            owner_path_authority=case.authority,
            expected_current_head_sha256=case.floor.head_sha256,
            expected_current_epoch=0,
            now_ms=NOW_MS,
        )
        next_head = successor(
            case.floor,
            issued_at_ms=NOW_MS,
            active=(bundle_revision(pending.opaque_source_bundle_id),),
        )

        def abrupt_exit(*args: object, **kwargs: object) -> Never:
            os._exit(73)

        _SourceHeadRepositoryV1.insert_and_advance = abrupt_exit  # type: ignore[method-assign]
        store.seal_bundle_current(
            owner_path_authority=case.authority,
            pending_selector=pending,
            bundle=case.bundle,
            expected_current_head_sha256=case.floor.head_sha256,
            expected_absent_row_revision=0,
            next_head=next_head,
            key_version=KEY_VERSION,
            now_ms=NOW_MS,
        )

    process = context.Process(target=worker)
    process.start()
    process.join(timeout=15)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
    assert process.exitcode == 73
    reopened = _reopen_store(case)
    replay = reopened.admit_trusted_floor(head=case.floor, now_ms=NOW_MS)
    assert replay.applied is False and replay.current_epoch == 0
    with sqlite3.connect(case.store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_encrypted_source_bundles"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_source_authority_heads"
        ).fetchone() == (1,)


@pytest.mark.parametrize("shape", ("pairs", "head", "revision", "authority", "key"))
def test_exact_resolution_wrong_pair_head_revision_authority_or_key_rejects_opaquely(
    tmp_path: Path,
    shape: str,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / shape)
    _admit_floor(case)
    pending, next_head = _seal(case)
    authority: object = case.authority
    pairs = case.receipt_pairs
    head_sha256 = next_head.head_sha256
    revision = 1
    if shape == "pairs":
        pairs = ((pairs[0][0], "f" * 64),)
    elif shape == "head":
        head_sha256 = "f" * 64
    elif shape == "revision":
        revision = 2
    elif shape == "authority":
        authority = OpaqueOwnerPathAuthority()
    else:
        case.key_provider.keys[KEY_VERSION] = WRONG_DATA_KEY
    with pytest.raises(OwnerPrivateSourceStoreRejected) as raised:
        case.store.resolve_exact_current(
            owner_path_authority=authority,
            opaque_source_bundle_id=pending.opaque_source_bundle_id,
            expected_current_head_sha256=head_sha256,
            expected_row_revision=revision,
            expected_receipt_pairs=pairs,
            now_ms=NOW_MS,
            required_until_ms=case.bundle.required_until_ms,
        )
    assert raised.value.__cause__ is None
    assert "opsbs1_" not in str(raised.value)
    if shape in {"authority", "key"}:
        case.key_provider.assert_all_opened_keys_cleared()


def test_wrong_authority_cannot_consume_pending_or_write_a_row(tmp_path: Path) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "authority")
    _admit_floor(case)
    pending, next_head = _pending_and_successor(case)
    with pytest.raises(OwnerPrivateSourceStoreRejected):
        case.store.seal_bundle_current(
            owner_path_authority=OpaqueOwnerPathAuthority(),
            pending_selector=pending,
            bundle=case.bundle,
            expected_current_head_sha256=case.floor.head_sha256,
            expected_absent_row_revision=0,
            next_head=next_head,
            key_version=KEY_VERSION,
            now_ms=NOW_MS,
        )
    with sqlite3.connect(case.store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_encrypted_source_bundles"
        ).fetchone() == (0,)
    result = case.store.seal_bundle_current(
        owner_path_authority=case.authority,
        pending_selector=pending,
        bundle=case.bundle,
        expected_current_head_sha256=case.floor.head_sha256,
        expected_absent_row_revision=0,
        next_head=next_head,
        key_version=KEY_VERSION,
        now_ms=NOW_MS,
    )
    assert result.applied is True


def test_pending_is_one_use_expiring_noncopyable_and_nonserializable(
    tmp_path: Path,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "pending")
    _admit_floor(case)
    pending, next_head = _pending_and_successor(case)
    assert pending.expires_at_ms == NOW_MS + PENDING_SELECTOR_TTL_MS
    assert "opsbs1_" not in repr(pending)
    for operation in (
        lambda: copy.copy(pending),
        lambda: copy.deepcopy(pending),
        lambda: pickle.dumps(pending),
    ):
        with pytest.raises(TypeError):
            operation()
    case.store.seal_bundle_current(
        owner_path_authority=case.authority,
        pending_selector=pending,
        bundle=case.bundle,
        expected_current_head_sha256=case.floor.head_sha256,
        expected_absent_row_revision=0,
        next_head=next_head,
        key_version=KEY_VERSION,
        now_ms=NOW_MS,
    )
    with pytest.raises(OwnerPrivateSourceStoreRejected):
        case.store.seal_bundle_current(
            owner_path_authority=case.authority,
            pending_selector=pending,
            bundle=case.bundle,
            expected_current_head_sha256=case.floor.head_sha256,
            expected_absent_row_revision=0,
            next_head=next_head,
            key_version=KEY_VERSION,
            now_ms=NOW_MS,
        )

    expired_case = owner_private_source_bundle_store_case(tmp_path / "expired")
    _admit_floor(expired_case)
    expired, expired_head = _pending_and_successor(expired_case)
    with pytest.raises(OwnerPrivateSourceStoreRejected):
        expired_case.store.seal_bundle_current(
            owner_path_authority=expired_case.authority,
            pending_selector=expired,
            bundle=expired_case.bundle,
            expected_current_head_sha256=expired_case.floor.head_sha256,
            expected_absent_row_revision=0,
            next_head=expired_head,
            key_version=KEY_VERSION,
            now_ms=expired.expires_at_ms,
        )
    with sqlite3.connect(expired_case.store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_encrypted_source_bundles"
        ).fetchone() == (0,)


def test_selector_collision_retry_skips_live_pending_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "selector-collision")
    _admit_floor(case)
    first = case.store.mint_pending_selector(
        owner_path_authority=case.authority,
        expected_current_head_sha256=case.floor.head_sha256,
        expected_current_epoch=0,
        now_ms=NOW_MS,
    )
    candidates = iter(
        (
            first._handle_id.removeprefix("opsph1_"),
            first.opaque_source_bundle_id.removeprefix("opsbs1_"),
            "a" * 64,
            "b" * 64,
        )
    )
    monkeypatch.setattr(secrets, "token_hex", lambda _: next(candidates))
    second = case.store.mint_pending_selector(
        owner_path_authority=case.authority,
        expected_current_head_sha256=case.floor.head_sha256,
        expected_current_epoch=0,
        now_ms=NOW_MS,
    )
    assert second.opaque_source_bundle_id == "opsbs1_" + "b" * 64


def test_nonce_collision_retry_selects_next_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "nonce-collision")
    _admit_floor(case)
    first_pending, first_head = _seal(case)
    first_row = _stored_row(case)
    first_nonce = first_row[1]
    assert type(first_nonce) is bytes
    second_pending = case.store.mint_pending_selector(
        owner_path_authority=case.authority,
        expected_current_head_sha256=first_head.head_sha256,
        expected_current_epoch=1,
        now_ms=NOW_MS + 1,
    )
    second_head = successor(
        first_head,
        issued_at_ms=NOW_MS + 1,
        active=(
            bundle_revision(first_pending.opaque_source_bundle_id),
            bundle_revision(second_pending.opaque_source_bundle_id),
        ),
    )
    next_nonce = b"z" * 12
    monkeypatch.setattr(
        OwnerPrivateEncryptedSourceBundleStoreV1,
        "_nonce_candidates",
        lambda _: (first_nonce, next_nonce),
    )
    result = case.store.seal_bundle_current(
        owner_path_authority=case.authority,
        pending_selector=second_pending,
        bundle=case.bundle,
        expected_current_head_sha256=first_head.head_sha256,
        expected_absent_row_revision=0,
        next_head=second_head,
        key_version=KEY_VERSION,
        now_ms=NOW_MS + 1,
    )
    assert result.applied is True
    with sqlite3.connect(case.store.path) as connection:
        nonces = connection.execute(
            "SELECT nonce FROM owner_private_encrypted_source_bundles ORDER BY rowid"
        ).fetchall()
    assert nonces == [(first_nonce,), (next_nonce,)]


def test_sqlite_contains_ciphertext_and_no_private_columns_or_needles(
    tmp_path: Path,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "ciphertext")
    _admit_floor(case)
    _seal(case)
    with sqlite3.connect(case.store.path) as connection:
        columns = tuple(
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info('owner_private_encrypted_source_bundles')"
            ).fetchall()
        )
        row = connection.execute(
            "SELECT ciphertext, ciphertext_length FROM owner_private_encrypted_source_bundles"
        ).fetchone()
    assert columns == (
        "opaque_source_bundle_id",
        "owner_path_discriminator",
        "categorical_state",
        "aead_suite",
        "key_version",
        "nonce_length",
        "nonce",
        "ciphertext_schema",
        "ciphertext_type",
        "ciphertext_length",
        "row_revision",
        "ciphertext",
    )
    assert {
        "owner_id",
        "owner_scope_sha256",
        "operation_id",
        "receipt_id",
        "receipt_sha256",
        "source_sha256",
        "private_input_commitment_sha256",
    }.isdisjoint(columns)
    assert row is not None and type(row[0]) is bytes and len(row[0]) == row[1]
    assert case.bundle.model_dump_json().encode("utf-8") not in row[0]
    artifacts = [
        path
        for path in case.store.path.parent.iterdir()
        if path.name.startswith(case.store.path.name)
    ]
    disk = b"\n".join(path.read_bytes() for path in artifacts if path.is_file())
    for needle in encoded_private_needles(case.predecessor):
        assert needle not in disk


def test_online_backup_contains_no_private_canary_encoding(tmp_path: Path) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "backup")
    _admit_floor(case)
    _seal(case)
    backup_path = tmp_path / "private-backup.sqlite3"
    with sqlite3.connect(case.store.path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
    backup_bytes = backup_path.read_bytes()
    for needle in encoded_private_needles(case.predecessor):
        assert needle not in backup_bytes


def test_live_wal_and_shm_contain_no_private_canary_encoding(tmp_path: Path) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "live-wal")
    observer = sqlite3.connect(case.store.path, isolation_level=None)
    try:
        observer.execute("PRAGMA journal_mode=WAL")
        observer.execute("BEGIN")
        observer.execute("SELECT * FROM owner_private_source_schema").fetchall()
        _admit_floor(case)
        _seal(case)
        sidecars = tuple(
            path
            for path in case.store.path.parent.iterdir()
            if path.name in {case.store.path.name + "-wal", case.store.path.name + "-shm"}
        )
        assert {path.suffix for path in sidecars} == {".sqlite3-wal", ".sqlite3-shm"}
        durable_bytes = b"\n".join(path.read_bytes() for path in sidecars)
        for needle in encoded_private_needles(case.predecessor):
            assert needle not in durable_bytes
        assert not Path(str(case.store.path) + "-journal").exists()
    finally:
        observer.execute("ROLLBACK")
        observer.close()


@pytest.mark.parametrize("location", ("body", "tag"))
def test_ciphertext_or_tag_corruption_rejects_opaquely(
    tmp_path: Path,
    location: str,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "corrupt-ciphertext")
    _admit_floor(case)
    pending, next_head = _seal(case)
    with sqlite3.connect(case.store.path) as connection:
        ciphertext = connection.execute(
            "SELECT ciphertext FROM owner_private_encrypted_source_bundles"
        ).fetchone()
        assert ciphertext is not None and type(ciphertext[0]) is bytes
        offset = 0 if location == "body" else len(ciphertext[0]) - 1
        changed = (
            ciphertext[0][:offset]
            + bytes([ciphertext[0][offset] ^ 1])
            + ciphertext[0][offset + 1 :]
        )
        connection.execute(
            "UPDATE owner_private_encrypted_source_bundles SET ciphertext=?",
            (changed,),
        )
    with pytest.raises(OwnerPrivateSourceStoreRejected) as raised:
        case.store.resolve_exact_current(
            owner_path_authority=case.authority,
            opaque_source_bundle_id=pending.opaque_source_bundle_id,
            expected_current_head_sha256=next_head.head_sha256,
            expected_row_revision=1,
            expected_receipt_pairs=case.receipt_pairs,
            now_ms=NOW_MS,
            required_until_ms=case.bundle.required_until_ms,
        )
    assert raised.value.__cause__ is None


@pytest.mark.parametrize(
    ("column", "value"),
    (
        ("categorical_state", "changed"),
        ("aead_suite", "changed"),
        ("nonce_length", 11),
        ("ciphertext_schema", "changed"),
        ("ciphertext_type", "changed"),
        ("ciphertext_length", bundle_store.MAX_SOURCE_BUNDLE_CIPHERTEXT_BYTES + 1),
        ("row_revision", 2),
    ),
)
def test_wrong_aad_schema_type_length_or_revision_rejects_opaquely(
    tmp_path: Path,
    column: str,
    value: object,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / column)
    _admit_floor(case)
    pending, next_head = _seal(case)
    with sqlite3.connect(case.store.path) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            f"UPDATE owner_private_encrypted_source_bundles SET {column}=?",
            (value,),
        )
    with pytest.raises(OwnerPrivateSourceStoreRejected) as raised:
        case.store.resolve_exact_current(
            owner_path_authority=case.authority,
            opaque_source_bundle_id=pending.opaque_source_bundle_id,
            expected_current_head_sha256=next_head.head_sha256,
            expected_row_revision=1,
            expected_receipt_pairs=case.receipt_pairs,
            now_ms=NOW_MS,
            required_until_ms=case.bundle.required_until_ms,
        )
    assert raised.value.__cause__ is None


def test_plaintext_bound_rejects_before_key_or_durable_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "plaintext-bound")
    _admit_floor(case)
    pending, next_head = _pending_and_successor(case)
    monkeypatch.setattr(bundle_store, "MAX_SOURCE_BUNDLE_PLAINTEXT_BYTES", 1)
    with pytest.raises(OwnerPrivateSourceStoreRejected):
        case.store.seal_bundle_current(
            owner_path_authority=case.authority,
            pending_selector=pending,
            bundle=case.bundle,
            expected_current_head_sha256=case.floor.head_sha256,
            expected_absent_row_revision=0,
            next_head=next_head,
            key_version=KEY_VERSION,
            now_ms=NOW_MS,
        )
    assert case.key_provider.calls == []
    with sqlite3.connect(case.store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_encrypted_source_bundles"
        ).fetchone() == (0,)


@pytest.mark.parametrize("replacement", ("hardlink", "symlink"))
def test_durable_path_replacement_rejects_before_authority_use(
    tmp_path: Path,
    replacement: str,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / replacement)
    original = case.store.path.with_suffix(".original")
    case.store.path.rename(original)
    if replacement == "hardlink":
        case.store.path.hardlink_to(original)
    else:
        case.store.path.symlink_to(original)
    with pytest.raises(OwnerPrivateSourceStoreRejected) as raised:
        case.store.admit_trusted_floor(head=case.floor, now_ms=NOW_MS)
    assert raised.value.__cause__ is None


def test_world_readable_database_mode_rejects_on_reopen(tmp_path: Path) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "public-db")
    case.store.path.chmod(0o644)
    with pytest.raises(OwnerPrivateSourceStoreRejected) as raised:
        case.store.admit_trusted_floor(head=case.floor, now_ms=NOW_MS)
    assert raised.value.__cause__ is None


def test_higher_ancestor_symlink_substitution_rejects(tmp_path: Path) -> None:
    ancestor = tmp_path / "authority-root"
    case = owner_private_source_bundle_store_case(ancestor / "nested" / "store")
    relocated = tmp_path / "authority-root-relocated"
    ancestor.rename(relocated)
    ancestor.symlink_to(relocated, target_is_directory=True)
    with pytest.raises(OwnerPrivateSourceStoreRejected) as raised:
        case.store.admit_trusted_floor(head=case.floor, now_ms=NOW_MS)
    assert raised.value.__cause__ is None


def test_broken_ancestor_symlink_rejects_without_creating_target(tmp_path: Path) -> None:
    missing_target = tmp_path / "missing-target"
    broken_ancestor = tmp_path / "broken-authority-root"
    broken_ancestor.symlink_to(missing_target, target_is_directory=True)
    target = broken_ancestor / "nested" / "source.sqlite3"
    with pytest.raises(OwnerPrivateSourceStoreRejected) as raised:
        OwnerPrivateEncryptedSourceBundleStoreV1(
            target,
            owner_path_discriminator="opspd1_" + "1" * 64,
            registry_id="opsreg1_" + "2" * 64,
            trusted_floor_sha256="3" * 64,
            creation_anchor_verification_keys={"anchor": b"a" * 32},
            source_head_verification_keys={"head": b"h" * 32},
            key_provider=object(),  # type: ignore[arg-type]
        )
    assert raised.value.__cause__ is None
    assert not missing_target.exists()


def test_failure_after_ciphertext_insert_rolls_back_bundle_and_head_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "rollback")
    _admit_floor(case)
    pending, next_head = _pending_and_successor(case)

    def fail_after_insert(*args: object, **kwargs: object) -> Never:
        raise RuntimeError("injected-after-ciphertext-insert")

    monkeypatch.setattr(_SourceHeadRepositoryV1, "insert_and_advance", fail_after_insert)
    with pytest.raises(OwnerPrivateSourceStoreRejected) as raised:
        case.store.seal_bundle_current(
            owner_path_authority=case.authority,
            pending_selector=pending,
            bundle=case.bundle,
            expected_current_head_sha256=case.floor.head_sha256,
            expected_absent_row_revision=0,
            next_head=next_head,
            key_version=KEY_VERSION,
            now_ms=NOW_MS,
        )
    assert raised.value.__cause__ is None
    with sqlite3.connect(case.store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_encrypted_source_bundles"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_source_authority_heads"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT head_sha256 FROM owner_private_source_authority_current"
        ).fetchone() == (case.floor.head_sha256,)
    case.key_provider.assert_all_opened_keys_cleared()


def test_constructor_rejects_before_creating_path_and_maps_path_errors_opaquely(
    tmp_path: Path,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "reference")
    absent = tmp_path / "must-not-exist" / "source.sqlite3"
    with pytest.raises(OwnerPrivateSourceStoreRejected) as malformed:
        OwnerPrivateEncryptedSourceBundleStoreV1(
            absent,
            owner_path_discriminator="not-an-owner-path",
            registry_id=case.store.registry_id,
            trusted_floor_sha256=case.floor.head_sha256,
            creation_anchor_verification_keys=case.store._anchor_keys,
            source_head_verification_keys=case.store._head_repository.verification_keys,
            key_provider=case.key_provider,
        )
    assert malformed.value.__cause__ is None
    assert not absent.parent.exists()

    public_parent = tmp_path / "public-parent"
    public_parent.mkdir(mode=0o777)
    public_parent.chmod(0o777)
    with pytest.raises(OwnerPrivateSourceStoreRejected) as path_error:
        OwnerPrivateEncryptedSourceBundleStoreV1(
            public_parent / "source.sqlite3",
            owner_path_discriminator=case.store.owner_path_discriminator,
            registry_id=case.store.registry_id,
            trusted_floor_sha256=case.floor.head_sha256,
            creation_anchor_verification_keys=case.store._anchor_keys,
            source_head_verification_keys=case.store._head_repository.verification_keys,
            key_provider=case.key_provider,
        )
    assert path_error.value.__cause__ is None

    class UnexpectedPathLike:
        def __fspath__(self) -> str:
            return str(tmp_path / "unexpected-pathlike.sqlite3")

    with pytest.raises(OwnerPrivateSourceStoreRejected):
        OwnerPrivateEncryptedSourceBundleStoreV1(
            UnexpectedPathLike(),  # type: ignore[arg-type]
            owner_path_discriminator=case.store.owner_path_discriminator,
            registry_id=case.store.registry_id,
            trusted_floor_sha256=case.floor.head_sha256,
            creation_anchor_verification_keys=case.store._anchor_keys,
            source_head_verification_keys=case.store._head_repository.verification_keys,
            key_provider=case.key_provider,
        )


def test_constructor_rejects_duplicate_public_key_bytes(tmp_path: Path) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "reference")
    duplicated = dict(case.store._anchor_keys)
    duplicated["duplicate-anchor"] = next(iter(duplicated.values()))
    with pytest.raises(OwnerPrivateSourceStoreRejected):
        OwnerPrivateEncryptedSourceBundleStoreV1(
            tmp_path / "duplicate" / "source.sqlite3",
            owner_path_discriminator=case.store.owner_path_discriminator,
            registry_id=case.store.registry_id,
            trusted_floor_sha256=case.floor.head_sha256,
            creation_anchor_verification_keys=duplicated,
            source_head_verification_keys=case.store._head_repository.verification_keys,
            key_provider=case.key_provider,
        )


def test_schema_initialization_failure_rolls_back_all_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = owner_private_source_bundle_store_case(tmp_path / "reference")
    target = tmp_path / "interrupted-init" / "source.sqlite3"

    def reject_schema(*args: object, **kwargs: object) -> Never:
        raise RuntimeError("injected schema audit failure")

    monkeypatch.setattr(
        OwnerPrivateEncryptedSourceBundleStoreV1,
        "_validate_schema",
        reject_schema,
    )
    with pytest.raises(OwnerPrivateSourceStoreRejected):
        OwnerPrivateEncryptedSourceBundleStoreV1(
            target,
            owner_path_discriminator=reference.store.owner_path_discriminator,
            registry_id=reference.store.registry_id,
            trusted_floor_sha256=reference.floor.head_sha256,
            creation_anchor_verification_keys=reference.store._anchor_keys,
            source_head_verification_keys=(
                reference.store._head_repository.verification_keys
            ),
            key_provider=reference.key_provider,
        )
    if target.exists():
        with sqlite3.connect(target) as connection:
            assert connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall() == []


def test_every_reopen_rejects_exact_schema_drift(tmp_path: Path) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "schema-drift")
    with sqlite3.connect(case.store.path) as connection:
        connection.execute("CREATE TABLE unauthorized_extension(value TEXT)")
    with pytest.raises(OwnerPrivateSourceStoreRejected) as raised:
        case.store.admit_trusted_floor(head=case.floor, now_ms=NOW_MS)
    assert raised.value.__cause__ is None


def test_floor_and_mint_reconcile_rows_to_signed_snapshot(tmp_path: Path) -> None:
    floor_case = owner_private_source_bundle_store_case(tmp_path / "floor-mismatch")
    _admit_floor(floor_case)
    _insert_unattested_bundle_row(floor_case)
    with pytest.raises(OwnerPrivateSourceStoreRejected):
        floor_case.store.admit_trusted_floor(head=floor_case.floor, now_ms=NOW_MS)

    mint_case = owner_private_source_bundle_store_case(tmp_path / "mint-mismatch")
    _admit_floor(mint_case)
    _insert_unattested_bundle_row(mint_case)
    with pytest.raises(OwnerPrivateSourceStoreRejected):
        mint_case.store.mint_pending_selector(
            owner_path_authority=mint_case.authority,
            expected_current_head_sha256=mint_case.floor.head_sha256,
            expected_current_epoch=0,
            now_ms=NOW_MS,
        )


def _insert_unattested_bundle_row(case: OwnerPrivateSourceBundleStoreCase) -> None:
    with sqlite3.connect(case.store.path) as connection:
        connection.execute(
            "INSERT INTO owner_private_encrypted_source_bundles VALUES "
            "(?,?,'sealed','aes-256-gcm',?,12,?,"
            "'owner_private_encrypted_source_bundle_v1_json','application/json',17,1,?)",
            (
                "opsbs1_" + "ab" * 32,
                case.store.owner_path_discriminator,
                KEY_VERSION,
                b"n" * 12,
                b"c" * 17,
            ),
        )


@pytest.mark.parametrize(
    "pairs",
    (
        [["opsr5_" + "1" * 24, "2" * 64]],
        tuple(("opsr5_" + "1" * 24, "2" * 64) for _ in range(MAX_SOURCE_RECEIPT_PAIRS + 1)),
    ),
)
def test_resolver_rejects_non_tuple_or_oversized_pairs_before_storage_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pairs: object,
) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "bounded-pairs")

    def storage_access_forbidden(*args: object, **kwargs: object) -> Never:
        raise AssertionError("storage access occurred")

    monkeypatch.setattr(
        OwnerPrivateEncryptedSourceBundleStoreV1,
        "_read_row_and_head",
        storage_access_forbidden,
    )
    with pytest.raises(OwnerPrivateSourceStoreRejected) as raised:
        case.store.resolve_exact_current(
            owner_path_authority=case.authority,
            opaque_source_bundle_id="opsbs1_" + "1" * 64,
            expected_current_head_sha256="2" * 64,
            expected_row_revision=1,
            expected_receipt_pairs=pairs,  # type: ignore[arg-type]
            now_ms=NOW_MS,
            required_until_ms=NOW_MS,
        )
    assert raised.value.__cause__ is None


def test_store_and_embedded_head_repository_are_immutable(tmp_path: Path) -> None:
    case = owner_private_source_bundle_store_case(tmp_path / "immutable")
    with pytest.raises(AttributeError):
        case.store.path = tmp_path / "redirected"
    with pytest.raises(AttributeError):
        case.store._head_repository.registry_id = "opsreg1_" + "0" * 64


def test_bundle_and_head_stores_remain_quarantined_from_production_composition() -> None:
    module_names = ("private_source_bundle_store", "private_source_head_store")
    excluded = {
        ROOT / "substrate/midnight_oil/private_source_bundle_store.py",
        ROOT / "substrate/midnight_oil/private_source_head_store.py",
    }
    violations = [
        path.relative_to(ROOT)
        for path in ROOT.rglob("*.py")
        if path not in excluded
        and "tests" not in path.relative_to(ROOT).parts
        and not {".git", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache"}.intersection(
            path.relative_to(ROOT).parts
        )
        if any(name in path.read_text(encoding="utf-8") for name in module_names)
    ]
    assert violations == []


def test_bundle_store_public_surface_is_closed_and_nonconferring() -> None:
    assert bundle_store.__all__ == [
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
    forbidden = ("sign", "issue", "generic", "decrypt", "list", "get")
    assert not any(name.lower().startswith(forbidden) for name in bundle_store.__all__)
