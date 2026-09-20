from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import substrate.multimedia.execution_authorization as execution_authorization
from runtime.db_lock import connect_read
from substrate.midnight_oil.budget_ledger import BudgetLedger
from substrate.multimedia.execution_authorization import (
    MAX_CENTS,
    ExecutionAuthorizationConsumed,
    ExecutionAuthorizationIntegrityError,
    ExecutionAuthorizationRevoked,
    MultimediaExecutionAuthorization,
    execute_authorized_call,
    issue_execution_authorization,
    revoke_execution_authorization,
    verify_execution_authorization,
)

KEY = b"multimedia-execution-authorization-key"
ISSUED_AT = datetime(2026, 7, 11, 1, 30, tzinfo=UTC)
EXPIRES_AT = ISSUED_AT + timedelta(hours=1)
EXECUTION_TIME = ISSUED_AT + timedelta(minutes=1)
REVOCATION_RACE_ROUNDS = 12


def _authorization(**overrides: object) -> MultimediaExecutionAuthorization:
    values: dict[str, object] = {
        "signing_key": KEY,
        "request_id": "request-1",
        "operator_id": "alice",
        "asset_id": "asset-1",
        "revision_id": "revision-2",
        "provider": "krea",
        "route_policy": "balanced",
        "approved_ceiling_cents": 250,
        "issued_at": ISSUED_AT,
        "expires_at": EXPIRES_AT,
    }
    values.update(overrides)
    return issue_execution_authorization(**values)  # type: ignore[arg-type]


def _db_path(tmp_path: Path) -> str:
    return str(tmp_path / "multimedia.duckdb")


def _execute(
    authorization: MultimediaExecutionAuthorization,
    db_path: str,
    call,  # type: ignore[no-untyped-def]
):  # type: ignore[no-untyped-def]
    return execute_authorized_call(
        authorization,
        signing_key=KEY,
        db_path=db_path,
        operator_id="alice",
        asset_id="asset-1",
        revision_id="revision-2",
        provider="krea",
        route_policy="balanced",
        now=EXECUTION_TIME,
        projected_max_cents=250,
        call=call,
    )


def test_receipt_is_deterministic_round_trippable_and_bound() -> None:
    authorization = _authorization()
    assert authorization == _authorization()
    assert MultimediaExecutionAuthorization.from_dict(authorization.to_dict()) == authorization
    verify_execution_authorization(
        authorization,
        signing_key=KEY,
        operator_id="alice",
        asset_id="asset-1",
        revision_id="revision-2",
        provider="krea",
        route_policy="balanced",
        now=EXECUTION_TIME,
    )

    for field, value in (
        ("operator_id", "bob"),
        ("asset_id", "asset-elsewhere"),
        ("revision_id", "revision-stale"),
        ("provider", "other-provider"),
        ("route_policy", "highest_quality"),
    ):
        kwargs = {
            "operator_id": "alice",
            "asset_id": "asset-1",
            "revision_id": "revision-2",
            "provider": "krea",
            "route_policy": "balanced",
            "now": EXECUTION_TIME,
        }
        kwargs[field] = value
        with pytest.raises(ExecutionAuthorizationIntegrityError, match=field):
            verify_execution_authorization(authorization, signing_key=KEY, **kwargs)


def test_tamper_and_wrong_key_fail_closed() -> None:
    authorization = _authorization()
    with pytest.raises(ExecutionAuthorizationIntegrityError, match="identity|signature"):
        verify_execution_authorization(
            replace(authorization, approved_ceiling_cents=251),
            signing_key=KEY,
            operator_id="alice",
            asset_id="asset-1",
            revision_id="revision-2",
            provider="krea",
            route_policy="balanced",
            now=EXECUTION_TIME,
        )

    for malformed in (
        replace(authorization, version=True),
        replace(authorization, authorization_id=1),  # type: ignore[arg-type]
        replace(authorization, signature=None),  # type: ignore[arg-type]
    ):
        with pytest.raises(ExecutionAuthorizationIntegrityError, match="malformed"):
            verify_execution_authorization(
                malformed,
                signing_key=KEY,
                operator_id="alice",
                asset_id="asset-1",
                revision_id="revision-2",
                provider="krea",
                route_policy="balanced",
                now=EXECUTION_TIME,
            )
    with pytest.raises(ExecutionAuthorizationIntegrityError):
        verify_execution_authorization(
            authorization,
            signing_key=b"different-multimedia-signing-key-32",
            operator_id="alice",
            asset_id="asset-1",
            revision_id="revision-2",
            provider="krea",
            route_policy="balanced",
            now=EXECUTION_TIME,
        )


@pytest.mark.parametrize("invalid", [True, 1.5, "250", 0, -1, MAX_CENTS + 1])
def test_money_is_strict_positive_signed_bigint(invalid: object) -> None:
    with pytest.raises(ValueError, match="cents"):
        _authorization(approved_ceiling_cents=invalid)


def test_authorization_has_a_bounded_active_window() -> None:
    authorization = _authorization()
    for checked_at, reason in (
        (ISSUED_AT - timedelta(seconds=1), "not active"),
        (EXPIRES_AT, "expired"),
    ):
        with pytest.raises(ExecutionAuthorizationIntegrityError, match=reason):
            verify_execution_authorization(
                authorization,
                signing_key=KEY,
                operator_id="alice",
                asset_id="asset-1",
                revision_id="revision-2",
                provider="krea",
                route_policy="balanced",
                now=checked_at,
            )

    with pytest.raises(ValueError, match="lifetime"):
        _authorization(expires_at=ISSUED_AT + timedelta(hours=25))


def test_success_holds_before_dispatch_settles_and_is_one_shot(tmp_path: Path) -> None:
    authorization = _authorization()
    db_path = _db_path(tmp_path)
    ledger = BudgetLedger(db_path)
    balances_seen = []

    def provider_call() -> tuple[str, int]:
        balances_seen.append(ledger.balance(authorization.authorization_id))
        return "media-file", 175

    result, balance = _execute(authorization, db_path, provider_call)
    assert result == "media-file"
    assert balances_seen[0].held_cents == 250
    assert balances_seen[0].spent_cents == 0
    assert balance.spent_cents == 175
    assert balance.held_cents == 0
    assert balance.status == "released"

    replay_calls = 0

    def replay() -> tuple[str, int]:
        nonlocal replay_calls
        replay_calls += 1
        return "duplicate", 1

    with pytest.raises(ExecutionAuthorizationConsumed):
        _execute(authorization, db_path, replay)
    assert replay_calls == 0


def test_concurrent_reentry_cannot_dispatch_second_call(tmp_path: Path) -> None:
    authorization = _authorization()
    db_path = _db_path(tmp_path)
    inner_calls = 0

    def outer() -> tuple[str, int]:
        nonlocal inner_calls

        def inner() -> tuple[str, int]:
            nonlocal inner_calls
            inner_calls += 1
            return "inner", 1

        with pytest.raises(ExecutionAuthorizationConsumed):
            _execute(authorization, db_path, inner)
        return "outer", 100

    result, _ = _execute(authorization, db_path, outer)
    assert result == "outer"
    assert inner_calls == 0


def test_unknown_outcome_charges_full_band_and_blocks_replay(tmp_path: Path) -> None:
    authorization = _authorization()
    db_path = _db_path(tmp_path)
    ledger = BudgetLedger(db_path)
    calls = 0

    def uncertain() -> tuple[str, int]:
        nonlocal calls
        calls += 1
        raise TimeoutError("provider may have accepted the call")

    with pytest.raises(TimeoutError):
        _execute(authorization, db_path, uncertain)
    assert calls == 1
    balance = ledger.balance(authorization.authorization_id)
    assert balance.spent_cents == 250
    assert balance.remaining_cents == 0
    assert balance.status == "exhausted"

    with pytest.raises(ExecutionAuthorizationConsumed):
        _execute(authorization, db_path, uncertain)
    assert calls == 1


@pytest.mark.parametrize("actual", [True, -1, 1.5, "10", MAX_CENTS + 1])
def test_malformed_actual_cost_is_charged_conservatively_and_consumed(
    tmp_path: Path,
    actual: object,
) -> None:
    authorization = _authorization(request_id=f"malformed-{actual!r}")
    db_path = _db_path(tmp_path)
    calls = 0

    def malformed():  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return "provider-result", actual

    with pytest.raises(ValueError, match="actual_cents"):
        _execute(authorization, db_path, malformed)
    assert calls == 1
    balance = BudgetLedger(db_path).balance(authorization.authorization_id)
    assert balance.spent_cents == authorization.approved_ceiling_cents
    assert balance.status == "exhausted"
    with pytest.raises(ExecutionAuthorizationConsumed):
        _execute(authorization, db_path, malformed)
    assert calls == 1


def test_zero_cost_and_post_settlement_failure_still_consume_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _authorization(request_id="zero-cost")
    db_path = _db_path(tmp_path)
    calls = 0

    def zero_cost() -> tuple[str, int]:
        nonlocal calls
        calls += 1
        return "free-result", 0

    def fail_settlement(*_args: object) -> None:
        raise RuntimeError("simulated claim settlement failure")

    monkeypatch.setattr(execution_authorization, "_settle_authorization", fail_settlement)
    with pytest.raises(RuntimeError, match="settlement failure"):
        _execute(authorization, db_path, zero_cost)
    assert calls == 1
    with pytest.raises(ExecutionAuthorizationConsumed):
        _execute(authorization, db_path, zero_cost)
    assert calls == 1

    con = connect_read(db_path)
    try:
        row = con.execute(
            "SELECT status FROM multimedia_execution_authorization_claims "
            "WHERE authorization_id = ?",
            [authorization.authorization_id],
        ).fetchone()
    finally:
        con.close()
    assert row == ("claimed",)


@pytest.mark.parametrize("output", [None, "result", ("result",), ["result", 1]])
def test_malformed_callback_shape_is_charged_and_consumed(
    tmp_path: Path,
    output: object,
) -> None:
    authorization = _authorization(request_id=f"shape-{output!r}")
    db_path = _db_path(tmp_path)
    calls = 0

    def malformed():  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return output

    with pytest.raises(ValueError, match="callback must return"):
        _execute(authorization, db_path, malformed)
    assert calls == 1
    balance = BudgetLedger(db_path).balance(authorization.authorization_id)
    assert balance.spent_cents == 250
    with pytest.raises(ExecutionAuthorizationConsumed):
        _execute(authorization, db_path, malformed)
    assert calls == 1


def test_projected_maximum_must_equal_signed_ceiling_before_reserve(tmp_path: Path) -> None:
    authorization = _authorization()
    db_path = _db_path(tmp_path)
    calls = 0

    def call() -> tuple[str, int]:
        nonlocal calls
        calls += 1
        return "never", 1

    with pytest.raises(ExecutionAuthorizationIntegrityError, match="projected maximum"):
        execute_authorized_call(
            authorization,
            signing_key=KEY,
            db_path=db_path,
            operator_id="alice",
            asset_id="asset-1",
            revision_id="revision-2",
            provider="krea",
            route_policy="balanced",
            projected_max_cents=249,
            now=EXECUTION_TIME,
            call=call,
        )
    assert calls == 0


def test_revocation_is_idempotent_and_blocks_execution(tmp_path: Path) -> None:
    authorization = _authorization(request_id="revoked")
    db_path = _db_path(tmp_path)
    first = revoke_execution_authorization(
        authorization,
        signing_key=KEY,
        db_path=db_path,
        operator_id="alice",
        now=EXECUTION_TIME,
    )
    replay = revoke_execution_authorization(
        authorization,
        signing_key=KEY,
        db_path=db_path,
        operator_id="alice",
        now=EXECUTION_TIME + timedelta(seconds=1),
    )
    assert replay == first
    expired_replay = revoke_execution_authorization(
        authorization,
        signing_key=KEY,
        db_path=db_path,
        operator_id="alice",
        now=EXPIRES_AT + timedelta(days=1),
    )
    assert expired_replay == first
    calls = 0

    def call() -> tuple[str, int]:
        nonlocal calls
        calls += 1
        return "never", 1

    with pytest.raises(ExecutionAuthorizationRevoked):
        _execute(authorization, db_path, call)
    assert calls == 0

    with pytest.raises(ExecutionAuthorizationIntegrityError, match="operator_id"):
        revoke_execution_authorization(
            _authorization(request_id="wrong-operator"),
            signing_key=KEY,
            db_path=db_path,
            operator_id="bob",
            now=EXECUTION_TIME,
        )

    consumed = _authorization(request_id="already-executed")
    consumed_root = tmp_path / "consumed"
    consumed_root.mkdir()
    consumed_db = _db_path(consumed_root)
    _execute(consumed, consumed_db, lambda: ("done", 1))
    with pytest.raises(ExecutionAuthorizationConsumed):
        revoke_execution_authorization(
            consumed,
            signing_key=KEY,
            db_path=consumed_db,
            operator_id="alice",
            now=EXECUTION_TIME,
        )


def test_execution_and_revocation_have_exactly_one_durable_winner(tmp_path: Path) -> None:
    for index in range(REVOCATION_RACE_ROUNDS):
        authorization = _authorization(request_id=f"race-{index}")
        race_root = tmp_path / str(index)
        race_root.mkdir()
        db_path = _db_path(race_root)
        calls = 0

        def execute(
            authorization: MultimediaExecutionAuthorization = authorization,
            db_path: str = db_path,
        ) -> str:
            nonlocal calls

            def call() -> tuple[str, int]:
                nonlocal calls
                calls += 1
                return "executed", 1

            try:
                _execute(authorization, db_path, call)
                return "executed"
            except ExecutionAuthorizationRevoked:
                return "revoked"

        def revoke(
            authorization: MultimediaExecutionAuthorization = authorization,
            db_path: str = db_path,
        ) -> str:
            try:
                revoke_execution_authorization(
                    authorization,
                    signing_key=KEY,
                    db_path=db_path,
                    operator_id="alice",
                    now=EXECUTION_TIME,
                )
                return "revoked"
            except ExecutionAuthorizationConsumed:
                return "executed"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = {pool.submit(execute), pool.submit(revoke)}
            results = [future.result() for future in outcomes]
        assert len(set(results)) == 1
        assert results[0] in {"executed", "revoked"}
        assert calls == (1 if results[0] == "executed" else 0)


def test_module_has_no_provider_network_or_environment_surface() -> None:
    source = Path(__file__).parents[1] / "substrate" / "multimedia" / "execution_authorization.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    assert roots.isdisjoint({"httpx", "requests", "urllib", "socket", "subprocess", "os", "krea"})
