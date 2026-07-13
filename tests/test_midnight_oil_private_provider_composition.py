from __future__ import annotations

import base64
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from substrate.midnight_oil.private_provider_composition import (
    MAX_PRIVATE_PROVIDER_HEAD_CHAIN,
    PRIVATE_PROVIDER_CAPABILITY_KEYRING_ENVS_ENV,
    PRIVATE_PROVIDER_CAPABILITY_PATHS_ENV,
    PRIVATE_PROVIDER_EXPECTED_COMPOSITION_SHA256_ENV,
    PRIVATE_PROVIDER_EXPECTED_CURRENT_PATH_ENV,
    PRIVATE_PROVIDER_EXPECTED_CURRENT_SHA256_ENV,
    PRIVATE_PROVIDER_REVOCATION_KEYRING_ENVS_ENV,
    PRIVATE_PROVIDER_TRUSTED_FLOOR_PATH_ENV,
    PRIVATE_PROVIDER_TRUSTED_FLOOR_SHA256_ENV,
    DurablePrivateProviderRevocationHeadStore,
    InvalidPrivateProviderRevocationStore,
    PrivateProviderRevocationHeadV1,
    build_private_provider_composition,
    parse_private_provider_revocation_head_json,
    private_provider_composition_sha256,
    signed_private_provider_revocation_head,
    verify_private_provider_revocation_head,
)
from substrate.midnight_oil.private_provider_policy import (
    OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
    PrivateProviderProcessingCapabilityV1,
    PrivateProviderRevocationSnapshotV1,
    signed_private_provider_capability,
    signed_private_provider_revocation_snapshot,
)
from substrate.midnight_oil.substack_authorization import (
    SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
)

_CAP_PRIVATE = bytes(range(32))
_REV_PRIVATE = bytes(range(32, 64))
_CAP_KEY_ID = "private-capability-issuer-2026-07"
_REV_KEY_ID = "private-revocation-issuer-2026-07"


def _public(private: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(private).public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


_CAP_PUBLIC = _public(_CAP_PRIVATE)
_REV_PUBLIC = _public(_REV_PRIVATE)


def _competing_child_process(
    path: str,
    floor_json: str,
    child_json: str,
    start: Any,
    results: Any,
) -> None:
    floor = parse_private_provider_revocation_head_json(floor_json)
    child = parse_private_provider_revocation_head_json(child_json)
    store = DurablePrivateProviderRevocationHeadStore(
        path,
        verification_keys={_REV_KEY_ID: _REV_PUBLIC},
        trusted_floor_sha256=floor.head_sha256,
    )
    store.admit_trusted_floor(floor)
    start.wait()
    outcome = store.compare_and_set(
        expected_head_sha256=floor.head_sha256,
        next_head=child,
        now_ms=child.issued_at_ms,
    )
    results.put((outcome.applied, outcome.current.head_sha256))


def _snapshot(
    *, epoch: int, issued_at_ms: int, revoked: tuple[str, ...] = ()
) -> PrivateProviderRevocationSnapshotV1:
    return signed_private_provider_revocation_snapshot(
        epoch=epoch,
        issued_at_ms=issued_at_ms,
        revoked_capability_sha256s=revoked,
        key_id=_REV_KEY_ID,
        signing_key=_REV_PRIVATE,
    )


def _head(
    *,
    epoch: int,
    issued_at_ms: int,
    previous: str = "0" * 64,
    revoked: tuple[str, ...] = (),
) -> PrivateProviderRevocationHeadV1:
    return signed_private_provider_revocation_head(
        snapshot=_snapshot(epoch=epoch, issued_at_ms=issued_at_ms, revoked=revoked),
        previous_head_sha256=previous,
        key_id=_REV_KEY_ID,
        signing_key=_REV_PRIVATE,
    )


def _capability(
    *, revocation_epoch: int = 0, provider_id: str = "openai-private-project"
) -> PrivateProviderProcessingCapabilityV1:
    return signed_private_provider_capability(
        {
            "schema_version": 1,
            "purpose": "midnight_oil_owner_private_substack_research",
            "provider_id": provider_id,
            "model_id": "gpt-private",
            "route_key": f"{provider_id}/gpt-private",
            "api_mode": "responses_no_store",
            "processing_region": "us",
            "endpoint_origin_sha256": "1" * 64,
            "account_project_scope_sha256": "2" * 64,
            "adapter_contract_sha256": "3" * 64,
            "dispatch_config_sha256": "4" * 64,
            "allowed_router_roles": ("gatherer", "synthesizer", "verifier"),
            "max_private_input_bytes": 8_192,
            "max_output_bytes": 1_000_000,
            "provider_constraints_sha256": SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
            "evidence_ref": "urn:test:private-provider-composition",
            "evidence_sha256": "5" * 64,
            "evidence_observed_at_ms": 900,
            "output_policy_sha256": OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
            "revocation_epoch": revocation_epoch,
            "issued_at_ms": 1_000,
            "not_before_ms": 1_000,
            "expires_at_ms": 1_000_000,
        },
        key_id=_CAP_KEY_ID,
        signing_key=_CAP_PRIVATE,
    )


def _store(
    tmp_path: Path, floor: PrivateProviderRevocationHeadV1
) -> DurablePrivateProviderRevocationHeadStore:
    store = DurablePrivateProviderRevocationHeadStore(
        tmp_path / "revocations.sqlite3",
        verification_keys={_REV_KEY_ID: _REV_PUBLIC},
        trusted_floor_sha256=floor.head_sha256,
    )
    store.admit_trusted_floor(floor)
    return store


def test_head_is_ed25519_signed_nested_and_validation_bypass_safe() -> None:
    genesis = _head(epoch=0, issued_at_ms=1_000)
    assert genesis.head_sha256 == (
        "2787fb2cca0ef9580208f9a54d58cc3161e8e6b3b257d13bece42159b02811e0"
    )
    assert genesis.signature_ed25519 == (
        "2b102d26dbfb3cd0c7b23d8a4f3869c071d23279df458cd0e294d0695290d975"
        "04d93e928678242dfb19d7c163c14d3bf9b345fa630cc3faaa1edb917e7dfe00"
    )
    assert genesis.confers_execution_authority is False
    assert len(genesis.signature_ed25519) == 128
    verify_private_provider_revocation_head(
        genesis, verification_keys={_REV_KEY_ID: _REV_PUBLIC}
    )
    assert parse_private_provider_revocation_head_json(genesis.model_dump_json()) == genesis
    bypassed = genesis.model_copy(update={"issued_at_ms": 999})
    with pytest.raises(ValueError, match="unavailable"):
        verify_private_provider_revocation_head(
            bypassed, verification_keys={_REV_KEY_ID: _REV_PUBLIC}
        )
    forged_with_public_bytes = signed_private_provider_revocation_head(
        snapshot=genesis.snapshot,
        previous_head_sha256=genesis.previous_head_sha256,
        key_id=_REV_KEY_ID,
        signing_key=_REV_PUBLIC,
    )
    with pytest.raises(ValueError, match="unavailable"):
        verify_private_provider_revocation_head(
            forged_with_public_bytes,
            verification_keys={_REV_KEY_ID: _REV_PUBLIC},
        )


def test_store_enforces_floor_successor_superset_cas_and_restart(tmp_path: Path) -> None:
    revoked = "a" * 64
    genesis = _head(epoch=0, issued_at_ms=1_000)
    store = _store(tmp_path, genesis)
    assert store.current(now_ms=1_000) == genesis
    successor = _head(
        epoch=1,
        issued_at_ms=2_000,
        previous=genesis.head_sha256,
        revoked=(revoked,),
    )
    applied = store.compare_and_set(
        expected_head_sha256=genesis.head_sha256,
        next_head=successor,
        now_ms=2_000,
    )
    assert applied.applied is True
    assert applied.current == successor
    replay = store.compare_and_set(
        expected_head_sha256=successor.head_sha256,
        next_head=successor,
        now_ms=2_000,
    )
    assert replay.applied is False
    restarted = DurablePrivateProviderRevocationHeadStore(
        store.path,
        verification_keys={_REV_KEY_ID: _REV_PUBLIC},
        trusted_floor_sha256=genesis.head_sha256,
    )
    restarted.admit_trusted_floor(genesis)
    assert restarted.current(now_ms=2_000) == successor
    losing_fork = _head(
        epoch=1,
        issued_at_ms=2_001,
        previous=genesis.head_sha256,
        revoked=("b" * 64,),
    )
    lost = restarted.compare_and_set(
        expected_head_sha256=genesis.head_sha256,
        next_head=losing_fork,
        now_ms=2_001,
    )
    assert lost.applied is False
    assert lost.current == successor
    omission = _head(
        epoch=2,
        issued_at_ms=3_000,
        previous=successor.head_sha256,
    )
    with pytest.raises(ValueError, match="successor conflicts"):
        restarted.compare_and_set(
            expected_head_sha256=successor.head_sha256,
            next_head=omission,
            now_ms=3_000,
        )


def test_store_rejects_stale_future_wrong_floor_and_corrupt_history(tmp_path: Path) -> None:
    genesis = _head(epoch=0, issued_at_ms=1_000)
    store = _store(tmp_path, genesis)
    with pytest.raises(ValueError, match="stale"):
        store.current(now_ms=301_001)
    with pytest.raises(ValueError, match="stale"):
        store.current(now_ms=999)
    wrong = DurablePrivateProviderRevocationHeadStore(
        tmp_path / "wrong.sqlite3",
        verification_keys={_REV_KEY_ID: _REV_PUBLIC},
        trusted_floor_sha256="f" * 64,
    )
    with pytest.raises(ValueError, match="floor conflicts"):
        wrong.admit_trusted_floor(genesis)
    connection = sqlite3.connect(store.path)
    connection.execute(
        "UPDATE private_provider_revocation_heads SET document_json = ?",
        [json.dumps({"corrupt": True})],
    )
    connection.commit()
    connection.close()
    with pytest.raises(InvalidPrivateProviderRevocationStore, match="chain is invalid"):
        store.current(now_ms=1_000)


def test_store_rejects_valid_signed_document_substituted_into_another_row(
    tmp_path: Path,
) -> None:
    genesis = _head(epoch=0, issued_at_ms=1_000)
    store = _store(tmp_path, genesis)
    successor = _head(
        epoch=1,
        issued_at_ms=2_000,
        previous=genesis.head_sha256,
        revoked=("a" * 64,),
    )
    assert store.compare_and_set(
        expected_head_sha256=genesis.head_sha256,
        next_head=successor,
        now_ms=2_000,
    ).applied
    connection = sqlite3.connect(store.path)
    connection.execute(
        "UPDATE private_provider_revocation_heads SET document_json = ? "
        "WHERE head_sha256 = ?",
        [genesis.model_dump_json(), successor.head_sha256],
    )
    connection.commit()
    connection.close()
    with pytest.raises(InvalidPrivateProviderRevocationStore, match="durable row"):
        store.current(now_ms=2_000)


def test_store_rejects_lookalike_schema_without_required_constraints(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lookalike.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE private_provider_revocation_schema (
            singleton INTEGER PRIMARY KEY,
            schema_version INTEGER NOT NULL
        );
        CREATE TABLE private_provider_revocation_heads (
            head_sha256 TEXT PRIMARY KEY,
            epoch BIGINT NOT NULL,
            previous_head_sha256 TEXT NOT NULL,
            issued_at_ms BIGINT NOT NULL,
            document_json TEXT NOT NULL
        );
        CREATE TABLE private_provider_revocation_current (
            registry_id TEXT PRIMARY KEY,
            head_sha256 TEXT NOT NULL
        );
        INSERT INTO private_provider_revocation_schema VALUES (1, 1);
        """
    )
    connection.commit()
    connection.close()
    with pytest.raises(InvalidPrivateProviderRevocationStore, match="schema"):
        DurablePrivateProviderRevocationHeadStore(
            path,
            verification_keys={_REV_KEY_ID: _REV_PUBLIC},
            trusted_floor_sha256="a" * 64,
        )


def test_store_rejects_partial_initialization_and_missing_predecessor(
    tmp_path: Path,
) -> None:
    genesis = _head(epoch=0, issued_at_ms=1_000)
    partial = _store(tmp_path / "partial", genesis)
    connection = sqlite3.connect(partial.path)
    connection.execute("DELETE FROM private_provider_revocation_current")
    connection.commit()
    connection.close()
    with pytest.raises(InvalidPrivateProviderRevocationStore, match="partially initialized"):
        partial.admit_trusted_floor(genesis)

    complete = _store(tmp_path / "missing", genesis)
    successor = _head(
        epoch=1,
        issued_at_ms=2_000,
        previous=genesis.head_sha256,
        revoked=("a" * 64,),
    )
    assert complete.compare_and_set(
        expected_head_sha256=genesis.head_sha256,
        next_head=successor,
        now_ms=2_000,
    ).applied
    connection = sqlite3.connect(complete.path)
    connection.execute(
        "DELETE FROM private_provider_revocation_heads WHERE head_sha256 = ?",
        [genesis.head_sha256],
    )
    connection.commit()
    connection.close()
    with pytest.raises(InvalidPrivateProviderRevocationStore, match="lost its trusted floor"):
        complete.current(now_ms=2_000)


def test_store_reanchors_to_new_external_floor_and_prunes_only_older_history(
    tmp_path: Path,
) -> None:
    genesis = _head(epoch=0, issued_at_ms=1_000)
    store = _store(tmp_path, genesis)
    successor = _head(
        epoch=1,
        issued_at_ms=2_000,
        previous=genesis.head_sha256,
        revoked=("a" * 64,),
    )
    assert store.compare_and_set(
        expected_head_sha256=genesis.head_sha256,
        next_head=successor,
        now_ms=2_000,
    ).applied
    reanchored = DurablePrivateProviderRevocationHeadStore(
        store.path,
        verification_keys={_REV_KEY_ID: _REV_PUBLIC},
        trusted_floor_sha256=successor.head_sha256,
    )
    reanchored.admit_trusted_floor(successor)
    assert reanchored.current(now_ms=2_000) == successor
    connection = sqlite3.connect(store.path)
    rows = connection.execute(
        "SELECT head_sha256 FROM private_provider_revocation_heads"
    ).fetchall()
    connection.close()
    assert rows == [(successor.head_sha256,)]
    rolled_back_floor = DurablePrivateProviderRevocationHeadStore(
        store.path,
        verification_keys={_REV_KEY_ID: _REV_PUBLIC},
        trusted_floor_sha256=genesis.head_sha256,
    )
    with pytest.raises(InvalidPrivateProviderRevocationStore, match="not in current history"):
        rolled_back_floor.admit_trusted_floor(genesis)


def test_two_process_competing_children_leave_one_winner_and_no_orphan(
    tmp_path: Path,
) -> None:
    genesis = _head(epoch=0, issued_at_ms=1_000)
    store = _store(tmp_path, genesis)
    first = _head(
        epoch=1,
        issued_at_ms=2_000,
        previous=genesis.head_sha256,
        revoked=("a" * 64,),
    )
    second = _head(
        epoch=1,
        issued_at_ms=2_001,
        previous=genesis.head_sha256,
        revoked=("b" * 64,),
    )
    context = get_context("spawn")
    start = context.Event()
    results = context.Queue()
    processes = tuple(
        context.Process(
            target=_competing_child_process,
            args=(
                str(store.path),
                genesis.model_dump_json(),
                child.model_dump_json(),
                start,
                results,
            ),
        )
        for child in (first, second)
    )
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    outcomes = (results.get(timeout=2), results.get(timeout=2))
    assert sorted(applied for applied, _ in outcomes) == [False, True]
    current_hashes = {current for _, current in outcomes}
    assert len(current_hashes) == 1
    connection = sqlite3.connect(store.path)
    rows = connection.execute(
        "SELECT head_sha256 FROM private_provider_revocation_heads"
    ).fetchall()
    connection.close()
    assert {row[0] for row in rows} == {genesis.head_sha256, *current_hashes}


def test_cas_never_commits_row_beyond_bound_and_reanchor_restores_capacity(
    tmp_path: Path,
) -> None:
    genesis = _head(epoch=0, issued_at_ms=1_000)
    store = _store(tmp_path, genesis)
    heads = [genesis]
    for epoch in range(1, MAX_PRIVATE_PROVIDER_HEAD_CHAIN):
        heads.append(
            _head(
                epoch=epoch,
                issued_at_ms=1_000 + epoch,
                previous=heads[-1].head_sha256,
            )
        )
    connection = sqlite3.connect(store.path)
    connection.executemany(
        "INSERT INTO private_provider_revocation_heads "
        "(head_sha256, epoch, previous_head_sha256, issued_at_ms, document_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            (
                head.head_sha256,
                head.epoch,
                head.previous_head_sha256,
                head.issued_at_ms,
                head.model_dump_json(),
            )
            for head in heads[1:]
        ),
    )
    connection.execute(
        "UPDATE private_provider_revocation_current SET head_sha256 = ?",
        [heads[-1].head_sha256],
    )
    connection.commit()
    connection.close()
    assert store.current(now_ms=heads[-1].issued_at_ms) == heads[-1]
    blocked = _head(
        epoch=MAX_PRIVATE_PROVIDER_HEAD_CHAIN,
        issued_at_ms=heads[-1].issued_at_ms + 1,
        previous=heads[-1].head_sha256,
    )
    with pytest.raises(InvalidPrivateProviderRevocationStore, match="re-anchoring"):
        store.compare_and_set(
            expected_head_sha256=heads[-1].head_sha256,
            next_head=blocked,
            now_ms=blocked.issued_at_ms,
        )
    connection = sqlite3.connect(store.path)
    assert connection.execute(
        "SELECT COUNT(*) FROM private_provider_revocation_heads"
    ).fetchone() == (MAX_PRIVATE_PROVIDER_HEAD_CHAIN,)
    connection.close()
    reanchored = DurablePrivateProviderRevocationHeadStore(
        store.path,
        verification_keys={_REV_KEY_ID: _REV_PUBLIC},
        trusted_floor_sha256=heads[-1].head_sha256,
    )
    reanchored.admit_trusted_floor(heads[-1])
    assert reanchored.compare_and_set(
        expected_head_sha256=heads[-1].head_sha256,
        next_head=blocked,
        now_ms=blocked.issued_at_ms,
    ).applied


def _composition_files(
    tmp_path: Path,
) -> tuple[
    dict[str, str], PrivateProviderProcessingCapabilityV1, PrivateProviderRevocationHeadV1
]:
    capability = _capability()
    floor = _head(epoch=0, issued_at_ms=1_000)
    capability_path = tmp_path / "capability.json"
    floor_path = tmp_path / "floor.json"
    capability_path.write_text(capability.model_dump_json(), encoding="utf-8")
    floor_path.write_text(floor.model_dump_json(), encoding="utf-8")
    environment = {
        PRIVATE_PROVIDER_CAPABILITY_KEYRING_ENVS_ENV: json.dumps(
            {_CAP_KEY_ID: "PRIVATE_CAPABILITY_PUBLIC_KEY"}
        ),
        PRIVATE_PROVIDER_REVOCATION_KEYRING_ENVS_ENV: json.dumps(
            {_REV_KEY_ID: "PRIVATE_REVOCATION_PUBLIC_KEY"}
        ),
        PRIVATE_PROVIDER_CAPABILITY_PATHS_ENV: json.dumps([str(capability_path)]),
        PRIVATE_PROVIDER_TRUSTED_FLOOR_PATH_ENV: str(floor_path),
        PRIVATE_PROVIDER_TRUSTED_FLOOR_SHA256_ENV: floor.head_sha256,
        PRIVATE_PROVIDER_EXPECTED_CURRENT_PATH_ENV: str(floor_path),
        PRIVATE_PROVIDER_EXPECTED_CURRENT_SHA256_ENV: floor.head_sha256,
        "PRIVATE_CAPABILITY_PUBLIC_KEY": base64.urlsafe_b64encode(_CAP_PUBLIC)
        .decode()
        .rstrip("="),
        "PRIVATE_REVOCATION_PUBLIC_KEY": base64.urlsafe_b64encode(_REV_PUBLIC)
        .decode()
        .rstrip("="),
    }
    environment[PRIVATE_PROVIDER_EXPECTED_COMPOSITION_SHA256_ENV] = (
        private_provider_composition_sha256(
            capabilities=(capability,),
            capability_keys={_CAP_KEY_ID: _CAP_PUBLIC},
            revocation_keys={_REV_KEY_ID: _REV_PUBLIC},
            floor=floor,
            current=floor,
            state_path=tmp_path / "state" / "private-provider-revocations.sqlite3",
        )
    )
    return environment, capability, floor


def test_composition_is_optional_closed_distinct_and_restart_identical(
    tmp_path: Path,
) -> None:
    assert (
        build_private_provider_composition(
            state_dir=tmp_path / "absent", environ={}, now_ms=1_000
        )
        is None
    )
    environment, capability, floor = _composition_files(tmp_path)
    first = build_private_provider_composition(
        state_dir=tmp_path / "state", environ=environment, now_ms=1_000
    )
    second = build_private_provider_composition(
        state_dir=tmp_path / "state", environ=environment, now_ms=1_000
    )
    assert first is not None and second is not None
    assert first.confers_execution_authority is False
    assert first.capability_hashes == second.capability_hashes == (
        capability.capability_sha256,
    )
    assert first.current_head == second.current_head == floor
    assert first.capability_key_ids == (_CAP_KEY_ID,)
    assert first.revocation_key_ids == (_REV_KEY_ID,)
    partial = dict(environment)
    partial.pop(PRIVATE_PROVIDER_TRUSTED_FLOOR_SHA256_ENV)
    with pytest.raises(ValueError, match="incomplete"):
        build_private_provider_composition(
            state_dir=tmp_path / "partial", environ=partial, now_ms=1_000
        )
    collision = dict(environment)
    collision[PRIVATE_PROVIDER_REVOCATION_KEYRING_ENVS_ENV] = json.dumps(
        {_REV_KEY_ID: "PRIVATE_CAPABILITY_PUBLIC_KEY"}
    )
    with pytest.raises(ValueError, match="reuse"):
        build_private_provider_composition(
            state_dir=tmp_path / "collision", environ=collision, now_ms=1_000
        )


def test_composition_admits_exact_signed_successor_once_under_concurrency(
    tmp_path: Path,
) -> None:
    environment, capability, floor = _composition_files(tmp_path)
    state = tmp_path / "state"
    initial = build_private_provider_composition(
        state_dir=state, environ=environment, now_ms=1_000
    )
    assert initial is not None and initial.current_head == floor
    successor = _head(
        epoch=1,
        issued_at_ms=2_000,
        previous=floor.head_sha256,
        revoked=("a" * 64,),
    )
    successor_path = tmp_path / "successor.json"
    successor_path.write_text(successor.model_dump_json(), encoding="utf-8")
    environment[PRIVATE_PROVIDER_EXPECTED_CURRENT_PATH_ENV] = str(successor_path)
    environment[PRIVATE_PROVIDER_EXPECTED_CURRENT_SHA256_ENV] = successor.head_sha256
    environment[PRIVATE_PROVIDER_EXPECTED_COMPOSITION_SHA256_ENV] = (
        private_provider_composition_sha256(
            capabilities=(capability,),
            capability_keys={_CAP_KEY_ID: _CAP_PUBLIC},
            revocation_keys={_REV_KEY_ID: _REV_PUBLIC},
            floor=floor,
            current=successor,
            state_path=state / "private-provider-revocations.sqlite3",
        )
    )

    def compose() -> str:
        result = build_private_provider_composition(
            state_dir=state, environ=environment, now_ms=2_000
        )
        assert result is not None
        return result.current_head.head_sha256

    with ThreadPoolExecutor(max_workers=2) as pool:
        current_hashes = tuple(pool.map(lambda _: compose(), range(2)))
    assert current_hashes == (successor.head_sha256, successor.head_sha256)
    connection = sqlite3.connect(state / "private-provider-revocations.sqlite3")
    rows = connection.execute(
        "SELECT head_sha256, epoch FROM private_provider_revocation_heads "
        "ORDER BY epoch"
    ).fetchall()
    connection.close()
    assert rows == [(floor.head_sha256, 0), (successor.head_sha256, 1)]


def test_composition_rejects_expected_current_that_skips_persisted_head(
    tmp_path: Path,
) -> None:
    environment, capability, floor = _composition_files(tmp_path)
    state = tmp_path / "state"
    assert build_private_provider_composition(
        state_dir=state, environ=environment, now_ms=1_000
    ) is not None
    successor = _head(
        epoch=1,
        issued_at_ms=2_000,
        previous=floor.head_sha256,
        revoked=("a" * 64,),
    )
    skipped = _head(
        epoch=2,
        issued_at_ms=3_000,
        previous=successor.head_sha256,
        revoked=("a" * 64, "b" * 64),
    )
    skipped_path = tmp_path / "skipped.json"
    skipped_path.write_text(skipped.model_dump_json(), encoding="utf-8")
    environment[PRIVATE_PROVIDER_EXPECTED_CURRENT_PATH_ENV] = str(skipped_path)
    environment[PRIVATE_PROVIDER_EXPECTED_CURRENT_SHA256_ENV] = skipped.head_sha256
    environment[PRIVATE_PROVIDER_EXPECTED_COMPOSITION_SHA256_ENV] = (
        private_provider_composition_sha256(
            capabilities=(capability,),
            capability_keys={_CAP_KEY_ID: _CAP_PUBLIC},
            revocation_keys={_REV_KEY_ID: _REV_PUBLIC},
            floor=floor,
            current=skipped,
            state_path=state / "private-provider-revocations.sqlite3",
        )
    )
    with pytest.raises(ValueError, match="successor conflicts"):
        build_private_provider_composition(
            state_dir=state, environ=environment, now_ms=3_000
        )


def test_external_composition_pin_rejects_path_and_keyring_divergence(
    tmp_path: Path,
) -> None:
    environment, _, _ = _composition_files(tmp_path)
    with pytest.raises(ValueError, match="fingerprint conflicts"):
        build_private_provider_composition(
            state_dir=tmp_path / "different-state",
            environ=environment,
            now_ms=1_000,
        )
    assert not (tmp_path / "different-state").exists()
    divergent = dict(environment)
    extra_public = _public(b"x" * 32)
    divergent[PRIVATE_PROVIDER_CAPABILITY_KEYRING_ENVS_ENV] = json.dumps(
        {
            _CAP_KEY_ID: "PRIVATE_CAPABILITY_PUBLIC_KEY",
            "private-capability-issuer-extra": "PRIVATE_CAPABILITY_PUBLIC_KEY_EXTRA",
        }
    )
    divergent["PRIVATE_CAPABILITY_PUBLIC_KEY_EXTRA"] = (
        base64.urlsafe_b64encode(extra_public).decode().rstrip("=")
    )
    with pytest.raises(ValueError, match="fingerprint conflicts"):
        build_private_provider_composition(
            state_dir=tmp_path / "state", environ=divergent, now_ms=1_000
        )
    divergent_capability = _capability(provider_id="another-private-project")
    divergent_capability_path = tmp_path / "divergent-capability.json"
    divergent_capability_path.write_text(
        divergent_capability.model_dump_json(), encoding="utf-8"
    )
    divergent = dict(environment)
    divergent[PRIVATE_PROVIDER_CAPABILITY_PATHS_ENV] = json.dumps(
        [str(divergent_capability_path)]
    )
    with pytest.raises(ValueError, match="fingerprint conflicts"):
        build_private_provider_composition(
            state_dir=tmp_path / "state", environ=divergent, now_ms=1_000
        )
