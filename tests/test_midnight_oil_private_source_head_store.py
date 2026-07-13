from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import ValidationError

import substrate.midnight_oil.private_source_head_store as heads
from substrate.midnight_oil.private_source_head_store import (
    PRIVATE_SOURCE_HEAD_STORE_MODULE_SOURCE_SHA256,
    InvalidOwnerPrivateSourceHeadStore,
    OwnerPrivateSourceHeadRejected,
    owner_private_source_authority_head_v1_sha256,
    owner_private_source_authority_snapshot_v1_sha256,
    parse_owner_private_source_authority_head_v1_json,
    private_source_head_store_module_source_sha256,
    require_owner_private_source_head_fresh,
    require_private_source_head_store_module_source,
    validate_owner_private_source_head_successor,
    verify_owner_private_source_authority_head_v1,
)
from tests.support.owner_private_source_head_v1 import (
    HEAD_PRIVATE_KEY,
    HEAD_SIGNATURE_DOMAIN,
    OTHER_OWNER_PATH_DISCRIMINATOR,
    OTHER_REGISTRY_ID,
    OWNER_PATH_DISCRIMINATOR,
    REGISTRY_ID,
    SELECTOR_ONE,
    SELECTOR_THREE,
    SELECTOR_TWO,
    bundle_revision,
    empty_floor,
    head_verification_keys,
    signed_source_head,
    successor,
)

SNAPSHOT_DOMAIN = b"antiek.midnight-oil.owner-private-source-authority-snapshot.v1\x00"
HEAD_DOMAIN = b"antiek.midnight-oil.owner-private-source-authority-head.v1\x00"


def test_head_module_semantic_source_identity_is_pinned() -> None:
    assert (
        private_source_head_store_module_source_sha256()
        == PRIVATE_SOURCE_HEAD_STORE_MODULE_SOURCE_SHA256
    )
    require_private_source_head_store_module_source()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _database(path: Path | str = ":memory:") -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(heads._HEADS_DDL)
    connection.execute(heads._CURRENT_DDL)
    return connection


def _repository(
    floor_sha256: str,
    *,
    verification_keys: Mapping[str, bytes] | None = None,
) -> heads._SourceHeadRepositoryV1:
    return heads._SourceHeadRepositoryV1(
        owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
        registry_id=REGISTRY_ID,
        verification_keys=(
            head_verification_keys() if verification_keys is None else verification_keys
        ),
        trusted_floor_sha256=floor_sha256,
    )


def _admit(
    connection: sqlite3.Connection,
    repository: heads._SourceHeadRepositoryV1,
    floor: heads.OwnerPrivateSourceAuthorityHeadV1,
) -> None:
    connection.execute("BEGIN IMMEDIATE")
    repository.admit_trusted_floor(connection, floor)
    connection.execute("COMMIT")


def test_empty_floor_and_successor_have_exact_domains_identity_and_purpose() -> None:
    floor = empty_floor()
    first = successor(floor, active=(bundle_revision(SELECTOR_ONE),))
    snapshot_raw = first.snapshot.model_dump(mode="json", exclude={"snapshot_sha256"})
    head_raw = first.model_dump(mode="json", exclude={"head_sha256", "signature_ed25519"})
    assert (
        first.snapshot.snapshot_sha256
        == hashlib.sha256(SNAPSHOT_DOMAIN + _canonical(snapshot_raw)).hexdigest()
    )
    assert (
        owner_private_source_authority_snapshot_v1_sha256(first.snapshot)
        == first.snapshot.snapshot_sha256
    )
    assert first.head_sha256 == hashlib.sha256(HEAD_DOMAIN + _canonical(head_raw)).hexdigest()
    assert owner_private_source_authority_head_v1_sha256(first) == first.head_sha256
    assert first.key_purpose == "owner_private_source_head_issuer_v1"
    assert first.issuer_role == "owner_private_source_head_issuer"
    assert floor.epoch == 0 and floor.previous_head_sha256 == heads.ZERO_SHA256
    assert floor.snapshot.active_bundle_revisions == ()
    assert floor.snapshot.tombstoned_bundle_ids == ()
    assert first.previous_head_sha256 == floor.head_sha256
    assert first.epoch == 1
    Ed25519PublicKey.from_public_bytes(next(iter(head_verification_keys().values()))).verify(
        bytes.fromhex(first.signature_ed25519),
        HEAD_SIGNATURE_DOMAIN + first.head_sha256.encode("ascii"),
    )
    verify_owner_private_source_authority_head_v1(floor, verification_keys=head_verification_keys())
    verify_owner_private_source_authority_head_v1(first, verification_keys=head_verification_keys())
    validate_owner_private_source_head_successor(floor, first)
    assert "SELECTOR_ONE" not in repr(first)
    for model in (floor, floor.snapshot, first, first.snapshot):
        raw = model.model_dump(mode="python")
        assert raw["confers_execution_authority"] is False
        assert raw["confers_checkpoint_authority"] is False
        assert raw["confers_sink_authority"] is False
        assert raw["confers_transition_authority"] is False
        assert raw["production_consumer_enabled"] is False


@pytest.mark.parametrize(
    "field",
    (
        "registry_id",
        "owner_path_discriminator",
        "epoch",
        "issued_at_ms",
        "previous_head_sha256",
        "head_sha256",
        "signature_ed25519",
        "key_purpose",
        "confers_transition_authority",
    ),
)
def test_head_identity_purpose_and_authority_mutations_reject(field: str) -> None:
    original = empty_floor()
    replacement: object
    if field == "registry_id":
        replacement = OTHER_REGISTRY_ID
    elif field == "owner_path_discriminator":
        replacement = OTHER_OWNER_PATH_DISCRIMINATOR
    elif field in {"epoch", "issued_at_ms"}:
        replacement = getattr(original, field) + 1
    elif field == "key_purpose":
        replacement = "owner_private_source_creation_issuer_v1"
    elif field == "confers_transition_authority":
        replacement = True
    elif field == "signature_ed25519":
        replacement = "0" * 128
    elif field == "previous_head_sha256":
        replacement = "f" * 64
    else:
        replacement = "0" * 64
    forged = original.model_copy(update={field: replacement})
    with pytest.raises(OwnerPrivateSourceHeadRejected):
        verify_owner_private_source_authority_head_v1(
            forged, verification_keys=head_verification_keys()
        )


def test_snapshot_mutation_and_nested_model_copy_bypass_reject() -> None:
    original = successor(empty_floor(), active=(bundle_revision(SELECTOR_ONE),))
    forged_snapshot = original.snapshot.model_copy(
        update={"active_bundle_revisions": (bundle_revision(SELECTOR_TWO),)}
    )
    forged = original.model_copy(update={"snapshot": forged_snapshot})
    with pytest.raises(OwnerPrivateSourceHeadRejected):
        verify_owner_private_source_authority_head_v1(
            forged, verification_keys=head_verification_keys()
        )


def test_wrong_signature_unknown_key_and_malicious_mapping_reject_opaquely() -> None:
    head = empty_floor()
    wrong_domain = head.model_copy(update={"signature_ed25519": "0" * 128})
    with pytest.raises(OwnerPrivateSourceHeadRejected):
        verify_owner_private_source_authority_head_v1(
            wrong_domain, verification_keys=head_verification_keys()
        )
    with pytest.raises(OwnerPrivateSourceHeadRejected):
        verify_owner_private_source_authority_head_v1(head, verification_keys={})

    class MaliciousKeys(Mapping[str, bytes]):
        def __getitem__(self, key: str) -> bytes:
            raise RuntimeError("head-key-secret-must-not-escape")

        def __iter__(self) -> Iterator[str]:
            raise RuntimeError("head-key-secret-must-not-escape")

        def __len__(self) -> int:
            return 1

    with pytest.raises(OwnerPrivateSourceHeadRejected) as raised:
        verify_owner_private_source_authority_head_v1(head, verification_keys=MaliciousKeys())
    assert raised.value.__cause__ is None
    assert "head-key-secret" not in str(raised.value)


def test_parser_round_trip_duplicate_bound_and_opaque_failures() -> None:
    head = empty_floor()
    encoded = head.model_dump_json().encode("utf-8")
    assert parse_owner_private_source_authority_head_v1_json(encoded) == head
    duplicate = encoded.replace(
        b'{"schema_version":1', b'{"schema_version":1,"schema_version":1', 1
    )
    for raw in (
        duplicate,
        b"{}",
        b"\xff",
        b"x" * (heads.MAX_OWNER_PRIVATE_SOURCE_HEAD_BYTES + 1),
    ):
        with pytest.raises(OwnerPrivateSourceHeadRejected) as raised:
            parse_owner_private_source_authority_head_v1_json(raw)
        assert raised.value.__cause__ is None


def test_freshness_bound_is_inclusive_and_bool_is_rejected() -> None:
    head = empty_floor(issued_at_ms=1_000)
    require_owner_private_source_head_fresh(
        head, now_ms=1_000 + heads.MAX_OWNER_PRIVATE_SOURCE_HEAD_AGE_MS
    )
    for now_ms in (
        1_000 - heads.MAX_OWNER_PRIVATE_SOURCE_HEAD_FUTURE_SKEW_MS - 1,
        1_001 + heads.MAX_OWNER_PRIVATE_SOURCE_HEAD_AGE_MS,
        True,
    ):
        with pytest.raises(OwnerPrivateSourceHeadRejected):
            require_owner_private_source_head_fresh(head, now_ms=now_ms)


def test_validly_rehashed_and_resigned_append_only_successors() -> None:
    floor = empty_floor()
    first = successor(floor, active=(bundle_revision(SELECTOR_ONE),))
    second = successor(
        first,
        active=(bundle_revision(SELECTOR_ONE), bundle_revision(SELECTOR_TWO)),
    )
    third = successor(
        second,
        active=(
            bundle_revision(SELECTOR_ONE),
            bundle_revision(SELECTOR_TWO),
            bundle_revision(SELECTOR_THREE),
        ),
    )
    for current, next_head in ((floor, first), (first, second), (second, third)):
        verify_owner_private_source_authority_head_v1(
            next_head, verification_keys=head_verification_keys()
        )
        validate_owner_private_source_head_successor(current, next_head)


def test_tombstones_are_reserved_but_unavailable_in_cycle31b() -> None:
    floor = empty_floor()
    with pytest.raises(ValidationError):
        successor(
            floor,
            active=(bundle_revision(SELECTOR_ONE),),
            tombstones=(SELECTOR_TWO,),
        )


@pytest.mark.parametrize(
    "shape",
    (
        "no_addition",
        "two_additions",
        "change_revision",
        "new_revision_not_one",
    ),
)
def test_validly_rehashed_and_resigned_successor_set_mutations_reject(
    shape: str,
) -> None:
    floor = empty_floor()
    first = successor(floor, active=(bundle_revision(SELECTOR_ONE),))
    current = first
    active = current.snapshot.active_bundle_revisions
    with pytest.raises((OwnerPrivateSourceHeadRejected, ValidationError)):
        if shape == "no_addition":
            candidate = successor(current, active=active)
        elif shape == "two_additions":
            candidate = successor(
                current,
                active=(
                    *active,
                    bundle_revision(SELECTOR_TWO),
                    bundle_revision(SELECTOR_THREE),
                ),
            )
        elif shape == "change_revision":
            forged_existing = active[0].model_copy(update={"row_revision": 2})
            candidate = successor(
                current,
                active=(forged_existing, bundle_revision(SELECTOR_TWO)),
            )
        else:
            forged_new = bundle_revision(SELECTOR_TWO).model_copy(update={"row_revision": 2})
            candidate = successor(
                current,
                active=(*active, forged_new),
            )
        validate_owner_private_source_head_successor(current, candidate)


@pytest.mark.parametrize(
    "shape",
    ("registry", "owner", "predecessor", "epoch", "time"),
)
def test_validly_rehashed_and_resigned_successor_lineage_mutations_reject(
    shape: str,
) -> None:
    current = empty_floor()
    values: dict[str, object] = {
        "epoch": 1,
        "issued_at_ms": 1_001,
        "previous_head_sha256": current.head_sha256,
        "active": (),
        "registry_id": REGISTRY_ID,
        "owner_path_discriminator": OWNER_PATH_DISCRIMINATOR,
    }
    if shape == "registry":
        values["registry_id"] = OTHER_REGISTRY_ID
    elif shape == "owner":
        values["owner_path_discriminator"] = OTHER_OWNER_PATH_DISCRIMINATOR
    elif shape == "predecessor":
        values["previous_head_sha256"] = "f" * 64
    elif shape == "epoch":
        values["epoch"] = 2
    else:
        values["issued_at_ms"] = current.issued_at_ms
    candidate = signed_source_head(**values)  # type: ignore[arg-type]
    with pytest.raises(OwnerPrivateSourceHeadRejected):
        validate_owner_private_source_head_successor(current, candidate)


def test_connection_bound_schema_is_exact_and_repository_never_owns_transaction() -> None:
    connection = _database()
    try:
        heads_columns = tuple(
            (row[1], row[2].upper(), row[3], row[5])
            for row in connection.execute(
                "PRAGMA table_info('owner_private_source_authority_heads')"
            )
        )
        current_columns = tuple(
            (row[1], row[2].upper(), row[3], row[5])
            for row in connection.execute(
                "PRAGMA table_info('owner_private_source_authority_current')"
            )
        )
        assert heads_columns == (
            ("head_sha256", "TEXT", 0, 1),
            ("registry_id", "TEXT", 1, 0),
            ("owner_path_discriminator", "TEXT", 1, 0),
            ("epoch", "INTEGER", 1, 0),
            ("previous_head_sha256", "TEXT", 1, 0),
            ("issued_at_ms", "INTEGER", 1, 0),
            ("document_json", "TEXT", 1, 0),
        )
        assert current_columns == (
            ("registry_id", "TEXT", 0, 1),
            ("owner_path_discriminator", "TEXT", 1, 0),
            ("head_sha256", "TEXT", 1, 0),
        )
        floor = empty_floor()
        repository = _repository(floor.head_sha256)
        with pytest.raises(InvalidOwnerPrivateSourceHeadStore):
            repository.admit_trusted_floor(connection, floor)
        connection.execute("BEGIN IMMEDIATE")
        repository.admit_trusted_floor(connection, floor)
        assert connection.in_transaction
        connection.execute("ROLLBACK")
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_source_authority_heads"
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_repository_floor_cas_chain_restart_and_current_only_freshness(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.sqlite3"
    floor = empty_floor(issued_at_ms=100_000)
    first = successor(
        floor,
        issued_at_ms=400_000,
        active=(bundle_revision(SELECTOR_ONE),),
    )
    repository = _repository(floor.head_sha256)
    connection = _database(path)
    try:
        _admit(connection, repository, floor)
        connection.execute("BEGIN IMMEDIATE")
        stale = repository.insert_and_advance(
            connection,
            expected_head_sha256="f" * 64,
            next_head=first,
            now_ms=400_000,
        )
        assert stale.applied is False and stale.current == floor
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_source_authority_heads"
        ).fetchone() == (1,)
        applied = repository.insert_and_advance(
            connection,
            expected_head_sha256=floor.head_sha256,
            next_head=first,
            now_ms=400_000,
        )
        assert applied.applied is True and applied.current == first
        assert connection.in_transaction
        connection.execute("COMMIT")
    finally:
        connection.close()
    reopened = _database(path)
    try:
        reopened.execute("BEGIN")
        chain = repository.load_current_to_floor(reopened, now_ms=650_000)
        assert chain == (first, floor)
        reopened.execute("COMMIT")
    finally:
        reopened.close()


def test_repository_wrong_floor_or_signature_rejects_without_partial_state() -> None:
    floor = empty_floor()
    connection = _database()
    try:
        wrong_floor = _repository("f" * 64)
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(OwnerPrivateSourceHeadRejected):
            wrong_floor.admit_trusted_floor(connection, floor)
        connection.execute("ROLLBACK")
        wrong_key = _repository(floor.head_sha256, verification_keys={"wrong": b"x" * 32})
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(OwnerPrivateSourceHeadRejected):
            wrong_key.admit_trusted_floor(connection, floor)
        connection.execute("ROLLBACK")
        assert connection.execute(
            "SELECT COUNT(*) FROM owner_private_source_authority_heads"
        ).fetchone() == (0,)
    finally:
        connection.close()


@pytest.mark.parametrize(
    "corruption",
    ("document", "row_hash", "orphan", "fork", "cycle_attempt", "pointer"),
)
def test_repository_corruption_fork_cycle_floor_and_pointer_fail_closed(
    corruption: str,
) -> None:
    floor = empty_floor()
    first = successor(floor, active=(bundle_revision(SELECTOR_ONE),))
    sibling = signed_source_head(
        epoch=2,
        issued_at_ms=1_002,
        previous_head_sha256="b" * 64,
        active=(bundle_revision(SELECTOR_TWO),),
    )
    connection = _database()
    repository = _repository(floor.head_sha256)
    try:
        _admit(connection, repository, floor)
        if corruption == "orphan":
            connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        repository.insert_and_advance(
            connection,
            expected_head_sha256=floor.head_sha256,
            next_head=first,
            now_ms=first.issued_at_ms,
        )
        connection.execute("COMMIT")
        connection.execute("BEGIN IMMEDIATE")
        if corruption == "document":
            connection.execute(
                "UPDATE owner_private_source_authority_heads SET document_json = '{}' "
                "WHERE head_sha256 = ?",
                (first.head_sha256,),
            )
        elif corruption == "row_hash":
            connection.execute(
                "UPDATE owner_private_source_authority_heads SET previous_head_sha256 = ? "
                "WHERE head_sha256 = ?",
                ("e" * 64, first.head_sha256),
            )
        elif corruption == "orphan":
            connection.execute(
                "DELETE FROM owner_private_source_authority_heads WHERE head_sha256 = ?",
                (floor.head_sha256,),
            )
        elif corruption == "fork":
            heads._SourceHeadRepositoryV1._insert_head(connection, sibling)
        elif corruption == "cycle_attempt":
            connection.execute(
                "UPDATE owner_private_source_authority_heads SET previous_head_sha256 = ? "
                "WHERE head_sha256 = ?",
                (first.head_sha256, floor.head_sha256),
            )
        else:
            connection.execute(
                "UPDATE owner_private_source_authority_current SET registry_id = ?",
                (OTHER_REGISTRY_ID,),
            )
        with pytest.raises(InvalidOwnerPrivateSourceHeadStore):
            repository.load_current_to_floor(connection, now_ms=first.issued_at_ms)
        connection.execute("ROLLBACK")
    finally:
        connection.close()


def test_repository_external_floor_is_never_derived_from_database() -> None:
    floor = empty_floor()
    first = successor(floor, active=(bundle_revision(SELECTOR_ONE),))
    connection = _database()
    correct = _repository(floor.head_sha256)
    try:
        _admit(connection, correct, floor)
        connection.execute("BEGIN IMMEDIATE")
        correct.insert_and_advance(
            connection,
            expected_head_sha256=floor.head_sha256,
            next_head=first,
            now_ms=first.issued_at_ms,
        )
        connection.execute("COMMIT")
        untrusted = _repository("a" * 64)
        connection.execute("BEGIN")
        with pytest.raises(InvalidOwnerPrivateSourceHeadStore):
            untrusted.load_current_to_floor(connection, now_ms=first.issued_at_ms)
        connection.execute("ROLLBACK")
    finally:
        connection.close()


def test_chain_bound_and_below_external_floor_restore_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    floor = empty_floor()
    first = successor(floor, active=(bundle_revision(SELECTOR_ONE),))
    connection = _database()
    repository = _repository(floor.head_sha256)
    try:
        _admit(connection, repository, floor)
        connection.execute("BEGIN IMMEDIATE")
        repository.insert_and_advance(
            connection,
            expected_head_sha256=floor.head_sha256,
            next_head=first,
            now_ms=first.issued_at_ms,
        )
        connection.execute("COMMIT")
        monkeypatch.setattr(heads, "MAX_OWNER_PRIVATE_SOURCE_HEAD_CHAIN", 1)
        connection.execute("BEGIN")
        with pytest.raises(InvalidOwnerPrivateSourceHeadStore):
            repository.load_current_to_floor(connection, now_ms=first.issued_at_ms)
        connection.execute("ROLLBACK")
    finally:
        connection.close()

    restored_below_floor = _database()
    try:
        genesis_repository = _repository(floor.head_sha256)
        _admit(restored_below_floor, genesis_repository, floor)
        external_floor_repository = _repository(first.head_sha256)
        restored_below_floor.execute("BEGIN")
        with pytest.raises(InvalidOwnerPrivateSourceHeadStore):
            external_floor_repository.load_current_to_floor(
                restored_below_floor,
                now_ms=floor.issued_at_ms,
            )
        restored_below_floor.execute("ROLLBACK")
    finally:
        restored_below_floor.close()


def test_whole_state_restore_is_detected_by_external_expected_head(tmp_path: Path) -> None:
    path = tmp_path / "authority.sqlite3"
    backup_path = tmp_path / "ancestor.sqlite3"
    floor = empty_floor()
    first = successor(floor, active=(bundle_revision(SELECTOR_ONE),))
    second = successor(
        first,
        issued_at_ms=first.issued_at_ms + 1,
        active=(bundle_revision(SELECTOR_ONE), bundle_revision(SELECTOR_TWO)),
    )
    third = successor(
        second,
        issued_at_ms=second.issued_at_ms + 1,
        active=(
            bundle_revision(SELECTOR_ONE),
            bundle_revision(SELECTOR_TWO),
            bundle_revision(SELECTOR_THREE),
        ),
    )
    repository = _repository(floor.head_sha256)
    connection = _database(path)
    try:
        _admit(connection, repository, floor)
        connection.execute("BEGIN IMMEDIATE")
        repository.insert_and_advance(
            connection,
            expected_head_sha256=floor.head_sha256,
            next_head=first,
            now_ms=first.issued_at_ms,
        )
        connection.execute("COMMIT")
        with sqlite3.connect(backup_path) as backup:
            connection.backup(backup)
        connection.execute("BEGIN IMMEDIATE")
        repository.insert_and_advance(
            connection,
            expected_head_sha256=first.head_sha256,
            next_head=second,
            now_ms=second.issued_at_ms,
        )
        connection.execute("COMMIT")
    finally:
        connection.close()

    with sqlite3.connect(backup_path) as backup, sqlite3.connect(path) as restored:
        backup.backup(restored)
    restored = _database(path)
    try:
        restored.execute("BEGIN IMMEDIATE")
        result = repository.insert_and_advance(
            restored,
            expected_head_sha256=second.head_sha256,
            next_head=third,
            now_ms=third.issued_at_ms,
        )
        assert result.applied is False and result.current == first
        restored.execute("ROLLBACK")
    finally:
        restored.close()


def test_test_support_is_only_head_signer_and_production_has_no_issuer() -> None:
    assert HEAD_PRIVATE_KEY not in Path(heads.__file__).read_bytes()
    exported = set(heads.__all__)
    assert not any(name.startswith(("sign_", "signed_", "issue_", "create_")) for name in exported)
