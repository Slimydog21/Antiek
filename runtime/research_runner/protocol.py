"""DRW SPR-02 — the ResearchRunner execution contract.

This module defines the *interface* a research runner satisfies and the
plain dataclasses that cross it. It imports neither concrete
implementation, so the host-local runner that ships now and the Daytona
runner that is gated behind CLAUDE.md §16 are interchangeable behind it:
**a call site that targets this protocol needs zero changes when the
operator ratifies §16 and the Daytona impl drops in.** That mirrors the
existing ``runtime/db_lock.WriteCoordinator`` abstraction built for the
autumn-2026 Quack swap.

The unit of work is an Antiek *investigation* (``investigation_id``). One
investigation = one focused deep research running a multi-step *browse
loop*. The runner owns the loop's lifecycle (start / stream / steer /
status / cost / cancel); the loop's actual step logic (Exa retrieval →
Browserbase escalation → claim/insight emission) is injected as a
``BrowseLoop`` and wired by SPR-06 — the runner is deliberately ignorant
of it so it stays testable against a fake loop.

Concurrency model (host-local impl): each investigation's browse loop is
an ``asyncio`` task under a bounded semaphore. Browse loops only ever
append to their own per-investigation event-log JSONL; **no browse loop
writes the graph**. Graph promotion is drained by a single serialized
funnel (``promotion_funnel.py``) through ``runtime/db_lock`` — that is how
N parallel researches coexist with the ``--workers 1`` single-writer
invariant.
"""

from __future__ import annotations

import enum
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import (
    Any,
    Protocol,
    runtime_checkable,
)


class RunState(str, enum.Enum):
    """Lifecycle states of a single research. ``stopped`` and
    ``budget_halted`` are both terminal-by-steering / terminal-by-policy;
    ``done`` is terminal-by-completion; ``failed`` is terminal-by-error."""

    PENDING = "pending"        # accepted, not yet scheduled (semaphore wait)
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"      # stop requested, sealing in progress
    DONE = "done"
    STOPPED = "stopped"
    FAILED = "failed"
    BUDGET_HALTED = "budget_halted"

    def is_terminal(self) -> bool:
        return self in {RunState.DONE, RunState.STOPPED, RunState.FAILED, RunState.BUDGET_HALTED}


class CommandKind(str, enum.Enum):
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    REDIRECT = "redirect"   # inject a revised sub-question
    DEEPEN = "deepen"       # extend budget + queue a follow-up


class SpendControlMode(enum.StrEnum):
    """Execution accounting policy selected by the operator."""

    STOP_LIMIT = "stop_limit"
    HARD_CEILING = "hard_ceiling"


@dataclass(frozen=True)
class BudgetCap:
    """A research's stop limit based on reported cost.

    This preserves the original runner behavior. It is not a pre-dispatch
    authorization hold; ``SpendControlMode.HARD_CEILING`` uses the provider
    gateway for that stronger contract.
    """

    cost_usd: float = 0.50
    max_steps: int = 50


class BillingUnit(enum.StrEnum):
    """Closed billing vocabulary used by conservative cost projections."""

    CALL = "call"
    INPUT_TOKEN = "input_token"
    OUTPUT_TOKEN = "output_token"
    HTTP_REQUEST = "http_request"
    LOCAL_OPERATION = "local_operation"


class ProjectionDisposition(enum.StrEnum):
    """Whether a projection can back a hold, needs no hold, or is refused."""

    HOLD_ELIGIBLE = "hold_eligible"
    ZERO_COST_RECEIPT = "zero_cost_receipt"
    INELIGIBLE = "ineligible"


class ProjectionIneligibility(enum.StrEnum):
    UNKNOWN_DISPATCH = "unknown_dispatch"
    ROUTE_MISMATCH = "route_mismatch"
    UNKNOWN_PRICING = "unknown_pricing"
    ZERO_PRICE_FOR_PAID_SERVICE = "zero_price_for_paid_service"
    UNBOUNDED_USAGE = "unbounded_usage"
    STALE_RATE_SNAPSHOT = "stale_rate_snapshot"
    NON_USD_BILLING = "non_usd_billing"
    PROVIDER_IDEMPOTENCY_UNAVAILABLE = "provider_idempotency_unavailable"
    PROVIDER_RECONCILIATION_UNAVAILABLE = "provider_reconciliation_unavailable"
    HIDDEN_RETRIES_ENABLED = "hidden_retries_enabled"
    INVALID_RATE = "invalid_rate"
    PROJECTION_OVERFLOW = "projection_overflow"


@dataclass(frozen=True)
class BoundedUsage:
    unit: BillingUnit
    maximum: int

    def __post_init__(self) -> None:
        if not isinstance(self.unit, BillingUnit):
            raise TypeError("bounded usage unit must be BillingUnit")
        if isinstance(self.maximum, bool) or not isinstance(self.maximum, int):
            raise TypeError("bounded usage maximum must be an integer")
        if self.maximum < 0:
            raise ValueError("bounded usage maximum must be non-negative")
        if self.maximum > 9_223_372_036_854_775_807:
            raise ValueError("bounded usage maximum exceeds the signed 64-bit contract")


@dataclass(frozen=True)
class ProjectionRate:
    unit: BillingUnit
    usd_per_unit: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.unit, BillingUnit):
            raise TypeError("projection rate unit must be BillingUnit")
        if not isinstance(self.usd_per_unit, Decimal):
            raise TypeError("projection rate must be Decimal")
        if not self.usd_per_unit.is_finite() or self.usd_per_unit < 0:
            raise ValueError("projection rate must be finite and non-negative")
        exponent = self.usd_per_unit.as_tuple().exponent
        assert isinstance(exponent, int)
        if abs(exponent) > 1_000:
            raise ValueError("projection rate exponent exceeds the projection contract")
        if len(self.usd_per_unit.as_tuple().digits) > 1_000:
            raise ValueError("projection rate precision exceeds the projection contract")


@dataclass(frozen=True)
class CostProjectionRequest:
    """Caller-owned route identity and enforced maximum usage only.

    Rates and provider capabilities are deliberately absent: the server-owned
    catalog supplies them, so a client cannot make itself hold-eligible.
    """

    seam_id: str
    provider: str
    model: str
    operation: str
    bounded_usage: tuple[BoundedUsage, ...]
    expected_rate_snapshot: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("seam_id", self.seam_id),
            ("provider", self.provider),
            ("model", self.model),
            ("operation", self.operation),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        units = [item.unit for item in self.bounded_usage]
        if len(units) != len(set(units)):
            raise ValueError("bounded usage units must be unique")


@dataclass(frozen=True)
class CostProjection:
    seam_id: str
    provider: str
    model: str
    operation: str
    bounded_usage: tuple[BoundedUsage, ...]
    rates: tuple[ProjectionRate, ...]
    rate_snapshot: str
    currency: str
    maximum_cost_usd: Decimal
    reservation_cents: int
    disposition: ProjectionDisposition
    ineligibility: ProjectionIneligibility | None = None
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, ProjectionDisposition):
            raise TypeError("projection disposition must be ProjectionDisposition")
        if self.ineligibility is not None and not isinstance(
            self.ineligibility, ProjectionIneligibility
        ):
            raise TypeError("projection refusal must be ProjectionIneligibility")
        if not isinstance(self.maximum_cost_usd, Decimal):
            raise TypeError("maximum cost must be Decimal")
        for name, value in (
            ("seam_id", self.seam_id),
            ("provider", self.provider),
            ("model", self.model),
            ("operation", self.operation),
            ("rate_snapshot", self.rate_snapshot),
            ("currency", self.currency),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if not self.maximum_cost_usd.is_finite() or self.maximum_cost_usd < 0:
            raise ValueError("maximum cost must be finite and non-negative")
        finite_exponent = self.maximum_cost_usd.as_tuple().exponent
        assert isinstance(finite_exponent, int)
        if abs(finite_exponent) > 1_000:
            raise ValueError("maximum cost exponent exceeds the projection contract")
        if self.reservation_cents < 0:
            raise ValueError("reservation cents must be non-negative")
        eligible = self.disposition is ProjectionDisposition.HOLD_ELIGIBLE
        if eligible:
            rate_units = [rate.unit for rate in self.rates]
            if len(rate_units) != len(set(rate_units)):
                raise ValueError("eligible projection rates must be unique by unit")
            value_tuple = self.maximum_cost_usd.as_tuple()
            exponent = value_tuple.exponent
            assert isinstance(exponent, int)  # finite value checked above
            coefficient = int("".join(map(str, value_tuple.digits)) or "0")
            if exponent >= -2:
                expected_cents = coefficient * 10 ** (exponent + 2)
            else:
                denominator = 10 ** (-exponent - 2)
                expected_cents = (coefficient + denominator - 1) // denominator
            usage_by_unit = {item.unit: item.maximum for item in self.bounded_usage}
            rate_exponents = [rate.usd_per_unit.as_tuple().exponent for rate in self.rates]
            assert all(isinstance(item, int) for item in rate_exponents)
            integer_exponents = [int(item) for item in rate_exponents]
            common_exponent = min(integer_exponents, default=0)
            expected_coefficient = 0
            for rate, rate_exponent in zip(self.rates, integer_exponents, strict=True):
                rate_tuple = rate.usd_per_unit.as_tuple()
                rate_coefficient = int("".join(map(str, rate_tuple.digits)) or "0")
                expected_coefficient += (
                    usage_by_unit.get(rate.unit, 0)
                    * rate_coefficient
                    * 10 ** (rate_exponent - common_exponent)
                )
            expected_digits = Decimal(expected_coefficient).as_tuple().digits
            expected_maximum = Decimal((0, expected_digits, common_exponent))
            if (
                self.ineligibility is not None
                or self.maximum_cost_usd <= 0
                or self.currency != "USD"
                or not self.bounded_usage
                or {item.unit for item in self.bounded_usage} != {rate.unit for rate in self.rates}
                or self.maximum_cost_usd != expected_maximum
                or self.reservation_cents != expected_cents
            ):
                raise ValueError(
                    "eligible paid projections require USD bounds and the exact upward hold"
                )
        if self.disposition is ProjectionDisposition.INELIGIBLE and self.ineligibility is None:
            raise ValueError("ineligible projections require a typed reason")
        if self.disposition is ProjectionDisposition.INELIGIBLE and (
            self.maximum_cost_usd != 0 or self.reservation_cents != 0
        ):
            raise ValueError("ineligible projections cannot authorize spend")
        if self.disposition is ProjectionDisposition.ZERO_COST_RECEIPT and (
            self.maximum_cost_usd != 0
            or self.reservation_cents != 0
            or self.ineligibility is not None
            or any(rate.usd_per_unit != 0 for rate in self.rates)
            or {item.unit for item in self.bounded_usage} != {rate.unit for rate in self.rates}
        ):
            raise ValueError("zero-cost receipts cannot carry a hold or refusal")


@dataclass(frozen=True)
class ResearchPlan:
    """The approved unit of work handed to the runner. Produced by the
    cascade planner (SPR-05); the runner does not decompose, it executes."""

    investigation_id: str
    sub_question: str
    parent_investigation_id: str | None = None
    budget: BudgetCap = field(default_factory=BudgetCap)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CostState:
    """A live snapshot of a research's spend. ``spent_usd`` reconciles with
    the sum of ``DispatchCall`` cost events the loop's calls emit — the
    runner never invents cost, it accumulates what each step reports."""

    spent_usd: float
    cap_usd: float
    tokens: int
    steps: int

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.cap_usd - self.spent_usd)

    @property
    def over_budget(self) -> bool:
        return self.spent_usd > self.cap_usd


@dataclass(frozen=True)
class StepEvent:
    """One observable event in a research's stream. ``kind`` partitions the
    glass-box surface (SPR-09): plan/step/cost/note/question/status/error/done."""

    investigation_id: str
    seq: int
    kind: str            # "plan"|"step"|"cost"|"note"|"question"|"status"|"error"|"done"
    text: str = ""
    cost_usd: float = 0.0
    tokens: int = 0
    state: RunState | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Command:
    """A steer command. ``payload`` carries kind-specific data: redirect →
    ``{"sub_question": str}``; deepen → ``{"extra_budget_usd": float,
    "follow_up": str|None}``."""

    kind: CommandKind
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Status:
    investigation_id: str
    state: RunState
    sub_question: str
    cost: CostState
    started: bool
    follow_ups: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class Handle:
    """Opaque reference to a started research. Carries only the id; all
    mutable state lives inside the runner, so a handle is safe to pass to
    a UI layer."""

    investigation_id: str


# A browse loop drives one investigation. It receives a LoopContext (defined
# by the concrete runner) and yields StepEvents. Declared loosely here so the
# protocol module stays free of any impl dependency.
BrowseLoop = Callable[[Any], AsyncIterator[StepEvent]]


@runtime_checkable
class ResearchRunner(Protocol):
    """The execution abstraction. Host-local impl ships now; the Daytona
    impl is gated on §16 ratification and is a drop-in behind this
    protocol — no call-site changes.

    Contract:

    * ``start`` accepts a plan, registers the research, and schedules its
      browse loop (subject to the concurrency cap). Returns a Handle
      immediately; it does not block on completion.
    * ``stream`` yields the research's StepEvents in order until a terminal
      event (``kind == "done"``). Multiple consumers are not guaranteed;
      one consumer per handle.
    * ``steer`` applies a Command. A command targeting an already-terminal
      research is a safe no-op, never an error.
    * ``status`` / ``cost`` are synchronous snapshots.
    * ``cancel`` is graceful: it stops the loop, seals the investigation,
      and transitions to ``STOPPED``.
    """

    async def start(self, investigation_id: str, plan: ResearchPlan) -> Handle: ...

    def stream(self, handle: Handle) -> AsyncIterator[StepEvent]: ...

    async def steer(self, handle: Handle, command: Command) -> None: ...

    def status(self, handle: Handle) -> Status: ...

    def cost(self, handle: Handle) -> CostState: ...

    async def cancel(self, handle: Handle) -> None: ...


class StopResearch(Exception):
    """Raised inside a browse loop's checkpoint when a stop/cancel has been
    requested. The runner catches it, seals, and transitions to STOPPED."""


class BudgetExceeded(Exception):
    """Raised when a charge would push a research past its cap (per-research
    or aggregate). The runner catches it and transitions to BUDGET_HALTED."""

    def __init__(self, message: str, *, scope: str):
        super().__init__(message)
        self.scope = scope  # "per_research" | "aggregate"
