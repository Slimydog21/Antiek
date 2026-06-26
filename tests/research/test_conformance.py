"""Conformance harness tests — positive (GoodStub) + negative (BrokenStub).

Rigor #3: a harness that only blesses a good stub proves nothing. The
negative tests below assert the harness FAILS on each breach and names
the right invariant in the ``ConformanceError`` message. If the harness
ever silently passes a broken result, the corresponding negative test
fails.

The stubs here are hand-built ``ResearchResult`` values driven through
``StubResearchProvider`` (for the conformant case) or through a tiny
ad-hoc provider (for the broken cases, so we can inject exactly one
defect at a time). Fixtures are in-code dicts — no network.
"""

from __future__ import annotations

import pytest

from research.providers.base import ResearchProvider
from research.providers.conformance import ConformanceError, conformance
from research.providers.stub import StubResearchProvider
from research.providers.types import CostModel, RawRef, ResearchResult, Source


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _good_result(sub_question: str = "q") -> ResearchResult:
    """A fully-conformant result for ``sub_question``."""
    return ResearchResult(
        fields={"answer": "Paris", "population": "2.1M"},
        field_citations={
            "answer": [Source(url="https://example.com/paris", title="Paris")],
            "population": [Source(url="https://example.com/paris-pop",
                                  title="Paris population")],
        },
        confidence=0.9,
        cost=0.012,
        latency=340,
        provider="stub",
        tier="basic",
        raw_ref=RawRef(handle="stub:raw:1", provider="stub"),
    )


def _good_fixture(sub_question: str = "q") -> dict:
    return {
        "sub_question": sub_question,
        "output_schema": {"answer": "string", "population": "string"},
        "expected_fields": {"answer": "Paris", "population": "2.1M"},
        "expected_confidence": 0.9,
    }


class _FixedProvider:
    """A provider that always returns one fixed result (for negative tests).

    Builds the result via a factory so each test can inject exactly one
    defect. Carries conformant capability metadata so the harness's
    metadata checks don't fire before the result check we want to
    exercise.
    """

    provider_id = "stub"
    supports_async = False
    tiers = ("basic",)
    cost_model = (
        CostModel(tier="basic", cost_usd_estimate=0.0, latency_ms_estimate=0),
    )

    def __init__(self, result_factory) -> None:
        self._factory = result_factory

    def answer(self, sub_question, output_schema, *, tier=None):
        return self._factory(sub_question)


# --------------------------------------------------------------------------
# Positive: GoodStub passes
# --------------------------------------------------------------------------


def test_good_stub_passes_conformance():
    """A conformant provider+result passes the harness (no raise)."""
    provider = StubResearchProvider({"q": _good_result("q")})
    # Must not raise.
    conformance(provider, _good_fixture("q"))


def test_stub_satisfies_protocol():
    """StubResearchProvider structurally satisfies ResearchProvider."""
    provider = StubResearchProvider({"q": _good_result("q")})
    assert isinstance(provider, ResearchProvider)


# --------------------------------------------------------------------------
# Negative: BrokenStub fails, naming the invariant
# --------------------------------------------------------------------------


def test_missing_citation_fails_naming_inv4():
    """Field has a value but no citation → INV-4."""
    def factory(sq):
        r = _good_result(sq)
        # Remove the citation for 'answer' but keep the value populated.
        return ResearchResult(
            fields=r.fields,
            field_citations={"population": r.field_citations["population"]},
            confidence=r.confidence,
            cost=r.cost,
            latency=r.latency,
            provider=r.provider,
            tier=r.tier,
            raw_ref=r.raw_ref,
        )
    provider = _FixedProvider(factory)
    with pytest.raises(ConformanceError, match="INV-4.*answer.*no citation"):
        conformance(provider, _good_fixture("q"))


def test_confidence_out_of_range_fails_naming_inv4():
    """confidence > 1.0 → INV-4."""
    def factory(sq):
        r = _good_result(sq)
        return ResearchResult(
            fields=r.fields,
            field_citations=r.field_citations,
            confidence=1.5,
            cost=r.cost,
            latency=r.latency,
            provider=r.provider,
            tier=r.tier,
            raw_ref=r.raw_ref,
        )
    provider = _FixedProvider(factory)
    with pytest.raises(ConformanceError, match="INV-4.*confidence.*out of range"):
        conformance(provider, _good_fixture("q"))


def test_negative_cost_fails_naming_inv4():
    """cost < 0 → INV-4."""
    def factory(sq):
        r = _good_result(sq)
        return ResearchResult(
            fields=r.fields,
            field_citations=r.field_citations,
            confidence=r.confidence,
            cost=-0.01,
            latency=r.latency,
            provider=r.provider,
            tier=r.tier,
            raw_ref=r.raw_ref,
        )
    provider = _FixedProvider(factory)
    with pytest.raises(ConformanceError, match="INV-4.*cost.*≥ 0"):
        conformance(provider, _good_fixture("q"))


def test_unpopulated_cost_fails_naming_inv4():
    """cost is None → INV-4 (must be populated)."""
    def factory(sq):
        r = _good_result(sq)
        return ResearchResult(
            fields=r.fields,
            field_citations=r.field_citations,
            confidence=r.confidence,
            cost=None,  # type: ignore[arg-type]
            latency=r.latency,
            provider=r.provider,
            tier=r.tier,
            raw_ref=r.raw_ref,
        )
    provider = _FixedProvider(factory)
    with pytest.raises(ConformanceError, match="INV-4.*cost.*float"):
        conformance(provider, _good_fixture("q"))


def test_wrong_return_type_fails_naming_inv4():
    """answer returns a dict, not ResearchResult → INV-4."""
    class _DictProvider:
        provider_id = "stub"
        supports_async = False
        tiers = ("basic",)
        cost_model = (CostModel(tier="basic", cost_usd_estimate=0.0,
                                latency_ms_estimate=0),)

        def answer(self, sub_question, output_schema, *, tier=None):
            return {"fields": {"answer": "Paris"}}

    provider = _DictProvider()
    with pytest.raises(ConformanceError, match="INV-4.*not ResearchResult"):
        conformance(provider, _good_fixture("q"))


def test_tier_not_in_provider_tiers_fails_naming_inv4():
    """result.tier not in provider.tiers → INV-4."""
    def factory(sq):
        r = _good_result(sq)
        return ResearchResult(
            fields=r.fields,
            field_citations=r.field_citations,
            confidence=r.confidence,
            cost=r.cost,
            latency=r.latency,
            provider=r.provider,
            tier="ultra8x",  # not in _FixedProvider.tiers
            raw_ref=r.raw_ref,
        )
    provider = _FixedProvider(factory)
    with pytest.raises(ConformanceError, match="INV-4.*tier.*not in provider.tiers"):
        conformance(provider, _good_fixture("q"))


def test_raw_ref_not_a_rawref_fails_naming_inv4():
    """raw_ref is a dict, not RawRef → INV-4."""
    def factory(sq):
        r = _good_result(sq)
        return ResearchResult(
            fields=r.fields,
            field_citations=r.field_citations,
            confidence=r.confidence,
            cost=r.cost,
            latency=r.latency,
            provider=r.provider,
            tier=r.tier,
            raw_ref={"handle": "x", "provider": "stub"},  # type: ignore[arg-type]
        )
    provider = _FixedProvider(factory)
    with pytest.raises(ConformanceError, match="INV-4.*raw_ref.*RawRef"):
        conformance(provider, _good_fixture("q"))


def test_non_string_field_value_fails_naming_inv4():
    """A field value that is not str/None (e.g. an int) → INV-4.

    The normalized contract types fields as ``str | None``. A non-string
    value is both a type breach and an INV-4 leak vector (a dict value
    could smuggle provider-specific structure). The harness must reject it
    rather than silently bless it.
    """
    def factory(sq):
        r = _good_result(sq)
        return ResearchResult(
            fields={"answer": 42, "population": "2.1M"},  # type: ignore[arg-type]
            field_citations={
                "answer": [Source(url="https://example.com/paris", title="x")],
                "population": [Source(url="https://example.com/pop", title="x")],
            },
            confidence=r.confidence,
            cost=r.cost,
            latency=r.latency,
            provider=r.provider,
            tier=r.tier,
            raw_ref=r.raw_ref,
        )
    provider = _FixedProvider(factory)
    with pytest.raises(ConformanceError, match="INV-4.*fields.*answer.*str or None"):
        conformance(provider, _good_fixture("q"))


def test_deterministic_round_trip_mismatch_fails():
    """expected_fields present but result differs → INV-4 round-trip."""
    def factory(sq):
        r = _good_result(sq)
        return ResearchResult(
            fields={"answer": "London", "population": "8.8M"},
            field_citations={
                "answer": [Source(url="https://example.com/london", title="London")],
                "population": [Source(url="https://example.com/lon-pop",
                                      title="London pop")],
            },
            confidence=r.confidence,
            cost=r.cost,
            latency=r.latency,
            provider=r.provider,
            tier=r.tier,
            raw_ref=r.raw_ref,
        )
    provider = _FixedProvider(factory)
    with pytest.raises(ConformanceError, match="INV-4.*round-trip.*answer"):
        conformance(provider, _good_fixture("q"))


def test_capability_metadata_missing_provider_id_fails():
    """provider_id empty → INV-1 (capability metadata malformed)."""
    class _BadMetaProvider:
        provider_id = ""
        supports_async = False
        tiers = ("basic",)
        cost_model = (CostModel(tier="basic", cost_usd_estimate=0.0,
                                latency_ms_estimate=0),)

        def answer(self, sub_question, output_schema, *, tier=None):
            return _good_result(sub_question)

    provider = _BadMetaProvider()
    with pytest.raises(ConformanceError, match="INV-1.*provider_id"):
        conformance(provider, _good_fixture("q"))


def test_capability_metadata_cost_model_length_mismatch_fails():
    """cost_model has 2 entries for 1 tier → INV-1."""
    class _BadCostModelProvider:
        provider_id = "stub"
        supports_async = False
        tiers = ("basic",)
        cost_model = (
            CostModel(tier="basic", cost_usd_estimate=0.0, latency_ms_estimate=0),
            CostModel(tier="deep", cost_usd_estimate=0.05, latency_ms_estimate=500),
        )

        def answer(self, sub_question, output_schema, *, tier=None):
            return _good_result(sub_question)

    provider = _BadCostModelProvider()
    with pytest.raises(ConformanceError, match="INV-1.*cost_model.*per tier"):
        conformance(provider, _good_fixture("q"))


def test_null_field_exempt_from_citation():
    """A field with value None need not have a citation (explicit carve-out)."""
    def factory(sq):
        r = _good_result(sq)
        return ResearchResult(
            fields={"answer": "Paris", "population": None},
            field_citations={
                "answer": r.field_citations["answer"],
                # 'population' deliberately absent — it's None.
            },
            confidence=r.confidence,
            cost=r.cost,
            latency=r.latency,
            provider=r.provider,
            tier=r.tier,
            raw_ref=r.raw_ref,
        )
    provider = _FixedProvider(factory)
    fixture = _good_fixture("q")
    fixture["expected_fields"] = {"answer": "Paris", "population": None}
    # Must not raise — None fields are exempt.
    conformance(provider, fixture)
