"""Budget-gated provider execution with reservation-before-dispatch."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Protocol, TypeVar

from .budget import HardBudget
from .journal import Journal, LiveCallRecord

T = TypeVar("T")


class TimeoutRunner(Protocol):
    def run(self, fn: Callable[[], T], timeout_s: float) -> T: ...


@dataclass(frozen=True)
class ProviderResult:
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    latency_ms: int
    response_text: str = ""
    provider_id: str = ""
    route_receipt_id: str = ""
    keyword_score: Decimal | None = None
    hit_keywords: tuple[str, ...] = ()

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LiveCallRunner:
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
        wedge_id: str,
        week_id: str,
        suite_version: str,
        requested_provider: str,
        requested_model: str,
        task_class: str,
        item_id: str,
        prompt_hash: str,
        provider_fn: Callable[[], ProviderResult],
        timeout_s: float = 30.0,
        maximum_cost: Decimal | str | int | float = Decimal("0"),
    ) -> LiveCallRecord:
        """Reserve durably, dispatch once, then settle durably.

        A process crash after reservation leaves the full estimate charged and
        will never trigger an implicit retry. The caller must reconcile that
        outstanding reservation explicitly.
        """
        maximum = Decimal(str(maximum_cost))
        reservation = LiveCallRecord(
            wedge_id=wedge_id,
            week_id=week_id,
            suite_version=suite_version,
            requested_provider=requested_provider,
            requested_model=requested_model,
            task_class=task_class,
            item_id=item_id,
            status="reserved",
            reserved_usd=maximum,
            prompt_hash=prompt_hash,
        )
        if not self._journal.reserve_within_cap(reservation, self._budget.cap_usd):
            previous = self._journal.lookup(reservation.call_id)
            if previous is not None:
                return previous
            raise ValueError(
                f"budget exceeded: cap={self._budget.cap_usd}, "
                f"charged={self._budget.total_charged}, maximum={maximum}"
            )
        try:
            result = self._timeout.run(provider_fn, timeout_s)
            actual_provider = result.provider_id
            contract_breached = (
                result.cost_usd > maximum
                or not actual_provider
                or actual_provider != requested_provider
                or result.model_id != requested_model
                or not result.route_receipt_id
            )
            settlement = replace(
                reservation,
                status="failed" if contract_breached else "ok",
                actual_provider=actual_provider,
                actual_model=result.model_id,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                response_hash=hashlib.sha256(result.response_text.encode()).hexdigest(),
                route_receipt_id=result.route_receipt_id,
                keyword_score=result.keyword_score,
                hit_keywords=result.hit_keywords,
                failure_text=(
                    "provider measurement contract breached"
                    if contract_breached
                    else ""
                ),
            )
        except TimeoutError:
            settlement = replace(
                reservation,
                status="timeout",
                failure_text="call timed out",
            )
        except Exception:
            settlement = replace(
                reservation,
                status="failed",
                failure_text="provider call failed",
            )
        self._journal.append(settlement)
        return settlement
