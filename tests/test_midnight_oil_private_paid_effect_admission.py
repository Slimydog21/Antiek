from __future__ import annotations

import ast
import base64
import inspect
import json
import multiprocessing
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import substrate.midnight_oil.private_paid_effect_admission as paid_effect_module
from substrate.midnight_oil.private_paid_effect_admission import (
    MAX_ADMISSION_CIPHERTEXT_BYTES,
    MAX_ADMISSION_PLAINTEXT_BYTES,
    MAX_ADMISSIONS,
    MAX_DB_PAGES,
    MAX_FIXTURE_VERIFICATION_KEYS,
    MAX_MARKERS,
    MAX_OPEN_MARKERS,
    NONCE_COLLISION_RETRIES,
    PRIVATE_PAID_EFFECT_ADMISSION_CYCLE33_CONTRACT_SHA256,
    PRIVATE_PAID_EFFECT_ADMISSION_MODULE_SOURCE_SHA256,
    FixtureAdmissionCandidateV1,
    FixtureSourceReceiptPairV1,
    PrivatePaidEffectAdmissionCycle33ContractV1,
    PrivatePaidEffectAdmissionFixtureRejected,
    PrivatePaidEffectAdmissionFixtureStoreV1,
    build_private_paid_effect_admission_cycle33_contract_v1,
    parse_signed_fixture_authority_pair_v1_json,
    private_paid_effect_admission_module_source_sha256,
    require_private_paid_effect_admission_cycle33_contract,
    verify_signed_fixture_authority_pair_v1,
)
from tests.support.private_paid_effect_admission_v1 import (
    CAPABILITY_HEAD_0,
    CAPABILITY_HEAD_1,
    DATA_KEY,
    KEY_VERSION,
    OWNER_PATH_DISCRIMINATOR,
    PAIR_KEY_ID,
    SOURCE_HEAD_0,
    STORE_ID,
    CrashAfterAdmissionInsertFixtureStoreV1,
    admission_candidate,
    fixture_pair_verification_keys,
    fixture_store_case,
    genesis_pair,
    public_key,
    successor_pair,
)


def _candidate_wire(candidate: FixtureAdmissionCandidateV1) -> bytes:
    return json.dumps(
        candidate.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def _receipt_pairs(count: int) -> tuple[FixtureSourceReceiptPairV1, ...]:
    return tuple(
        FixtureSourceReceiptPairV1(
            receipt_id="opsr5_" + f"{index:024x}",
            receipt_sha256=f"{index + 1:064x}",
        )
        for index in range(count)
    )


def _seed_structural_rows(database: Path, *, marker_count: int, admission_count: int) -> None:
    if not 0 <= admission_count <= marker_count:
        raise ValueError
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executemany(
            "INSERT INTO private_paid_effect_fixture_exposure_markers "
            "(logical_effect_key,hold_id,owner_path_discriminator,projected_max_cents,"
            "exposure_state,created_at_ms,released_at_ms) VALUES (?,?,?,?,?,?,?)",
            (
                (
                    "mopeffect1_" + f"{index:064x}",
                    "mophold1_" + f"{index:064x}",
                    OWNER_PATH_DISCRIMINATOR,
                    1,
                    "released",
                    0,
                    0,
                )
                for index in range(1, marker_count + 1)
            ),
        )
        connection.executemany(
            "INSERT INTO private_paid_effect_fixture_admissions "
            "(admission_id,logical_effect_key,hold_id,owner_path_discriminator,"
            "fixture_pair_sha256,authority_revision,projected_max_cents,categorical_state,"
            "created_at_ms,aead_suite,key_version,nonce_length,nonce,ciphertext_schema,"
            "ciphertext_type,ciphertext_length,ciphertext) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                (
                    "moadmit1_" + f"{index:064x}",
                    "mopeffect1_" + f"{index:064x}",
                    "mophold1_" + f"{index:064x}",
                    OWNER_PATH_DISCRIMINATOR,
                    "01" * 32,
                    0,
                    1,
                    "admission_committed",
                    0,
                    "aes-256-gcm",
                    KEY_VERSION,
                    12,
                    index.to_bytes(12),
                    "private_paid_effect_admission_fixture_v1_json",
                    "application/json",
                    16,
                    b"x" * 16,
                )
                for index in range(1, admission_count + 1)
            ),
        )


def _candidate_mutation_value(field: str, candidate: FixtureAdmissionCandidateV1) -> object:
    false_literals = {
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
        "live_authority_verified",
        "user_accounting_effect",
        "transport_reachable",
    }
    hash_fields = {
        "fixture_pair_sha256",
        "capability_head_sha256",
        "source_head_sha256",
        "consent_receipt_sha256",
        "consent_config_sha256",
        "policy_v4_sha256",
        "capability_v4_sha256",
        "core_v4_sha256",
        "receipt_v7_sha256",
        "envelope_v4_sha256",
        "request_material_sha256",
    }
    integer_fields = {
        "projected_max_cents",
        "authority_revision",
        "capability_epoch",
        "source_epoch",
        "owner_job_state_version",
        "lease_generation",
        "lease_exclusive_until_ms",
        "source_revision",
        "approved_ceiling_cents",
        "maximum_output_bytes",
    }
    fixed_values: dict[str, object] = {
        "schema_version": 2,
        "owner_path_discriminator": "opspd1_" + "91" * 32,
        "logical_effect_key": "mopeffect1_" + "92" * 32,
        "hold_id": "mophold1_" + "93" * 32,
        "capability_registry_id": "capability.registry.changed",
        "source_registry_id": "source.registry.changed",
        "router_role": "verifier",
        "source_selector": "opsbs1_" + "94" * 32,
        "source_receipt_pairs": _receipt_pairs(2),
        "provider_scoped_idempotency_key": "idem-fixture-changed",
        "fixture_authority_only": False,
    }
    if field in fixed_values:
        return fixed_values[field]
    if field in false_literals:
        return True
    if field in hash_fields:
        return "95" * 32
    if field in integer_fields:
        return int(getattr(candidate, field)) + 1
    value = getattr(candidate, field)
    if type(value) is str:
        return "changed-" + field
    raise AssertionError(f"missing candidate mutation for {field}")


def _admission_process_worker(root: str, candidate_wire: bytes, start: Any, results: Any) -> None:
    case = fixture_store_case(Path(root))
    candidate = FixtureAdmissionCandidateV1.model_validate_json(candidate_wire)
    start.wait()
    try:
        evidence = case.store.admit_fixture_effect(
            expected_authority_revision=candidate.authority_revision,
            expected_capability_head=candidate.capability_head_sha256,
            expected_source_head=candidate.source_head_sha256,
            hold_id=candidate.hold_id,
            candidate=candidate,
            now_ms=1_020,
        )
        results.put("replay" if evidence.replayed else "first")
    except PrivatePaidEffectAdmissionFixtureRejected:
        results.put("rejected")


def _cas_process_worker(root: str, pair_wire: bytes, start: Any, results: Any) -> None:
    case = fixture_store_case(Path(root))
    pair = type(case.genesis).model_validate_json(pair_wire)
    start.wait()
    try:
        result = case.store.compare_and_set_fixture_authority_pair(
            expected_revision=0,
            expected_capability_head=case.genesis.capability_head_sha256,
            expected_source_head=case.genesis.source_head_sha256,
            signed_fixture_pair=pair,
            now_ms=1_100,
        )
        results.put("applied" if result.applied else "replay")
    except PrivatePaidEffectAdmissionFixtureRejected:
        results.put("rejected")


def _abrupt_after_insert_before_commit_worker(root: str, candidate_wire: bytes) -> None:
    case = fixture_store_case(Path(root))
    candidate = FixtureAdmissionCandidateV1.model_validate_json(candidate_wire)
    crash_store = CrashAfterAdmissionInsertFixtureStoreV1(
        case.store.path,
        owner_path_authority=case.authority,
        owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
        store_id=STORE_ID,
        key_version=KEY_VERSION,
        fixture_authority_verification_keys=fixture_pair_verification_keys(),
        key_provider=case.key_provider,
    )
    crash_store.admit_fixture_effect(
        expected_authority_revision=candidate.authority_revision,
        expected_capability_head=candidate.capability_head_sha256,
        expected_source_head=candidate.source_head_sha256,
        hold_id=candidate.hold_id,
        candidate=candidate,
        now_ms=1_020,
    )


def _abrupt_after_admission_worker(root: str, candidate_wire: bytes) -> None:
    case = fixture_store_case(Path(root))
    candidate = FixtureAdmissionCandidateV1.model_validate_json(candidate_wire)
    case.store.admit_fixture_effect(
        expected_authority_revision=candidate.authority_revision,
        expected_capability_head=candidate.capability_head_sha256,
        expected_source_head=candidate.source_head_sha256,
        hold_id=candidate.hold_id,
        candidate=candidate,
        now_ms=1_020,
    )
    os._exit(0)


def test_module_identity_and_no_signer_surface() -> None:
    assert (
        private_paid_effect_admission_module_source_sha256()
        == PRIVATE_PAID_EFFECT_ADMISSION_MODULE_SOURCE_SHA256
    )
    imported = {
        alias.name
        for node in ast.walk(
            ast.parse(Path("substrate/midnight_oil/private_paid_effect_admission.py").read_text())
        )
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "Ed25519PrivateKey" not in imported
    assert "requests" not in imported
    assert "httpx" not in imported
    store_id = inspect.signature(PrivatePaidEffectAdmissionFixtureStoreV1).parameters["store_id"]
    assert store_id.default is inspect.Parameter.empty
    assert store_id.annotation == "str"


def test_cycle33_declarative_contract_identity_and_one_bit_drift() -> None:
    contract = build_private_paid_effect_admission_cycle33_contract_v1()
    assert contract.contract_sha256 == PRIVATE_PAID_EFFECT_ADMISSION_CYCLE33_CONTRACT_SHA256
    assert contract.module_source_sha256 == PRIVATE_PAID_EFFECT_ADMISSION_MODULE_SOURCE_SHA256
    assert len(contract.tables) == 4
    assert contract.admission_framing_fields == paid_effect_module._CYCLE33_ADMISSION_FRAMING_FIELDS
    require_private_paid_effect_admission_cycle33_contract()

    raw = contract.model_dump(mode="python")
    final_bit = "0" if contract.schema_ddl_sha256[-1] != "0" else "1"
    raw["schema_ddl_sha256"] = contract.schema_ddl_sha256[:-1] + final_bit
    with pytest.raises(ValidationError):
        PrivatePaidEffectAdmissionCycle33ContractV1.model_validate(raw)


def test_candidate_receipt_roles_and_exact_shape() -> None:
    pair = genesis_pair()
    planner = admission_candidate(
        logical_effect_key="mopeffect1_" + "01" * 32,
        hold_id="mophold1_" + "02" * 32,
        projected_max_cents=123,
        authority=pair,
        router_role="planner",
    )
    assert planner.source_receipt_pairs == ()

    receipt = FixtureSourceReceiptPairV1(
        receipt_id="opsr5_" + "03" * 12,
        receipt_sha256="04" * 32,
    )
    with pytest.raises(ValidationError):
        admission_candidate(
            logical_effect_key=planner.logical_effect_key,
            hold_id=planner.hold_id,
            projected_max_cents=123,
            authority=pair,
            router_role="planner",
            source_receipt_pairs=(receipt,),
        )
    with pytest.raises(ValidationError):
        admission_candidate(
            logical_effect_key=planner.logical_effect_key,
            hold_id=planner.hold_id,
            projected_max_cents=123,
            authority=pair,
            router_role="verifier",
            source_receipt_pairs=(),
        )
    with pytest.raises(ValidationError):
        FixtureSourceReceiptPairV1.model_validate(
            {
                "receipt_id": "opsr5_" + "03" * 12,
                "receipt_sha256": "04" * 32,
                "exact_source_sha256": "05" * 32,
            }
        )


def test_receipt_pair_boundary_seven_eight_nine() -> None:
    pair = genesis_pair()
    for count in (7, 8):
        candidate = admission_candidate(
            logical_effect_key="mopeffect1_" + f"{count:064x}",
            hold_id="mophold1_" + f"{count:064x}",
            projected_max_cents=123,
            authority=pair,
            source_receipt_pairs=_receipt_pairs(count),
        )
        assert len(candidate.source_receipt_pairs) == count
    with pytest.raises(ValidationError):
        admission_candidate(
            logical_effect_key="mopeffect1_" + "09" * 32,
            hold_id="mophold1_" + "09" * 32,
            projected_max_cents=123,
            authority=pair,
            source_receipt_pairs=_receipt_pairs(9),
        )


def test_open_marker_boundary_sixty_three_sixty_four_sixty_five(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    for _ in range(MAX_OPEN_MARKERS - 1):
        case.store.reserve_fixture_exposure(projected_max_cents=1, now_ms=1_010)
    with sqlite3.connect(case.store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM private_paid_effect_fixture_exposure_markers "
            "WHERE exposure_state='open'"
        ).fetchone() == (MAX_OPEN_MARKERS - 1,)
    case.store.reserve_fixture_exposure(projected_max_cents=1, now_ms=1_010)
    with sqlite3.connect(case.store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM private_paid_effect_fixture_exposure_markers "
            "WHERE exposure_state='open'"
        ).fetchone() == (MAX_OPEN_MARKERS,)
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.reserve_fixture_exposure(projected_max_cents=1, now_ms=1_010)


def test_total_marker_boundary_1023_1024_1025(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    _seed_structural_rows(case.store.path, marker_count=MAX_MARKERS - 1, admission_count=0)
    with sqlite3.connect(case.store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM private_paid_effect_fixture_exposure_markers"
        ).fetchone() == (MAX_MARKERS - 1,)
    case.store.reserve_fixture_exposure(projected_max_cents=1, now_ms=1_010)
    with sqlite3.connect(case.store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM private_paid_effect_fixture_exposure_markers"
        ).fetchone() == (MAX_MARKERS,)
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.reserve_fixture_exposure(projected_max_cents=1, now_ms=1_010)


def test_total_admission_boundary_1023_1024_1025(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    _seed_structural_rows(
        case.store.path,
        marker_count=MAX_ADMISSIONS - 1,
        admission_count=MAX_ADMISSIONS - 1,
    )
    marker = case.store.reserve_fixture_exposure(projected_max_cents=1, now_ms=1_010)
    candidate = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=1,
        authority=case.genesis,
    )
    case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=marker.hold_id,
        candidate=candidate,
        now_ms=1_020,
    )
    with sqlite3.connect(case.store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM private_paid_effect_fixture_admissions"
        ).fetchone() == (MAX_ADMISSIONS,)
        extra_effect = "mopeffect1_" + f"{MAX_ADMISSIONS + 1:064x}"
        extra_hold = "mophold1_" + f"{MAX_ADMISSIONS + 1:064x}"
        connection.execute(
            "INSERT INTO private_paid_effect_fixture_exposure_markers "
            "(logical_effect_key,hold_id,owner_path_discriminator,projected_max_cents,"
            "exposure_state,created_at_ms,released_at_ms) VALUES (?,?,?,?,?,?,NULL)",
            (extra_effect, extra_hold, OWNER_PATH_DISCRIMINATOR, 1, "open", 1_010),
        )
    extra_candidate = admission_candidate(
        logical_effect_key=extra_effect,
        hold_id=extra_hold,
        projected_max_cents=1,
        authority=case.genesis,
    )
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.admit_fixture_effect(
            expected_authority_revision=0,
            expected_capability_head=case.genesis.capability_head_sha256,
            expected_source_head=case.genesis.source_head_sha256,
            hold_id=extra_hold,
            candidate=extra_candidate,
            now_ms=1_020,
        )
    with sqlite3.connect(case.store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM private_paid_effect_fixture_admissions"
        ).fetchone() == (MAX_ADMISSIONS,)


def test_signed_pair_verifier_rejects_bad_hash_signature_and_purpose() -> None:
    pair = genesis_pair()
    canonical = json.dumps(
        pair.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    parsed = parse_signed_fixture_authority_pair_v1_json(canonical)
    verify_signed_fixture_authority_pair_v1(
        parsed, verification_keys=fixture_pair_verification_keys()
    )

    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        verify_signed_fixture_authority_pair_v1(parsed, verification_keys={})
    boundary_keyring = {PAIR_KEY_ID: public_key()}
    boundary_keyring.update(
        {
            f"fixture-key-{index}": bytes([index]) * 32
            for index in range(1, MAX_FIXTURE_VERIFICATION_KEYS)
        }
    )
    verify_signed_fixture_authority_pair_v1(
        parsed,
        verification_keys=dict(list(boundary_keyring.items())[:-1]),
    )
    verify_signed_fixture_authority_pair_v1(parsed, verification_keys=boundary_keyring)
    oversized_keyring = {
        **boundary_keyring,
        "fixture-key-overflow": bytes([MAX_FIXTURE_VERIFICATION_KEYS]) * 32,
    }
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        verify_signed_fixture_authority_pair_v1(parsed, verification_keys=oversized_keyring)

    forged_literal = parsed.model_copy(update={"fixture_authority_only": False})
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        verify_signed_fixture_authority_pair_v1(
            forged_literal, verification_keys=fixture_pair_verification_keys()
        )

    with pytest.raises(ValidationError):
        type(parsed).model_validate(
            {
                **parsed.model_dump(mode="python"),
                "key_purpose": "owner_private_source_head_issuer_v1",
            }
        )

    duplicate = canonical.replace(b'"revision":0', b'"revision":0,"revision":0')
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        parse_signed_fixture_authority_pair_v1_json(duplicate)


def test_authority_init_cas_and_stale_or_invalid_successors_reject(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    initialized = case.store.initialize_fixture_authority_pair(
        signed_fixture_pair=case.genesis, now_ms=1_000
    )
    assert initialized.applied is True
    assert initialized.fixture_authority_only is True
    assert initialized.live_authority_verified is False
    assert initialized.user_accounting_effect is False
    assert initialized.transport_reachable is False

    exact = case.store.initialize_fixture_authority_pair(
        signed_fixture_pair=case.genesis, now_ms=999_999
    )
    assert exact.applied is False

    exact_cas = case.store.compare_and_set_fixture_authority_pair(
        expected_revision=0,
        expected_capability_head=CAPABILITY_HEAD_0,
        expected_source_head=SOURCE_HEAD_0,
        signed_fixture_pair=case.genesis,
        now_ms=999_999,
    )
    assert exact_cas.applied is False

    next_pair = successor_pair(case.genesis, issued_at_ms=1_100)
    advanced = case.store.compare_and_set_fixture_authority_pair(
        expected_revision=0,
        expected_capability_head=CAPABILITY_HEAD_0,
        expected_source_head=SOURCE_HEAD_0,
        signed_fixture_pair=next_pair,
        now_ms=1_100,
    )
    assert advanced.applied is True
    assert advanced.revision == 1
    assert advanced.capability_head_sha256 == CAPABILITY_HEAD_1

    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.compare_and_set_fixture_authority_pair(
            expected_revision=0,
            expected_capability_head=CAPABILITY_HEAD_0,
            expected_source_head=SOURCE_HEAD_0,
            signed_fixture_pair=next_pair,
            now_ms=1_101,
        )

    invalid = successor_pair(next_pair, capability_head_sha256=next_pair.capability_head_sha256)
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.compare_and_set_fixture_authority_pair(
            expected_revision=1,
            expected_capability_head=next_pair.capability_head_sha256,
            expected_source_head=next_pair.source_head_sha256,
            signed_fixture_pair=invalid,
            now_ms=1_102,
        )


def test_marker_admission_replay_release_and_key_clearing(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    marker = case.store.reserve_fixture_exposure(projected_max_cents=123, now_ms=1_010)
    assert marker.exposure_state == "open"
    assert marker.user_accounting_effect is False
    candidate = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=123,
        authority=case.genesis,
    )
    first = case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=marker.hold_id,
        candidate=candidate,
        now_ms=1_020,
    )
    assert first.replayed is False
    assert first.exposure_state == "open"
    assert first.transport_reachable is False

    next_pair = successor_pair(case.genesis, issued_at_ms=1_030)
    case.store.compare_and_set_fixture_authority_pair(
        expected_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        signed_fixture_pair=next_pair,
        now_ms=1_030,
    )
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.admit_fixture_effect(
            expected_authority_revision=next_pair.revision,
            expected_capability_head=next_pair.capability_head_sha256,
            expected_source_head=next_pair.source_head_sha256,
            hold_id=marker.hold_id,
            candidate=candidate,
            now_ms=99_000,
        )
    replay = case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=marker.hold_id,
        candidate=candidate,
        now_ms=99_000,
    )
    assert replay.replayed is True
    assert replay.admission_id == first.admission_id
    assert first.historical_fixture_pair_sha256 == case.genesis.pair_sha256
    assert replay.historical_fixture_pair_sha256 == case.genesis.pair_sha256
    assert replay.historical_authority_revision == 0
    assert replay.created_at_ms == first.created_at_ms

    release = case.store.release_fixture_unreachable_transport(
        admission_id=first.admission_id, hold_id=marker.hold_id, now_ms=99_001
    )
    assert release.applied is True
    release_replay = case.store.release_fixture_unreachable_transport(
        admission_id=first.admission_id, hold_id=marker.hold_id, now_ms=99_999
    )
    assert release_replay.applied is False
    assert release_replay.released_at_ms == release.released_at_ms

    replay_after_release = case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=marker.hold_id,
        candidate=candidate,
        now_ms=100_000,
    )
    assert replay_after_release.exposure_state == "released"
    case.key_provider.assert_all_opened_keys_cleared()


def test_authoritative_join_drift_and_replay_candidate_drift_reject(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    marker = case.store.reserve_fixture_exposure(projected_max_cents=123, now_ms=1_010)
    candidate = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=123,
        authority=case.genesis,
    )

    wrong_cents = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=124,
        authority=case.genesis,
    )
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.admit_fixture_effect(
            expected_authority_revision=0,
            expected_capability_head=case.genesis.capability_head_sha256,
            expected_source_head=case.genesis.source_head_sha256,
            hold_id=marker.hold_id,
            candidate=wrong_cents,
            now_ms=1_020,
        )

    authoritative_drift = {
        "owner_path_discriminator": "opspd1_" + "d1" * 32,
        "logical_effect_key": "mopeffect1_" + "d2" * 32,
        "hold_id": "mophold1_" + "d3" * 32,
        "projected_max_cents": 124,
        "authority_revision": 1,
        "fixture_pair_sha256": "d0" * 32,
        "capability_registry_id": "capability.fixture.changed",
        "capability_head_sha256": "d4" * 32,
        "capability_epoch": 1,
        "source_registry_id": "source.fixture.changed",
        "source_head_sha256": "d5" * 32,
        "source_epoch": 1,
    }
    for field, value in authoritative_drift.items():
        with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
            case.store.admit_fixture_effect(
                expected_authority_revision=0,
                expected_capability_head=case.genesis.capability_head_sha256,
                expected_source_head=case.genesis.source_head_sha256,
                hold_id=marker.hold_id,
                candidate=candidate.model_copy(update={field: value}),
                now_ms=1_020,
            )

    first = case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=marker.hold_id,
        candidate=candidate,
        now_ms=1_020,
    )
    drift = candidate.model_copy(update={"provider": "provider.changed"})
    assert isinstance(drift, FixtureAdmissionCandidateV1)
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.admit_fixture_effect(
            expected_authority_revision=0,
            expected_capability_head=case.genesis.capability_head_sha256,
            expected_source_head=case.genesis.source_head_sha256,
            hold_id=marker.hold_id,
            candidate=drift,
            now_ms=1_030,
        )

    forged_literal = candidate.model_copy(update={"transport_reachable": True})
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.admit_fixture_effect(
            expected_authority_revision=0,
            expected_capability_head=case.genesis.capability_head_sha256,
            expected_source_head=case.genesis.source_head_sha256,
            hold_id=marker.hold_id,
            candidate=forged_literal,
            now_ms=1_030,
        )

    with sqlite3.connect(case.store.path) as connection:
        rows = connection.execute(
            "SELECT admission_id,created_at_ms FROM private_paid_effect_fixture_admissions"
        ).fetchall()
    assert rows == [(first.admission_id, first.created_at_ms)]


@pytest.mark.parametrize("candidate_field", tuple(FixtureAdmissionCandidateV1.model_fields))
def test_exact_replay_rejects_drift_in_every_candidate_field(
    tmp_path: Path, candidate_field: str
) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    marker = case.store.reserve_fixture_exposure(projected_max_cents=123, now_ms=1_010)
    candidate = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=123,
        authority=case.genesis,
    )
    case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=marker.hold_id,
        candidate=candidate,
        now_ms=1_020,
    )
    mutation = _candidate_mutation_value(candidate_field, candidate)
    singleton_literal_fields = {
        "schema_version",
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
        "fixture_authority_only",
        "live_authority_verified",
        "user_accounting_effect",
        "transport_reachable",
    }
    if candidate_field in singleton_literal_fields:
        drift = candidate.model_copy(update={candidate_field: mutation})
    else:
        raw = candidate.model_dump(mode="python")
        raw[candidate_field] = mutation
        drift = FixtureAdmissionCandidateV1.model_validate(raw)
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.admit_fixture_effect(
            expected_authority_revision=0,
            expected_capability_head=case.genesis.capability_head_sha256,
            expected_source_head=case.genesis.source_head_sha256,
            hold_id=marker.hold_id,
            candidate=drift,
            now_ms=1_030,
        )


def test_expired_unadmitted_marker_is_reaped_without_deleting_admission(
    tmp_path: Path,
) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    stale = case.store.reserve_fixture_exposure(projected_max_cents=123, now_ms=1_010)
    live = case.store.reserve_fixture_exposure(projected_max_cents=222, now_ms=1_020)
    candidate = admission_candidate(
        logical_effect_key=live.logical_effect_key,
        hold_id=live.hold_id,
        projected_max_cents=222,
        authority=case.genesis,
    )
    admitted = case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=live.hold_id,
        candidate=candidate,
        now_ms=1_030,
    )

    case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=live.hold_id,
        candidate=candidate,
        now_ms=401_011,
    )
    with sqlite3.connect(case.store.path) as connection:
        before_reservation = connection.execute(
            "SELECT 1 FROM private_paid_effect_fixture_exposure_markers WHERE logical_effect_key=?",
            (stale.logical_effect_key,),
        ).fetchone()
    assert before_reservation == (1,)

    case.store.reserve_fixture_exposure(projected_max_cents=333, now_ms=401_011)
    with sqlite3.connect(case.store.path) as connection:
        marker_keys = {
            str(row[0])
            for row in connection.execute(
                "SELECT logical_effect_key FROM private_paid_effect_fixture_exposure_markers"
            ).fetchall()
        }
        admissions = connection.execute(
            "SELECT admission_id FROM private_paid_effect_fixture_admissions"
        ).fetchall()
    assert stale.logical_effect_key not in marker_keys
    assert live.logical_effect_key in marker_keys
    assert admissions == [(admitted.admission_id,)]


def test_schema_four_tables_and_reopen_corruption_detection(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    with sqlite3.connect(case.store.path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        views = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('view','trigger')"
        ).fetchone()
        admission_columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info('private_paid_effect_fixture_admissions')"
            ).fetchall()
        }
        connection.execute(
            "UPDATE private_paid_effect_fixture_authority_current SET capability_head_sha256=?",
            ("fe" * 32,),
        )
    assert tables == {
        "private_paid_effect_fixture_schema",
        "private_paid_effect_fixture_authority_current",
        "private_paid_effect_fixture_exposure_markers",
        "private_paid_effect_fixture_admissions",
    }
    assert views == (0,)
    assert "fixture_pair_sha256" in admission_columns
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        PrivatePaidEffectAdmissionFixtureStoreV1(
            case.store.path,
            owner_path_authority=case.authority,
            owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
            store_id=STORE_ID,
            key_version=KEY_VERSION,
            fixture_authority_verification_keys=fixture_pair_verification_keys(),
            key_provider=case.key_provider,
        )


def test_schema_rejects_extra_nonunique_index(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    with sqlite3.connect(case.store.path) as connection:
        connection.execute(
            "CREATE INDEX forbidden_fixture_index "
            "ON private_paid_effect_fixture_exposure_markers(created_at_ms)"
        )
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        PrivatePaidEffectAdmissionFixtureStoreV1(
            case.store.path,
            owner_path_authority=case.authority,
            owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
            store_id=STORE_ID,
            key_version=KEY_VERSION,
            fixture_authority_verification_keys=fixture_pair_verification_keys(),
            key_provider=case.key_provider,
        )


def test_schema_audit_preserves_quoted_check_literal_case(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    table = "private_paid_effect_fixture_exposure_markers"
    with sqlite3.connect(case.store.path) as connection:
        stored_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        assert stored_sql is not None
        altered_sql = str(stored_sql[0]).replace("'open'", "'OPEN'")
        assert altered_sql != stored_sql[0]
        connection.execute("PRAGMA writable_schema=ON")
        connection.execute(
            "UPDATE sqlite_master SET sql=? WHERE type='table' AND name=?",
            (altered_sql, table),
        )
        connection.execute("PRAGMA writable_schema=OFF")
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        PrivatePaidEffectAdmissionFixtureStoreV1(
            case.store.path,
            owner_path_authority=case.authority,
            owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
            store_id=STORE_ID,
            key_version=KEY_VERSION,
            fixture_authority_verification_keys=fixture_pair_verification_keys(),
            key_provider=case.key_provider,
        )


def test_wrong_length_returned_key_is_cleared(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    marker = case.store.reserve_fixture_exposure(projected_max_cents=123, now_ms=1_010)
    candidate = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=123,
        authority=case.genesis,
    )
    case.key_provider.keys[KEY_VERSION] = b"x" * 31
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.admit_fixture_effect(
            expected_authority_revision=0,
            expected_capability_head=case.genesis.capability_head_sha256,
            expected_source_head=case.genesis.source_head_sha256,
            hold_id=marker.hold_id,
            candidate=candidate,
            now_ms=1_020,
        )
    assert case.key_provider.opened_buffers[-1] == bytearray(31)
    assert case.key_provider.cleared_snapshots[-1] == b"\x00" * 31


def test_nonce_retry_boundary_seven_collisions_then_success_and_eight_reject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    first_marker = case.store.reserve_fixture_exposure(projected_max_cents=1, now_ms=1_010)
    first_candidate = admission_candidate(
        logical_effect_key=first_marker.logical_effect_key,
        hold_id=first_marker.hold_id,
        projected_max_cents=1,
        authority=case.genesis,
    )
    case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=first_marker.hold_id,
        candidate=first_candidate,
        now_ms=1_020,
    )
    with sqlite3.connect(case.store.path) as connection:
        used_nonce = bytes(
            connection.execute(
                "SELECT nonce FROM private_paid_effect_fixture_admissions"
            ).fetchone()[0]
        )

    second_marker = case.store.reserve_fixture_exposure(projected_max_cents=1, now_ms=1_030)
    second_candidate = admission_candidate(
        logical_effect_key=second_marker.logical_effect_key,
        hold_id=second_marker.hold_id,
        projected_max_cents=1,
        authority=case.genesis,
    )
    eighth_nonce = b"u" * 12
    retry_values = iter([used_nonce] * (NONCE_COLLISION_RETRIES - 1) + [eighth_nonce])
    retry_calls = 0
    original_token_bytes = secrets.token_bytes

    def seven_collisions_then_unique(length: int) -> bytes:
        nonlocal retry_calls
        if length != 12:
            return original_token_bytes(length)
        retry_calls += 1
        return next(retry_values)

    monkeypatch.setattr(secrets, "token_bytes", seven_collisions_then_unique)
    case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=second_marker.hold_id,
        candidate=second_candidate,
        now_ms=1_040,
    )
    assert retry_calls == NONCE_COLLISION_RETRIES

    third_marker = case.store.reserve_fixture_exposure(projected_max_cents=1, now_ms=1_050)
    third_candidate = admission_candidate(
        logical_effect_key=third_marker.logical_effect_key,
        hold_id=third_marker.hold_id,
        projected_max_cents=1,
        authority=case.genesis,
    )
    exhaustion_calls = 0

    def always_collides(length: int) -> bytes:
        nonlocal exhaustion_calls
        if length != 12:
            return original_token_bytes(length)
        exhaustion_calls += 1
        return used_nonce

    monkeypatch.setattr(secrets, "token_bytes", always_collides)
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.admit_fixture_effect(
            expected_authority_revision=0,
            expected_capability_head=case.genesis.capability_head_sha256,
            expected_source_head=case.genesis.source_head_sha256,
            hold_id=third_marker.hold_id,
            candidate=third_candidate,
            now_ms=1_060,
        )
    assert exhaustion_calls == NONCE_COLLISION_RETRIES


def test_reachable_plaintext_max_direct_size_guards_and_database_page_bound(
    tmp_path: Path,
) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    marker = case.store.reserve_fixture_exposure(projected_max_cents=1_000_000_000, now_ms=1_010)
    base = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=1_000_000_000,
        authority=case.genesis,
        router_role="synthesizer",
        source_receipt_pairs=_receipt_pairs(8),
    ).model_dump(mode="python")
    for field in (
        "operation_id",
        "job_id",
        "execution_id",
        "stage_id",
        "queue_operation_id",
        "queue_cursor",
        "worker_id",
        "provider",
        "model",
        "route",
        "account_scope",
        "project_scope",
        "api_mode",
        "processing_region",
        "output_schema",
    ):
        base[field] = "a" * 128
    base.update(
        {
            "provider_scoped_idempotency_key": "!" * 256,
            "owner_job_state_version": paid_effect_module.MAX_I63,
            "lease_generation": paid_effect_module.MAX_I63,
            "lease_exclusive_until_ms": paid_effect_module.MAX_I63,
            "source_revision": paid_effect_module.MAX_I63,
            "approved_ceiling_cents": 1_000_000_000,
            "maximum_output_bytes": 67_108_864,
        }
    )
    maximal_reachable_candidate = FixtureAdmissionCandidateV1.model_validate(base)
    plaintext = paid_effect_module._canonical_model_json(
        paid_effect_module._AdmissionPlaintextV1(
            admitted_at_ms=1_020,
            candidate=maximal_reachable_candidate,
        )
    )
    reachable_plaintext_length = len(plaintext)
    structural_raw = maximal_reachable_candidate.model_dump(mode="python")
    structural_raw.update(
        {
            "authority_revision": paid_effect_module.MAX_I63,
            "capability_registry_id": "c" * 128,
            "capability_epoch": paid_effect_module.MAX_I63,
            "source_registry_id": "s" * 128,
            "source_epoch": paid_effect_module.MAX_I63,
        }
    )
    structurally_maximal_candidate = FixtureAdmissionCandidateV1.model_validate(structural_raw)
    structural_plaintext = paid_effect_module._canonical_model_json(
        paid_effect_module._AdmissionPlaintextV1(
            admitted_at_ms=paid_effect_module.MAX_I63,
            candidate=structurally_maximal_candidate,
        )
    )
    structural_plaintext_length = len(structural_plaintext)
    assert reachable_plaintext_length < MAX_ADMISSION_PLAINTEXT_BYTES
    assert reachable_plaintext_length < structural_plaintext_length
    assert structural_plaintext_length < MAX_ADMISSION_PLAINTEXT_BYTES
    paid_effect_module._require_admission_size_bounds(
        reachable_plaintext_length, reachable_plaintext_length + 16
    )
    paid_effect_module._require_admission_size_bounds(
        structural_plaintext_length, structural_plaintext_length + 16
    )
    evidence = case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=marker.hold_id,
        candidate=maximal_reachable_candidate,
        now_ms=1_020,
    )
    assert evidence.replayed is False
    with sqlite3.connect(case.store.path) as connection:
        stored_lengths = connection.execute(
            "SELECT ciphertext_length,length(ciphertext) "
            "FROM private_paid_effect_fixture_admissions"
        ).fetchone()
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
    configured_connection = case.store._connect()
    try:
        max_page_count = int(configured_connection.execute("PRAGMA max_page_count").fetchone()[0])
    finally:
        configured_connection.close()
    assert stored_lengths == (
        reachable_plaintext_length + 16,
        reachable_plaintext_length + 16,
    )
    for plaintext_length in (
        MAX_ADMISSION_PLAINTEXT_BYTES - 1,
        MAX_ADMISSION_PLAINTEXT_BYTES,
    ):
        paid_effect_module._require_admission_size_bounds(plaintext_length, plaintext_length + 16)
    with pytest.raises(ValueError):
        paid_effect_module._require_admission_size_bounds(
            MAX_ADMISSION_PLAINTEXT_BYTES + 1,
            MAX_ADMISSION_CIPHERTEXT_BYTES + 1,
        )
    assert page_size == 4_096
    assert max_page_count == MAX_DB_PAGES
    assert page_count <= MAX_DB_PAGES
    assert MAX_DB_PAGES * page_size == 268_435_456
    assert case.store.path.stat().st_size <= MAX_DB_PAGES * page_size
    for drifted_page_bound in (MAX_DB_PAGES - 1, MAX_DB_PAGES + 1):
        drifted_connection = case.store._connect()
        try:
            applied_bound = int(
                drifted_connection.execute(
                    f"PRAGMA max_page_count={drifted_page_bound}"
                ).fetchone()[0]
            )
            assert applied_bound == drifted_page_bound
            with pytest.raises(ValueError):
                case.store._validate_schema(drifted_connection)
        finally:
            drifted_connection.close()


@pytest.mark.parametrize(
    ("table", "column", "value"),
    [
        ("private_paid_effect_fixture_admissions", "admission_id", "moadmit1_" + "01" * 32),
        (
            "private_paid_effect_fixture_admissions",
            "logical_effect_key",
            "mopeffect1_" + "02" * 32,
        ),
        ("private_paid_effect_fixture_admissions", "hold_id", "mophold1_" + "03" * 32),
        (
            "private_paid_effect_fixture_admissions",
            "owner_path_discriminator",
            "opspd1_" + "04" * 32,
        ),
        ("private_paid_effect_fixture_admissions", "fixture_pair_sha256", "05" * 32),
        ("private_paid_effect_fixture_admissions", "authority_revision", 1),
        ("private_paid_effect_fixture_admissions", "projected_max_cents", 124),
        ("private_paid_effect_fixture_admissions", "categorical_state", "wrong"),
        ("private_paid_effect_fixture_admissions", "created_at_ms", 1_021),
        ("private_paid_effect_fixture_admissions", "aead_suite", "wrong"),
        ("private_paid_effect_fixture_admissions", "key_version", "moakv1_alias"),
        ("private_paid_effect_fixture_admissions", "nonce_length", 11),
        ("private_paid_effect_fixture_admissions", "nonce", b"n" * 12),
        ("private_paid_effect_fixture_admissions", "ciphertext_schema", "wrong"),
        ("private_paid_effect_fixture_admissions", "ciphertext_type", "text/plain"),
        ("private_paid_effect_fixture_admissions", "ciphertext_length", 17),
        ("private_paid_effect_fixture_admissions", "ciphertext", b"c" * 32),
        (
            "private_paid_effect_fixture_exposure_markers",
            "logical_effect_key",
            "mopeffect1_" + "06" * 32,
        ),
        (
            "private_paid_effect_fixture_exposure_markers",
            "hold_id",
            "mophold1_" + "07" * 32,
        ),
        (
            "private_paid_effect_fixture_exposure_markers",
            "owner_path_discriminator",
            "opspd1_" + "08" * 32,
        ),
        ("private_paid_effect_fixture_exposure_markers", "projected_max_cents", 124),
        ("private_paid_effect_fixture_exposure_markers", "exposure_state", "released"),
        ("private_paid_effect_fixture_exposure_markers", "created_at_ms", 1_021),
        ("private_paid_effect_fixture_exposure_markers", "released_at_ms", 1_019),
    ],
)
def test_release_authenticates_every_persisted_row_field(
    tmp_path: Path, table: str, column: str, value: object
) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    marker = case.store.reserve_fixture_exposure(projected_max_cents=123, now_ms=1_010)
    candidate = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=123,
        authority=case.genesis,
    )
    admitted = case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=marker.hold_id,
        candidate=candidate,
        now_ms=1_020,
    )
    case.key_provider.keys["moakv1_alias"] = DATA_KEY
    calls_before = len(case.key_provider.calls)
    with sqlite3.connect(case.store.path) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(f"UPDATE {table} SET {column}=?", (value,))
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.release_fixture_unreachable_transport(
            admission_id=admitted.admission_id,
            hold_id=marker.hold_id,
            now_ms=1_030,
        )
    if table == "private_paid_effect_fixture_admissions":
        with sqlite3.connect(case.store.path) as connection:
            marker_state = connection.execute(
                "SELECT exposure_state,released_at_ms "
                "FROM private_paid_effect_fixture_exposure_markers"
            ).fetchone()
        assert marker_state == ("open", None)
    if column == "key_version":
        assert len(case.key_provider.calls) == calls_before


def test_temporal_first_writes_and_exact_replays(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.reserve_fixture_exposure(projected_max_cents=123, now_ms=999)
    marker = case.store.reserve_fixture_exposure(projected_max_cents=123, now_ms=1_010)
    next_pair = successor_pair(case.genesis, issued_at_ms=1_100)
    case.store.compare_and_set_fixture_authority_pair(
        expected_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        signed_fixture_pair=next_pair,
        now_ms=1_100,
    )
    candidate = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=123,
        authority=next_pair,
    )
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.admit_fixture_effect(
            expected_authority_revision=1,
            expected_capability_head=next_pair.capability_head_sha256,
            expected_source_head=next_pair.source_head_sha256,
            hold_id=marker.hold_id,
            candidate=candidate,
            now_ms=1_099,
        )
    admitted = case.store.admit_fixture_effect(
        expected_authority_revision=1,
        expected_capability_head=next_pair.capability_head_sha256,
        expected_source_head=next_pair.source_head_sha256,
        hold_id=marker.hold_id,
        candidate=candidate,
        now_ms=1_100,
    )
    final_pair = successor_pair(next_pair, issued_at_ms=1_200, source_head_sha256="45" * 32)
    case.store.compare_and_set_fixture_authority_pair(
        expected_revision=1,
        expected_capability_head=next_pair.capability_head_sha256,
        expected_source_head=next_pair.source_head_sha256,
        signed_fixture_pair=final_pair,
        now_ms=1_200,
    )
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.release_fixture_unreachable_transport(
            admission_id=admitted.admission_id, hold_id=marker.hold_id, now_ms=1_199
        )
    released = case.store.release_fixture_unreachable_transport(
        admission_id=admitted.admission_id, hold_id=marker.hold_id, now_ms=1_200
    )
    replay = case.store.release_fixture_unreachable_transport(
        admission_id=admitted.admission_id, hold_id=marker.hold_id, now_ms=0
    )
    assert replay.applied is False
    assert replay.released_at_ms == released.released_at_ms
    admission_replay = case.store.admit_fixture_effect(
        expected_authority_revision=1,
        expected_capability_head=next_pair.capability_head_sha256,
        expected_source_head=next_pair.source_head_sha256,
        hold_id=marker.hold_id,
        candidate=candidate,
        now_ms=0,
    )
    assert admission_replay.historical_fixture_pair_sha256 == next_pair.pair_sha256


def test_secure_paths_reject_symlink_mode_and_uid_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_root = tmp_path / "real-root"
    real_root.mkdir(mode=0o700)
    real_root.chmod(0o700)
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        fixture_store_case(linked_root)

    loose_root = tmp_path / "loose-root"
    loose_root.mkdir(mode=0o700)
    loose_root.chmod(0o750)
    authority = fixture_store_case(tmp_path / "valid-root")
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        PrivatePaidEffectAdmissionFixtureStoreV1(
            loose_root / "fixture.sqlite3",
            owner_path_authority=authority.authority,
            owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
            store_id=STORE_ID,
            key_version=KEY_VERSION,
            fixture_authority_verification_keys=fixture_pair_verification_keys(),
            key_provider=authority.key_provider,
        )

    valid_root = tmp_path / "uid-root"
    valid_root.mkdir(mode=0o700)
    valid_root.chmod(0o700)
    monkeypatch.setattr(os, "getuid", lambda: os.stat(valid_root).st_uid + 1)
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        PrivatePaidEffectAdmissionFixtureStoreV1(
            valid_root / "fixture.sqlite3",
            owner_path_authority=authority.authority,
            owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
            store_id=STORE_ID,
            key_version=KEY_VERSION,
            fixture_authority_verification_keys=fixture_pair_verification_keys(),
            key_provider=authority.key_provider,
        )


def test_two_process_admission_race_and_drift_loser(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    marker = case.store.reserve_fixture_exposure(projected_max_cents=123, now_ms=1_010)
    candidate = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=123,
        authority=case.genesis,
    )
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    processes = [
        context.Process(
            target=_admission_process_worker,
            args=(str(tmp_path), _candidate_wire(candidate), start, results),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    start.set()
    outcomes = sorted(results.get(timeout=20) for _ in processes)
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    assert outcomes == ["first", "replay"]

    drift = candidate.model_copy(update={"provider": "provider.changed"})
    drift_start = context.Event()
    drift_results = context.Queue()
    drift_process = context.Process(
        target=_admission_process_worker,
        args=(str(tmp_path), _candidate_wire(drift), drift_start, drift_results),
    )
    drift_process.start()
    drift_start.set()
    assert drift_results.get(timeout=20) == "rejected"
    drift_process.join(timeout=20)
    assert drift_process.exitcode == 0


def test_two_process_authority_cas_has_one_winner(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    successor = successor_pair(case.genesis, issued_at_ms=1_100)
    pair_wire = json.dumps(
        successor.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    processes = [
        context.Process(
            target=_cas_process_worker,
            args=(str(tmp_path), pair_wire, start, results),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    start.set()
    outcomes = sorted(results.get(timeout=20) for _ in processes)
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    assert outcomes == ["applied", "rejected"]


def test_abrupt_exit_before_and_after_commit_recovers(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    marker = case.store.reserve_fixture_exposure(projected_max_cents=123, now_ms=1_010)
    candidate = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=123,
        authority=case.genesis,
    )
    context = multiprocessing.get_context("spawn")
    before = context.Process(
        target=_abrupt_after_insert_before_commit_worker,
        args=(str(tmp_path), _candidate_wire(candidate)),
    )
    before.start()
    before.join(timeout=20)
    assert before.exitcode == 79
    with sqlite3.connect(case.store.path) as connection:
        admission_count = connection.execute(
            "SELECT COUNT(*) FROM private_paid_effect_fixture_admissions"
        ).fetchone()
    assert admission_count == (0,)

    after = context.Process(
        target=_abrupt_after_admission_worker,
        args=(str(tmp_path), _candidate_wire(candidate)),
    )
    after.start()
    after.join(timeout=20)
    assert after.exitcode == 0
    recovered = case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=marker.hold_id,
        candidate=candidate,
        now_ms=1_030,
    )
    assert recovered.replayed is True


def test_production_import_graph_quarantine_and_zero_operational_calls() -> None:
    module_name = "substrate.midnight_oil.private_paid_effect_admission"
    module_path = Path("substrate/midnight_oil/private_paid_effect_admission.py").resolve()
    excluded_roots = {".git", ".infinite", ".venv", "docs", "tests"}

    def references_quarantined_module(tree: ast.AST) -> tuple[str, ...]:
        references: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name == module_name or alias.name.startswith(module_name + ".")
                for alias in node.names
            ):
                references.append("import")
            if isinstance(node, ast.ImportFrom):
                imports_leaf = any(
                    alias.name == "private_paid_effect_admission" for alias in node.names
                )
                if (
                    node.module == module_name
                    or (node.module is not None and node.module.startswith(module_name + "."))
                    or (node.module == "substrate.midnight_oil" and imports_leaf)
                    or (node.level > 0 and imports_leaf)
                ):
                    references.append("from")
            if isinstance(node, ast.Constant) and node.value == module_name:
                references.append("dynamic-string")
        return tuple(references)

    importers: list[tuple[str, str]] = []
    for path in Path(".").rglob("*.py"):
        if path.resolve() == module_path or any(part in excluded_roots for part in path.parts):
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        importers.extend((str(path), kind) for kind in references_quarantined_module(tree))
    assert importers == []
    planted_vectors = (
        "import substrate.midnight_oil.private_paid_effect_admission",
        "from substrate.midnight_oil.private_paid_effect_admission import FixtureAdmissionCandidateV1",
        "from substrate.midnight_oil import private_paid_effect_admission",
        "from . import private_paid_effect_admission",
        "__import__('substrate.midnight_oil.private_paid_effect_admission')",
        "importlib.import_module('substrate.midnight_oil.private_paid_effect_admission')",
    )
    for vector in planted_vectors:
        assert references_quarantined_module(ast.parse(vector))

    module_tree = ast.parse(
        Path("substrate/midnight_oil/private_paid_effect_admission.py").read_text()
    )
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(module_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported_roots.isdisjoint(
        {"requests", "httpx", "urllib", "socket", "boto3", "openai", "stripe"}
    )
    operational_calls = []
    forbidden_call_tokens = (
        "accounting",
        "charge",
        "dispatch",
        "provider_call",
        "request_provider",
        "send",
        "settle",
        "transport_call",
    )
    for node in ast.walk(module_tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute):
            name = node.func.attr
        elif isinstance(node.func, ast.Name):
            name = node.func.id
        else:
            continue
        if any(token in name.lower() for token in forbidden_call_tokens):
            operational_calls.append(name)
    assert operational_calls == []


def test_isolated_admission_pair_column_mutation_rejects(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    marker = case.store.reserve_fixture_exposure(projected_max_cents=123, now_ms=1_010)
    candidate = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=123,
        authority=case.genesis,
    )
    case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=marker.hold_id,
        candidate=candidate,
        now_ms=1_020,
    )
    with sqlite3.connect(case.store.path) as connection:
        connection.execute(
            "UPDATE private_paid_effect_fixture_admissions SET fixture_pair_sha256=?",
            ("f0" * 32,),
        )
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.admit_fixture_effect(
            expected_authority_revision=0,
            expected_capability_head=case.genesis.capability_head_sha256,
            expected_source_head=case.genesis.source_head_sha256,
            hold_id=marker.hold_id,
            candidate=candidate,
            now_ms=1_030,
        )


def test_replay_rejects_aliased_same_key_wrong_version_before_key_open(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path)
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    marker = case.store.reserve_fixture_exposure(projected_max_cents=123, now_ms=1_010)
    candidate = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=123,
        authority=case.genesis,
    )
    case.store.admit_fixture_effect(
        expected_authority_revision=0,
        expected_capability_head=case.genesis.capability_head_sha256,
        expected_source_head=case.genesis.source_head_sha256,
        hold_id=marker.hold_id,
        candidate=candidate,
        now_ms=1_020,
    )
    case.key_provider.keys["moakv1_alias"] = DATA_KEY
    with sqlite3.connect(case.store.path) as connection:
        connection.execute(
            "UPDATE private_paid_effect_fixture_admissions SET key_version='moakv1_alias'"
        )
    calls_before = len(case.key_provider.calls)
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.admit_fixture_effect(
            expected_authority_revision=0,
            expected_capability_head=case.genesis.capability_head_sha256,
            expected_source_head=case.genesis.source_head_sha256,
            hold_id=marker.hold_id,
            candidate=candidate,
            now_ms=1_030,
        )
    assert len(case.key_provider.calls) == calls_before


def test_database_and_backup_do_not_expose_encrypted_candidate_fields(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path / "root")
    case.store.initialize_fixture_authority_pair(signed_fixture_pair=case.genesis, now_ms=1_000)
    marker = case.store.reserve_fixture_exposure(projected_max_cents=123, now_ms=1_010)
    candidate = admission_candidate(
        logical_effect_key=marker.logical_effect_key,
        hold_id=marker.hold_id,
        projected_max_cents=123,
        authority=case.genesis,
    )
    reader = sqlite3.connect(case.store.path, isolation_level=None)
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM private_paid_effect_fixture_admissions").fetchone()
    try:
        case.store.admit_fixture_effect(
            expected_authority_revision=0,
            expected_capability_head=case.genesis.capability_head_sha256,
            expected_source_head=case.genesis.source_head_sha256,
            hold_id=marker.hold_id,
            candidate=candidate,
            now_ms=1_020,
        )
        wal = Path(str(case.store.path) + "-wal")
        shm = Path(str(case.store.path) + "-shm")
        assert wal.is_file() and wal.stat().st_size > 0
        assert shm.is_file() and shm.stat().st_size > 0

        backup_root = tmp_path / "backup-root"
        backup_root.mkdir(mode=0o700)
        backup_root.chmod(0o700)
        backup = backup_root / "backup.sqlite3"
        case.store.backup_to(backup)
        assert backup.stat().st_mode & 0o777 == 0o600
        reopened = PrivatePaidEffectAdmissionFixtureStoreV1(
            backup,
            owner_path_authority=case.authority,
            owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
            store_id=STORE_ID,
            key_version=KEY_VERSION,
            fixture_authority_verification_keys=fixture_pair_verification_keys(),
            key_provider=case.key_provider,
        )
        assert reopened.store_id == STORE_ID
        with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
            case.store.backup_to(backup)
        assert backup.exists()

        joined = b"\n".join(
            [case.store.path.read_bytes(), wal.read_bytes(), shm.read_bytes(), backup.read_bytes()]
        )
        private_values = [
            candidate.provider,
            candidate.model,
            candidate.account_scope,
            candidate.project_scope,
            candidate.provider_scoped_idempotency_key,
            candidate.source_selector,
            candidate.consent_receipt_sha256,
            candidate.consent_config_sha256,
            candidate.policy_v4_sha256,
            candidate.capability_v4_sha256,
            candidate.core_v4_sha256,
            candidate.receipt_v7_sha256,
            candidate.envelope_v4_sha256,
            candidate.request_material_sha256,
            *(pair.receipt_id for pair in candidate.source_receipt_pairs),
            *(pair.receipt_sha256 for pair in candidate.source_receipt_pairs),
        ]
        forbidden: list[bytes] = []
        for value in private_values:
            raw = value.encode()
            forbidden.extend((raw, base64.b64encode(raw), raw.hex().encode()))
        for needle in forbidden:
            assert needle not in joined
    finally:
        reader.execute("ROLLBACK")
        reader.close()


def test_backup_failure_removes_exclusive_partial_destination(tmp_path: Path) -> None:
    case = fixture_store_case(tmp_path / "source-root")
    destination_root = tmp_path / "destination-root"
    destination_root.mkdir(mode=0o700)
    destination_root.chmod(0o700)
    destination = destination_root / "failed.sqlite3"
    with sqlite3.connect(case.store.path) as connection:
        connection.execute(
            "CREATE INDEX forbidden_fixture_index "
            "ON private_paid_effect_fixture_exposure_markers(created_at_ms)"
        )
    with pytest.raises(PrivatePaidEffectAdmissionFixtureRejected):
        case.store.backup_to(destination)
    assert not destination.exists()
    assert not Path(str(destination) + "-wal").exists()
    assert not Path(str(destination) + "-shm").exists()
