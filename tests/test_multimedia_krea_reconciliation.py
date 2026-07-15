from __future__ import annotations

import hashlib
import importlib.resources
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from integrations.krea.client import KreaClient, KreaClientError
from integrations.krea.reconciliation import (
    RECONCILIATION_OPENAPI_SUBSET_SHA256,
    receive_webhook_wake,
)
from runtime.db_lock import connect_read, connect_write
from substrate.midnight_oil.budget_ledger import BudgetLedger, CallHold
from substrate.multimedia.execution_authorization import issue_async_execution_authorization
from substrate.multimedia.krea_reconcile import observe_provider_job
from substrate.multimedia.provider_execution import (
    ProviderExecutionIntegrityError,
    ProviderExecutionStatus,
    begin_reserved_provider_submission,
    bind_provider_job,
    get_provider_execution,
    request_provider_cancellation,
)

KEY = b"reconciliation-test-signing-key-32"
NOW = datetime(2026, 7, 11, tzinfo=UTC)
JOB = "10000000-0000-4000-8000-000000000001"
BODY = hashlib.sha256(b"body").hexdigest()
ACCOUNT = hashlib.sha256(b"token-id").hexdigest()


class _LoopbackKreaClient(KreaClient):
    def __init__(self, payload: object, token: str = "token-id:secret-never-log-this") -> None:
        super().__init__(token)
        self.payload = payload
        self.paths: list[str] = []

    def _request(self, method: str, path: str) -> bytes:
        assert method == "GET"
        self.paths.append(path)
        return json.dumps(self.payload).encode()


def _payload(status: str, *, job_id: str = JOB, urls: object = None) -> dict[str, object]:
    value: dict[str, object] = {
        "job_id": job_id,
        "status": status,
        "created_at": "2026-07-11T00:00:00Z",
    }
    if status == "completed":
        value.update(
            completed_at="2026-07-11T00:00:01Z",
            result={"urls": urls or ["https://cdn.example/a.png"]},
        )
    elif status == "failed":
        value.update(
            completed_at="2026-07-11T00:00:01Z",
            error={"code": "generation_failed", "message": "safe"},
        )
    elif status == "cancelled":
        value.update(completed_at="2026-07-11T00:00:01Z")
    return value


def _execution(tmp_path: Path, suffix: str = "one"):
    authorization = issue_async_execution_authorization(
        signing_key=KEY,
        request_id=f"request-{suffix}",
        operator_id="operator",
        asset_id="asset",
        revision_id="revision",
        provider="krea",
        route_policy="balanced",
        model="model",
        endpoint_capability="image",
        catalog_version="v1",
        catalog_digest=hashlib.sha256(b"catalog").hexdigest(),
        quote_id="quote",
        quote_expires_at=NOW + timedelta(minutes=5),
        recovery_authority_id="recovery",
        recovery_verification_key_digest=hashlib.sha256(b"recovery-key").hexdigest(),
        approved_ceiling_microdollars=250_001,
        request_body_digest=BODY,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    db_path = str(tmp_path / f"{suffix}.duckdb")
    record, _ = begin_reserved_provider_submission(
        db_path=db_path, authorization=authorization, signing_key=KEY, now=NOW
    )
    record = bind_provider_job(
        db_path=db_path,
        execution_id=record.execution_id,
        provider_job_id=JOB,
        signing_key=KEY,
        now=NOW + timedelta(seconds=1),
    )
    return db_path, authorization, record


def _observe(
    db_path: str,
    execution_id: str,
    status: str,
    *,
    at: datetime,
    before_commit=None,
    token="token-id:secret",
):
    client = _LoopbackKreaClient(_payload(status), token)
    result = observe_provider_job(
        db_path=db_path,
        execution_id=execution_id,
        client=client,
        signing_key=KEY,
        observed_at=at,
        before_commit=before_commit,
    )
    assert client.paths == [f"/jobs/{JOB}"]
    return result


@pytest.mark.parametrize(
    "urls,expected",
    [
        (["https://cdn.example/a.png"], ("https://cdn.example/a.png",)),
        ([{"type": "model", "url": "https://cdn.example/a.mp4"}], ("https://cdn.example/a.mp4",)),
        (
            {"preview": "https://cdn.example/p.png", "model": "https://cdn.example/m.png"},
            ("https://cdn.example/m.png", "https://cdn.example/p.png"),
        ),
    ],
)
def test_poll_uses_complete_pinned_job_contract_once(
    urls: object, expected: tuple[str, ...]
) -> None:
    client = _LoopbackKreaClient(_payload("completed", urls=urls))
    observed = client.poll(JOB)
    assert observed.results == expected and observed.account_identity_digest == ACCOUNT
    assert client.paths == [f"/jobs/{JOB}"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.pop("created_at"),
        lambda p: p.update(created_at="x"),
        lambda p: p.update(completed_at="2026-07-11T00:00:01+00:00"),
        lambda p: p.update(result={"urls": [], "extra": 1}),
        lambda p: p.update(result={"urls": ["not a uri"]}),
        lambda p: p.update(result={"style_id": 3}),
        lambda p: p.update(error={"message": "missing code"}),
    ],
)
def test_poll_rejects_incomplete_or_status_inconsistent_schema(mutation) -> None:
    payload = _payload("completed")
    mutation(payload)
    with pytest.raises(KreaClientError) as caught:
        _LoopbackKreaClient(payload).poll(JOB)
    assert "secret-never-log-this" not in repr(caught.value)


def test_poll_accepts_optional_terminal_fields_and_fractional_timestamp() -> None:
    payload = _payload("completed")
    payload["created_at"] = "2026-07-11T00:00:00.123Z"
    payload.pop("completed_at")
    payload.pop("result")
    observed = _LoopbackKreaClient(payload).poll(JOB)
    assert observed.status == "completed"
    assert observed.results == ()


def test_openapi_subset_is_packaged_and_pinned() -> None:
    resource = importlib.resources.files("integrations.krea").joinpath(
        "reconciliation_openapi_subset.json"
    )
    assert hashlib.sha256(resource.read_bytes()).hexdigest() == RECONCILIATION_OPENAPI_SUBSET_SHA256


def test_public_boundary_polls_and_settles_without_caller_evidence(tmp_path: Path) -> None:
    db_path, authorization, record = _execution(tmp_path)
    result = _observe(db_path, record.execution_id, "completed", at=NOW + timedelta(seconds=2))
    assert result.status is ProviderExecutionStatus.SUCCEEDED
    assert (
        _observe(db_path, record.execution_id, "completed", at=NOW + timedelta(seconds=3)) == result
    )
    assert (
        BudgetLedger(db_path).balance(authorization.authorization_id).spent_cents,
        BudgetLedger(db_path).balance(authorization.authorization_id).held_cents,
    ) == (26, 0)
    with connect_read(db_path) as connection:
        claim = connection.execute(
            "SELECT status, actual_cents, settled_at FROM "
            "multimedia_execution_authorization_claims WHERE authorization_id=?",
            [authorization.authorization_id],
        ).fetchone()
    assert claim is not None
    assert claim[:2] == ("settled", 26)
    assert claim[2] is not None


def test_success_rejects_a_hold_pre_settled_below_ceiling(tmp_path: Path) -> None:
    db_path, authorization, record = _execution(tmp_path, "under-settled")
    ledger = BudgetLedger(db_path)
    with connect_read(db_path) as connection:
        hold_row = connection.execute(
            "SELECT hold_id, run_id, role, projected_max_cents "
            "FROM midnight_oil_call_holds WHERE run_id=?",
            [authorization.authorization_id],
        ).fetchone()
    assert hold_row is not None
    ledger.settle(CallHold(*hold_row), 1)
    with pytest.raises(ProviderExecutionIntegrityError, match="ceiling-settled"):
        _observe(db_path, record.execution_id, "completed", at=NOW + timedelta(seconds=2))
    assert ledger.balance(authorization.authorization_id).spent_cents == 1


def test_terminal_same_outcome_converges_but_competing_outcome_fails(tmp_path: Path) -> None:
    db_path, _, record = _execution(tmp_path, "terminal-replay")
    first = _observe(db_path, record.execution_id, "failed", at=NOW + timedelta(seconds=2))
    payload = _payload("failed")
    payload["error"] = {"code": "different-safe-code"}
    replay = observe_provider_job(
        db_path=db_path,
        execution_id=record.execution_id,
        client=_LoopbackKreaClient(payload),
        signing_key=KEY,
        observed_at=NOW + timedelta(seconds=3),
    )
    assert replay == first
    with pytest.raises(ProviderExecutionIntegrityError, match="terminal"):
        _observe(db_path, record.execution_id, "completed", at=NOW + timedelta(seconds=4))


@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
def test_nonbillable_terminal_proof_retains_full_hold(tmp_path: Path, terminal: str) -> None:
    db_path, authorization, record = _execution(tmp_path, f"retain-{terminal}")
    result = _observe(db_path, record.execution_id, terminal, at=NOW + timedelta(seconds=2))
    assert result.status.value == terminal
    balance = BudgetLedger(db_path).balance(authorization.authorization_id)
    assert (balance.spent_cents, balance.held_cents) == (0, 26)
    with connect_read(db_path) as connection:
        claim = connection.execute(
            "SELECT status, actual_cents, settled_at FROM "
            "multimedia_execution_authorization_claims WHERE authorization_id=?",
            [authorization.authorization_id],
        ).fetchone()
    assert claim == ("reconciliation_required", None, None)


@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
def test_nonbillable_terminal_rejects_tampered_hold_state(tmp_path: Path, terminal: str) -> None:
    db_path, authorization, record = _execution(tmp_path, f"tampered-{terminal}")
    ledger = BudgetLedger(db_path)
    with connect_read(db_path) as connection:
        hold_row = connection.execute(
            "SELECT hold_id, run_id, role, projected_max_cents "
            "FROM midnight_oil_call_holds WHERE run_id=?",
            [authorization.authorization_id],
        ).fetchone()
    assert hold_row is not None
    ledger.settle(CallHold(*hold_row), 1)
    with pytest.raises(ProviderExecutionIntegrityError, match="retention"):
        _observe(db_path, record.execution_id, terminal, at=NOW + timedelta(seconds=2))


def test_exact_terminal_replay_revalidates_accounting(tmp_path: Path) -> None:
    db_path, authorization, record = _execution(tmp_path, "replay-accounting")
    _observe(db_path, record.execution_id, "failed", at=NOW + timedelta(seconds=2))
    with connect_read(db_path) as connection:
        hold_row = connection.execute(
            "SELECT hold_id, run_id, role, projected_max_cents "
            "FROM midnight_oil_call_holds WHERE run_id=?",
            [authorization.authorization_id],
        ).fetchone()
    assert hold_row is not None
    BudgetLedger(db_path).settle(CallHold(*hold_row), 1)
    with pytest.raises(ProviderExecutionIntegrityError, match="accounting"):
        _observe(db_path, record.execution_id, "failed", at=NOW + timedelta(seconds=3))


def test_terminal_rejects_tampered_authorization_claim_signature(tmp_path: Path) -> None:
    db_path, authorization, record = _execution(tmp_path, "claim-signature")
    with connect_write(db_path, purpose="test.tamper_claim_signature") as connection:
        connection.execute(
            "UPDATE multimedia_execution_authorization_claims SET signature='tampered' "
            "WHERE authorization_id=?",
            [authorization.authorization_id],
        )
    with pytest.raises(ProviderExecutionIntegrityError, match="terminalization"):
        _observe(db_path, record.execution_id, "failed", at=NOW + timedelta(seconds=2))


def test_wrong_job_account_and_signed_record_tamper_fail(tmp_path: Path) -> None:
    db_path, _, record = _execution(tmp_path, "binding")
    with pytest.raises(KreaClientError):
        observe_provider_job(
            db_path=db_path,
            execution_id=record.execution_id,
            client=_LoopbackKreaClient(
                _payload("completed", job_id="20000000-0000-4000-8000-000000000002")
            ),
            signing_key=KEY,
            observed_at=NOW + timedelta(seconds=2),
        )
    _observe(
        db_path,
        record.execution_id,
        "processing",
        at=NOW + timedelta(seconds=2),
        token="other-account:secret",
    )
    with pytest.raises(ProviderExecutionIntegrityError, match="account"):
        _observe(db_path, record.execution_id, "completed", at=NOW + timedelta(seconds=3))
    with pytest.raises(ProviderExecutionIntegrityError):
        get_provider_execution(
            db_path=db_path, execution_id=record.execution_id, signing_key=b"x" * 32
        )


def test_crash_rolls_back_and_retry_is_safe(tmp_path: Path) -> None:
    db_path, authorization, record = _execution(tmp_path, "crash")
    with pytest.raises(RuntimeError, match="crash"):
        _observe(
            db_path,
            record.execution_id,
            "completed",
            at=NOW + timedelta(seconds=2),
            before_commit=lambda _: (_ for _ in ()).throw(RuntimeError("crash")),
        )
    assert (
        get_provider_execution(
            db_path=db_path, execution_id=record.execution_id, signing_key=KEY
        ).status
        is ProviderExecutionStatus.SUBMITTED
    )
    assert BudgetLedger(db_path).balance(authorization.authorization_id).held_cents == 26
    assert (
        _observe(db_path, record.execution_id, "completed", at=NOW + timedelta(seconds=3)).status
        is ProviderExecutionStatus.SUCCEEDED
    )


def test_100_deterministic_randomized_poll_cancel_orderings(tmp_path: Path) -> None:
    rng = random.Random(3)
    for case in range(100):
        db_path, _, record = _execution(tmp_path, f"order-{case}")
        steps = sorted(
            [rng.choice(["queued", "processing"]) for _ in range(rng.randrange(0, 4))],
            key={"queued": 0, "processing": 1}.get,
        )
        cancel_at = rng.randrange(len(steps) + 1)
        for index, status in enumerate(steps):
            if index == cancel_at:
                request_provider_cancellation(
                    db_path=db_path,
                    execution_id=record.execution_id,
                    signing_key=KEY,
                    now=NOW + timedelta(seconds=2 + index * 2),
                )
            _observe(
                db_path, record.execution_id, status, at=NOW + timedelta(seconds=3 + index * 2)
            )
        if cancel_at == len(steps):
            request_provider_cancellation(
                db_path=db_path,
                execution_id=record.execution_id,
                signing_key=KEY,
                now=NOW + timedelta(seconds=20),
            )
        terminal = rng.choice(["completed", "failed", "cancelled"])
        result = _observe(db_path, record.execution_id, terminal, at=NOW + timedelta(seconds=30))
        assert (
            result.status.value
            == {"completed": "succeeded", "failed": "failed", "cancelled": "cancelled"}[terminal]
        )


def test_webhook_is_wake_only(tmp_path: Path) -> None:
    receipt = receive_webhook_wake(b'{"status":"completed"}')
    assert receipt.wake_only and receipt.byte_count
