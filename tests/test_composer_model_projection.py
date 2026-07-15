"""Tests for substrate/dispatch/composer_model_projection.py — asks #8/#10 Slice A.

Each test maps 1:1 to one of the 6 load-bearing invariants in the model-decision-composer
spec §3. The projector is a fake returning valid CostProjections (built so the
__post_init__ money invariant holds); the resolver is pure composition.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from runtime.research_runner.protocol import (
    BillingUnit,
    BoundedUsage,
    CostProjection,
    ProjectionDisposition,
    ProjectionIneligibility,
    ProjectionRate,
)
from substrate.dispatch.advisory_decision import DecisionCandidate
from substrate.dispatch.composer_model_projection import (
    BudgetSnapshot,
    ComposerCandidateView,
    ProjectionResolver,
    resolve_composer_projection,
)

_USAGE_MAX = 1_000_000


def _projection(*, provider: str, model: str, tenths: int) -> CostProjection:
    """Build a valid HOLD_ELIGIBLE projection whose max cost is ``tenths`` × $0.10.

    Derived so rate × usage == maximum_cost_usd (the __post_init__ money invariant):
    rate_coeff = tenths, rate_exp = -7, usage = 10^6 ⟹ max = tenths × 10^-1.
    """
    rate = Decimal(tenths) * (Decimal(10) ** -7)
    max_usd = Decimal(tenths) / Decimal(10)
    cents = tenths * 10
    return CostProjection(
        seam_id="seam-1",
        provider=provider,
        model=model,
        operation="deep_research",
        bounded_usage=(BoundedUsage(unit=BillingUnit.INPUT_TOKEN, maximum=_USAGE_MAX),),
        rates=(ProjectionRate(unit=BillingUnit.INPUT_TOKEN, usd_per_unit=rate),),
        rate_snapshot="snap-1",
        currency="USD",
        maximum_cost_usd=max_usd,
        reservation_cents=cents,
        disposition=ProjectionDisposition.HOLD_ELIGIBLE,
    )


class _FakeProjector:
    """A projector whose max cost (in tenths-of-a-dollar) depends on (provider, model)."""

    def __init__(self, costs: dict[tuple[str, str], int]) -> None:
        self._costs = costs

    def __call__(self, provider: str, model: str) -> CostProjection:
        return _projection(provider=provider, model=model, tenths=self._costs[(provider, model)])


def _candidate(
    provider: str,
    model: str,
    *,
    tier: str = "pro",
    low: float | None = 0.10,
    high: float | None = 0.20,
    ready: bool = True,
    would_exceed: bool | None = False,
    bench: float | None = 0.9,
    samples: int | None = 50,
) -> DecisionCandidate:
    return DecisionCandidate(
        tier=tier,
        provider=provider,
        model=model,
        ready=ready,
        estimated_usd_low=low,
        estimated_usd_high=high,
        would_exceed_budget=would_exceed,
        benchmark_score=bench,
        benchmark_samples=samples,
    )


def _candidates() -> tuple[DecisionCandidate, ...]:
    return (
        _candidate("openai", "gpt-pro", tier="pro"),
        _candidate(
            "openai", "gpt-flash", tier="flash", bench=None, samples=None, low=0.01, high=0.02
        ),
    )


# ---------------------------------------------------------------------------
# I1 — client projection is explanatory, NOT authorization
# ---------------------------------------------------------------------------


def test_authority_is_advisory_explanatory_not_authorization() -> None:
    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
        chosen=("openai", "gpt-pro"),
        project=_FakeProjector({("openai", "gpt-pro"): 2}),
    )
    assert res.authority == "advisory_explanatory"
    assert any("server re-validates" in n for n in res.notes)


# ---------------------------------------------------------------------------
# I2 — unknown pricing is visibly unknown, never $0.00
# ---------------------------------------------------------------------------


def test_unknown_pricing_is_unknown_not_zero() -> None:
    cands = (_candidate("openai", "gpt-pro", low=None, high=None),)
    res = resolve_composer_projection(
        task="deep_research",
        candidates=cands,
        budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
        chosen=("openai", "gpt-pro"),
        project=_FakeProjector({("openai", "gpt-pro"): 2}),
    )
    assert res.pricing_status == "unknown"
    view = res.ranked_candidates[0]
    assert view.pricing_status == "unknown"
    assert view.estimated_usd_low is None


def test_known_pricing_when_bounds_present() -> None:
    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
        chosen=None,
        project=_FakeProjector({}),
    )
    pro = next(v for v in res.ranked_candidates if v.model == "gpt-pro")
    assert pro.pricing_status == "known"


# ---------------------------------------------------------------------------
# I3 — would_exceed_budget derived from the authoritative projection
# ---------------------------------------------------------------------------


def test_would_exceed_true_when_projection_crosses_ceiling() -> None:
    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=9.5),  # 0.50 remaining
        chosen=("openai", "gpt-pro"),
        project=_FakeProjector({("openai", "gpt-pro"): 8}),  # $0.80 exceeds $0.50
    )
    assert res.would_exceed_budget is True
    assert res.chosen_projection is not None


def test_would_exceed_false_when_within_ceiling() -> None:
    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),  # 9.0 remaining
        chosen=("openai", "gpt-pro"),
        project=_FakeProjector({("openai", "gpt-pro"): 2}),  # $0.20 within $9.0
    )
    assert res.would_exceed_budget is False


def test_would_exceed_null_when_budget_unmeasurable() -> None:
    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=None, spent_usd=None),
        chosen=("openai", "gpt-pro"),
        project=_FakeProjector({("openai", "gpt-pro"): 2}),
    )
    assert res.would_exceed_budget is None  # never fabricated False
    assert res.remaining_usd is None


def test_would_exceed_null_when_projection_source_is_unavailable() -> None:
    class _Exploder:
        def __call__(self, provider: str, model: str) -> CostProjection:
            raise LookupError("catalog down")

    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
        chosen=("openai", "gpt-pro"),
        project=_Exploder(),
    )
    assert res.would_exceed_budget is None
    assert res.chosen_projection is None
    assert any("withheld" in n for n in res.notes)


def test_unexpected_projector_error_is_not_silently_downgraded() -> None:
    class _BuggyProjector:
        def __call__(self, provider: str, model: str) -> CostProjection:
            raise RuntimeError("programmer bug")

    with pytest.raises(RuntimeError, match="programmer bug"):
        resolve_composer_projection(
            task="deep_research",
            candidates=_candidates(),
            budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
            chosen=("openai", "gpt-pro"),
            project=_BuggyProjector(),
        )


# ---------------------------------------------------------------------------
# I4 — quality basis carried (measured vs absent)
# ---------------------------------------------------------------------------


def test_quality_basis_carried_measured_vs_absent() -> None:
    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
        chosen=None,
        project=_FakeProjector({}),
    )
    pro = next(v for v in res.ranked_candidates if v.model == "gpt-pro")
    flash = next(v for v in res.ranked_candidates if v.model == "gpt-flash")
    assert pro.quality_basis == "measured"  # bench + samples present
    assert flash.quality_basis == "absent"  # bench/samples None
    assert flash.quality_score is None


# ---------------------------------------------------------------------------
# I5 — curated default is the honest fallback
# ---------------------------------------------------------------------------


def test_curated_default_when_no_explicit_choice() -> None:
    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
        chosen=None,
        project=_FakeProjector({}),
    )
    assert res.chosen_provider is None
    assert res.chosen_model is None
    assert res.chosen_projection is None
    assert any("curated default" in n for n in res.notes)


def test_choice_not_in_ranked_set_is_honest_unknown() -> None:
    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
        chosen=("anthropic", "claude-opus"),  # not in candidates
        project=_FakeProjector({}),
    )
    assert res.chosen_provider is None
    assert res.would_exceed_budget is None
    assert any("not in the ranked" in n for n in res.notes)


# ---------------------------------------------------------------------------
# I6 — ranked list is the advisory ranking verbatim
# ---------------------------------------------------------------------------


def test_ranked_list_preserves_rank_and_fields() -> None:
    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
        chosen=None,
        project=_FakeProjector({}),
    )
    assert len(res.ranked_candidates) == 2
    ranks = [v.rank for v in res.ranked_candidates]
    assert ranks == sorted(ranks)  # monotonic
    assert all(isinstance(v, ComposerCandidateView) for v in res.ranked_candidates)
    assert all(
        isinstance(v.quality_score, float) if v.quality_basis == "measured" else v.quality_score is None
        for v in res.ranked_candidates
    )


def test_remaining_is_cap_minus_spent() -> None:
    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=3.0),
        chosen=None,
        project=_FakeProjector({}),
    )
    assert res.remaining_usd == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# purity + determinism + protocol
# ---------------------------------------------------------------------------


def test_resolver_is_pure_and_deterministic() -> None:
    budget = BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0)
    proj = _FakeProjector({("openai", "gpt-pro"): 2})
    a = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=budget,
        chosen=("openai", "gpt-pro"),
        project=proj,
    )
    b = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=budget,
        chosen=("openai", "gpt-pro"),
        project=proj,
    )
    assert a == b  # identical inputs → identical output


def test_projection_resolver_is_runtime_checkable_protocol() -> None:
    assert isinstance(_FakeProjector({}), ProjectionResolver)


# ---------------------------------------------------------------------------
# trust-boundary hardening — exact money, identity, shape, and bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "invalid", [float("nan"), float("inf"), -0.01, 1_000_000_000_001.0]
)
def test_budget_rejects_invalid_money(invalid: float) -> None:
    with pytest.raises(ValueError):
        BudgetSnapshot(daily_cap_usd=invalid, spent_usd=0.0)
    with pytest.raises(ValueError):
        BudgetSnapshot(daily_cap_usd=1.0, spent_usd=invalid)


def test_budget_rejects_integer_and_boolean_money() -> None:
    with pytest.raises(TypeError):
        BudgetSnapshot(daily_cap_usd=10, spent_usd=0.0)
    with pytest.raises(TypeError):
        BudgetSnapshot(daily_cap_usd=10.0, spent_usd=False)


def test_spent_over_cap_clamps_remaining_to_zero_and_paid_projection_exceeds() -> None:
    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=1.0, spent_usd=2.0),
        chosen=("openai", "gpt-pro"),
        project=_FakeProjector({("openai", "gpt-pro"): 1}),
    )
    assert res.remaining_usd == 0.0
    assert res.would_exceed_budget is True


def test_decimal_projection_does_not_underflow_through_float() -> None:
    def tiny_projection(provider: str, model: str) -> CostProjection:
        tiny = Decimal("1e-1000")
        return CostProjection(
            seam_id="tiny-seam",
            provider=provider,
            model=model,
            operation="deep_research",
            bounded_usage=(BoundedUsage(BillingUnit.INPUT_TOKEN, maximum=1),),
            rates=(ProjectionRate(BillingUnit.INPUT_TOKEN, usd_per_unit=tiny),),
            rate_snapshot="tiny-snapshot",
            currency="USD",
            maximum_cost_usd=tiny,
            reservation_cents=1,
            disposition=ProjectionDisposition.HOLD_ELIGIBLE,
        )

    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=0.0, spent_usd=0.0),
        chosen=("openai", "gpt-pro"),
        project=tiny_projection,
    )
    assert res.would_exceed_budget is True


def test_projection_for_different_route_is_rejected() -> None:
    def wrong_route(provider: str, model: str) -> CostProjection:
        return _projection(provider="other-provider", model="other-model", tenths=1)

    with pytest.raises(ValueError, match="different route"):
        resolve_composer_projection(
            task="deep_research",
            candidates=_candidates(),
            budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
            chosen=("openai", "gpt-pro"),
            project=wrong_route,
        )


def test_ineligible_projection_never_claims_within_budget() -> None:
    def ineligible(provider: str, model: str) -> CostProjection:
        return CostProjection(
            seam_id="missing-route",
            provider=provider,
            model=model,
            operation="deep_research",
            bounded_usage=(),
            rates=(),
            rate_snapshot="catalog-v1",
            currency="USD",
            maximum_cost_usd=Decimal(0),
            reservation_cents=0,
            disposition=ProjectionDisposition.INELIGIBLE,
            ineligibility=ProjectionIneligibility.UNKNOWN_DISPATCH,
        )

    res = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
        chosen=("openai", "gpt-pro"),
        project=ineligible,
    )
    assert res.chosen_projection is not None
    assert res.chosen_projection.disposition is ProjectionDisposition.INELIGIBLE
    assert res.would_exceed_budget is None
    assert any("ineligible" in note for note in res.notes)


def test_duplicate_route_candidates_are_rejected() -> None:
    duplicate = (
        _candidate("openai", "same", tier="pro"),
        _candidate("openai", "same", tier="flash"),
    )
    with pytest.raises(ValueError, match="identities must be unique"):
        resolve_composer_projection(
            task="deep_research",
            candidates=duplicate,
            budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
            chosen=None,
            project=_FakeProjector({}),
        )


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    ("low", "high"),
    [(None, 0.2), (0.1, None), (-0.1, 0.2), (0.3, 0.2), (float("nan"), 0.2)],
)
def test_invalid_candidate_price_bounds_are_rejected(low: float | None, high: float | None) -> None:
    with pytest.raises((TypeError, ValueError)):
        resolve_composer_projection(
            task="deep_research",
            candidates=(_candidate("openai", "bad", low=low, high=high),),
            budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
            chosen=None,
            project=_FakeProjector({}),
        )


def test_benchmark_score_and_samples_must_be_present_together() -> None:
    no_samples = _candidate("openai", "bad", bench=0.9, samples=None)
    with pytest.raises(ValueError, match="present together"):
        resolve_composer_projection(
            task="deep_research",
            candidates=(no_samples,),
            budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
            chosen=None,
            project=_FakeProjector({}),
        )


def test_candidate_collection_and_choice_are_closed() -> None:
    with pytest.raises(ValueError, match="candidates must be a tuple"):
        resolve_composer_projection(
            task="deep_research",
            candidates=list(_candidates()),  # type: ignore[arg-type]
            budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
            chosen=None,
            project=_FakeProjector({}),
        )
    with pytest.raises(TypeError, match="chosen must be"):
        resolve_composer_projection(
            task="deep_research",
            candidates=_candidates(),
            budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
            chosen=["openai", "gpt-pro"],  # type: ignore[arg-type]
            project=_FakeProjector({}),
        )


def test_incomplete_forged_projection_is_rejected() -> None:
    forged = object.__new__(CostProjection)

    def forged_projection(provider: str, model: str) -> CostProjection:
        return forged

    with pytest.raises(ValueError, match="incomplete CostProjection"):
        resolve_composer_projection(
            task="deep_research",
            candidates=_candidates(),
            budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
            chosen=("openai", "gpt-pro"),
            project=forged_projection,
        )


def test_projection_aggregate_rejects_contradictory_forged_fields() -> None:
    result = resolve_composer_projection(
        task="deep_research",
        candidates=_candidates(),
        budget=BudgetSnapshot(daily_cap_usd=10.0, spent_usd=1.0),
        chosen=("openai", "gpt-pro"),
        project=_FakeProjector({("openai", "gpt-pro"): 2}),
    )
    with pytest.raises(ValueError, match="would_exceed_budget conflicts"):
        replace(result, would_exceed_budget=True)
    with pytest.raises(ValueError, match="chosen route"):
        replace(result, chosen_model="not-ranked")
    with pytest.raises(ValueError, match="pricing_status conflicts"):
        replace(result, pricing_status="unknown")
    with pytest.raises(ValueError, match="recommended_tier"):
        replace(result, recommended_tier="not-eligible")
