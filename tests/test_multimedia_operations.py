from __future__ import annotations

import ast
import hashlib
import hmac
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from integrations.krea.client import KreaClient
from runtime.db_lock import connect_write
from substrate.midnight_oil.budget_ledger import BudgetLedger
from substrate.multimedia.execution_authorization import issue_async_execution_authorization
from substrate.multimedia.krea_reconcile import observe_provider_job
from substrate.multimedia.operations import (
    KillSwitchPolicy,
    MultimediaExecutionUnavailable,
    MultimediaOperationConflict,
    MultimediaOperationRateLimited,
    cancel_execution,
    get_execution,
    list_executions,
    request_reconciliation,
)
from substrate.multimedia.provider_execution import (
    ProviderExecutionStatus,
    begin_reserved_provider_submission,
    bind_provider_job,
    charge_and_mark_submission_unknown,
    record_external_recovery_evidence,
)

KEY = b"operations-test-signing-key-32-bytes"
NOW = datetime(2026, 7, 11, tzinfo=UTC)


class _PollClient(KreaClient):
    def __init__(self, payload: dict[str, object]) -> None:
        super().__init__("account:secret")
        self.payload = payload

    def _request(self, method: str, path: str) -> bytes:
        assert method == "GET" and path.startswith("/jobs/")
        return json.dumps(self.payload).encode()


def _authorization(suffix: str, operator: str = "operator-a", recovery_key: bytes = b"recovery"):
    return issue_async_execution_authorization(
        signing_key=KEY,
        request_id=f"request-{suffix}",
        operator_id=operator,
        asset_id=f"asset-{suffix}",
        revision_id="revision",
        provider="krea",
        route_policy="balanced",
        model="imagen-3",
        endpoint_capability="image",
        catalog_version="v1",
        catalog_digest=hashlib.sha256(b"catalog").hexdigest(),
        quote_id=f"quote-{suffix}",
        quote_expires_at=NOW + timedelta(minutes=5),
        recovery_authority_id="recovery",
        recovery_verification_key_digest=hashlib.sha256(recovery_key).hexdigest(),
        approved_ceiling_microdollars=250_001,
        request_body_digest=hashlib.sha256(suffix.encode()).hexdigest(),
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )


def _seed(db_path: str, suffix: str = "one", operator: str = "operator-a", job: str | None = None):
    authorization = _authorization(suffix, operator)
    record, _ = begin_reserved_provider_submission(
        db_path=db_path, authorization=authorization, signing_key=KEY, now=NOW
    )
    if job is not None:
        record = bind_provider_job(
            db_path=db_path,
            execution_id=record.execution_id,
            provider_job_id=job,
            signing_key=KEY,
            now=NOW + timedelta(seconds=1),
        )
    return authorization, record


def test_owner_get_is_redacted_accounted_and_reopen_safe(tmp_path: Path) -> None:
    db = str(tmp_path / "db.duckdb")
    authorization, record = _seed(db, job="job-one")
    view = get_execution(
        db_path=db,
        execution_id=record.execution_id,
        authenticated_operator_id="operator-a",
        signing_key=KEY,
    )
    assert view.status is ProviderExecutionStatus.SUBMITTED
    assert (view.charged_cents, view.retained_cents, view.claim_status) == (0, 26, "claimed")
    text = repr(asdict(view))
    for secret in (authorization.signature, record.request_body_digest, "job-one", "recovery"):
        assert secret not in text
    assert (
        get_execution(
            db_path=db,
            execution_id=record.execution_id,
            authenticated_operator_id="operator-a",
            signing_key=KEY,
        )
        == view
    )


@pytest.mark.parametrize("candidate", ["missing", " bad ", None, 7])
def test_missing_malformed_and_cross_owner_are_identical(tmp_path: Path, candidate: object) -> None:
    db = str(tmp_path / "db.duckdb")
    _, record = _seed(db, job="job-one")
    messages = []
    for execution_id, operator in ((candidate, "operator-a"), (record.execution_id, "operator-b")):
        with pytest.raises(MultimediaExecutionUnavailable) as caught:
            get_execution(
                db_path=db,
                execution_id=execution_id,
                authenticated_operator_id=operator,
                signing_key=KEY,
            )
        messages.append(str(caught.value))
    assert len(set(messages)) == 1


def test_empty_and_owner_keyset_pages_are_bounded(tmp_path: Path) -> None:
    missing = list_executions(
        db_path=str(tmp_path / "missing.duckdb"),
        authenticated_operator_id="operator-a",
        signing_key=KEY,
    )
    assert missing.items == () and missing.next_cursor is None
    db = str(tmp_path / "shared.duckdb")
    ids = []
    for index in range(5):
        _, record = _seed(db, f"a-{index}", job=f"job-a-{index}")
        ids.append(record.execution_id)
    _seed(db, "other", "operator-b", "job-other")
    first = list_executions(
        db_path=db, authenticated_operator_id="operator-a", signing_key=KEY, limit=2
    )
    second = list_executions(
        db_path=db,
        authenticated_operator_id="operator-a",
        signing_key=KEY,
        limit=2,
        after=first.next_cursor,
    )
    third = list_executions(
        db_path=db,
        authenticated_operator_id="operator-a",
        signing_key=KEY,
        limit=2,
        after=second.next_cursor,
    )
    assert [item.execution_id for page in (first, second, third) for item in page.items] == sorted(
        ids
    )
    with pytest.raises(ValueError):
        list_executions(
            db_path=db, authenticated_operator_id="operator-a", signing_key=KEY, limit=101
        )


def test_read_fails_closed_on_execution_claim_and_accounting_tamper(tmp_path: Path) -> None:
    db = str(tmp_path / "db.duckdb")
    authorization, record = _seed(db, job="job-one")
    with connect_write(db, purpose="test.tamper_claim") as connection:
        connection.execute(
            "UPDATE multimedia_execution_authorization_claims SET signature='tampered' WHERE authorization_id=?",
            [authorization.authorization_id],
        )
    with pytest.raises(MultimediaOperationConflict, match="claim"):
        get_execution(
            db_path=db,
            execution_id=record.execution_id,
            authenticated_operator_id="operator-a",
            signing_key=KEY,
        )


def test_submitting_and_unknown_views_enforce_exact_accounting(tmp_path: Path) -> None:
    submitting_db = str(tmp_path / "submitting.duckdb")
    _, submitting = _seed(submitting_db, "submitting")
    submitting_view = get_execution(
        db_path=submitting_db,
        execution_id=submitting.execution_id,
        authenticated_operator_id="operator-a",
        signing_key=KEY,
    )
    assert (submitting_view.charged_cents, submitting_view.retained_cents) == (0, 26)

    unknown_db = str(tmp_path / "unknown.duckdb")
    authorization = _authorization("unknown")
    unknown, hold = begin_reserved_provider_submission(
        db_path=unknown_db, authorization=authorization, signing_key=KEY, now=NOW
    )
    unknown = charge_and_mark_submission_unknown(
        db_path=unknown_db,
        execution_id=unknown.execution_id,
        hold=hold,
        signing_key=KEY,
        now=NOW + timedelta(seconds=1),
    )
    unknown_view = get_execution(
        db_path=unknown_db,
        execution_id=unknown.execution_id,
        authenticated_operator_id="operator-a",
        signing_key=KEY,
    )
    assert (unknown_view.charged_cents, unknown_view.retained_cents) == (26, 0)
    with connect_write(unknown_db, purpose="test.tamper_unknown_accounting") as connection:
        connection.execute(
            "UPDATE midnight_oil_reservations SET spent_cents=25, held_cents=1 WHERE run_id=?",
            [authorization.authorization_id],
        )
    with pytest.raises(MultimediaOperationConflict, match="accounting"):
        get_execution(
            db_path=unknown_db,
            execution_id=unknown.execution_id,
            authenticated_operator_id="operator-a",
            signing_key=KEY,
        )


def test_recovered_unknown_remains_readable_and_cancellable_at_full_charge(tmp_path: Path) -> None:
    db = str(tmp_path / "recovered.duckdb")
    evidence_key = b"operations-external-evidence-key!!"
    authorization = _authorization("recovered", recovery_key=evidence_key)
    unknown, hold = begin_reserved_provider_submission(
        db_path=db, authorization=authorization, signing_key=KEY, now=NOW
    )
    unknown = charge_and_mark_submission_unknown(
        db_path=db,
        execution_id=unknown.execution_id,
        hold=hold,
        signing_key=KEY,
        now=NOW + timedelta(seconds=1),
    )
    job_id = "10000000-0000-4000-8000-000000000003"
    recorded_at = NOW + timedelta(seconds=2)
    evidence_digest = hashlib.sha256(b"account-audit").hexdigest()
    timestamp = recorded_at.isoformat().replace("+00:00", "Z")
    payload = json.dumps(
        [unknown.execution_id, job_id, "recovery", evidence_digest, timestamp],
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    record_external_recovery_evidence(
        db_path=db,
        execution_id=unknown.execution_id,
        provider_job_id=job_id,
        source="recovery",
        evidence_digest=evidence_digest,
        signing_key=KEY,
        evidence_verification_key=evidence_key,
        external_signature=hmac.new(evidence_key, payload, hashlib.sha256).hexdigest(),
        recorded_at=recorded_at,
    )
    recovered = bind_provider_job(
        db_path=db,
        execution_id=unknown.execution_id,
        provider_job_id=job_id,
        signing_key=KEY,
        now=NOW + timedelta(seconds=3),
    )
    view = get_execution(
        db_path=db,
        execution_id=recovered.execution_id,
        authenticated_operator_id="operator-a",
        signing_key=KEY,
    )
    assert (view.charged_cents, view.retained_cents) == (26, 0)
    cancelled = cancel_execution(
        db_path=db,
        execution_id=recovered.execution_id,
        authenticated_operator_id="operator-a",
        signing_key=KEY,
        now=NOW + timedelta(seconds=4),
    )
    assert (cancelled.status, cancelled.charged_cents, cancelled.retained_cents) == (
        ProviderExecutionStatus.CANCEL_REQUESTED,
        26,
        0,
    )


def test_cancel_is_owner_scoped_local_idempotent_and_retains_hold(tmp_path: Path) -> None:
    db = str(tmp_path / "db.duckdb")
    _, record = _seed(db, job="job-one")
    first = cancel_execution(
        db_path=db,
        execution_id=record.execution_id,
        authenticated_operator_id="operator-a",
        signing_key=KEY,
        now=NOW + timedelta(seconds=2),
    )
    second = cancel_execution(
        db_path=db,
        execution_id=record.execution_id,
        authenticated_operator_id="operator-a",
        signing_key=KEY,
        now=NOW + timedelta(seconds=3),
    )
    assert first == second
    assert first.cancellation_state == "pending"
    assert BudgetLedger(db).balance(record.authorization_id).held_cents == 26


@pytest.mark.parametrize(
    ("provider_status", "expected_status", "claim_status", "charged", "retained"),
    [
        ("completed", ProviderExecutionStatus.SUCCEEDED, "settled", 26, 0),
        ("failed", ProviderExecutionStatus.FAILED, "reconciliation_required", 0, 26),
    ],
)
def test_terminal_views_follow_authenticated_reconciliation_accounting(
    tmp_path: Path,
    provider_status: str,
    expected_status: ProviderExecutionStatus,
    claim_status: str,
    charged: int,
    retained: int,
) -> None:
    db = str(tmp_path / f"{provider_status}.duckdb")
    job_id = "10000000-0000-4000-8000-000000000001"
    _, record = _seed(db, provider_status, job=job_id)
    payload: dict[str, object] = {
        "job_id": job_id,
        "status": provider_status,
        "created_at": "2026-07-11T00:00:00Z",
    }
    if provider_status == "completed":
        payload["result"] = {"urls": ["https://cdn.example/a.png"]}
    else:
        payload["error"] = {"code": "generation_failed"}
    observe_provider_job(
        db_path=db,
        execution_id=record.execution_id,
        client=_PollClient(payload),
        signing_key=KEY,
        observed_at=NOW + timedelta(seconds=2),
    )
    view = get_execution(
        db_path=db,
        execution_id=record.execution_id,
        authenticated_operator_id="operator-a",
        signing_key=KEY,
    )
    assert (view.status, view.claim_status) == (expected_status, claim_status)
    assert (view.charged_cents, view.retained_cents) == (charged, retained)


def test_reconciliation_wake_replay_precedes_conflict_and_rate_limit(tmp_path: Path) -> None:
    db = str(tmp_path / "db.duckdb")
    _, record = _seed(db, job="job-one")
    first = request_reconciliation(
        db_path=db,
        execution_id=record.execution_id,
        authenticated_operator_id="operator-a",
        reason="manual",
        idempotency_key="key-1",
        signing_key=KEY,
        now=NOW + timedelta(seconds=2),
        max_requests=2,
    )
    assert (
        request_reconciliation(
            db_path=db,
            execution_id=record.execution_id,
            authenticated_operator_id="operator-a",
            reason="manual",
            idempotency_key="key-1",
            signing_key=KEY,
            now=NOW + timedelta(seconds=50),
            max_requests=1,
        )
        == first
    )
    with pytest.raises(MultimediaOperationConflict):
        request_reconciliation(
            db_path=db,
            execution_id=record.execution_id,
            authenticated_operator_id="operator-a",
            reason="stale",
            idempotency_key="key-1",
            signing_key=KEY,
            now=NOW + timedelta(seconds=3),
        )
    request_reconciliation(
        db_path=db,
        execution_id=record.execution_id,
        authenticated_operator_id="operator-a",
        reason="stale",
        idempotency_key="key-2",
        signing_key=KEY,
        now=NOW + timedelta(seconds=3),
        max_requests=2,
    )
    with pytest.raises(MultimediaOperationRateLimited):
        request_reconciliation(
            db_path=db,
            execution_id=record.execution_id,
            authenticated_operator_id="operator-a",
            reason="manual",
            idempotency_key="key-3",
            signing_key=KEY,
            now=NOW + timedelta(seconds=4),
            max_requests=2,
        )


def test_existing_wake_replays_after_terminal_but_new_wake_is_rejected(tmp_path: Path) -> None:
    db = str(tmp_path / "db.duckdb")
    job_id = "10000000-0000-4000-8000-000000000002"
    _, record = _seed(db, job="10000000-0000-4000-8000-000000000002")
    receipt = request_reconciliation(
        db_path=db,
        execution_id=record.execution_id,
        authenticated_operator_id="operator-a",
        reason="manual",
        idempotency_key="before-terminal",
        signing_key=KEY,
        now=NOW + timedelta(seconds=2),
    )
    observe_provider_job(
        db_path=db,
        execution_id=record.execution_id,
        client=_PollClient(
            {
                "job_id": job_id,
                "status": "failed",
                "created_at": "2026-07-11T00:00:00Z",
                "error": {"code": "generation_failed"},
            }
        ),
        signing_key=KEY,
        observed_at=NOW + timedelta(seconds=3),
    )
    assert (
        request_reconciliation(
            db_path=db,
            execution_id=record.execution_id,
            authenticated_operator_id="operator-a",
            reason="manual",
            idempotency_key="before-terminal",
            signing_key=KEY,
            now=NOW + timedelta(seconds=4),
        )
        == receipt
    )
    with pytest.raises(MultimediaOperationConflict, match="not eligible"):
        request_reconciliation(
            db_path=db,
            execution_id=record.execution_id,
            authenticated_operator_id="operator-a",
            reason="manual",
            idempotency_key="after-terminal",
            signing_key=KEY,
            now=NOW + timedelta(seconds=4),
        )


def test_wake_crash_rolls_back_and_mac_tamper_fails(tmp_path: Path) -> None:
    db = str(tmp_path / "db.duckdb")
    _, record = _seed(db, job="job-one")
    with pytest.raises(RuntimeError, match="crash"):
        request_reconciliation(
            db_path=db,
            execution_id=record.execution_id,
            authenticated_operator_id="operator-a",
            reason="manual",
            idempotency_key="crash",
            signing_key=KEY,
            now=NOW + timedelta(seconds=2),
            before_commit=lambda _: (_ for _ in ()).throw(RuntimeError("crash")),
        )
    receipt = request_reconciliation(
        db_path=db,
        execution_id=record.execution_id,
        authenticated_operator_id="operator-a",
        reason="manual",
        idempotency_key="crash",
        signing_key=KEY,
        now=NOW + timedelta(seconds=3),
    )
    with connect_write(db, purpose="test.tamper_wake") as connection:
        connection.execute(
            "UPDATE multimedia_reconciliation_wake_requests SET reason='stale' WHERE wake_id=?",
            [receipt.wake_id],
        )
    with pytest.raises(MultimediaOperationConflict):
        request_reconciliation(
            db_path=db,
            execution_id=record.execution_id,
            authenticated_operator_id="operator-a",
            reason="manual",
            idempotency_key="crash",
            signing_key=KEY,
            now=NOW + timedelta(seconds=4),
        )


def test_kill_switch_matrix_is_typed_and_does_not_block_read_or_reconcile() -> None:
    policy = KillSwitchPolicy(
        disabled_providers=frozenset({"krea"}),
        disabled_models=frozenset({"runway"}),
        disabled_routes=frozenset({"highest_quality"}),
        webhook_disabled=True,
        artifact_fetch_disabled=True,
    )
    assert policy.blocks_paid_start(provider="krea", model="x", route_policy="balanced")
    assert policy.blocks_paid_start(provider="x", model="runway", route_policy="balanced")
    assert policy.blocks_paid_start(provider="x", model="x", route_policy="highest_quality")
    assert not policy.blocks_paid_start(provider="x", model="x", route_policy="balanced")
    assert policy.allows_reads() and policy.allows_reconciliation()
    with pytest.raises(ValueError):
        KillSwitchPolicy(disabled_providers={"krea"})  # type: ignore[arg-type]


def test_module_has_no_transport_submit_or_poll_surface() -> None:
    tree = ast.parse(Path("substrate/multimedia/operations.py").read_text())
    imports = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(name.startswith(("httpx", "requests", "urllib", "socket")) for name in imports)
    public = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    assert not any("submit" in name or "poll" in name or "start" in name for name in public)
