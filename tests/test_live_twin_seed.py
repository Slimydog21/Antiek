from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.engagement_routes import (
    bind_live_twin_seed_execution,
    get_engagement_store,
    register_engagement_routes,
    reset_engagement_stores,
)
from substrate.engagement_spine.authority import (
    EngagementAuthority,
    operator_engagement_authority,
)
from substrate.engagement_spine.live_twin_seed import (
    LiveTwinDispatchResult,
    LiveTwinReconciliationRequired,
    LiveTwinUnit,
    run_live_twin_seed,
)
from substrate.engagement_spine.store import InMemoryEngagementStore, authorized_store
from substrate.engagement_spine.twin import list_twin_notes, record_twin_insight
from substrate.midnight_oil.budget_ledger import (
    BudgetLedger,
    CallNotDispatched,
    UnknownCallOutcome,
)


def _canonical(store, asset_id: str = "paper") -> None:
    body = "Owner-only canonical evidence. " * 80
    store.put_document(
        asset_id,
        {
            "document_id": asset_id,
            "title": "Canonical title",
            "body_text": body,
            "view_format": "html",
            "hydrated": True,
            "hydration_status": "body_complete",
            "hydration_receipt": {
                "verified_body": True,
                "canonical_content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "canonical_hosted_document_id": "hdoc_owner",
            },
        },
    )


def _scoped(base=None, owner: str = "alice"):
    return authorized_store(base or InMemoryEngagementStore(), EngagementAuthority(owner))


class _Executor:
    def __init__(self, *, route: str = "openai/gpt-test", malformed: bool = False):
        self.calls = []
        self.route = route
        self.malformed = malformed

    def execute(self, request):
        self.calls.append(request)
        provider, model = self.route.split("/", 1)
        units = (
            (LiveTwinUnit("insight", "Evidence-bound insight"),)
            if self.malformed
            else (
                LiveTwinUnit("insight", "Evidence-bound insight"),
                LiveTwinUnit("question", "What evidence could refute this?"),
            )
        )
        return LiveTwinDispatchResult(
            units=units,
            provider=provider,
            model=model,
            dispatch_event_id="evt-dispatch",
            prompt_sha256=request.prompt_sha256,
            source_text_sha256=request.source_text_sha256,
            input_tokens=120,
            output_tokens=30,
            actual_cents=3,
            finish_reason="stop",
        )


def _ledger(path) -> BudgetLedger:
    ledger = BudgetLedger(str(path))
    ledger.ensure_schema()
    return ledger


def test_live_seed_uses_canonical_body_budget_receipt_and_preserves_user_note(tmp_path):
    store = _scoped()
    _canonical(store)
    record_twin_insight("paper", "My irreplaceable note", store=store)
    executor = _Executor()
    ledger = _ledger(tmp_path / "budget.duckdb")
    outcome = run_live_twin_seed(
        asset_id="paper",
        owner_id="alice",
        store=store,
        ledger=ledger,
        executor=executor,
        approved_ceiling_cents=10,
        approval_nonce="approval-1",
        allowed_routes=["openai/gpt-test"],
        projected_max_cents=5,
    )
    assert outcome.state == "live_committed"
    assert outcome.receipt["actual_cents"] == 3
    assert outcome.receipt["promotion_performed"] is False
    assert (
        outcome.receipt["canonical_content_hash"]
        == hashlib.sha256(store.get_document("paper")["body_text"].encode("utf-8")).hexdigest()
    )
    assert executor.calls[0].allowed_routes == frozenset({"openai/gpt-test"})
    assert "Owner-only canonical evidence" in executor.calls[0].prompt
    assert "caller supplied" not in executor.calls[0].prompt
    notes = list_twin_notes("paper", store=store)
    assert any(note.text == "My irreplaceable note" for note in notes)
    live = [note for note in notes if (note.origin or "").startswith("live_twin_seed:")]
    assert {note.kind for note in live} == {"insight", "question"}
    assert all(note.seed_receipt and note.seed_receipt["actual_cents"] == 3 for note in live)
    balance = ledger.balance(f"live-twin:{outcome.receipt['attempt_id']}")
    assert balance.spent_cents == 3
    assert balance.held_cents == 0


def test_missing_canonical_body_and_malformed_output_write_no_live_batch(tmp_path):
    store = _scoped()
    executor = _Executor()
    skipped = run_live_twin_seed(
        asset_id="missing",
        owner_id="alice",
        store=store,
        ledger=_ledger(tmp_path / "missing.duckdb"),
        executor=executor,
        approved_ceiling_cents=10,
        approval_nonce="approval-missing",
        allowed_routes=["openai/gpt-test"],
        projected_max_cents=5,
    )
    assert skipped.state == "skipped"
    assert executor.calls == []

    _canonical(store)
    malformed = _Executor(malformed=True)
    rejected = run_live_twin_seed(
        asset_id="paper",
        owner_id="alice",
        store=store,
        ledger=_ledger(tmp_path / "malformed.duckdb"),
        executor=malformed,
        approved_ceiling_cents=10,
        approval_nonce="approval-malformed",
        allowed_routes=["openai/gpt-test"],
        projected_max_cents=5,
    )
    assert rejected.state == "rejected"
    assert rejected.receipt["actual_cents"] == 3
    assert [
        note
        for note in list_twin_notes("paper", store=store)
        if (note.origin or "").startswith("live_twin_seed:")
    ] == []


def test_api_requires_every_authority_and_forbids_caller_source(monkeypatch, tmp_path):
    reset_engagement_stores()
    store = authorized_store(get_engagement_store(), operator_engagement_authority())
    _canonical(store)
    executor = _Executor()
    app = FastAPI()
    register_engagement_routes(app)
    bind_live_twin_seed_execution(
        app,
        ledger=BudgetLedger(str(tmp_path / "api.duckdb")),
        executor=executor,
        route_projected_max_cents={"openai/gpt-test": 5},
    )
    client = TestClient(app)
    payload = {
        "asset_id": "paper",
        "approval_nonce": "api-approval",
        "approved_ceiling_cents": 10,
        "allowed_routes": ["openai/gpt-test"],
    }
    monkeypatch.delenv("ANTIEK_TWIN_SEED_LIVE", raising=False)
    monkeypatch.delenv("ANTIEK_TWIN_SEED_USE_DISPATCH", raising=False)
    skipped = client.post("/engagement/twins/seed-live", json=payload)
    assert skipped.status_code == 200
    assert skipped.json()["receipt"]["request_attempted"] is False
    assert executor.calls == []

    monkeypatch.setenv("ANTIEK_TWIN_SEED_LIVE", "1")
    monkeypatch.setenv("ANTIEK_TWIN_SEED_USE_DISPATCH", "1")
    injected = client.post(
        "/engagement/twins/seed-live",
        json={**payload, "body_text": "caller supplied forged evidence"},
    )
    assert injected.status_code == 422
    uncovered = client.post(
        "/engagement/twins/seed-live",
        json={**payload, "allowed_routes": ["openai/unpriced"]},
    )
    assert uncovered.status_code == 400
    assert executor.calls == []
    success = client.post("/engagement/twins/seed-live", json=payload)
    assert success.status_code == 200, success.text
    assert success.json()["state"] == "live_committed"
    assert success.json()["promotion_performed"] is False
    assert (
        hashlib.sha256(store.get_document("paper")["body_text"].encode("utf-8")).hexdigest()
        == success.json()["receipt"]["source_text_sha256"]
    )


@pytest.mark.parametrize(
    "units,finish_reason",
    [
        ((LiveTwinUnit("hypothesis", "Not a closed kind"),), "stop"),
        (
            (
                LiveTwinUnit("insight", ""),
                LiveTwinUnit("question", "Question"),
            ),
            "stop",
        ),
        (
            (
                LiveTwinUnit("insight", "x" * 1001),
                LiveTwinUnit("question", "Question"),
            ),
            "stop",
        ),
        (
            (
                LiveTwinUnit("insight", "Insight"),
                LiveTwinUnit("question", "Question"),
            ),
            "length",
        ),
    ],
)
def test_entire_paid_batch_is_rejected_for_invalid_units(tmp_path, units, finish_reason):
    store = _scoped()
    _canonical(store)

    class InvalidExecutor:
        def execute(self, request):
            return LiveTwinDispatchResult(
                units=units,
                provider="openai",
                model="gpt-test",
                dispatch_event_id="evt-invalid",
                prompt_sha256=request.prompt_sha256,
                source_text_sha256=request.source_text_sha256,
                input_tokens=12,
                output_tokens=5,
                actual_cents=2,
                finish_reason=finish_reason,
            )

    outcome = run_live_twin_seed(
        asset_id="paper",
        owner_id="alice",
        store=store,
        ledger=_ledger(tmp_path / f"invalid-{finish_reason}.duckdb"),
        executor=InvalidExecutor(),
        approved_ceiling_cents=10,
        approval_nonce=f"invalid-{len(units[0].text)}-{finish_reason}",
        allowed_routes=["openai/gpt-test"],
        projected_max_cents=5,
    )
    assert outcome.state == "rejected"
    assert outcome.receipt["accepted_units"] == []
    assert outcome.receipt["rejected_units"]
    assert list_twin_notes("paper", store=store) == []


def test_unapproved_route_and_underapproved_projection_make_no_false_live_batch(tmp_path):
    store = _scoped()
    _canonical(store)
    route_drift = _Executor(route="anthropic/other")
    rejected = run_live_twin_seed(
        asset_id="paper",
        owner_id="alice",
        store=store,
        ledger=_ledger(tmp_path / "route.duckdb"),
        executor=route_drift,
        approved_ceiling_cents=10,
        approval_nonce="route-drift",
        allowed_routes=["openai/gpt-test"],
        projected_max_cents=5,
    )
    assert rejected.state == "rejected"
    assert "outside operator approval" in rejected.receipt["reason"]
    before = len(route_drift.calls)
    with pytest.raises(ValueError, match="projected maximum"):
        run_live_twin_seed(
            asset_id="paper",
            owner_id="alice",
            store=store,
            ledger=_ledger(tmp_path / "underapproved.duckdb"),
            executor=route_drift,
            approved_ceiling_cents=4,
            approval_nonce="underapproved",
            allowed_routes=["openai/gpt-test"],
            projected_max_cents=5,
        )
    assert len(route_drift.calls) == before


def test_provider_failure_retains_unknown_hold_and_pre_dispatch_failure_releases(tmp_path):
    store = _scoped()
    _canonical(store)

    class Failing:
        def __init__(self, error):
            self.error = error
            self.requests = []

        def execute(self, request):
            self.requests.append(request)
            raise self.error

    unknown_ledger = _ledger(tmp_path / "unknown.duckdb")
    with pytest.raises(UnknownCallOutcome) as unknown:
        run_live_twin_seed(
            asset_id="paper",
            owner_id="alice",
            store=store,
            ledger=unknown_ledger,
            executor=Failing(TimeoutError("provider response lost")),
            approved_ceiling_cents=10,
            approval_nonce="unknown",
            allowed_routes=["openai/gpt-test"],
            projected_max_cents=5,
        )
    assert unknown_ledger.balance(unknown.value.hold.run_id).held_cents == 5
    with pytest.raises(LiveTwinReconciliationRequired):
        run_live_twin_seed(
            asset_id="paper",
            owner_id="alice",
            store=store,
            ledger=unknown_ledger,
            executor=_Executor(),
            approved_ceiling_cents=10,
            approval_nonce="unknown",
            allowed_routes=["openai/gpt-test"],
            projected_max_cents=5,
        )

    clean_ledger = _ledger(tmp_path / "pre-dispatch.duckdb")
    pre_dispatch = Failing(CallNotDispatched("local refusal"))
    with pytest.raises(CallNotDispatched):
        run_live_twin_seed(
            asset_id="paper",
            owner_id="alice",
            store=store,
            ledger=clean_ledger,
            executor=pre_dispatch,
            approved_ceiling_cents=10,
            approval_nonce="pre-dispatch",
            allowed_routes=["openai/gpt-test"],
            projected_max_cents=5,
        )
    assert (
        clean_ledger.balance(f"live-twin:{pre_dispatch.requests[0].idempotency_key}").held_cents
        == 0
    )
    assert list_twin_notes("paper", store=store) == []
    retry = _Executor()
    recovered = run_live_twin_seed(
        asset_id="paper",
        owner_id="alice",
        store=store,
        ledger=clean_ledger,
        executor=retry,
        approved_ceiling_cents=10,
        approval_nonce="pre-dispatch",
        allowed_routes=["openai/gpt-test"],
        projected_max_cents=5,
    )
    assert recovered.state == "live_committed"
    assert len(retry.calls) == 1


def test_owner_scope_blocks_foreign_canonical_body_before_dispatch(tmp_path):
    base = InMemoryEngagementStore()
    alice = authorized_store(base, EngagementAuthority("alice"))
    bob = authorized_store(base, EngagementAuthority("bob"))
    _canonical(alice)
    executor = _Executor()
    outcome = run_live_twin_seed(
        asset_id="paper",
        owner_id="bob",
        store=bob,
        ledger=_ledger(tmp_path / "owner.duckdb"),
        executor=executor,
        approved_ceiling_cents=10,
        approval_nonce="bob-cannot-read-alice",
        allowed_routes=["openai/gpt-test"],
        projected_max_cents=5,
    )
    assert outcome.state == "skipped"
    assert executor.calls == []
    assert bob.list_twins("paper") == []


def test_retry_recovers_committed_batch_after_final_receipt_write_failure(tmp_path):
    class FailCompleteStore(InMemoryEngagementStore):
        fail_complete = True

        def put_document(self, document_id, doc):
            if self.fail_complete and doc.get("state") == "live_committed":
                self.fail_complete = False
                raise RuntimeError("final receipt disk failure")
            return super().put_document(document_id, doc)

    store = _scoped(FailCompleteStore())
    _canonical(store)
    executor = _Executor()
    ledger = _ledger(tmp_path / "recovery.duckdb")
    kwargs = dict(
        asset_id="paper",
        owner_id="alice",
        store=store,
        ledger=ledger,
        executor=executor,
        approved_ceiling_cents=10,
        approval_nonce="recovery",
        allowed_routes=["openai/gpt-test"],
        projected_max_cents=5,
    )
    with pytest.raises(RuntimeError, match="final receipt disk failure"):
        run_live_twin_seed(**kwargs)
    assert len(executor.calls) == 1
    recovered = run_live_twin_seed(**kwargs)
    assert recovered.state == "live_committed"
    assert recovered.receipt["recovered_from_committed_batch"] is True
    assert len(executor.calls) == 1


def test_retry_uses_settled_provider_checkpoint_without_redispatch(tmp_path):
    class FailBatchOnceStore(InMemoryEngagementStore):
        fail_batch = True

        def replace_twins_for_origin(self, asset_id, origin, notes):
            if self.fail_batch and origin.startswith("live_twin_seed:"):
                self.fail_batch = False
                raise RuntimeError("batch storage unavailable")
            return super().replace_twins_for_origin(asset_id, origin, notes)

    store = _scoped(FailBatchOnceStore())
    _canonical(store)
    executor = _Executor()
    kwargs = dict(
        asset_id="paper",
        owner_id="alice",
        store=store,
        ledger=_ledger(tmp_path / "checkpoint-recovery.duckdb"),
        executor=executor,
        approved_ceiling_cents=10,
        approval_nonce="checkpoint-recovery",
        allowed_routes=["openai/gpt-test"],
        projected_max_cents=5,
    )
    with pytest.raises(RuntimeError, match="batch storage unavailable"):
        run_live_twin_seed(**kwargs)
    assert len(executor.calls) == 1
    recovered = run_live_twin_seed(**kwargs)
    assert recovered.state == "live_committed"
    assert len(executor.calls) == 1


@pytest.mark.parametrize("fault", ["missing_receipt", "forged_hash", "unverified"])
def test_unverified_canonical_evidence_never_dispatches(tmp_path, fault):
    store = _scoped()
    _canonical(store)
    row = store.get_document("paper")
    assert row is not None
    if fault == "missing_receipt":
        row.pop("hydration_receipt")
    elif fault == "forged_hash":
        row["hydration_receipt"]["canonical_content_hash"] = "a" * 64
    else:
        row["hydration_receipt"]["verified_body"] = False
    store.put_document("paper", row)
    executor = _Executor()
    outcome = run_live_twin_seed(
        asset_id="paper",
        owner_id="alice",
        store=store,
        ledger=_ledger(tmp_path / f"canonical-{fault}.duckdb"),
        executor=executor,
        approved_ceiling_cents=10,
        approval_nonce=f"canonical-{fault}",
        allowed_routes=["openai/gpt-test"],
        projected_max_cents=5,
    )
    assert outcome.state == "skipped"
    assert executor.calls == []


def test_unscoped_store_is_rejected_before_canonical_read_or_dispatch(tmp_path):
    store = InMemoryEngagementStore()
    _canonical(store)
    executor = _Executor()
    with pytest.raises(PermissionError, match="owner-scoped"):
        run_live_twin_seed(
            asset_id="paper",
            owner_id="alice",
            store=store,
            ledger=_ledger(tmp_path / "unscoped.duckdb"),
            executor=executor,
            approved_ceiling_cents=10,
            approval_nonce="unscoped",
            allowed_routes=["openai/gpt-test"],
            projected_max_cents=5,
        )
    assert executor.calls == []


def test_distinct_approvals_preserve_immutable_batches_and_receipts(tmp_path):
    store = _scoped()
    _canonical(store)
    executor = _Executor()
    ledger = _ledger(tmp_path / "distinct.duckdb")
    outcomes = [
        run_live_twin_seed(
            asset_id="paper",
            owner_id="alice",
            store=store,
            ledger=ledger,
            executor=executor,
            approved_ceiling_cents=10,
            approval_nonce=nonce,
            allowed_routes=["openai/gpt-test"],
            projected_max_cents=5,
        )
        for nonce in ("distinct-a", "distinct-b")
    ]
    assert len(executor.calls) == 2
    assert outcomes[0].receipt["attempt_id"] != outcomes[1].receipt["attempt_id"]
    assert {note.seed_batch_id for note in list_twin_notes("paper", store=store)} == {
        outcomes[0].receipt["batch_id"],
        outcomes[1].receipt["batch_id"],
    }
    for outcome in outcomes:
        receipt = store.get_document(f"live_twin_seed_receipt:{outcome.receipt['attempt_id']}")
        assert receipt and receipt["state"] == "live_committed"


def test_concurrent_identical_approval_dispatches_exactly_once(tmp_path):
    store = _scoped()
    _canonical(store)
    entered = threading.Event()
    release = threading.Event()

    class BlockingExecutor(_Executor):
        def execute(self, request):
            entered.set()
            assert release.wait(timeout=5)
            return super().execute(request)

    executor = BlockingExecutor()
    kwargs = dict(
        asset_id="paper",
        owner_id="alice",
        store=store,
        ledger=_ledger(tmp_path / "concurrent.duckdb"),
        executor=executor,
        approved_ceiling_cents=10,
        approval_nonce="same-approval",
        allowed_routes=["openai/gpt-test"],
        projected_max_cents=5,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run_live_twin_seed, **kwargs)
        assert entered.wait(timeout=5)
        second = pool.submit(run_live_twin_seed, **kwargs)
        with pytest.raises(LiveTwinReconciliationRequired):
            second.result(timeout=5)
        release.set()
        assert first.result(timeout=5).state == "live_committed"
    assert len(executor.calls) == 1
