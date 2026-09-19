"""Exact, replay-safe pre-provider authority for reviewed gather calls."""

from __future__ import annotations

import hashlib
import json
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from runtime.research_runner.gather_plan import AuthorizedGatherPlan, GatherSource, GatherSourcePlan
from substrate.investigation_tenancy import InvestigationAuthority


class GatherAuthorityDenied(RuntimeError):
    pass


class GatherNotDispatched(RuntimeError):
    """The adapter proved that no provider request left the process."""


class GatherOutcomeUnknown(RuntimeError):
    """A prior dispatch has no terminal receipt and must be reconciled."""


@dataclass(frozen=True, slots=True)
class GatherProviderResult:
    document_ids: tuple[str, ...]
    actual_cost_micros: int
    tokens: int = 0
    provider_receipt_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.actual_cost_micros, bool) or not isinstance(
            self.actual_cost_micros, int
        ):
            raise ValueError("provider cost must be integer micros")
        if isinstance(self.tokens, bool) or not isinstance(self.tokens, int):
            raise ValueError("provider tokens must be an integer")
        if self.actual_cost_micros < 0 or self.tokens < 0:
            raise ValueError("provider usage must be non-negative")
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("provider document IDs must be unique")
        if any(not item.strip() for item in self.document_ids):
            raise ValueError("provider document IDs must be non-empty")


class GatherClaimState(StrEnum):
    CLAIMED = "claimed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class GatherCallClaim:
    state: GatherClaimState
    result: GatherProviderResult | None = None
    failure_code: str | None = None
    dispatch_allowed: bool = False


class GatherReceiptStore(Protocol):
    def claim(self, *, call_id: str, request_fingerprint: str) -> GatherCallClaim: ...
    def release_unexecuted(self, *, call_id: str, request_fingerprint: str) -> None: ...
    def record_succeeded(
        self, *, call_id: str, request_fingerprint: str, result: GatherProviderResult
    ) -> None: ...
    def record_failed(
        self, *, call_id: str, request_fingerprint: str, result: GatherProviderResult, failure_code: str
    ) -> None: ...
    def record_unknown(self, *, call_id: str, request_fingerprint: str) -> None: ...


class ExactGatherBudget(Protocol):
    def bind_plan(
        self,
        *,
        plan_fingerprint: str,
        investigation_id: str,
        aggregate_max_cost_micros: int,
        aggregate_max_results: int,
    ) -> None: ...
    def reserve_micros(
        self,
        *,
        plan_fingerprint: str,
        investigation_id: str,
        projected_cost_micros: int,
        projected_results: int,
    ) -> str: ...
    def release_micros(self, reservation_id: str) -> None: ...
    def settle_micros(
        self,
        reservation_id: str,
        *,
        actual_cost_micros: int,
        actual_results: int,
        tokens: int,
    ) -> None: ...


class AuthorizedGatherProvider(Protocol):
    source: GatherSource

    def execute(
        self,
        *,
        query: str,
        source_plan: GatherSourcePlan,
        idempotency_key: str,
        authority: InvestigationAuthority,
    ) -> GatherProviderResult: ...


class PolicySnapshotValidator(Protocol):
    def __call__(self, authority: InvestigationAuthority, expected_snapshot_sha256: str) -> None: ...


def _request_fingerprint(
    *, plan: AuthorizedGatherPlan, source: GatherSource, query: str, call_id: str
) -> str:
    encoded = json.dumps(
        {"plan": plan.fingerprint, "source": source.value, "query": query, "call_id": call_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def execute_authorized_gather_call(
    *,
    plan: AuthorizedGatherPlan,
    expected_plan_fingerprint: str,
    authority: InvestigationAuthority,
    source: GatherSource,
    query: str,
    idempotency_key: str,
    provider: AuthorizedGatherProvider,
    validate_policy_snapshot: PolicySnapshotValidator,
    budget: ExactGatherBudget,
    receipts: GatherReceiptStore,
) -> GatherProviderResult:
    if (authority.account_digest, authority.investigation_digest) != (
        plan.account_digest,
        plan.investigation_digest,
    ):
        raise GatherAuthorityDenied("gather plan authority drifted")
    if expected_plan_fingerprint != plan.fingerprint:
        raise GatherAuthorityDenied("gather plan fingerprint drifted")
    normalized_query = query.strip()
    normalized_call_id = idempotency_key.strip()
    if not normalized_query:
        raise ValueError("gather query must be non-empty")
    if not normalized_call_id or len(normalized_call_id) > 256:
        raise ValueError("provider idempotency key must contain 1 through 256 characters")
    if provider.source is not source:
        raise GatherAuthorityDenied("provider does not match the reviewed source")
    source_plan = next((item for item in plan.sources if item.source is source), None)
    if source_plan is None:
        raise GatherAuthorityDenied("source is absent from the reviewed gather plan")

    validate_policy_snapshot(authority, plan.legal_policy_snapshot_sha256)
    budget.bind_plan(
        plan_fingerprint=plan.fingerprint,
        investigation_id=authority.investigation_id,
        aggregate_max_cost_micros=plan.aggregate_max_cost_micros,
        aggregate_max_results=plan.aggregate_max_results,
    )
    request_fingerprint = _request_fingerprint(
        plan=plan, source=source, query=normalized_query, call_id=normalized_call_id
    )
    claim = receipts.claim(call_id=normalized_call_id, request_fingerprint=request_fingerprint)
    if claim.state is GatherClaimState.SUCCEEDED:
        if claim.result is None:
            raise GatherAuthorityDenied("success receipt is missing its result")
        return claim.result
    if claim.state is GatherClaimState.UNKNOWN:
        raise GatherOutcomeUnknown("prior provider outcome requires reconciliation")
    if claim.state is GatherClaimState.FAILED:
        raise GatherAuthorityDenied(f"prior provider result failed: {claim.failure_code}")
    if not claim.dispatch_allowed:
        raise GatherOutcomeUnknown("provider call is already claimed")

    try:
        reservation_id = budget.reserve_micros(
            plan_fingerprint=plan.fingerprint,
            investigation_id=authority.investigation_id,
            projected_cost_micros=source_plan.max_cost_micros,
            projected_results=source_plan.max_results,
        )
    except BaseException:
        receipts.release_unexecuted(
            call_id=normalized_call_id, request_fingerprint=request_fingerprint
        )
        raise
    try:
        result = provider.execute(
            query=normalized_query,
            source_plan=source_plan,
            idempotency_key=normalized_call_id,
            authority=authority,
        )
    except GatherNotDispatched:
        budget.release_micros(reservation_id)
        receipts.release_unexecuted(
            call_id=normalized_call_id, request_fingerprint=request_fingerprint
        )
        raise
    except BaseException:
        receipts.record_unknown(call_id=normalized_call_id, request_fingerprint=request_fingerprint)
        raise

    failure_code: str | None = None
    if result.actual_cost_micros > source_plan.max_cost_micros:
        failure_code = "source_cost_cap_exceeded"
    elif len(result.document_ids) > source_plan.max_results:
        failure_code = "source_result_cap_exceeded"
    if not source_plan.max_cost_micros and result.actual_cost_micros:
        failure_code = "zero_cost_source_reported_spend"
    try:
        budget.settle_micros(
            reservation_id,
            actual_cost_micros=result.actual_cost_micros,
            actual_results=len(result.document_ids),
            tokens=result.tokens,
        )
    except BaseException as exc:
        with suppress(BaseException):
            receipts.record_unknown(
                call_id=normalized_call_id,
                request_fingerprint=request_fingerprint,
            )
        raise GatherOutcomeUnknown("provider returned but budget settlement is uncertain") from exc
    if failure_code is not None:
        try:
            receipts.record_failed(
                call_id=normalized_call_id,
                request_fingerprint=request_fingerprint,
                result=result,
                failure_code=failure_code,
            )
        except BaseException as exc:
            raise GatherOutcomeUnknown("provider rejection receipt is uncertain") from exc
        raise GatherAuthorityDenied(failure_code)
    try:
        receipts.record_succeeded(
            call_id=normalized_call_id,
            request_fingerprint=request_fingerprint,
            result=result,
        )
    except BaseException as exc:
        raise GatherOutcomeUnknown("provider success receipt is uncertain") from exc
    return result
