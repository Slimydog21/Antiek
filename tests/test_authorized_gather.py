from dataclasses import dataclass, field
from pathlib import Path

import pytest

from runtime.research_runner.authorized_gather import (
    GatherAuthorityDenied,
    GatherCallClaim,
    GatherClaimState,
    GatherNotDispatched,
    GatherOutcomeUnknown,
    GatherProviderResult,
    execute_authorized_gather_call,
)
from runtime.research_runner.gather_plan import AuthorizedGatherPlan, GatherSource, GatherSourcePlan
from substrate.investigation_tenancy import InvestigationAuthority


def _authority(account: str = "acct-1") -> InvestigationAuthority:
    return InvestigationAuthority(account, "inv-1", Path("/tmp/antiek-gather"))


def _source(source: GatherSource, cost: str) -> GatherSourcePlan:
    return GatherSourcePlan.reviewed(
        source=source, max_results=2, max_cost_usd=cost, policy_version=f"{source.value}-v1"
    )


def _plan(authority: InvestigationAuthority) -> AuthorizedGatherPlan:
    return AuthorizedGatherPlan.reviewed(
        authority,
        legal_policy_snapshot_sha256="a" * 64,
        aggregate_max_results=4,
        aggregate_max_cost_usd="0.05",
        sources=(_source(GatherSource.EXA, "0.05"), _source(GatherSource.ARXIV, "0")),
    )


@dataclass
class ExactBudget:
    cap: int = 50_000
    result_cap: int = 4
    plans: dict[str, tuple[str, int, int]] = field(default_factory=dict)
    reservations: dict[str, tuple[str, int, int]] = field(default_factory=dict)
    spent: int = 0
    results: int = 0
    log: list[str] = field(default_factory=list)

    def bind_plan(
        self,
        *,
        plan_fingerprint: str,
        investigation_id: str,
        aggregate_max_cost_micros: int,
        aggregate_max_results: int,
    ) -> None:
        binding = (investigation_id, aggregate_max_cost_micros, aggregate_max_results)
        prior = self.plans.setdefault(plan_fingerprint, binding)
        if prior != binding:
            raise GatherAuthorityDenied("plan budget binding conflict")
        self.cap = min(self.cap, aggregate_max_cost_micros)
        self.result_cap = min(self.result_cap, aggregate_max_results)

    def reserve_micros(
        self,
        *,
        plan_fingerprint: str,
        investigation_id: str,
        projected_cost_micros: int,
        projected_results: int,
    ) -> str:
        self.log.append("reserve")
        reserved_cost = sum(item[1] for item in self.reservations.values())
        reserved_results = sum(item[2] for item in self.reservations.values())
        if self.spent + reserved_cost + projected_cost_micros > self.cap:
            raise GatherAuthorityDenied("exact budget exceeded")
        if self.results + reserved_results + projected_results > self.result_cap:
            raise GatherAuthorityDenied("exact result budget exceeded")
        reservation_id = f"reservation-{len(self.reservations) + 1}"
        self.reservations[reservation_id] = (
            plan_fingerprint,
            projected_cost_micros,
            projected_results,
        )
        return reservation_id

    def release_micros(self, reservation_id: str) -> None:
        self.log.append("release")
        del self.reservations[reservation_id]

    def settle_micros(
        self,
        reservation_id: str,
        *,
        actual_cost_micros: int,
        actual_results: int,
        tokens: int,
    ) -> None:
        self.log.append("settle")
        del self.reservations[reservation_id]
        self.spent += actual_cost_micros
        self.results += actual_results


@dataclass
class MemoryReceipts:
    rows: dict[str, tuple[str, GatherCallClaim]] = field(default_factory=dict)

    def claim(self, *, call_id: str, request_fingerprint: str) -> GatherCallClaim:
        prior = self.rows.get(call_id)
        if prior is not None:
            if prior[0] != request_fingerprint:
                raise GatherAuthorityDenied("idempotency key conflict")
            return prior[1]
        claim = GatherCallClaim(GatherClaimState.CLAIMED, dispatch_allowed=True)
        self.rows[call_id] = (request_fingerprint, claim)
        return claim

    def release_unexecuted(self, *, call_id: str, request_fingerprint: str) -> None:
        assert self.rows[call_id][0] == request_fingerprint
        del self.rows[call_id]

    def record_succeeded(self, *, call_id: str, request_fingerprint: str, result: GatherProviderResult) -> None:
        self.rows[call_id] = (
            request_fingerprint,
            GatherCallClaim(GatherClaimState.SUCCEEDED, result),
        )

    def record_failed(self, *, call_id: str, request_fingerprint: str, result: GatherProviderResult, failure_code: str) -> None:
        self.rows[call_id] = (
            request_fingerprint,
            GatherCallClaim(GatherClaimState.FAILED, result, failure_code),
        )

    def record_unknown(self, *, call_id: str, request_fingerprint: str) -> None:
        self.rows[call_id] = (request_fingerprint, GatherCallClaim(GatherClaimState.UNKNOWN))


@dataclass
class FakeProvider:
    source: GatherSource
    result: GatherProviderResult = GatherProviderResult(("doc-1",), 20_001, 4, "receipt-1")
    error: BaseException | None = None
    calls: list[dict[str, object]] = field(default_factory=list)
    budget: ExactBudget | None = None

    def execute(self, **kwargs: object) -> GatherProviderResult:
        assert self.budget is None or self.budget.log[-1] == "reserve"
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


def _execute(
    provider: FakeProvider,
    *,
    authority: InvestigationAuthority | None = None,
    plan: AuthorizedGatherPlan | None = None,
    expected: str | None = None,
    validator=lambda authority, snapshot: None,
    budget: ExactBudget | None = None,
    receipts: MemoryReceipts | None = None,
    key: str = "gather-call-1",
) -> GatherProviderResult:
    resolved_authority = authority or _authority()
    resolved_plan = plan or _plan(resolved_authority)
    return execute_authorized_gather_call(
        plan=resolved_plan,
        expected_plan_fingerprint=expected or resolved_plan.fingerprint,
        authority=resolved_authority,
        source=provider.source,
        query="  quantum error correction  ",
        idempotency_key=key,
        provider=provider,
        validate_policy_snapshot=validator,
        budget=budget or ExactBudget(),
        receipts=receipts or MemoryReceipts(),
    )


def test_paid_call_reserves_exact_micros_before_execute_and_settles() -> None:
    budget = ExactBudget()
    provider = FakeProvider(GatherSource.EXA, budget=budget)
    result = _execute(provider, budget=budget)
    assert result.actual_cost_micros == 20_001
    assert budget.log == ["reserve", "settle"]
    assert budget.spent == 20_001


@pytest.mark.parametrize("failure", ["foreign", "fingerprint", "policy", "budget"])
def test_authority_failures_make_zero_provider_calls(failure: str) -> None:
    authority, provider = _authority(), FakeProvider(GatherSource.EXA)
    plan = _plan(authority)
    kwargs: dict[str, object] = {"authority": authority, "plan": plan}
    if failure == "foreign":
        kwargs["authority"] = _authority("acct-2")
    elif failure == "fingerprint":
        kwargs["expected"] = "f" * 64
    elif failure == "policy":
        kwargs["validator"] = lambda authority, snapshot: (_ for _ in ()).throw(
            GatherAuthorityDenied("policy drift")
        )
    else:
        kwargs["budget"] = ExactBudget(cap=49_999)
    with pytest.raises(GatherAuthorityDenied):
        _execute(provider, **kwargs)  # type: ignore[arg-type]
    assert provider.calls == []


def test_budget_refusal_releases_claim_for_a_later_authorized_retry() -> None:
    receipts = MemoryReceipts()
    with pytest.raises(GatherAuthorityDenied, match="budget"):
        _execute(
            FakeProvider(GatherSource.EXA),
            budget=ExactBudget(cap=49_999),
            receipts=receipts,
        )
    assert receipts.rows == {}
    retry = FakeProvider(GatherSource.EXA)
    _execute(retry, budget=ExactBudget(), receipts=receipts)
    assert len(retry.calls) == 1


def test_success_replays_without_second_reservation_or_provider_call() -> None:
    receipts, budget, provider = MemoryReceipts(), ExactBudget(cap=100_000), FakeProvider(GatherSource.EXA)
    first = _execute(provider, receipts=receipts, budget=budget, key="  call-1  ")
    second = _execute(provider, receipts=receipts, budget=budget, key="call-1")
    assert second == first
    assert len(provider.calls) == 1
    assert budget.log == ["reserve", "settle"]
    assert provider.calls[0]["idempotency_key"] == "call-1"


def test_same_key_with_changed_request_fails_without_dispatch() -> None:
    receipts, budget = MemoryReceipts(), ExactBudget(cap=100_000)
    _execute(FakeProvider(GatherSource.EXA), receipts=receipts, budget=budget)
    other = FakeProvider(GatherSource.EXA)
    with pytest.raises(GatherAuthorityDenied, match="conflict"):
        execute_authorized_gather_call(
            plan=_plan(_authority()), expected_plan_fingerprint=_plan(_authority()).fingerprint,
            authority=_authority(), source=GatherSource.EXA, query="different", idempotency_key="gather-call-1",
            provider=other, validate_policy_snapshot=lambda authority, snapshot: None,
            budget=budget, receipts=receipts,
        )
    assert other.calls == []


def test_proven_not_dispatched_releases_claim_and_budget_for_retry() -> None:
    receipts, budget = MemoryReceipts(), ExactBudget()
    with pytest.raises(GatherNotDispatched):
        _execute(FakeProvider(GatherSource.EXA, error=GatherNotDispatched("no call")), receipts=receipts, budget=budget)
    _execute(FakeProvider(GatherSource.EXA), receipts=receipts, budget=budget)
    assert budget.log[:2] == ["reserve", "release"]


def test_ambiguous_failure_is_durable_and_same_key_never_redispatches() -> None:
    receipts, budget = MemoryReceipts(), ExactBudget(cap=1_000_000)
    provider = FakeProvider(GatherSource.EXA, error=TimeoutError("unknown"))
    with pytest.raises(TimeoutError):
        _execute(provider, receipts=receipts, budget=budget)
    retry = FakeProvider(GatherSource.EXA)
    with pytest.raises(GatherOutcomeUnknown):
        _execute(retry, receipts=receipts, budget=budget)
    assert retry.calls == []
    assert next(iter(budget.reservations.values()))[1:] == (50_000, 2)


def test_existing_inflight_claim_never_dispatches_a_second_observer() -> None:
    receipts = MemoryReceipts()
    plan = _plan(_authority())
    # The first owner has claimed but has not written a terminal receipt.
    from runtime.research_runner.authorized_gather import _request_fingerprint

    fingerprint = _request_fingerprint(
        plan=plan,
        source=GatherSource.EXA,
        query="quantum error correction",
        call_id="gather-call-1",
    )
    receipts.rows["gather-call-1"] = (
        fingerprint,
        GatherCallClaim(GatherClaimState.CLAIMED, dispatch_allowed=False),
    )
    observer = FakeProvider(GatherSource.EXA)
    with pytest.raises(GatherOutcomeUnknown, match="already claimed"):
        _execute(observer, plan=plan, receipts=receipts, budget=ExactBudget(cap=1_000_000))
    assert observer.calls == []


def test_known_cap_breach_is_settled_and_replays_as_failed_without_dispatch() -> None:
    receipts, budget = MemoryReceipts(), ExactBudget(cap=100_000)
    provider = FakeProvider(GatherSource.EXA, result=GatherProviderResult(("a", "b", "c"), 20_001))
    with pytest.raises(GatherAuthorityDenied, match="result_cap"):
        _execute(provider, receipts=receipts, budget=budget)
    retry = FakeProvider(GatherSource.EXA)
    with pytest.raises(GatherAuthorityDenied, match="prior provider result failed"):
        _execute(retry, receipts=receipts, budget=budget)
    assert budget.spent == 20_001
    assert budget.reservations == {}
    assert retry.calls == []


def test_zero_fee_source_still_crosses_policy_and_receipt_authority() -> None:
    receipts, seen = MemoryReceipts(), []
    provider = FakeProvider(GatherSource.ARXIV, GatherProviderResult(("doc-arxiv",), 0))
    _execute(provider, receipts=receipts, validator=lambda authority, snapshot: seen.append(snapshot))
    assert seen == ["a" * 64]
    assert receipts.rows["gather-call-1"][1].state is GatherClaimState.SUCCEEDED


def test_post_provider_settlement_failure_is_unknown_and_never_retried() -> None:
    class BrokenSettlementBudget(ExactBudget):
        def settle_micros(self, reservation_id: str, **kwargs: int) -> None:
            raise OSError("ledger unavailable")

    receipts = MemoryReceipts()
    provider = FakeProvider(GatherSource.EXA)
    with pytest.raises(GatherOutcomeUnknown, match="settlement is uncertain"):
        _execute(
            provider,
            budget=BrokenSettlementBudget(cap=100_000),
            receipts=receipts,
        )
    retry = FakeProvider(GatherSource.EXA)
    with pytest.raises(GatherOutcomeUnknown):
        _execute(
            retry,
            budget=ExactBudget(cap=100_000),
            receipts=receipts,
        )
    assert len(provider.calls) == 1
    assert retry.calls == []


def test_distinct_call_ids_cannot_exceed_one_reviewed_plan_aggregate() -> None:
    receipts, budget = MemoryReceipts(), ExactBudget(cap=1_000_000, result_cap=400)
    first = FakeProvider(GatherSource.EXA, GatherProviderResult(("doc-1",), 20_001))
    _execute(first, receipts=receipts, budget=budget, key="call-1")
    second = FakeProvider(GatherSource.EXA)
    with pytest.raises(GatherAuthorityDenied, match="budget"):
        _execute(second, receipts=receipts, budget=budget, key="call-2")
    assert second.calls == []
    assert "call-2" not in receipts.rows


def test_zero_fee_calls_reserve_and_settle_aggregate_result_capacity() -> None:
    receipts, budget = MemoryReceipts(), ExactBudget(cap=50_000, result_cap=2)
    provider = FakeProvider(GatherSource.ARXIV, GatherProviderResult(("doc-a", "doc-b"), 0))
    _execute(provider, receipts=receipts, budget=budget, key="arxiv-1")
    second = FakeProvider(GatherSource.ARXIV, GatherProviderResult(("doc-c",), 0))
    with pytest.raises(GatherAuthorityDenied, match="result budget"):
        _execute(second, receipts=receipts, budget=budget, key="arxiv-2")
    assert second.calls == []
