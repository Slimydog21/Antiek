"""Typed-payload tests for the schema-v6 Exa/Browserbase precursor.

Spec: docs/integration_exa_browserbase.md §18.3. This precursor lands
three typed payloads ahead of Wedge 1 (Exa discovery adapter) and
Wedge 2 (Browserbase escalation fallback) so the wedge PRs hit the
ground typed. The wedges themselves ship Sprint 18-19 and emit these
events; this test file only verifies the schema scaffold.

Covers:
  - DiscoveryProposedPayload
  - DiscoverySelectedPayload (including the legal-gate rejection path)
  - FetchFallbackEscalatedPayload

Each payload roundtrips through the TypedPayload discriminated union
TypeAdapter to confirm the action_type discriminator routes correctly.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from substrate.schemas.events import (
    EVENT_SCHEMA_VERSION,
    TYPED_PAYLOAD_ACTION_TYPES,
    ActionType,
    DiscoveryProposedPayload,
    DiscoverySelectedPayload,
    FetchFallbackEscalatedPayload,
    TypedPayload,
)


# ── Schema-level guarantees ─────────────────────────────────────────


def test_schema_version_bumped_past_v6():
    """The Exa/Browserbase precursor bumped to v6. The test enforces a
    monotonic floor so future bumps don't require touching this file."""
    assert EVENT_SCHEMA_VERSION >= 6


def test_precursor_action_types_in_typed_union():
    for at in (
        ActionType.DISCOVERY_PROPOSED,
        ActionType.DISCOVERY_SELECTED,
        ActionType.FETCH_FALLBACK_ESCALATED,
    ):
        assert at.value in TYPED_PAYLOAD_ACTION_TYPES, at


# ── DiscoveryProposedPayload ────────────────────────────────────────


def _build_proposed(**overrides) -> DiscoveryProposedPayload:
    """Fixture builder — fully-populated proposal with sensible defaults."""
    base = dict(
        discovery_id="disc-exa-abc1234567890def",
        provider="exa",
        query="anthropic claude pricing late 2025 vs 2026",
        url="https://www.anthropic.com/news/api-pricing",
        title="API pricing — Anthropic",
        published_date="2025-11-04",
        author=None,
        relevance_score=0.83,
        suggested_tier=4,
        text_snippet_preview="Anthropic published updated API pricing covering Opus 4.7, Sonnet 4.6, and Haiku 4.5 …",
        provider_response_id="exa-req-9f2c",
        cost_usd_estimate=0.0005,
    )
    base.update(overrides)
    return DiscoveryProposedPayload(**base)


def test_discovery_proposed_payload_roundtrips():
    p = _build_proposed()
    adapter = TypeAdapter(TypedPayload)
    re = adapter.validate_python(p.model_dump())
    assert isinstance(re, DiscoveryProposedPayload)
    assert re.discovery_id == "disc-exa-abc1234567890def"
    assert re.provider == "exa"
    assert re.suggested_tier == 4


def test_discovery_proposed_rejects_unknown_provider():
    with pytest.raises(ValidationError):
        _build_proposed(provider="serpapi")  # not in DiscoveryProvider yet


def test_discovery_proposed_tier_must_be_1_to_4():
    with pytest.raises(ValidationError):
        _build_proposed(suggested_tier=5)
    with pytest.raises(ValidationError):
        _build_proposed(suggested_tier=0)


def test_discovery_proposed_truncates_snippet_at_300_chars():
    long_snippet = "x" * 301
    with pytest.raises(ValidationError):
        _build_proposed(text_snippet_preview=long_snippet)


def test_discovery_proposed_omits_optional_fields():
    """Title/author/published_date/score/snippet/response_id/cost are all
    optional. A bare proposal (provider + query + url + tier + id)
    validates."""
    p = DiscoveryProposedPayload(
        discovery_id="disc-exa-bareminimum",
        provider="operator",
        query="manual paste",
        url="https://example.com/x",
        suggested_tier=4,
    )
    assert p.title is None
    assert p.cost_usd_estimate is None


# ── DiscoverySelectedPayload ────────────────────────────────────────


def test_discovery_selected_ingested_carries_document_id():
    p = DiscoverySelectedPayload(
        discovery_id="disc-exa-abc",
        document_id="doc-url-a1b2c3d4e5f6a7b8",
        decision="ingested",
    )
    adapter = TypeAdapter(TypedPayload)
    re = adapter.validate_python(p.model_dump())
    assert isinstance(re, DiscoverySelectedPayload)
    assert re.decision == "ingested"
    assert re.document_id == "doc-url-a1b2c3d4e5f6a7b8"
    assert re.rejection_reason is None


def test_discovery_selected_legal_gate_rejection_omits_document_id():
    """Spec §6.8 — when the Sprint 18 retrieval-time legal gate refuses
    an ingestion, the Selected event carries decision=rejected_by_legal_gate
    and document_id is None. The audit trail records the refusal; no
    graph write happened."""
    p = DiscoverySelectedPayload(
        discovery_id="disc-exa-banned",
        document_id=None,
        decision="rejected_by_legal_gate",
        rejection_reason="domain in Bartz banned-corpus list",
    )
    adapter = TypeAdapter(TypedPayload)
    re = adapter.validate_python(p.model_dump())
    assert isinstance(re, DiscoverySelectedPayload)
    assert re.decision == "rejected_by_legal_gate"
    assert re.document_id is None
    assert "Bartz" in (re.rejection_reason or "")


def test_discovery_selected_rejects_unknown_decision():
    with pytest.raises(ValidationError):
        DiscoverySelectedPayload(
            discovery_id="disc-exa-x",
            decision="rejected_by_paywall",  # not in DiscoveryDecision
        )


def test_discovery_selected_supports_all_four_decisions():
    for d in ("ingested", "rejected_by_legal_gate", "rejected_by_operator", "fetch_failed"):
        p = DiscoverySelectedPayload(
            discovery_id="disc-exa-x",
            decision=d,
            document_id="doc-url-x" if d == "ingested" else None,
        )
        assert p.decision == d


# ── FetchFallbackEscalatedPayload ───────────────────────────────────


def test_fetch_fallback_escalated_roundtrips():
    p = FetchFallbackEscalatedPayload(
        url="https://twitter.com/some/thread/12345",
        primary_word_count=12,
        fallback_fetcher="browserbase",
        fallback_word_count=380,
        escalation_reason="low_word_count",
        estimated_cost_usd=0.25,
    )
    adapter = TypeAdapter(TypedPayload)
    re = adapter.validate_python(p.model_dump())
    assert isinstance(re, FetchFallbackEscalatedPayload)
    assert re.primary_fetcher == "httpx"
    assert re.fallback_fetcher == "browserbase"
    assert re.escalation_reason == "low_word_count"
    assert re.fallback_word_count > re.primary_word_count


def test_fetch_fallback_recovered_versus_paywall_signal():
    """Spec §7.2 — fallback_word_count near primary signals captcha or
    paywall (escalation didn't recover); fallback_word_count >>
    primary signals genuine JS-rendering recovery. The payload itself
    doesn't classify; it logs both numbers so the operator can
    distinguish on review."""
    recovered = FetchFallbackEscalatedPayload(
        url="https://example.com/spa",
        primary_word_count=8,
        fallback_fetcher="browserbase",
        fallback_word_count=850,
        escalation_reason="low_word_count",
        estimated_cost_usd=0.10,
    )
    paywall = FetchFallbackEscalatedPayload(
        url="https://example.com/paywalled",
        primary_word_count=15,
        fallback_fetcher="browserbase",
        fallback_word_count=18,
        escalation_reason="low_word_count",
        estimated_cost_usd=0.10,
    )
    assert recovered.fallback_word_count - recovered.primary_word_count > 500
    assert paywall.fallback_word_count - paywall.primary_word_count < 20


def test_fetch_fallback_rejects_negative_cost():
    with pytest.raises(ValidationError):
        FetchFallbackEscalatedPayload(
            url="https://example.com/x",
            primary_word_count=10,
            fallback_fetcher="browserbase",
            fallback_word_count=100,
            escalation_reason="low_word_count",
            estimated_cost_usd=-0.01,
        )


def test_fetch_fallback_rejects_unknown_reason():
    with pytest.raises(ValidationError):
        FetchFallbackEscalatedPayload(
            url="https://example.com/x",
            primary_word_count=10,
            fallback_fetcher="browserbase",
            fallback_word_count=100,
            escalation_reason="captcha_solver_used",  # not in Literal
            estimated_cost_usd=0.10,
        )


def test_fetch_fallback_action_type_pinned():
    """Defensive: the discriminator must remain pinned via Literal[...]."""
    p = FetchFallbackEscalatedPayload(
        url="https://example.com/x",
        primary_word_count=10,
        fallback_fetcher="browserbase",
        fallback_word_count=100,
        escalation_reason="operator_override",
        estimated_cost_usd=0.10,
    )
    assert p.action_type == ActionType.FETCH_FALLBACK_ESCALATED.value


# ── Cross-payload invariant: extra='forbid' ─────────────────────────


@pytest.mark.parametrize(
    "model,kwargs",
    [
        (
            DiscoveryProposedPayload,
            dict(
                discovery_id="disc-x",
                provider="exa",
                query="q",
                url="https://e.com",
                suggested_tier=4,
            ),
        ),
        (
            DiscoverySelectedPayload,
            dict(discovery_id="disc-x", decision="ingested", document_id="doc-x"),
        ),
        (
            FetchFallbackEscalatedPayload,
            dict(
                url="https://e.com",
                primary_word_count=1,
                fallback_fetcher="browserbase",
                fallback_word_count=10,
                escalation_reason="low_word_count",
                estimated_cost_usd=0.1,
            ),
        ),
    ],
)
def test_precursor_payloads_forbid_extra_fields(model, kwargs):
    """_PayloadBase has extra='forbid'. A typo in a payload field should
    fail loudly, not silently land as a stray column that breaks
    codegen."""
    with pytest.raises(ValidationError):
        model(**kwargs, unexpected_field="oops")
