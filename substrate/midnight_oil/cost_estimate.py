"""Pure, fail-closed price-ceiling estimation for Midnight Oil.

The operator approves an integer-cent ceiling before an unattended swarm starts.
This module therefore computes a conservative bound, not an average or a binary-
float approximation.  Any phase that can *start* during the approved duration is
counted, every outbound call is rounded upward to a whole-cent ledger hold, and
the total is the exact sum of those auditable call reservations.

``0`` or ``None`` pricing retains the dispatch configuration's placeholder
meaning: unknown, never free.  Unknown pricing makes the complete ceiling unknown
while preserving a per-tier breakdown for remediation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from decimal import ROUND_CEILING, Decimal, InvalidOperation, localcontext
from typing import Any, cast

__all__ = [
    "CadenceProfile",
    "MidnightOilCostError",
    "MidnightOilCostEstimate",
    "PhaseTokenBudget",
    "TierCallCostBreakdown",
    "TierCostBreakdown",
    "TierPricing",
    "estimate_midnight_oil_cost",
    "validate_cost_estimate",
]


class MidnightOilCostError(ValueError):
    """A cost-estimation value violates a load-bearing invariant."""


RateInput = Decimal | int | float | str | None
DurationInput = Decimal | int | float

_TIER_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_MAX_RATE_TEXT = 64
_MAX_RATE_SIGNIFICANT_DIGITS = 28
_MAX_RATE_DECIMAL_PLACES = 18
_MAX_DURATION_SIGNIFICANT_DIGITS = 28
_MAX_DURATION_DECIMAL_PLACES = 6
_MAX_RATE_USD_PER_MTOK = Decimal("1000000")
_MAX_PHASE_BUDGETS = 256
_MAX_PRICING_ROWS = 256
_MAX_TOKEN_BUDGET = 1_000_000_000_000
_MAX_AGGREGATE_TOKENS = 9_000_000_000_000_000_000
_MAX_PHASES_PER_GOAL = 1_000
_MAX_GOALS = 10_000
_MAX_TOTAL_PHASES = 10_000_000
_MAX_DURATION_MINUTES = Decimal("5256000")  # ten years
_MAX_NOTES = 8
_MAX_NOTE_LENGTH = 512
_ONE_HUNDRED = Decimal(100)
_ONE_MILLION = Decimal(1_000_000)
_ARITHMETIC_PRECISION = 96


def _fail(message: str) -> None:
    raise MidnightOilCostError(message)


def _validate_tier(tier: object, *, name: str = "tier") -> str:
    if type(tier) is not str or _TIER_RE.fullmatch(tier) is None:
        _fail(f"{name} must match {_TIER_RE.pattern!r}")
    assert isinstance(tier, str)
    return tier


def _validate_exact_int(
    value: object,
    *,
    name: str,
    minimum: int,
    maximum: int,
) -> int:
    if type(value) is not int:
        _fail(f"{name} must be an exact int")
    assert isinstance(value, int)
    if value < minimum or value > maximum:
        _fail(f"{name} must be between {minimum} and {maximum}")
    return value


def _as_decimal(value: object, *, name: str, allow_string: bool) -> Decimal:
    if type(value) is bool:
        _fail(f"{name} must be a finite decimal number")
    if type(value) is Decimal:
        result = value
    elif type(value) is int:
        result = Decimal(value)
    elif type(value) is float:
        result = Decimal(str(value))
    elif allow_string and type(value) is str:
        if not value or len(value) > _MAX_RATE_TEXT or value != value.strip():
            _fail(f"{name} has an invalid decimal representation")
        try:
            result = Decimal(value)
        except InvalidOperation:
            _fail(f"{name} has an invalid decimal representation")
    else:
        _fail(f"{name} must be a finite decimal number")
    if not result.is_finite():
        _fail(f"{name} must be finite")
    return result


def _canonical_decimal(value: Decimal) -> Decimal:
    """Remove insignificant zeroes without context rounding or underflow."""

    if value == 0:
        return Decimal(0)
    decimal_tuple = value.as_tuple()
    exponent = decimal_tuple.exponent
    assert type(exponent) is int
    digits = list(decimal_tuple.digits)
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    return Decimal((decimal_tuple.sign, tuple(digits), exponent))


def _normalize_rate(value: object, *, name: str) -> Decimal | None:
    if value is None:
        return None
    rate = _canonical_decimal(_as_decimal(value, name=name, allow_string=True))
    rate_tuple = rate.as_tuple()
    rate_exponent = rate_tuple.exponent
    assert type(rate_exponent) is int
    if (
        len(rate_tuple.digits) > _MAX_RATE_SIGNIFICANT_DIGITS
        or rate_exponent < -_MAX_RATE_DECIMAL_PLACES
    ):
        _fail(
            f"{name} may have at most {_MAX_RATE_SIGNIFICANT_DIGITS} significant "
            f"digits and {_MAX_RATE_DECIMAL_PLACES} decimal places"
        )
    if rate < 0 or rate > _MAX_RATE_USD_PER_MTOK:
        _fail(f"{name} must be between 0 and {_MAX_RATE_USD_PER_MTOK}")
    return rate


def _bounded_decimal(
    value: object,
    *,
    name: str,
    minimum: Decimal,
    maximum: Decimal,
) -> Decimal:
    result = _canonical_decimal(_as_decimal(value, name=name, allow_string=False))
    result_tuple = result.as_tuple()
    result_exponent = result_tuple.exponent
    assert type(result_exponent) is int
    if (
        len(result_tuple.digits) > _MAX_DURATION_SIGNIFICANT_DIGITS
        or result_exponent < -_MAX_DURATION_DECIMAL_PLACES
    ):
        _fail(
            f"{name} may have at most {_MAX_DURATION_SIGNIFICANT_DIGITS} significant "
            f"digits and {_MAX_DURATION_DECIMAL_PLACES} decimal places"
        )
    if result < minimum or result > maximum:
        _fail(f"{name} must be between {minimum} and {maximum}")
    return result


def _assert_exact_dataclass_shape(value: object, expected_type: type[object]) -> None:
    if type(value) is not expected_type:
        _fail(f"value must be an exact {expected_type.__name__}")
    for field in fields(cast(Any, expected_type)):
        try:
            getattr(value, field.name)
        except AttributeError:
            _fail(f"{expected_type.__name__}.{field.name} is missing")


@dataclass(frozen=True, slots=True, init=False)
class TierPricing:
    """One tier's USD-per-million-token prices.

    Rates are normalized to exact :class:`~decimal.Decimal` values at
    construction.  ``0`` and ``None`` are placeholders and mean unpriced.
    """

    tier: str
    input_per_mtok: Decimal | None
    output_per_mtok: Decimal | None

    def __init__(
        self,
        tier: str,
        input_per_mtok: RateInput,
        output_per_mtok: RateInput,
    ) -> None:
        object.__setattr__(self, "tier", _validate_tier(tier))
        object.__setattr__(
            self, "input_per_mtok", _normalize_rate(input_per_mtok, name="input_per_mtok")
        )
        object.__setattr__(
            self,
            "output_per_mtok",
            _normalize_rate(output_per_mtok, name="output_per_mtok"),
        )
        _validate_tier_pricing(self)

    @property
    def is_priced(self) -> bool:
        _validate_tier_pricing(self)
        return bool(self.input_per_mtok and self.output_per_mtok)


def _validate_tier_pricing(value: object) -> TierPricing:
    _assert_exact_dataclass_shape(value, TierPricing)
    assert type(value) is TierPricing
    _validate_tier(value.tier)
    for name, rate in (
        ("input_per_mtok", value.input_per_mtok),
        ("output_per_mtok", value.output_per_mtok),
    ):
        if rate is not None:
            if type(rate) is not Decimal:
                _fail(f"TierPricing.{name} must be a normalized Decimal or None")
            assert isinstance(rate, Decimal)
            normalized = _normalize_rate(rate, name=f"TierPricing.{name}")
            assert type(normalized) is Decimal
            if normalized.as_tuple() != rate.as_tuple():
                _fail(f"TierPricing.{name} must use canonical Decimal storage")
    return value


@dataclass(frozen=True, slots=True)
class PhaseTokenBudget:
    """Maximum token use by one tier during one research phase."""

    tier: str
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        _validate_phase_budget(self)


def _validate_phase_budget(value: object) -> PhaseTokenBudget:
    _assert_exact_dataclass_shape(value, PhaseTokenBudget)
    assert type(value) is PhaseTokenBudget
    _validate_tier(value.tier)
    input_tokens = _validate_exact_int(
        value.input_tokens,
        name="input_tokens",
        minimum=0,
        maximum=_MAX_TOKEN_BUDGET,
    )
    output_tokens = _validate_exact_int(
        value.output_tokens,
        name="output_tokens",
        minimum=0,
        maximum=_MAX_TOKEN_BUDGET,
    )
    if input_tokens == 0 and output_tokens == 0:
        _fail("a phase token budget must reserve at least one token")
    return value


@dataclass(frozen=True, slots=True)
class CadenceProfile:
    """Goal-to-phase cadence and all calls made by each phase.

    Multiple entries for the same tier are intentional: they represent multiple
    billable calls in one phase and are aggregated in the result.
    """

    phases_per_goal: int
    phase_budgets: tuple[PhaseTokenBudget, ...]

    def __post_init__(self) -> None:
        _validate_cadence(self)


def _validate_cadence(value: object) -> CadenceProfile:
    _assert_exact_dataclass_shape(value, CadenceProfile)
    assert type(value) is CadenceProfile
    _validate_exact_int(
        value.phases_per_goal,
        name="phases_per_goal",
        minimum=1,
        maximum=_MAX_PHASES_PER_GOAL,
    )
    if type(value.phase_budgets) is not tuple:
        _fail("phase_budgets must be an exact tuple")
    if not value.phase_budgets or len(value.phase_budgets) > _MAX_PHASE_BUDGETS:
        _fail(f"phase_budgets must contain 1..{_MAX_PHASE_BUDGETS} entries")
    for budget in value.phase_budgets:
        _validate_phase_budget(budget)
    return value


@dataclass(frozen=True, slots=True)
class TierCallCostBreakdown:
    """One phase's maximum outbound call and its integer-cent ledger hold."""

    tier: str
    input_tokens: int
    output_tokens: int
    input_rate: Decimal | None
    output_rate: Decimal | None
    projected_max_cents: int | None

    def __post_init__(self) -> None:
        _validate_call_breakdown(self)


def _validate_call_breakdown(value: object) -> TierCallCostBreakdown:
    _assert_exact_dataclass_shape(value, TierCallCostBreakdown)
    assert type(value) is TierCallCostBreakdown
    _validate_tier(value.tier)
    input_tokens = _validate_exact_int(
        value.input_tokens,
        name="input_tokens",
        minimum=0,
        maximum=_MAX_TOKEN_BUDGET,
    )
    output_tokens = _validate_exact_int(
        value.output_tokens,
        name="output_tokens",
        minimum=0,
        maximum=_MAX_TOKEN_BUDGET,
    )
    if input_tokens == 0 and output_tokens == 0:
        _fail("a call breakdown must reserve at least one token")
    for name, rate in (("input_rate", value.input_rate), ("output_rate", value.output_rate)):
        if rate is not None:
            if type(rate) is not Decimal:
                _fail("call breakdown rates must be normalized bounded Decimals or None")
            normalized = _normalize_rate(rate, name=f"TierCallCostBreakdown.{name}")
            assert type(normalized) is Decimal
            if normalized.as_tuple() != rate.as_tuple():
                _fail("call breakdown rates must use canonical Decimal storage")
    priced = bool(
        value.input_rate is not None
        and value.input_rate > 0
        and value.output_rate is not None
        and value.output_rate > 0
    )
    if priced:
        projected = _validate_exact_int(
            value.projected_max_cents,
            name="projected_max_cents",
            minimum=1,
            maximum=_MAX_AGGREGATE_TOKENS,
        )
        assert type(value.input_rate) is Decimal
        assert type(value.output_rate) is Decimal
        expected = _ceil_cents(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_rate=value.input_rate,
            output_rate=value.output_rate,
        )
        if projected != expected:
            _fail("projected_max_cents must equal the upward-rounded exact call cost")
    elif value.projected_max_cents is not None:
        _fail("an unpriced call breakdown hold must be None")
    return value


@dataclass(frozen=True, slots=True)
class TierCostBreakdown:
    """One tier's auditable sum of repeated per-call ledger holds."""

    tier: str
    total_input_tokens: int
    total_output_tokens: int
    input_rate: Decimal | None
    output_rate: Decimal | None
    contribution_cents: int | None
    total_phases: int
    calls_per_phase: tuple[TierCallCostBreakdown, ...]

    def __post_init__(self) -> None:
        _validate_breakdown(self)

    @property
    def contribution_usd(self) -> Decimal | None:
        _validate_breakdown(self)
        if self.contribution_cents is None:
            return None
        return Decimal(self.contribution_cents) / _ONE_HUNDRED


def _validate_breakdown(value: object) -> TierCostBreakdown:
    _assert_exact_dataclass_shape(value, TierCostBreakdown)
    assert type(value) is TierCostBreakdown
    _validate_tier(value.tier)
    total_input_tokens = _validate_exact_int(
        value.total_input_tokens,
        name="total_input_tokens",
        minimum=0,
        maximum=_MAX_AGGREGATE_TOKENS,
    )
    total_output_tokens = _validate_exact_int(
        value.total_output_tokens,
        name="total_output_tokens",
        minimum=0,
        maximum=_MAX_AGGREGATE_TOKENS,
    )
    rates = (value.input_rate, value.output_rate)
    for name, rate in (("input_rate", value.input_rate), ("output_rate", value.output_rate)):
        if rate is not None:
            if type(rate) is not Decimal:
                _fail("breakdown rates must be normalized bounded Decimals or None")
            normalized = _normalize_rate(rate, name=f"TierCostBreakdown.{name}")
            assert type(normalized) is Decimal
            if normalized.as_tuple() != rate.as_tuple():
                _fail("breakdown rates must use canonical Decimal storage")
    total_phases = _validate_exact_int(
        value.total_phases,
        name="total_phases",
        minimum=1,
        maximum=_MAX_TOTAL_PHASES,
    )
    if (
        type(value.calls_per_phase) is not tuple
        or not value.calls_per_phase
        or len(value.calls_per_phase) > _MAX_PHASE_BUDGETS
    ):
        _fail("calls_per_phase must be a bounded, non-empty exact tuple")
    call_input_tokens = 0
    call_output_tokens = 0
    call_hold_cents = 0
    for call in value.calls_per_phase:
        call = _validate_call_breakdown(call)
        if call.tier != value.tier:
            _fail("every call breakdown must match its parent tier")
        if call.input_rate != value.input_rate or call.output_rate != value.output_rate:
            _fail("every call breakdown must match its parent rates")
        call_input_tokens += call.input_tokens
        call_output_tokens += call.output_tokens
        if call.projected_max_cents is not None:
            call_hold_cents += call.projected_max_cents
    if call_input_tokens * total_phases != total_input_tokens:
        _fail("total_input_tokens must equal per-phase calls times total_phases")
    if call_output_tokens * total_phases != total_output_tokens:
        _fail("total_output_tokens must equal per-phase calls times total_phases")

    priced = all(rate is not None and rate > 0 for rate in rates)
    if priced:
        contribution_cents = _validate_exact_int(
            value.contribution_cents,
            name="contribution_cents",
            minimum=1,
            maximum=_MAX_AGGREGATE_TOKENS,
        )
        expected_cents = call_hold_cents * total_phases
        if contribution_cents != expected_cents:
            _fail("contribution_cents must equal all repeated per-call ledger holds")
    elif value.contribution_cents is not None:
        _fail("an unpriced breakdown contribution must be None")
    return value


@dataclass(frozen=True, slots=True)
class MidnightOilCostEstimate:
    """Canonical cents ceiling plus an honest per-tier audit trail."""

    recommended_ceiling_cents: int | None
    total_phases: int
    breakdown: tuple[TierCostBreakdown, ...]
    unpriced_tiers: tuple[str, ...]
    pricing_known: bool
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_cost_estimate(self)

    @property
    def recommended_ceiling_usd(self) -> Decimal | None:
        validate_cost_estimate(self)
        if self.recommended_ceiling_cents is None:
            return None
        return Decimal(self.recommended_ceiling_cents) / _ONE_HUNDRED

    @property
    def is_estimable(self) -> bool:
        validate_cost_estimate(self)
        return self.recommended_ceiling_cents is not None


def _validate_notes(notes: object) -> tuple[str, ...]:
    if type(notes) is not tuple or len(notes) > _MAX_NOTES:
        _fail(f"notes must be an exact tuple with at most {_MAX_NOTES} entries")
    assert isinstance(notes, tuple)
    for note in notes:
        if type(note) is not str or not note or len(note) > _MAX_NOTE_LENGTH:
            _fail(f"each note must contain 1..{_MAX_NOTE_LENGTH} characters")
    return cast(tuple[str, ...], notes)


def validate_cost_estimate(value: object) -> MidnightOilCostEstimate:
    """Revalidate an exported estimate, including forged frozen instances."""

    _assert_exact_dataclass_shape(value, MidnightOilCostEstimate)
    assert type(value) is MidnightOilCostEstimate
    total_phases = _validate_exact_int(
        value.total_phases,
        name="total_phases",
        minimum=0,
        maximum=_MAX_TOTAL_PHASES,
    )
    if type(value.breakdown) is not tuple or len(value.breakdown) > _MAX_PHASE_BUDGETS:
        _fail("breakdown must be a bounded exact tuple")
    if type(value.unpriced_tiers) is not tuple:
        _fail("unpriced_tiers must be an exact tuple")
    if type(value.pricing_known) is not bool:
        _fail("pricing_known must be an exact bool")
    _validate_notes(value.notes)

    tiers: list[str] = []
    expected_unpriced: list[str] = []
    contribution_total = 0
    for row in value.breakdown:
        row = _validate_breakdown(row)
        if row.total_phases != total_phases:
            _fail("every breakdown row must match the estimate total_phases")
        tiers.append(row.tier)
        if row.contribution_cents is None:
            expected_unpriced.append(row.tier)
        else:
            contribution_total += row.contribution_cents
    if tiers != sorted(set(tiers)):
        _fail("breakdown tiers must be unique and sorted")
    if list(value.unpriced_tiers) != expected_unpriced:
        _fail("unpriced_tiers must exactly match the unpriced breakdown rows")
    for tier in value.unpriced_tiers:
        _validate_tier(tier, name="unpriced tier")

    if total_phases == 0:
        if value.breakdown or value.unpriced_tiers:
            _fail("a zero-phase estimate cannot have a breakdown")
        if value.recommended_ceiling_cents is not None or not value.pricing_known:
            _fail("a zero-phase estimate must be known no-work with no ceiling")
    elif expected_unpriced:
        if value.recommended_ceiling_cents is not None or value.pricing_known:
            _fail("unknown pricing requires a None ceiling and pricing_known=False")
    else:
        ceiling = _validate_exact_int(
            value.recommended_ceiling_cents,
            name="recommended_ceiling_cents",
            minimum=1,
            maximum=_MAX_AGGREGATE_TOKENS,
        )
        if not value.pricing_known or ceiling != contribution_total:
            _fail("the known ceiling must equal the tier contribution sum")
    return value


def _ceil_cents(
    *,
    input_tokens: int,
    output_tokens: int,
    input_rate: Decimal,
    output_rate: Decimal,
) -> int:
    with localcontext() as context:
        context.prec = _ARITHMETIC_PRECISION
        exact_cents = (
            (Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate)
            * _ONE_HUNDRED
            / _ONE_MILLION
        )
        return int(exact_cents.to_integral_value(rounding=ROUND_CEILING))


def estimate_midnight_oil_cost(
    *,
    duration_minutes: DurationInput,
    goals: int,
    cadence: CadenceProfile,
    pricing: list[TierPricing] | tuple[TierPricing, ...],
    minutes_per_phase: DurationInput = 3,
) -> MidnightOilCostEstimate:
    """Return a conservative, integer-cent Midnight Oil reservation.

    ``minutes_per_phase`` is a lower bound on the interval between phase starts.
    A positive partial interval can start one phase, so duration capacity is
    rounded upward.  The result is still capped by the declared goal cadence.
    """

    duration = _bounded_decimal(
        duration_minutes,
        name="duration_minutes",
        minimum=Decimal(0),
        maximum=_MAX_DURATION_MINUTES,
    )
    goal_count = _validate_exact_int(
        goals,
        name="goals",
        minimum=0,
        maximum=_MAX_GOALS,
    )
    cadence = _validate_cadence(cadence)
    phase_interval = _bounded_decimal(
        minutes_per_phase,
        name="minutes_per_phase",
        minimum=Decimal("0.000001"),
        maximum=_MAX_DURATION_MINUTES,
    )
    if type(pricing) not in (list, tuple):
        _fail("pricing must be an exact list or tuple")
    if len(pricing) > _MAX_PRICING_ROWS:
        _fail(f"pricing may contain at most {_MAX_PRICING_ROWS} entries")

    pricing_by_tier: dict[str, TierPricing] = {}
    for row in pricing:
        row = _validate_tier_pricing(row)
        if row.tier in pricing_by_tier:
            _fail(f"duplicate pricing for tier {row.tier!r}")
        pricing_by_tier[row.tier] = row

    if goal_count == 0 or duration == 0:
        return MidnightOilCostEstimate(
            recommended_ceiling_cents=None,
            total_phases=0,
            breakdown=(),
            unpriced_tiers=(),
            pricing_known=True,
            notes=("zero work requested — no spend to reserve",),
        )

    with localcontext() as context:
        context.prec = _ARITHMETIC_PRECISION
        duration_limited_phases = int(
            (duration / phase_interval).to_integral_value(rounding=ROUND_CEILING)
        )
    goal_limited_phases = goal_count * cadence.phases_per_goal
    total_phases = min(duration_limited_phases, goal_limited_phases)
    _validate_exact_int(
        total_phases,
        name="total_phases",
        minimum=1,
        maximum=_MAX_TOTAL_PHASES,
    )

    tier_input: dict[str, int] = {}
    tier_output: dict[str, int] = {}
    for budget in cadence.phase_budgets:
        input_tokens = tier_input.get(budget.tier, 0) + budget.input_tokens * total_phases
        output_tokens = tier_output.get(budget.tier, 0) + budget.output_tokens * total_phases
        if input_tokens > _MAX_AGGREGATE_TOKENS or output_tokens > _MAX_AGGREGATE_TOKENS:
            _fail("aggregate token reservation exceeds the supported BIGINT range")
        tier_input[budget.tier] = input_tokens
        tier_output[budget.tier] = output_tokens

    breakdown: list[TierCostBreakdown] = []
    unpriced: list[str] = []
    for tier in sorted(tier_input):
        input_tokens = tier_input[tier]
        output_tokens = tier_output[tier]
        tier_pricing = pricing_by_tier.get(tier)
        input_rate = tier_pricing.input_per_mtok if tier_pricing else None
        output_rate = tier_pricing.output_per_mtok if tier_pricing else None
        priced = (
            type(input_rate) is Decimal
            and input_rate > 0
            and type(output_rate) is Decimal
            and output_rate > 0
        )
        contribution_cents: int | None = None
        calls_per_phase: list[TierCallCostBreakdown] = []
        for budget in cadence.phase_budgets:
            if budget.tier != tier:
                continue
            projected_max_cents: int | None = None
            if priced:
                assert type(input_rate) is Decimal and type(output_rate) is Decimal
                projected_max_cents = _ceil_cents(
                    input_tokens=budget.input_tokens,
                    output_tokens=budget.output_tokens,
                    input_rate=input_rate,
                    output_rate=output_rate,
                )
            calls_per_phase.append(
                TierCallCostBreakdown(
                    tier=tier,
                    input_tokens=budget.input_tokens,
                    output_tokens=budget.output_tokens,
                    input_rate=input_rate,
                    output_rate=output_rate,
                    projected_max_cents=projected_max_cents,
                )
            )
        if priced:
            contribution_cents = total_phases * sum(
                call.projected_max_cents or 0 for call in calls_per_phase
            )
        else:
            unpriced.append(tier)
        breakdown.append(
            TierCostBreakdown(
                tier=tier,
                total_input_tokens=input_tokens,
                total_output_tokens=output_tokens,
                input_rate=input_rate,
                output_rate=output_rate,
                contribution_cents=contribution_cents,
                total_phases=total_phases,
                calls_per_phase=tuple(calls_per_phase),
            )
        )

    notes = [
        f"high-bound reservation over {total_phases} phase(s): "
        f"startable-by-duration {duration_limited_phases}, goal-capped {goal_limited_phases}",
        "each outbound call is rounded upward to whole cents for BudgetLedger holds",
    ]
    if unpriced:
        notes.append(f"UNPRICED {len(unpriced)} tier(s); see unpriced_tiers; ceiling is unknown")
        return MidnightOilCostEstimate(
            recommended_ceiling_cents=None,
            total_phases=total_phases,
            breakdown=tuple(breakdown),
            unpriced_tiers=tuple(unpriced),
            pricing_known=False,
            notes=tuple(notes),
        )

    ceiling_cents = sum(row.contribution_cents or 0 for row in breakdown)
    notes.append(f"reserve {ceiling_cents} integer cent(s) before dispatch")
    return MidnightOilCostEstimate(
        recommended_ceiling_cents=ceiling_cents,
        total_phases=total_phases,
        breakdown=tuple(breakdown),
        unpriced_tiers=(),
        pricing_known=True,
        notes=tuple(notes),
    )
