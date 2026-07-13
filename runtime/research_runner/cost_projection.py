"""Fail-closed, server-owned cost projection for cascade dispatches.

Projection is deliberately separate from reservation.  This module performs
no provider call and mutates no ledger; SPR-02 consumes eligible receipts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from .protocol import (
    BillingUnit,
    CostProjection,
    CostProjectionRequest,
    ProjectionDisposition,
    ProjectionIneligibility,
    ProjectionRate,
)

_INVENTORY_PATH = Path(__file__).with_name("dispatch_inventory.json")
_MAX_PROJECTED_USD = Decimal("1000000000")
_MAX_RATE_EXPONENT_SPREAD = 1_000


@dataclass(frozen=True)
class UnitRate:
    unit: BillingUnit
    usd_per_unit: Decimal


@dataclass(frozen=True)
class CostCatalogEntry:
    """Server-owned route, price, and enforceability authority."""

    seam_id: str
    provider: str
    model: str
    operation: str
    rates: tuple[UnitRate, ...]
    snapshot: str
    expires_at: datetime
    currency: str = "USD"
    paid_service: bool = True
    durable_idempotency: bool = False
    authoritative_reconciliation: bool = False
    hidden_retries_disabled: bool = False
    assumptions: tuple[str, ...] = ()


def _finite_exponent(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    assert isinstance(exponent, int)  # caller verifies Decimal.is_finite first
    return exponent


def load_dispatch_inventory(path: Path = _INVENTORY_PATH) -> tuple[dict[str, object], ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise ValueError("dispatch inventory must be a JSON array of objects")
    return tuple(raw)


def _refusal(
    request: CostProjectionRequest,
    reason: ProjectionIneligibility,
    *,
    snapshot: str = "unavailable",
    currency: str = "USD",
    rates: tuple[ProjectionRate, ...] = (),
    assumptions: tuple[str, ...] = (),
) -> CostProjection:
    return CostProjection(
        seam_id=request.seam_id,
        provider=request.provider,
        model=request.model,
        operation=request.operation,
        bounded_usage=request.bounded_usage,
        rates=rates,
        rate_snapshot=snapshot,
        currency=currency,
        maximum_cost_usd=Decimal(0),
        reservation_cents=0,
        disposition=ProjectionDisposition.INELIGIBLE,
        ineligibility=reason,
        assumptions=assumptions,
    )


class CostProjector:
    """Projects against an immutable catalog supplied by server code."""

    def __init__(self, entries: tuple[CostCatalogEntry, ...]) -> None:
        keys = [(e.seam_id, e.provider, e.model, e.operation) for e in entries]
        if len(keys) != len(set(keys)):
            raise ValueError("cost catalog contains duplicate routes")
        for entry in entries:
            units = [rate.unit for rate in entry.rates]
            if len(units) != len(set(units)):
                raise ValueError(f"cost catalog route {entry.seam_id!r} repeats a billing unit")
        self._entries = entries

    def project(
        self,
        request: CostProjectionRequest,
        *,
        now: datetime | None = None,
    ) -> CostProjection:
        candidates = [e for e in self._entries if e.seam_id == request.seam_id]
        if not candidates:
            return _refusal(request, ProjectionIneligibility.UNKNOWN_DISPATCH)
        entry = next(
            (
                e
                for e in candidates
                if (e.provider, e.model, e.operation)
                == (request.provider, request.model, request.operation)
            ),
            None,
        )
        if entry is None:
            return _refusal(request, ProjectionIneligibility.ROUTE_MISMATCH)
        assumptions = entry.assumptions
        if request.expected_rate_snapshot not in (None, entry.snapshot):
            return _refusal(
                request,
                ProjectionIneligibility.ROUTE_MISMATCH,
                snapshot=entry.snapshot,
                currency=entry.currency,
                assumptions=assumptions,
            )
        if entry.currency != "USD":
            return _refusal(
                request,
                ProjectionIneligibility.NON_USD_BILLING,
                snapshot=entry.snapshot,
                currency=entry.currency,
                assumptions=assumptions,
            )
        resolved_now = now or datetime.now(UTC)
        if resolved_now.tzinfo is None:
            resolved_now = resolved_now.replace(tzinfo=UTC)
        expiry = entry.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if resolved_now >= expiry:
            return _refusal(
                request,
                ProjectionIneligibility.STALE_RATE_SNAPSHOT,
                snapshot=entry.snapshot,
                assumptions=assumptions,
            )

        rates = {rate.unit: rate.usd_per_unit for rate in entry.rates}
        if not entry.paid_service:
            if any(not rate.is_finite() or rate != 0 for rate in rates.values()) or any(
                abs(_finite_exponent(rate)) > _MAX_RATE_EXPONENT_SPREAD
                for rate in rates.values()
                if rate.is_finite()
            ):
                return _refusal(
                    request,
                    ProjectionIneligibility.INVALID_RATE,
                    snapshot=entry.snapshot,
                    assumptions=assumptions,
                )
            if {item.unit for item in request.bounded_usage} != set(rates):
                return _refusal(
                    request,
                    ProjectionIneligibility.UNBOUNDED_USAGE,
                    snapshot=entry.snapshot,
                    assumptions=assumptions,
                )
            projection_rates = tuple(
                ProjectionRate(rate.unit, rate.usd_per_unit) for rate in entry.rates
            )
            return CostProjection(
                seam_id=request.seam_id,
                provider=request.provider,
                model=request.model,
                operation=request.operation,
                bounded_usage=request.bounded_usage,
                rates=projection_rates,
                rate_snapshot=entry.snapshot,
                currency="USD",
                maximum_cost_usd=Decimal(0),
                reservation_cents=0,
                disposition=ProjectionDisposition.ZERO_COST_RECEIPT,
                assumptions=assumptions,
            )

        if not request.bounded_usage:
            return _refusal(
                request,
                ProjectionIneligibility.UNBOUNDED_USAGE,
                snapshot=entry.snapshot,
                assumptions=assumptions,
            )
        for rate in rates.values():
            if not rate.is_finite() or rate < 0:
                return _refusal(
                    request,
                    ProjectionIneligibility.INVALID_RATE,
                    snapshot=entry.snapshot,
                    assumptions=assumptions,
                )
        if any(item.unit not in rates for item in request.bounded_usage):
            return _refusal(
                request,
                ProjectionIneligibility.UNKNOWN_PRICING,
                snapshot=entry.snapshot,
                assumptions=assumptions,
            )
        if {item.unit for item in request.bounded_usage} != set(rates):
            return _refusal(
                request,
                ProjectionIneligibility.UNBOUNDED_USAGE,
                snapshot=entry.snapshot,
                assumptions=assumptions,
            )
        if any(rates[item.unit] == 0 for item in request.bounded_usage):
            return _refusal(
                request,
                ProjectionIneligibility.ZERO_PRICE_FOR_PAID_SERVICE,
                snapshot=entry.snapshot,
                assumptions=assumptions,
            )
        capability_checks = (
            (entry.durable_idempotency, ProjectionIneligibility.PROVIDER_IDEMPOTENCY_UNAVAILABLE),
            (
                entry.authoritative_reconciliation,
                ProjectionIneligibility.PROVIDER_RECONCILIATION_UNAVAILABLE,
            ),
            (entry.hidden_retries_disabled, ProjectionIneligibility.HIDDEN_RETRIES_ENABLED),
        )
        for available, reason in capability_checks:
            if not available:
                return _refusal(request, reason, snapshot=entry.snapshot, assumptions=assumptions)

        terms = [(item.maximum, rates[item.unit]) for item in request.bounded_usage]
        exponents = [_finite_exponent(rate) for _, rate in terms]
        common_exponent = min(exponents)
        if (
            max(abs(exponent) for exponent in exponents) > _MAX_RATE_EXPONENT_SPREAD
            or max(exponents) - common_exponent > _MAX_RATE_EXPONENT_SPREAD
        ):
            return _refusal(
                request,
                ProjectionIneligibility.PROJECTION_OVERFLOW,
                snapshot=entry.snapshot,
                assumptions=assumptions,
            )
        if any(len(rate.as_tuple().digits) > 1_000 for _, rate in terms):
            return _refusal(
                request,
                ProjectionIneligibility.PROJECTION_OVERFLOW,
                snapshot=entry.snapshot,
                assumptions=assumptions,
            )
        projection_rates = tuple(
            ProjectionRate(rate.unit, rate.usd_per_unit) for rate in entry.rates
        )
        total_coefficient = 0
        for quantity, rate in terms:
            rate_tuple = rate.as_tuple()
            rate_exponent = _finite_exponent(rate)
            coefficient = int("".join(map(str, rate_tuple.digits)) or "0")
            total_coefficient += quantity * coefficient * 10 ** (rate_exponent - common_exponent)
        digits = Decimal(total_coefficient).as_tuple().digits
        maximum = Decimal((0, digits, common_exponent))
        if not maximum.is_finite() or maximum > _MAX_PROJECTED_USD:
            return _refusal(
                request,
                ProjectionIneligibility.PROJECTION_OVERFLOW,
                snapshot=entry.snapshot,
                assumptions=assumptions,
            )
        if common_exponent >= -2:
            cents = total_coefficient * 10 ** (common_exponent + 2)
        else:
            denominator = 10 ** (-common_exponent - 2)
            cents = (total_coefficient + denominator - 1) // denominator
        if cents <= 0:
            return _refusal(
                request,
                ProjectionIneligibility.ZERO_PRICE_FOR_PAID_SERVICE,
                snapshot=entry.snapshot,
                assumptions=assumptions,
            )
        return CostProjection(
            seam_id=request.seam_id,
            provider=request.provider,
            model=request.model,
            operation=request.operation,
            bounded_usage=request.bounded_usage,
            rates=projection_rates,
            rate_snapshot=entry.snapshot,
            currency="USD",
            maximum_cost_usd=maximum,
            reservation_cents=cents,
            disposition=ProjectionDisposition.HOLD_ELIGIBLE,
            assumptions=assumptions,
        )


def _server_catalog() -> tuple[CostCatalogEntry, ...]:
    never_stale = datetime.max.replace(tzinfo=UTC)
    local_entries = (
        CostCatalogEntry(
            seam_id="cascade.session.launch",
            provider="antiek",
            model="host-local",
            operation="launch",
            rates=(UnitRate(BillingUnit.LOCAL_OPERATION, Decimal(0)),),
            snapshot="antiek-local-v1",
            expires_at=never_stale,
            paid_service=False,
            assumptions=("host-local task creation has no provider dispatch",),
        ),
        CostCatalogEntry(
            seam_id="cascade.gather.contract_stub",
            provider="antiek",
            model="contract-stub",
            operation="gather",
            rates=(UnitRate(BillingUnit.LOCAL_OPERATION, Decimal(0)),),
            snapshot="antiek-local-v1",
            expires_at=never_stale,
            paid_service=False,
            assumptions=("no provider or network dispatch",),
        ),
        CostCatalogEntry(
            seam_id="cascade.gather.url.fetch",
            provider="origin-web",
            model="httpx",
            operation="fetch-url",
            rates=(UnitRate(BillingUnit.HTTP_REQUEST, Decimal(0)),),
            snapshot="unmetered-origin-http-v1",
            expires_at=never_stale,
            paid_service=False,
            assumptions=("Browserbase escalation is disabled on the cascade path",),
        ),
        CostCatalogEntry(
            seam_id="cascade.gather.embedding.bootstrap",
            provider="local",
            model="sentence-transformers-or-hash",
            operation="embed",
            rates=(UnitRate(BillingUnit.LOCAL_OPERATION, Decimal(0)),),
            snapshot="local-embedding-v1",
            expires_at=never_stale,
            paid_service=False,
            assumptions=("local inference and model download have no metered API fee",),
        ),
    )
    exa = CostCatalogEntry(
        seam_id="cascade.gather.exa.search",
        provider="exa",
        model="search",
        operation="search",
        rates=(UnitRate(BillingUnit.CALL, Decimal("0.005")),),
        snapshot="exa-estimate-2026-q1",
        expires_at=datetime(2026, 4, 1, tzinfo=UTC),
        assumptions=(
            "rate is an estimate rather than invoice authority",
            "client may retry one logical call",
        ),
    )
    llm_rates = (
        UnitRate(BillingUnit.INPUT_TOKEN, Decimal(0)),
        UnitRate(BillingUnit.OUTPUT_TOKEN, Decimal(0)),
    )
    llm_entries = tuple(
        CostCatalogEntry(
            seam_id=seam_id,
            provider=provider,
            model=model,
            operation="generate",
            rates=llm_rates,
            snapshot="dispatch-config-0.1.0-unverified",
            expires_at=datetime(2026, 10, 1, tzinfo=UTC),
            assumptions=(
                "config.yaml declares zero placeholders, not verified prices",
                "fallback attempts have no provider reconciliation identity",
            ),
        )
        for seam_id in (
            "cascade.plan.decomposer",
            "cascade.tail.synthesizer",
            "cascade.tail.knowledge_extractor",
        )
        for provider, model in (
            ("zai", "glm-5.2"),
            ("zai_reasoning", "glm-5.2"),
            ("deepseek", "deepseek-v4-pro"),
            ("xiaomi", "mimo-v2.5-pro"),
        )
    )
    return (*local_entries, exa, *llm_entries)


SERVER_COST_PROJECTOR = CostProjector(_server_catalog())


def project_cascade_cost(
    request: CostProjectionRequest, *, now: datetime | None = None
) -> CostProjection:
    """Project from Antiek's checked-in authorities; never accepts client rates."""
    return SERVER_COST_PROJECTOR.project(request, now=now)
