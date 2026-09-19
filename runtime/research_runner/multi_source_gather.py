"""Ordered composite execution over the reviewed SPR-DRL-16 gather plan."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from runtime.research_runner.authorized_gather import (
    AuthorizedGatherProvider,
    ExactGatherBudget,
    GatherAuthorityDenied,
    GatherNotDispatched,
    GatherOutcomeUnknown,
    GatherReceiptStore,
    PolicySnapshotValidator,
    execute_authorized_gather_call,
)
from runtime.research_runner.gather_plan import AuthorizedGatherPlan, GatherSource
from substrate.investigation_tenancy import InvestigationAuthority


class GatherSourceStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class GatherSourceReceipt:
    source: GatherSource
    status: GatherSourceStatus
    document_ids: tuple[str, ...] = ()
    actual_cost_micros: int = 0
    tokens: int = 0
    provider_receipt_id: str | None = None
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class MultiSourceGatherReport:
    plan_fingerprint: str
    source_receipts: tuple[GatherSourceReceipt, ...]
    document_ids: tuple[str, ...]
    minimum_evidence_documents: int
    evidence_complete: bool
    partial: bool
    unknown_outcome: bool


def _call_id(plan_fingerprint: str, source: GatherSource) -> str:
    digest = hashlib.sha256(f"{plan_fingerprint}\x1f{source.value}".encode()).hexdigest()
    return f"gather-{source.value}-{digest[:32]}"


def execute_authorized_gather_plan(
    *,
    plan: AuthorizedGatherPlan,
    expected_plan_fingerprint: str,
    authority: InvestigationAuthority,
    query: str,
    providers: Mapping[GatherSource, AuthorizedGatherProvider],
    validate_policy_snapshot: PolicySnapshotValidator,
    budget: ExactGatherBudget,
    receipts: GatherReceiptStore,
    minimum_evidence_documents: int = 1,
) -> MultiSourceGatherReport:
    """Execute every reviewed source in canonical order under one authority.

    ``GatherNotDispatched`` is the only failure that permits the next source:
    its adapter proved no external side effect. Unknown or authority failures
    stop the plan and mark later sources skipped. Successful terminal receipts
    replay through the lower boundary without provider dispatch.
    """

    if (
        isinstance(minimum_evidence_documents, bool)
        or not isinstance(minimum_evidence_documents, int)
        or not 1 <= minimum_evidence_documents <= plan.aggregate_max_results
    ):
        raise ValueError("minimum_evidence_documents must fit the reviewed aggregate result cap")
    reviewed_sources = tuple(item.source for item in plan.sources)
    if tuple(providers) != reviewed_sources:
        raise GatherAuthorityDenied("provider set/order does not match the reviewed gather plan")
    if any(provider.source is not source for source, provider in providers.items()):
        raise GatherAuthorityDenied("provider identity does not match its reviewed source")

    source_receipts: list[GatherSourceReceipt] = []
    documents: list[str] = []
    stop = False
    unknown = False
    for source in reviewed_sources:
        if stop:
            source_receipts.append(
                GatherSourceReceipt(
                    source,
                    GatherSourceStatus.SKIPPED,
                    failure_code="prior_source_not_terminal_safe",
                )
            )
            continue
        try:
            result = execute_authorized_gather_call(
                plan=plan,
                expected_plan_fingerprint=expected_plan_fingerprint,
                authority=authority,
                source=source,
                query=query,
                idempotency_key=_call_id(plan.fingerprint, source),
                provider=providers[source],
                validate_policy_snapshot=validate_policy_snapshot,
                budget=budget,
                receipts=receipts,
            )
        except GatherNotDispatched:
            source_receipts.append(
                GatherSourceReceipt(
                    source,
                    GatherSourceStatus.FAILED,
                    failure_code="proven_not_dispatched",
                )
            )
            continue
        except GatherOutcomeUnknown:
            unknown = True
            stop = True
            source_receipts.append(
                GatherSourceReceipt(
                    source,
                    GatherSourceStatus.UNKNOWN,
                    failure_code="provider_outcome_unknown",
                )
            )
            continue
        except GatherAuthorityDenied:
            stop = True
            source_receipts.append(
                GatherSourceReceipt(
                    source,
                    GatherSourceStatus.FAILED,
                    failure_code="authority_or_terminal_result_rejected",
                )
            )
            continue
        except Exception:
            # The lower boundary durably records generic provider exceptions
            # as unknown before re-raising. Never leak exception text or allow
            # a later source to spend against an ambiguous aggregate.
            unknown = True
            stop = True
            source_receipts.append(
                GatherSourceReceipt(
                    source,
                    GatherSourceStatus.UNKNOWN,
                    failure_code="provider_outcome_unknown",
                )
            )
            continue

        source_receipts.append(
            GatherSourceReceipt(
                source,
                GatherSourceStatus.SUCCEEDED,
                result.document_ids,
                result.actual_cost_micros,
                result.tokens,
                result.provider_receipt_id,
            )
        )
        for document_id in result.document_ids:
            if document_id not in documents:
                documents.append(document_id)

    complete = len(documents) >= minimum_evidence_documents and not unknown
    partial = complete and any(
        item.status is not GatherSourceStatus.SUCCEEDED for item in source_receipts
    )
    return MultiSourceGatherReport(
        plan.fingerprint,
        tuple(source_receipts),
        tuple(documents),
        minimum_evidence_documents,
        complete,
        partial,
        unknown,
    )


__all__ = [
    "GatherSourceReceipt",
    "GatherSourceStatus",
    "MultiSourceGatherReport",
    "execute_authorized_gather_plan",
]
