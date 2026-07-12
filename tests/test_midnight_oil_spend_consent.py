from __future__ import annotations

import base64
import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from substrate.midnight_oil.spend_consent import (
    ConsentRejected,
    ConsentRejection,
    JobConsentConfig,
    SpendConsentStore,
    decode_and_verify,
)

KEY = b"k" * 32
KEY_2 = b"z" * 32


def config() -> JobConsentConfig:
    return JobConsentConfig(
        job_id="moil_123",
        goals=("Investigate durable agent memory", "Stress-test the synthesis"),
        duration_minutes=120,
        model_id="gpt-5.5",
        research_tier="wrestle",
        fanout_depth=3,
        asset_id="moil_asset_123",
    )


def issue(store: SpendConsentStore, **overrides: object) -> str:
    values: dict[str, object] = {
        "operator_id": "operator-a",
        "config": config(),
        "operation_id": "operation-1",
        "ceiling_cents": 2500,
        "issued_at_ms": 1_000,
        "expires_at_ms": 11_000,
        "nonce": "nonce-1",
        "key_id": "key-1",
        "signing_key": KEY,
    }
    values.update(overrides)
    return store.issue(**values)  # type: ignore[arg-type]


def claim(store: SpendConsentStore, token: str, **overrides: object):  # type: ignore[no-untyped-def]
    values: dict[str, object] = {
        "expected_operator_id": "operator-a",
        "expected_config": config(),
        "expected_operation_id": "operation-1",
        "expected_ceiling_cents": 2500,
        "now_ms": 2_000,
        "verification_keys": {"key-1": KEY},
    }
    values.update(overrides)
    return store.claim(token, **values)  # type: ignore[arg-type]


def rejected(reason: ConsentRejection, fn) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ConsentRejected) as caught:
        fn()
    assert caught.value.reason is reason


def resign_with_field(token: str, field: str, value: object) -> str:
    encoded, _ = token.split(".")
    payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    raw = json.loads(payload)
    raw[field] = value
    changed = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.digest(KEY, b"antiek.midnight-oil.spend-consent.v1\x00" + changed, "sha256")
    return (
        base64.urlsafe_b64encode(changed).rstrip(b"=").decode()
        + "."
        + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    )


def test_issue_claim_and_exact_replay_are_distinct(tmp_path: Path) -> None:
    store = SpendConsentStore(tmp_path / "consent.sqlite3")
    token = issue(store)
    assert claim(store, token).claimed_now is True
    assert claim(store, token).claimed_now is False


def test_stage_plan_uses_v2_config_hash_without_changing_legacy_v1() -> None:
    legacy = config()
    legacy_material = {
        key: value
        for key, value in legacy.__dict__.items()
        if key
        not in {
            "stage_plan_hash",
            "context_binding_sha256",
            "publication_manifest_sha256",
        }
    }
    encoded = json.dumps(
        legacy_material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    expected = hashlib.sha256(
        b"antiek.midnight-oil.job-config.v1\x00" + encoded
    ).hexdigest()
    assert legacy.canonical_hash() == expected

    first = replace(
        legacy,
        live_execution_plan_hash="a" * 64,
        stage_plan_hash="b" * 64,
    )
    second = replace(first, stage_plan_hash="c" * 64)
    assert first.canonical_hash() != legacy.canonical_hash()
    assert second.canonical_hash() != first.canonical_hash()


def test_context_binding_uses_v3_and_changes_signed_configuration() -> None:
    legacy = config()
    first = replace(legacy, context_binding_sha256="1" * 64)
    second = replace(legacy, context_binding_sha256="2" * 64)
    assert first.canonical_hash() != legacy.canonical_hash()
    assert first.canonical_hash() != second.canonical_hash()


def test_publication_manifest_uses_v4_and_changes_signed_configuration() -> None:
    bound = replace(config(), context_binding_sha256="1" * 64)
    first = replace(bound, publication_manifest_sha256="a" * 64)
    second = replace(bound, publication_manifest_sha256="b" * 64)
    assert first.canonical_hash() != bound.canonical_hash()
    assert first.canonical_hash() != second.canonical_hash()


def test_reopen_preserves_claim_state(tmp_path: Path) -> None:
    path = tmp_path / "consent.sqlite3"
    token = issue(SpendConsentStore(path))
    assert claim(SpendConsentStore(path), token).claimed_now is True
    assert claim(SpendConsentStore(path), token).claimed_now is False


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    ("overrides", "reason"),
    [
        ({"expected_operator_id": "operator-b"}, ConsentRejection.WRONG_OPERATOR),
        ({"expected_config": replace(config(), job_id="moil_other")}, ConsentRejection.WRONG_JOB),
        ({"expected_operation_id": "operation-2"}, ConsentRejection.WRONG_OPERATION),
        (
            {"expected_config": replace(config(), duration_minutes=121)},
            ConsentRejection.CONFIG_DRIFT,
        ),
        ({"expected_ceiling_cents": 2501}, ConsentRejection.CEILING_MISMATCH),
        ({"now_ms": 999}, ConsentRejection.NOT_YET_VALID),
        ({"now_ms": 11_000}, ConsentRejection.EXPIRED),
    ],
)
def test_bound_claims_fail_closed(
    tmp_path: Path, overrides: dict[str, object], reason: ConsentRejection
) -> None:
    store = SpendConsentStore(tmp_path / "consent.sqlite3")
    token = issue(store)
    rejected(reason, lambda: claim(store, token, **overrides))


def test_tamper_and_unknown_key_fail_closed(tmp_path: Path) -> None:
    store = SpendConsentStore(tmp_path / "consent.sqlite3")
    token = issue(store)
    payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    rejected(
        ConsentRejection.BAD_SIGNATURE,
        lambda: claim(store, f"{payload}.{replacement}{signature[1:]}"),
    )
    rejected(
        ConsentRejection.UNKNOWN_KEY,
        lambda: claim(store, token, verification_keys={}),
    )
    rejected(ConsentRejection.MALFORMED, lambda: claim(store, "x" * 8_193))


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "field",
    ["receipt_id", "operator_id", "job_id", "operation_id", "config_hash", "key_id"],
)
def test_hostile_receipt_field_types_are_malformed(tmp_path: Path, field: str) -> None:
    store = SpendConsentStore(tmp_path / "consent.sqlite3")
    token = issue(store)
    hostile = resign_with_field(token, field, 1)
    rejected(ConsentRejection.MALFORMED, lambda: claim(store, hostile))


def test_fabricated_signed_but_unissued_receipt_is_rejected(tmp_path: Path) -> None:
    source = SpendConsentStore(tmp_path / "source.sqlite3")
    token = issue(source)
    target = SpendConsentStore(tmp_path / "target.sqlite3")
    rejected(ConsentRejection.UNKNOWN_RECEIPT, lambda: claim(target, token))


def test_key_rotation_verifies_old_and_new_receipts(tmp_path: Path) -> None:
    store = SpendConsentStore(tmp_path / "consent.sqlite3")
    old = issue(store)
    new = issue(store, nonce="nonce-2", key_id="key-2", signing_key=KEY_2)
    keys = {"key-1": KEY, "key-2": KEY_2}
    assert claim(store, old, verification_keys=keys).claimed_now
    assert claim(store, new, verification_keys=keys).claimed_now


def test_duplicate_nonce_is_a_conflicting_replay(tmp_path: Path) -> None:
    store = SpendConsentStore(tmp_path / "consent.sqlite3")
    issue(store)
    rejected(ConsentRejection.CONFLICTING_REPLAY, lambda: issue(store))


def test_concurrent_claim_has_one_winner_and_safe_replays(tmp_path: Path) -> None:
    store = SpendConsentStore(tmp_path / "consent.sqlite3")
    token = issue(store)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: claim(store, token), range(16)))
    assert sum(result.claimed_now for result in results) == 1


def test_receipt_contains_no_signing_key_and_issuance_only_writes_consent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "consent.sqlite3"
    store = SpendConsentStore(path)
    token = issue(store)
    receipt = decode_and_verify(token, verification_keys={"key-1": KEY})
    assert receipt.operator_id == "operator-a"
    assert KEY.decode() not in token
    assert path.is_file()
    assert not (tmp_path / "budget.duckdb").exists()


@pytest.mark.parametrize("ceiling", [0, -1])  # type: ignore[untyped-decorator]
def test_nonpositive_integer_ceiling_is_rejected(tmp_path: Path, ceiling: int) -> None:
    store = SpendConsentStore(tmp_path / "consent.sqlite3")
    with pytest.raises(ValueError, match="ceiling_cents"):
        issue(store, ceiling_cents=ceiling)


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    ("overrides", "match"),
    [
        ({"ceiling_cents": True}, "ceiling_cents"),
        ({"issued_at_ms": True}, "timestamps"),
        ({"expires_at_ms": 86_402_001}, "expiry"),
        ({"config": replace(config(), duration_minutes=True)}, "duration"),
        ({"config": replace(config(), fanout_depth=True)}, "fanout"),
        ({"config": replace(config(), goals=("x" * 4_097,))}, "goal text"),
    ],
)
def test_issuance_rejects_ambiguous_or_unbounded_inputs(
    tmp_path: Path, overrides: dict[str, object], match: str
) -> None:
    store = SpendConsentStore(tmp_path / "consent.sqlite3")
    with pytest.raises(ValueError, match=match):
        issue(store, **overrides)


def test_claim_rejects_boolean_money_and_time(tmp_path: Path) -> None:
    store = SpendConsentStore(tmp_path / "consent.sqlite3")
    token = issue(store)
    rejected(
        ConsentRejection.CEILING_MISMATCH,
        lambda: claim(store, token, expected_ceiling_cents=True),
    )
    rejected(ConsentRejection.MALFORMED, lambda: claim(store, token, now_ms=True))
