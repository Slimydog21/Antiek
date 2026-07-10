"""Budget-gated call execution with injected timeout runner.

The call runner composes the journal and budget into a single entry
point for executing a provider call.  It does NOT invent process
cancellation — the timeout runner is injected, and an already-issued
provider request is never cancelled.  A timeout is recorded once,
charged conservatively, and never retried implicitly.

Public protocols:

* ``TimeoutRunner`` — injectable timeout mechanism
* ``ProviderResult`` — structured result from the provider
* ``LiveCallRunner`` — budget-gated, journal-recording call executor
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from .budget import HardBudget
from .journal import Journal, LiveCallRecord, Status


@runtime_checkable
class TimeoutRunner(Protocol):
    """Injectable timeout mechanism.

    ``run(fn, timeout_s)`` executes ``fn()`` with a timeout of
    ``timeout_s`` seconds.  On success, returns the result.  On
    timeout, raises ``TimeoutError``.  The implementation does NOT
    cancel the underlying call — it simply stops waiting.
    """

    def run(self, fn: Any, timeout_s: float) -> Any: ...


@dataclass(frozen=True)
class ProviderResult:
    """Structured result from a provider call.

    Captures everything the journal needs without persisting secrets
    or raw response text.
    """

    model_id: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    latency_ms: int
    response_preview: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LiveCallRunner:
    """Budget-gated call execution with journal recording.

    Composes:

    * ``journal`` — append-only record of every call
    * ``budget`` — hard-cap enforcement derived from the journal
    * ``timeout_runner`` — injected timeout mechanism
    """

    def __init__(
        self,
        journal: Journal,
        budget: HardBudget,
        timeout_runner: TimeoutRunner,
    ) -> None:
        self._journal = journal
        self._budget = budget
        self._timeout = timeout_runner

    @property
    def journal(self) -> Journal:
        return self._journal

    @property
    def budget(self) -> HardBudget:
        return self._budget

    def execute(
        self,
        *,
        requested_model: str,
        actual_model: str,
        task_class: str,
        item_id: str,
        provider_fn: Any,
        timeout_s: float = 30.0,
        estimated_cost: Decimal | str | int | float = Decimal("0"),
    ) -> LiveCallRecord:
        """Execute a provider call with budget gating.

        Steps:

        1. Check budget — reject if ``spent + reserved + estimated_cost > cap``.
        2. Run the provider call through the injected timeout runner.
        3. Record the result in the journal.
        4. Return the record.

        A ``TimeoutError`` from the runner is recorded as ``status="timeout"``
        with the full estimated cost charged (conservative — the provider
        may have billed).  The timeout is never retried implicitly.

        Raises ``ValueError`` if the budget is exceeded.
        """
        # Budget gate — checked before any provider call.
        if not self._budget.can_start(estimated_cost):
            raise ValueError(
                f"budget exceeded: cap={self._budget.cap_usd} USD, "
                f"spent={self._budget.spent}, "
                f"reserved={self._budget.reserved}, "
                f"estimated_cost={estimated_cost}"
            )

        est = Decimal(str(estimated_cost))
        status: Status
        result: ProviderResult | None = None
        failure_text = ""

        try:
            result = self._timeout.run(provider_fn, timeout_s)
            status = "ok"
        except TimeoutError:
            status = "timeout"
            failure_text = "call timed out"
        except Exception as exc:
            status = "error"
            failure_text = str(exc)[:500]

        # Build the record from the result or from the timeout/error.
        if result is not None and status == "ok":
            record = LiveCallRecord(
                requested_model=requested_model,
                actual_model=result.model_id or actual_model,
                task_class=task_class,
                item_id=item_id,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                status=status,
                failure_text=failure_text,
            )
        else:
            # Timeout or error — charge the estimated cost conservatively.
            record = LiveCallRecord(
                requested_model=requested_model,
                actual_model=actual_model,
                task_class=task_class,
                item_id=item_id,
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=est,
                latency_ms=0,
                status=status,
                failure_text=failure_text,
            )

        self._journal.append(record)
        return record
