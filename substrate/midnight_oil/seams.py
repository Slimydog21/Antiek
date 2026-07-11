"""Closed, typed adapter boundary for live Midnight Oil execution.

The seven Protocols are interfaces, not implementations.  Their Null
implementations are the safe default: they perform no I/O, spend nothing, and
never manufacture a successful result.  SPR-04/05/06 replace individual
adapters behind this boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, runtime_checkable

from runtime.db_lock import LockedConnection
from substrate.dispatch.router import DispatchResult

from .budget_ledger import RemainingBalance
from .contracts import ADAPTER_KEYS, MidnightOilRole
from .deposit import DepositResult

if TYPE_CHECKING:
    from .runner import MidnightOilExecutionReceipt

AdapterKey = Literal[
    "budget_reservation_provider",
    "model_provider_route_executor",
    "retrieval_executor_source_receipts",
    "graph_mutation_writer",
    "final_html_artifact_writer",
    "operator_live_dispatch_enablement",
    "control_ledger_audit_rollback",
]

RETRIEVAL_REQUIRES_RESERVATION = "retrieval must not run before budget reservation"


class NotAuthorized(RuntimeError):
    """A side-effecting seam was invoked without its live authorization."""


class OperatorSpendNotAuthorized(NotAuthorized):
    """A provider call was attempted without an operator spend grant."""


class SeamOrderingViolation(RuntimeError):
    """A seam was invoked before its required predecessor completed."""


ReservedBalance = RemainingBalance
Balance = RemainingBalance


@dataclass(frozen=True)
class SourceReceipt:
    source_id: str
    source_url: str
    content_hash: str


@dataclass(frozen=True)
class RetrievalResult:
    receipts: tuple[SourceReceipt, ...] = ()
    blocked_reason: str | None = None

    def __bool__(self) -> bool:
        return bool(self.receipts)


ArtifactHandle = DepositResult


@dataclass(frozen=True)
class OperatorSpendGrant:
    run_id: str
    ceiling_usd: Decimal
    consent_receipt_id: str


@dataclass(frozen=True)
class LedgerEvent:
    run_id: str
    event_type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class RollbackReceipt:
    ledger_id: str
    rolled_back: bool


@runtime_checkable
class BudgetReservationProvider(Protocol):
    adapter_key: ClassVar[Literal["budget_reservation_provider"]] = (
        "budget_reservation_provider"
    )

    def reserve(
        self,
        run_id: str,
        approved_ceiling_cents: int,
        role_budgets: Mapping[str, int] | None = None,
    ) -> ReservedBalance: ...

    def debit(
        self, run_id: str, amount_cents: int, role: str | None = None
    ) -> Balance: ...


@runtime_checkable
class ModelProviderRouteExecutor(Protocol):
    adapter_key: ClassVar[Literal["model_provider_route_executor"]] = (
        "model_provider_route_executor"
    )

    def execute(
        self,
        prompt: str,
        role: MidnightOilRole,
        *,
        investigation_id: str,
        budget: Balance,
    ) -> DispatchResult: ...


@runtime_checkable
class RetrievalExecutorSourceReceipts(Protocol):
    adapter_key: ClassVar[Literal["retrieval_executor_source_receipts"]] = (
        "retrieval_executor_source_receipts"
    )

    def retrieve(
        self, query: str, source_policy: tuple[str, ...]
    ) -> RetrievalResult: ...


@runtime_checkable
class GraphMutationWriter(Protocol):
    adapter_key: ClassVar[Literal["graph_mutation_writer"]] = "graph_mutation_writer"

    def commit_asset(
        self,
        con: LockedConnection,
        html: str,
        twin_html: str,
        *,
        investigation_id: str,
    ) -> str: ...


@runtime_checkable
class FinalHtmlArtifactWriter(Protocol):
    adapter_key: ClassVar[Literal["final_html_artifact_writer"]] = (
        "final_html_artifact_writer"
    )

    def write(self, receipt: MidnightOilExecutionReceipt) -> ArtifactHandle: ...


@runtime_checkable
class OperatorLiveDispatchEnablement(Protocol):
    adapter_key: ClassVar[Literal["operator_live_dispatch_enablement"]] = (
        "operator_live_dispatch_enablement"
    )

    def is_authorized(self, run_id: str) -> bool: ...

    def authorization(self) -> OperatorSpendGrant | None: ...


@runtime_checkable
class ControlLedgerAuditRollback(Protocol):
    adapter_key: ClassVar[Literal["control_ledger_audit_rollback"]] = (
        "control_ledger_audit_rollback"
    )

    def append(self, event: LedgerEvent) -> str: ...

    def rollback_receipt(self, ledger_id: str) -> RollbackReceipt: ...


class NullBudgetReservationProvider:
    adapter_key: ClassVar[Literal["budget_reservation_provider"]] = (
        "budget_reservation_provider"
    )

    def reserve(
        self,
        run_id: str,
        approved_ceiling_cents: int,
        role_budgets: Mapping[str, int] | None = None,
    ) -> ReservedBalance:
        raise NotAuthorized("budget reservation is not authorized")

    def debit(
        self, run_id: str, amount_cents: int, role: str | None = None
    ) -> Balance:
        raise NotAuthorized("budget debit is not authorized")


class NullModelProviderRouteExecutor:
    adapter_key: ClassVar[Literal["model_provider_route_executor"]] = (
        "model_provider_route_executor"
    )

    def execute(
        self,
        prompt: str,
        role: MidnightOilRole,
        *,
        investigation_id: str,
        budget: Balance,
    ) -> DispatchResult:
        raise OperatorSpendNotAuthorized("provider execution is not authorized")


class NullRetrievalExecutorSourceReceipts:
    adapter_key: ClassVar[Literal["retrieval_executor_source_receipts"]] = (
        "retrieval_executor_source_receipts"
    )

    def retrieve(self, query: str, source_policy: tuple[str, ...]) -> RetrievalResult:
        return RetrievalResult(blocked_reason="retrieval adapter is not implemented")


class NullGraphMutationWriter:
    adapter_key: ClassVar[Literal["graph_mutation_writer"]] = "graph_mutation_writer"

    def commit_asset(
        self,
        con: LockedConnection,
        html: str,
        twin_html: str,
        *,
        investigation_id: str,
    ) -> str:
        raise NotAuthorized("graph mutation is not authorized")


class NullFinalHtmlArtifactWriter:
    adapter_key: ClassVar[Literal["final_html_artifact_writer"]] = (
        "final_html_artifact_writer"
    )

    def write(self, receipt: MidnightOilExecutionReceipt) -> ArtifactHandle:
        raise NotAuthorized("artifact persistence is not authorized")


class NullOperatorLiveDispatchEnablement:
    adapter_key: ClassVar[Literal["operator_live_dispatch_enablement"]] = (
        "operator_live_dispatch_enablement"
    )

    def is_authorized(self, run_id: str) -> bool:
        return False

    def authorization(self) -> OperatorSpendGrant | None:
        return None


class NullControlLedgerAuditRollback:
    adapter_key: ClassVar[Literal["control_ledger_audit_rollback"]] = (
        "control_ledger_audit_rollback"
    )

    def append(self, event: LedgerEvent) -> str:
        raise NotAuthorized("control-ledger persistence is not authorized")

    def rollback_receipt(self, ledger_id: str) -> RollbackReceipt:
        raise NotAuthorized("control-ledger rollback is not authorized")


ALL_SEAMS = (
    BudgetReservationProvider,
    ModelProviderRouteExecutor,
    RetrievalExecutorSourceReceipts,
    GraphMutationWriter,
    FinalHtmlArtifactWriter,
    OperatorLiveDispatchEnablement,
    ControlLedgerAuditRollback,
)

if {seam.adapter_key for seam in ALL_SEAMS} != set(ADAPTER_KEYS):
    raise RuntimeError("Midnight Oil seam catalog must exactly match ADAPTER_KEYS")


@dataclass
class MidnightOilSeams:
    """Injected live boundary plus the cross-seam ordering state machine."""

    budget: BudgetReservationProvider = field(default_factory=NullBudgetReservationProvider)
    provider: ModelProviderRouteExecutor = field(
        default_factory=NullModelProviderRouteExecutor
    )
    retrieval: RetrievalExecutorSourceReceipts = field(
        default_factory=NullRetrievalExecutorSourceReceipts
    )
    graph: GraphMutationWriter = field(default_factory=NullGraphMutationWriter)
    artifact: FinalHtmlArtifactWriter = field(default_factory=NullFinalHtmlArtifactWriter)
    operator: OperatorLiveDispatchEnablement = field(
        default_factory=NullOperatorLiveDispatchEnablement
    )
    ledger: ControlLedgerAuditRollback = field(
        default_factory=NullControlLedgerAuditRollback
    )
    _reserved_run_ids: set[str] = field(default_factory=set, init=False, repr=False)

    def reserve(
        self,
        run_id: str,
        approved_ceiling_cents: int,
        role_budgets: Mapping[str, int] | None = None,
    ) -> ReservedBalance:
        balance = self.budget.reserve(run_id, approved_ceiling_cents, role_budgets)
        self._reserved_run_ids.add(run_id)
        return balance

    def retrieve(
        self,
        run_id: str,
        query: str,
        source_policy: tuple[str, ...],
    ) -> RetrievalResult:
        if run_id not in self._reserved_run_ids:
            raise SeamOrderingViolation(RETRIEVAL_REQUIRES_RESERVATION)
        return self.retrieval.retrieve(query, source_policy)
