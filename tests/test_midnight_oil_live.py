from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from substrate.dispatch import (
    DispatchConfig,
    DispatchResult,
    NormalizedUsage,
    ProviderCallNotAttempted,
    ProviderError,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.engagement_spine.store import FileEngagementStore
from substrate.midnight_oil.job import MidnightOilJob, _job_from_row
from substrate.midnight_oil.live import (
    LiveExecutionFailed,
    LiveExecutionPlan,
    LiveOperatorCorpusStep,
    LivePolicyUnsupported,
    RouterIdempotentDispatch,
    build_router_live_plan,
    consume_authorized_live_operation,
    resume_terminal_deposit,
    run_authorized_live_iteration,
)
from substrate.midnight_oil.operation_queue import DurableOperationQueue
from substrate.midnight_oil.worker import FakeClock, lease_authorized_operation
from tests.test_midnight_oil_consent_routes import _client

HEADER = "X-Midnight-Oil-Spend-Consent"


class _Retrieval:
    name = "test-operator-corpus"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        source_tier_max: int | None = None,
        document_ids: list[str] | None = None,
        policy_tag: str = "attribution_eligible",
    ) -> dict[str, object]:
        self.calls.append(
            {"text": text, "top_k": top_k, "policy_tag": policy_tag}
        )
        return {
            "query": text,
            "top_k": top_k,
            "results": [
                {
                    "chunk_id": "chunk-1",
                    "document_id": "document-1",
                    "document_title": "Primary evidence",
                    "chunk_text": "Evidence with api_key=secret-value-never-forward.",
                }
            ],
            "node_matches": [],
        }


def _lease(
    tmp_path: Path, *, projected_max_cents: int = 2, max_input_bytes: int = 32_000
):  # type: ignore[no-untyped-def]
    client, deps = _client(tmp_path)
    queue = DurableOperationQueue(tmp_path / "operations.sqlite3")
    plan = LiveExecutionPlan(
        allowed_routes=("test-provider/test-model",),
        projected_max_cents=projected_max_cents,
        dispatch_config_hash="1" * 64,
        max_input_bytes=max_input_bytes,
    )
    wired = replace(
        deps,
        operation_queue=queue,
        live_plan_resolver=lambda _job: plan,
    )
    client.app.state.midnight_oil_dependencies = wired
    created = client.post(
        "/midnight-oil/create",
        headers={"x-test-user": "alice"},
        json={
            "goals": ["research carefully"],
            "duration_minutes": 30,
            "model_id": "test-model",
            "live": True,
        },
    )
    assert created.status_code == 200, created.text
    issued = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    )
    assert issued.status_code == 200, issued.text
    queued = client.post(
        "/midnight-oil/run",
        headers={
            "x-test-user": "alice",
            HEADER: issued.json()["token"],
        },
        json={"job_id": "job-owned"},
    )
    assert queued.status_code == 200, queued.text
    operation_id = queued.json()["operation_id"]
    lease = lease_authorized_operation(
        operation_queue=queue,
        owner_jobs=wired.owner_jobs,
        jobs=wired.jobs,
        operation_id=operation_id,
        owner_user_id="alice",
        job_id="job-owned",
        worker_id="live-worker",
        now_ms=1_000_001,
        lease_expires_at_ms=1_060_001,
    )
    return client, wired, queue, lease, plan


def test_external_source_policy_is_blocked_before_retrieval_or_dispatch(
    tmp_path: Path,
) -> None:
    with pytest.raises(LivePolicyUnsupported, match="operator_corpus only"):
        LiveExecutionPlan(
            allowed_routes=("test-provider/test-model",),
            projected_max_cents=2,
            dispatch_config_hash="1" * 64,
            max_input_bytes=32_000,
            source_policy=("arxiv",),
        )
    retrieval = _Retrieval()
    dispatch_calls: list[str] = []

    def dispatch(*args: object, **kwargs: object) -> DispatchResult:
        dispatch_calls.append("called")
        raise AssertionError("dispatch must remain unreachable")

    assert retrieval.calls == []
    assert dispatch_calls == []


def test_live_create_requires_server_owned_plan_resolver(tmp_path: Path) -> None:
    client, deps = _client(tmp_path)
    response = client.post(
        "/midnight-oil/create",
        headers={"x-test-user": "alice"},
        json={"goals": ["g"], "duration_minutes": 5, "live": True},
    )
    assert response.status_code == 503
    assert "resolver" not in response.text
    assert deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned") is None


def test_expired_lease_blocks_before_retrieval_and_provider(tmp_path: Path) -> None:
    _, deps, queue, lease, plan = _lease(tmp_path)
    retrieval = _Retrieval()
    dispatch_calls: list[str] = []

    def dispatch(*args: object, **kwargs: object) -> DispatchResult:
        dispatch_calls.append("called")
        raise AssertionError("dispatch must remain unreachable")

    dispatch.plan_hash = plan.plan_hash  # type: ignore[attr-defined]

    step = LiveOperatorCorpusStep(
        lease=lease,
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        clock=FakeClock(lease_expires_at_ms := 1_060_001),
        retrieval=retrieval,
        dispatch=dispatch,
    )
    raw = deps.jobs.get_job("job-owned")
    assert raw is not None
    with pytest.raises(ValueError, match="stale or expired"):
        step.project(_job_from_row(raw))
    assert lease_expires_at_ms == 1_060_001
    assert retrieval.calls == []
    assert dispatch_calls == []


def test_authorized_live_step_is_fenced_budgeted_and_durably_evidenced(
    tmp_path: Path,
) -> None:
    _, deps, queue, lease, plan = _lease(tmp_path)
    retrieval = _Retrieval()
    dispatch_keys: list[str] = []
    captured_prompts: list[str] = []

    def dispatch(
        prompt: str,
        role: str,
        *,
        investigation_id: str,
        idempotency_key: str,
    ) -> DispatchResult:
        assert role == "synthesizer"
        assert investigation_id == "midnight-oil:job-owned"
        dispatch_keys.append(idempotency_key)
        captured_prompts.append(prompt)
        return DispatchResult(
            text="Evidence-backed synthesis.",
            usage=NormalizedUsage(input_tokens=100, output_tokens=20),
            cost_usd=0.01,
            latency_ms=5,
            provider="test-provider",
            model="test-model",
            tier="synthesis",
            finish_reason="stop",
            fallback_chain_index=0,
            event_id="dispatch-event-1",
        )

    dispatch.plan_hash = plan.plan_hash  # type: ignore[attr-defined]

    engagement_root = tmp_path / "engagement"
    outcome = consume_authorized_live_operation(
        lease,
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        store=deps.jobs,
        engagement_store=FileEngagementStore(engagement_root),
        retrieval=retrieval,
        dispatch=dispatch,
        clock=FakeClock(1_000_002),
    )
    result = outcome.job

    assert result.status == "complete"
    assert result.spent_usd == 0.01
    assert dispatch_keys == [lease.idempotency_key(lease.step_index)]
    assert len(retrieval.calls) == 1
    assert retrieval.calls[0]["policy_tag"] == "private_research"
    assert "secret-value-never-forward" not in captured_prompts[0]
    assert "[REDACTED]" in captured_prompts[0]

    persisted = deps.jobs.get_job("job-owned")
    assert persisted is not None
    restarted = _job_from_row(persisted)
    assert len(restarted.step_evidence) == 1
    evidence = restarted.step_evidence[0]
    assert evidence.step_key == dispatch_keys[0]
    assert evidence.output_text == "Evidence-backed synthesis."
    assert evidence.route_receipt is not None
    assert evidence.route_receipt["event_id"] == "dispatch-event-1"
    assert evidence.source_receipts[0]["source_url"].startswith("antiek://document/")

    deposit = outcome.deposit
    assert "Evidence-backed synthesis" in deposit.html
    assert "dispatch-event-1" in deposit.html
    assert "antiek://document/document-1" in deposit.html
    assert FileEngagementStore(engagement_root).get_document(deposit.document_id) is not None


def test_pre_network_provider_refusal_releases_hold(tmp_path: Path) -> None:
    _, deps, queue, lease, plan = _lease(tmp_path)
    retrieval = _Retrieval()

    def dispatch(
        prompt: str,
        role: str,
        *,
        investigation_id: str,
        idempotency_key: str,
    ) -> DispatchResult:
        raise ProviderCallNotAttempted(
            "idempotent dispatch unavailable",
            provider="unsupported",
            model="unsupported",
            latency_ms=0,
        )

    dispatch.plan_hash = plan.plan_hash  # type: ignore[attr-defined]

    with pytest.raises(LiveExecutionFailed) as failure:
        run_authorized_live_iteration(
            lease,
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            store=deps.jobs,
            retrieval=retrieval,
            dispatch=dispatch,
            clock=FakeClock(1_000_002),
        )
    assert "idempotent dispatch unavailable" not in str(failure.value)

    from substrate.midnight_oil.budget_ledger import BudgetLedger

    balance = BudgetLedger(deps.jobs.budget_db_path()).balance("job-owned")
    assert balance.spent_cents == 0
    assert balance.held_cents == 0


def test_projection_over_remaining_budget_blocks_retrieval_and_provider(
    tmp_path: Path,
) -> None:
    _, deps, queue, lease, plan = _lease(
        tmp_path, projected_max_cents=99_999_900
    )
    retrieval = _Retrieval()
    dispatch_calls: list[str] = []

    def dispatch(
        prompt: str,
        role: str,
        *,
        investigation_id: str,
        idempotency_key: str,
    ) -> DispatchResult:
        dispatch_calls.append(idempotency_key)
        raise AssertionError("provider must remain unreachable")

    dispatch.plan_hash = plan.plan_hash  # type: ignore[attr-defined]

    result = run_authorized_live_iteration(
        lease,
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        store=deps.jobs,
        retrieval=retrieval,
        dispatch=dispatch,
        clock=FakeClock(1_000_002),
    )

    assert result.status == "budget_halted"
    assert result.spent_usd == 0.0
    assert retrieval.calls == []
    assert dispatch_calls == []


def test_dispatch_plan_drift_blocks_before_retrieval_or_provider(tmp_path: Path) -> None:
    _, deps, queue, lease, _ = _lease(tmp_path)
    retrieval = _Retrieval()
    calls: list[str] = []

    def dispatch(*args: object, **kwargs: object) -> DispatchResult:
        calls.append("called")
        raise AssertionError("provider must remain unreachable")

    dispatch.plan_hash = "0" * 64  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="signed plan"):
        LiveOperatorCorpusStep(
            lease=lease,
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            clock=FakeClock(1_000_002),
            retrieval=retrieval,
            dispatch=dispatch,
        )
    assert retrieval.calls == []
    assert calls == []


def test_durable_plan_rewrite_cannot_escape_signed_consent(tmp_path: Path) -> None:
    _, deps, queue, lease, plan = _lease(tmp_path)
    retrieval = _Retrieval()

    def dispatch(*args: object, **kwargs: object) -> DispatchResult:
        raise AssertionError("provider must remain unreachable")

    rewritten = LiveExecutionPlan(
        allowed_routes=plan.allowed_routes,
        projected_max_cents=1,
        dispatch_config_hash=plan.dispatch_config_hash,
        max_input_bytes=plan.max_input_bytes,
    )
    dispatch.plan_hash = rewritten.plan_hash  # type: ignore[attr-defined]
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None
    payload = dict(authority.payload)
    payload.update(
        {
            "live_plan_hash": rewritten.plan_hash,
            "live_projected_max_cents": rewritten.projected_max_cents,
        }
    )
    # Simulate hostile storage mutation below the validated store API. The
    # worker must still compare the reconstructed config to signed consent.
    deps.owner_jobs._jobs[("alice", "job-owned")] = replace(  # type: ignore[attr-defined]
        authority, payload=payload
    )
    with pytest.raises(ValueError, match="signed consent"):
        LiveOperatorCorpusStep(
            lease=lease,
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            clock=FakeClock(1_000_002),
            retrieval=retrieval,
            dispatch=dispatch,
        ).project(_job_from_row(deps.jobs.get_job("job-owned") or {}))
    assert retrieval.calls == []


def test_ambiguous_provider_failure_is_sanitized_held_and_never_replayed(
    tmp_path: Path,
) -> None:
    _, deps, queue, lease, plan = _lease(tmp_path)
    retrieval = _Retrieval()
    calls: list[str] = []
    canary = "provider-secret-canary"

    def dispatch(
        prompt: str,
        role: str,
        *,
        investigation_id: str,
        idempotency_key: str,
    ) -> DispatchResult:
        calls.append(idempotency_key)
        raise ProviderError(
            f"timeout after upstream accepted {canary}",
            provider="test-provider",
            model="test-model",
            latency_ms=1000,
            retryable=True,
        )

    dispatch.plan_hash = plan.plan_hash  # type: ignore[attr-defined]
    with pytest.raises(LiveExecutionFailed) as failure:
        run_authorized_live_iteration(
            lease,
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            store=deps.jobs,
            retrieval=retrieval,
            dispatch=dispatch,
            clock=FakeClock(1_000_002),
        )
    assert canary not in str(failure.value)
    assert calls == [lease.idempotency_key(0)]

    from substrate.midnight_oil.budget_ledger import BudgetLedger
    from substrate.midnight_oil.job_store import OperationState

    balance = BudgetLedger(deps.jobs.budget_db_path()).balance("job-owned")
    assert balance.held_cents == plan.projected_max_cents
    authority = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert authority is not None
    assert authority.operation_state is OperationState.FAILED_RECONCILE
    with pytest.raises(ValueError, match="not dispatchable"):
        lease_authorized_operation(
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            jobs=deps.jobs,
            operation_id=lease.operation_id,
            owner_user_id="alice",
            job_id="job-owned",
            worker_id="replacement-worker",
            now_ms=1_060_002,
            lease_expires_at_ms=1_120_002,
        )
    assert len(calls) == 1


def test_deposit_crash_retries_from_evidence_without_provider_replay(
    tmp_path: Path,
) -> None:
    _, deps, queue, lease, plan = _lease(tmp_path)
    retrieval = _Retrieval()
    provider_calls: list[str] = []

    def dispatch(
        prompt: str,
        role: str,
        *,
        investigation_id: str,
        idempotency_key: str,
    ) -> DispatchResult:
        provider_calls.append(idempotency_key)
        return DispatchResult(
            text="Durable paid output.",
            usage=NormalizedUsage(input_tokens=100, output_tokens=20),
            cost_usd=0.01,
            latency_ms=5,
            provider="test-provider",
            model="test-model",
            tier="synthesis",
            finish_reason="stop",
            fallback_chain_index=0,
            event_id="dispatch-event-crash",
        )

    dispatch.plan_hash = plan.plan_hash  # type: ignore[attr-defined]

    class CrashOnceStore(FileEngagementStore):
        failed = False

        def put_document(self, document_id: str, doc: dict[str, Any]) -> None:
            if not self.failed:
                self.failed = True
                raise RuntimeError("deposit-secret-canary")
            super().put_document(document_id, doc)

    root = tmp_path / "crash-engagement"
    with pytest.raises(LiveExecutionFailed) as failure:
        consume_authorized_live_operation(
            lease,
            operation_queue=queue,
            owner_jobs=deps.owner_jobs,
            store=deps.jobs,
            engagement_store=CrashOnceStore(root),
            retrieval=retrieval,
            dispatch=dispatch,
            clock=FakeClock(1_000_002),
        )
    assert "deposit-secret-canary" not in str(failure.value)
    pending = _job_from_row(deps.jobs.get_job("job-owned") or {})
    assert pending.status == "complete"
    assert pending.deposit_state == "pending"
    assert len(provider_calls) == 1

    deposit = resume_terminal_deposit(
        "job-owned",
        store=deps.jobs,
        engagement_store=FileEngagementStore(root),
    )
    completed = _job_from_row(deps.jobs.get_job("job-owned") or {})
    assert completed.deposit_state == "complete"
    assert completed.deposit_document_id == deposit.document_id
    assert "Durable paid output" in deposit.html
    assert len(provider_calls) == 1


def test_overlong_retrieval_is_hard_capped_before_provider(tmp_path: Path) -> None:
    _, deps, queue, lease, plan = _lease(tmp_path, max_input_bytes=1024)

    class HugeRetrieval(_Retrieval):
        def query(self, *args: object, **kwargs: object) -> dict[str, object]:
            payload = super().query("goal", top_k=12, policy_tag="private_research")
            results = payload["results"]
            assert isinstance(results, list)
            results[0]["chunk_text"] = "evidence" * 100_000
            return payload

    retrieval = HugeRetrieval()
    prompt_sizes: list[int] = []

    def dispatch(
        prompt: str,
        role: str,
        *,
        investigation_id: str,
        idempotency_key: str,
    ) -> DispatchResult:
        prompt_sizes.append(len(prompt.encode("utf-8")))
        return DispatchResult(
            text="Bounded synthesis.",
            usage=NormalizedUsage(input_tokens=100, output_tokens=20),
            cost_usd=0.01,
            latency_ms=1,
            provider="test-provider",
            model="test-model",
            tier="synthesis",
            finish_reason="stop",
            fallback_chain_index=0,
            event_id="bounded-event",
        )

    dispatch.plan_hash = plan.plan_hash  # type: ignore[attr-defined]
    outcome = consume_authorized_live_operation(
        lease,
        operation_queue=queue,
        owner_jobs=deps.owner_jobs,
        store=deps.jobs,
        engagement_store=FileEngagementStore(tmp_path / "bounded-engagement"),
        retrieval=retrieval,
        dispatch=dispatch,
        clock=FakeClock(1_000_002),
    )
    assert outcome.job.status == "complete"
    assert prompt_sizes and prompt_sizes[0] <= plan.max_input_bytes


def test_router_config_drift_is_rejected_before_provider_network() -> None:
    class VerifiedProvider:
        name = "verified"
        idempotency_guaranteed = True

        def call_idempotent(self, **kwargs: object):  # type: ignore[no-untyped-def]
            raise AssertionError("network must remain unreachable")

        def call(self, **kwargs: object):  # type: ignore[no-untyped-def]
            raise AssertionError("network must remain unreachable")

        def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
            return NormalizedUsage(input_tokens=0, output_tokens=0)

    pricing = TierPricing(input_per_mtok=1.0, output_per_mtok=2.0)
    tier = TierConfig(
        name="synthesis",
        provider="verified",
        model="model",
        max_tokens=100,
        temperature=0.2,
        context_budget_tokens=2048,
        pricing=pricing,
        fallback=None,
    )
    config = DispatchConfig(
        role_tiers={"synthesizer": "synthesis"}, tiers={"synthesis": tier}
    )
    reset_provider_registry()
    register_provider(VerifiedProvider())
    try:
        job = MidnightOilJob(
            job_id="job",
            goals=("goal",),
            duration_minutes=5,
            model_id="model",
            recommended_price_ceiling_usd=1.0,
            status="approved",
        )
        plan = build_router_live_plan(job, config=config)
        drifted = DispatchConfig(
            role_tiers=config.role_tiers,
            tiers={
                "synthesis": replace(tier, max_tokens=tier.max_tokens + 1)
            },
        )
        with pytest.raises(ValueError, match="router config conflicts"):
            RouterIdempotentDispatch(plan=plan, config=drifted)
    finally:
        reset_provider_registry()


def test_late_registered_excluded_fallback_is_blocked_before_network() -> None:
    calls: list[str] = []

    class Primary:
        name = "primary"
        idempotency_guaranteed = True

        def call_idempotent(self, **kwargs: object):  # type: ignore[no-untyped-def]
            raise ProviderCallNotAttempted(
                "primary unavailable before request",
                provider=self.name,
                model="primary-model",
                latency_ms=0,
            )

        def call(self, **kwargs: object):  # type: ignore[no-untyped-def]
            raise AssertionError("normal call is forbidden")

        def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
            return NormalizedUsage(input_tokens=0, output_tokens=0)

    class LateFallback:
        name = "late-fallback"
        idempotency_guaranteed = True

        def call_idempotent(self, **kwargs: object):  # type: ignore[no-untyped-def]
            calls.append("network")
            raise AssertionError("excluded fallback must remain unreachable")

        def call(self, **kwargs: object):  # type: ignore[no-untyped-def]
            calls.append("network")
            raise AssertionError("excluded fallback must remain unreachable")

        def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
            return NormalizedUsage(input_tokens=0, output_tokens=0)

    pricing = TierPricing(input_per_mtok=1.0, output_per_mtok=2.0)
    fallback = TierConfig(
        name="fallback",
        provider="late-fallback",
        model="fallback-model",
        max_tokens=100,
        temperature=0.2,
        context_budget_tokens=2048,
        pricing=pricing,
        fallback=None,
    )
    primary_tier = replace(
        fallback,
        name="synthesis",
        provider="primary",
        model="primary-model",
        fallback=fallback,
    )
    config = DispatchConfig(
        role_tiers={"synthesizer": "synthesis"},
        tiers={"synthesis": primary_tier},
    )
    reset_provider_registry()
    register_provider(Primary())
    try:
        job = MidnightOilJob(
            job_id="job",
            goals=("goal",),
            duration_minutes=5,
            model_id="primary-model",
            recommended_price_ceiling_usd=1.0,
            status="approved",
        )
        plan = build_router_live_plan(job, config=config)
        assert plan.allowed_routes == ("primary/primary-model",)
        adapter = RouterIdempotentDispatch(plan=plan, config=config)
        register_provider(LateFallback())
        with pytest.raises(ProviderCallNotAttempted, match="signed allowlist"):
            adapter(
                "prompt",
                "synthesizer",
                investigation_id="investigation",
                idempotency_key="operation-step-key",
            )
        assert calls == []
    finally:
        reset_provider_registry()
