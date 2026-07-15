from __future__ import annotations

from datetime import UTC, datetime

import pytest

from interfaces.research.api.multimedia_routes import (
    _DISPATCH_CONFIG_PATH,
    _production_activation_quote_resolver,
)
from substrate.multimedia.research_plan import PreparedInvestigation, _assert_quote_integrity


def _prepared() -> PreparedInvestigation:
    return PreparedInvestigation(
        investigation_id="mpi_" + "1" * 48,
        source_plan_id="mrp_" + "2" * 48,
        source_plan_version=1,
        source_plan_integrity_digest="3" * 64,
        source_intent_id="mmri_" + "4" * 48,
        source_intent_digest="5" * 64,
        source_evidence_digest="6" * 64,
        tree={"root": {"node_id": "root", "question": "Why?", "children": []}},
        total_node_count=3,
        leaf_question_count=2,
        request_digest="7" * 64,
        state="prepared",
        created_at="2026-07-15T00:00:00Z",
    )


def test_production_quote_fails_closed_for_current_zero_placeholders() -> None:
    resolver = _production_activation_quote_resolver(_DISPATCH_CONFIG_PATH)

    with pytest.raises(ValueError, match="^activation quote unavailable$"):
        resolver(_prepared(), "balanced")


@pytest.mark.parametrize(
    ("policy", "tier", "provider"),
    [
        ("cheapest", "flash", "flash-provider"),
        ("balanced", "pro", "pro-provider"),
        ("highest_quality", "synthesis", "synthesis-provider"),
    ],
)
def test_production_quote_uses_exact_positive_structural_config(
    tmp_path, policy: str, tier: str, provider: str,
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        """
tiers:
  flash: &tier
    provider: flash-provider
    model: flash-model
    pricing: &pricing
      input_per_mtok: 1.25
      output_per_mtok: 2.5
      cached_input_per_mtok: 0.5
  pro:
    <<: *tier
    provider: pro-provider
    model: pro-model
  synthesis:
    <<: *tier
    provider: synthesis-provider
    model: synthesis-model
tier_defaults:
  flash: &limits
    context_budget_tokens: 1000
    max_tokens: 500
  pro: *limits
  synthesis: *limits
""",
        encoding="utf-8",
    )
    now = datetime(2026, 7, 15, 12, 30, 45, 123456, tzinfo=UTC)
    resolver = _production_activation_quote_resolver(config, clock=lambda: now)

    quote = resolver(_prepared(), policy)
    replay = resolver(_prepared(), policy)

    assert quote == replay
    _assert_quote_integrity(quote, policy, _prepared())
    assert (quote.resolved_tier, quote.provider) == (tier, provider)
    # Five calls * ((1000 * 1.25 + 500 * 2.5) / 1m) USD = 1.25 cents.
    assert quote.quoted_ceiling_cents == 2
    assert quote.pricing_source == "substrate/dispatch/config.yaml"
    assert len(quote.dispatch_config_digest) == len(quote.pricing_digest) == 64
    assert quote.quote_id.startswith("aq_") and len(quote.quote_id) == 51
    assert quote.issued_at == "2026-07-15T12:30:45Z"
    assert quote.expires_at == "2026-07-16T12:30:45Z"


@pytest.mark.parametrize("bad_rate", ["0", "-1", ".nan", ".inf", "null", "malformed"])
def test_production_quote_rejects_unusable_pricing_without_disclosing_value(
    tmp_path, bad_rate: str,
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
tiers:
  pro:
    provider: provider
    model: model
    pricing:
      input_per_mtok: {bad_rate}
      output_per_mtok: 1
      cached_input_per_mtok: 1
tier_defaults:
  pro:
    context_budget_tokens: 1000
    max_tokens: 500
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as caught:
        _production_activation_quote_resolver(config)(_prepared(), "balanced")

    assert str(caught.value) == "activation quote unavailable"
