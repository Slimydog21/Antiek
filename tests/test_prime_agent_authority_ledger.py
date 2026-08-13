from __future__ import annotations

import concurrent.futures
import os
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from orchestration.rlm.prime_authority import (
    PrimeAuthorizationRefused,
    PrimeAuthorizationRequest,
    PrimeCallState,
    PrimeLedgerCorrupt,
    PrimeReplayMismatch,
    PrimeSecret,
    PrimeUsage,
    ResolvedPrimeCredential,
)
from orchestration.rlm.prime_ledger import PrimeLedger


def _request(number: int = 1, *, cost: int = 1_000_000) -> PrimeAuthorizationRequest:
    return PrimeAuthorizationRequest(
        owner_id="owner",
        payer_id="payer",
        session_id="session",
        request_id=f"request-{number}",
        idempotency_key=f"idem-{number}",
        workflow="repl",
        prompt_digest=f"{number:064x}",
        provider="anthropic",
        credential_id="credential-1",
        credential_fingerprint="a" * 64,
        credential_env_name="ANTHROPIC_API_KEY",
        model="prime-model",
        prime_version="1.2.3",
        max_cost_micro_usd=cost,
        issued_at_ms=100,
        expires_at_ms=1_000,
        nonce=f"nonce-{number}",
    )


def _usage(cost: int = 400_000) -> PrimeUsage:
    return PrimeUsage("anthropic", "prime-model", "1.2.3", 100, 20, cost, 300)


def test_exact_idempotent_replay_and_identity_tamper_refused(tmp_path: Path) -> None:
    ledger = PrimeLedger(tmp_path / "prime.sqlite3")
    request = _request()
    first = ledger.authorize(request, now_ms=200)
    assert ledger.authorize(request, now_ms=201) == first
    for field, tampered in (
        ("owner_id", "tampered"),
        ("payer_id", "tampered"),
        ("prompt_digest", "f" * 64),
        ("credential_id", "tampered"),
        ("credential_fingerprint", "b" * 64),
        ("model", "tampered"),
    ):
        with pytest.raises(PrimeReplayMismatch):
            ledger.authorize(replace(request, **{field: tampered}), now_ms=202)
    with pytest.raises(PrimeReplayMismatch):
        ledger.authorize(
            replace(request, provider="openai", credential_env_name="OPENAI_API_KEY"),
            now_ms=202,
        )
    assert ledger.mark_started(request.request_id, now_ms=250) is True
    assert ledger.mark_started(request.request_id, now_ms=251) is False

    with pytest.raises(PrimeReplayMismatch):
        ledger.authorize(replace(_request(2), payer_id="different"), now_ms=202)


def test_atomic_concurrent_reservations_never_cross_session_cap(tmp_path: Path) -> None:
    path = tmp_path / "prime.sqlite3"
    PrimeLedger(path)

    def reserve(number: int) -> bool:
        try:
            PrimeLedger(path).authorize(_request(number, cost=1_000_000), now_ms=200)
        except PrimeAuthorizationRefused:
            return False
        return True

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(reserve, range(10)))
    assert sum(results) == 5
    connection = sqlite3.connect(path)
    assert (
        connection.execute("SELECT SUM(held_micro_usd) FROM authorizations").fetchone()[0]
        == 5_000_000
    )


def test_expiry_and_cancel_before_start_release_reservation(tmp_path: Path) -> None:
    ledger = PrimeLedger(tmp_path / "prime.sqlite3")
    ledger.authorize(_request(), now_ms=200)
    with pytest.raises(PrimeAuthorizationRefused):
        ledger.mark_started("request-1", now_ms=1_000)
    assert ledger.receipt("request-1").state is PrimeCallState.CANCELLED
    assert ledger.receipt("request-1").held_micro_usd == 0
    cancelled = ledger.cancel("request-1", now_ms=1_001)
    assert cancelled.state is PrimeCallState.CANCELLED


def test_success_charges_exact_usage_and_releases_remainder(tmp_path: Path) -> None:
    ledger = PrimeLedger(tmp_path / "prime.sqlite3")
    ledger.authorize(_request(), now_ms=200)
    ledger.mark_started("request-1", now_ms=210)
    observed = ledger.observe_usage("request-1", _usage(), now_ms=310)
    assert observed.state is PrimeCallState.USAGE_OBSERVED
    assert ledger.observe_usage("request-1", _usage(), now_ms=311) == observed
    with pytest.raises(PrimeReplayMismatch):
        ledger.observe_usage("request-1", _usage(400_001), now_ms=312)
    done = ledger.succeed("request-1", now_ms=320)
    assert (done.charged_micro_usd, done.held_micro_usd) == (400_000, 0)
    assert [event.state for event in ledger.events("request-1")] == [
        PrimeCallState.AUTHORIZED,
        PrimeCallState.STARTED,
        PrimeCallState.USAGE_OBSERVED,
        PrimeCallState.SUCCEEDED,
    ]


@pytest.mark.parametrize(
    "usage",
    [None, PrimeUsage("openai", "prime-model", "1.2.3", 1, 1, 10, 300), _usage(1_000_001)],
)
def test_missing_mismatched_or_overrun_usage_is_unknown_and_holds(
    tmp_path: Path, usage: PrimeUsage | None
) -> None:
    ledger = PrimeLedger(tmp_path / "prime.sqlite3")
    ledger.authorize(_request(), now_ms=200)
    ledger.mark_started("request-1", now_ms=210)
    result = ledger.observe_usage("request-1", usage, now_ms=310)
    assert result.state is PrimeCallState.UNKNOWN
    assert result.held_micro_usd == 1_000_000
    if usage is not None:
        assert result.observed_cost_micro_usd == usage.cost_micro_usd
        assert result.charged_micro_usd == usage.cost_micro_usd
        if usage.cost_micro_usd > 1_000_000:
            with pytest.raises(PrimeAuthorizationRefused):
                ledger.authorize(_request(2), now_ms=320)


def test_cancel_after_start_without_usage_is_unknown_but_complete_usage_reconciles(
    tmp_path: Path,
) -> None:
    ledger = PrimeLedger(tmp_path / "prime.sqlite3")
    ledger.authorize(_request(), now_ms=200)
    ledger.mark_started("request-1", now_ms=210)
    assert ledger.cancel("request-1", now_ms=220).state is PrimeCallState.UNKNOWN
    ledger.authorize(_request(2), now_ms=200)
    ledger.mark_started("request-2", now_ms=210)
    ledger.observe_usage("request-2", _usage(), now_ms=310)
    cancelled = ledger.cancel("request-2", now_ms=320)
    assert (cancelled.state, cancelled.charged_micro_usd, cancelled.held_micro_usd) == (
        PrimeCallState.CANCELLED,
        400_000,
        0,
    )


def test_public_mark_unknown_is_durable_idempotent_and_retains_liability(tmp_path: Path) -> None:
    ledger = PrimeLedger(tmp_path / "prime.sqlite3")
    ledger.authorize(_request(), now_ms=200)
    ledger.mark_started("request-1", now_ms=210)
    usage = _usage(1_200_000)
    unknown = ledger.mark_unknown("request-1", usage, now_ms=310)
    assert (unknown.state, unknown.charged_micro_usd, unknown.held_micro_usd) == (
        PrimeCallState.UNKNOWN,
        1_200_000,
        1_000_000,
    )
    assert ledger.mark_unknown("request-1", usage, now_ms=311) == unknown
    with pytest.raises(PrimeReplayMismatch):
        ledger.mark_unknown("request-1", _usage(1_200_001), now_ms=312)


def test_private_digest_only_store_and_corruption_version_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "prime.sqlite3"
    ledger = PrimeLedger(path)
    ledger.authorize(_request(), now_ms=200)
    assert path.stat().st_mode & 0o777 == 0o600
    data = path.read_bytes()
    assert b"super secret prompt" not in data
    assert b"provider-secret-never-log" not in data
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=999")
    with pytest.raises(PrimeLedgerCorrupt):
        PrimeLedger(path)
    path.write_bytes(os.urandom(128))
    with pytest.raises(PrimeLedgerCorrupt):
        PrimeLedger(path)


def test_hostile_types_digests_timestamps_and_paths_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        replace(_request(), prompt_digest="ABC")
    with pytest.raises(ValueError):
        replace(_request(), credential_fingerprint="ABC")
    with pytest.raises(ValueError, match="noncanonical"):
        replace(_request(), credential_env_name="OPENAI_API_KEY")
    with pytest.raises(ValueError, match="unsupported"):
        replace(_request(), provider="prime", credential_env_name="PRIME_API_KEY")
    with pytest.raises(ValueError):
        replace(_request(), max_cost_micro_usd=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        replace(_request(), workflow="x" * 257)
    with pytest.raises(ValueError):
        replace(_usage(), input_tokens=1.5)  # type: ignore[arg-type]

    ledger = PrimeLedger(tmp_path / "typed.sqlite3")
    request = _request()
    receipt = ledger.authorize(request, now_ms=200)
    assert ledger.authorize(request, now_ms=2_000) == receipt
    with pytest.raises(PrimeAuthorizationRefused):
        ledger.mark_started(request.request_id, now_ms=199)

    unsafe_parent = tmp_path / "unsafe"
    unsafe_parent.mkdir(mode=0o755)
    with pytest.raises(PrimeLedgerCorrupt):
        PrimeLedger(unsafe_parent / "prime.sqlite3")
    target = tmp_path / "target"
    target.write_text("not sqlite")
    link = tmp_path / "linked.sqlite3"
    link.symlink_to(target)
    with pytest.raises(PrimeLedgerCorrupt):
        PrimeLedger(link)


def test_resolved_credential_is_bound_and_redacted() -> None:
    secret_text = "provider-secret-never-log"
    resolved = ResolvedPrimeCredential(
        owner_id="owner",
        payer_id="payer",
        provider="anthropic",
        credential_id="credential-1",
        credential_fingerprint="a" * 64,
        env_name="ANTHROPIC_API_KEY",
        secret=PrimeSecret(secret_text),
    )
    assert resolved.matches(_request())
    assert not resolved.matches(replace(_request(), payer_id="other"))
    assert resolved.secret.reveal() == secret_text
    assert secret_text not in repr(resolved)
    assert secret_text not in repr(resolved.secret)
    assert secret_text not in str(resolved.secret)
    with pytest.raises(ValueError, match="noncanonical"):
        replace(resolved, env_name="OPENAI_API_KEY")
    with pytest.raises(ValueError, match="redacted PrimeSecret") as caught:
        replace(resolved, secret=secret_text)  # type: ignore[arg-type]
    assert secret_text not in str(caught.value)
