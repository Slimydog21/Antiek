from __future__ import annotations

from dataclasses import replace

import pytest

from substrate.dispatch import DispatchConfig, TierConfig, TierPricing
from substrate.dispatch.research_quote import (
    ResearchQuoteInvalid,
    build_research_route_manifest,
    issue_research_quote,
    verify_research_quote,
)

KEY = b"q" * 32


def _pricing(rate: float = 1.0) -> TierPricing:
    return TierPricing(
        input_per_mtok=rate,
        output_per_mtok=rate * 2,
        cached_input_per_mtok=rate / 10,
        currency="USD",
        billing_unit="per_million_tokens",
        source_url="https://provider.example/pricing",
        verified_at="2026-01-01T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
    )


def _config(rate: float = 1.0) -> DispatchConfig:
    fallback = TierConfig("pro-fallback", "fallback", "model-b", 200, 0.2, 1000, _pricing(rate * 3))
    primary = TierConfig("pro", "primary", "model-a", 100, 0.2, 1000, _pricing(rate), fallback)
    return DispatchConfig(role_tiers={"synthesizer": "pro", "decomposer": "pro"}, tiers={"pro": primary})


def _quote():
    manifest = build_research_route_manifest(_config())
    token, receipt = issue_research_quote(
        account_id="alice", prompt="question", research_tier="deep",
        manifest=manifest, approved_run_ceiling_usd=2.0,
        issued_at_ms=1_000, expires_at_ms=61_000, nonce="nonce-1",
        key_id="current", signing_key=KEY,
    )
    return manifest, token, receipt


def test_manifest_binds_roles_order_fallback_prices_and_output_limits():
    original = build_research_route_manifest(_config())
    assert [(row.role, row.fallback_index) for row in original.routes] == [
        ("decomposer", 0), ("decomposer", 1), ("synthesizer", 0), ("synthesizer", 1)
    ]
    logical_tier_changed = _config()
    logical_tier_changed.tiers["synthesis"] = logical_tier_changed.tiers["pro"]
    logical_tier_changed.role_tiers["decomposer"] = "synthesis"
    assert (
        build_research_route_manifest(logical_tier_changed).fingerprint
        != original.fingerprint
    )
    assert build_research_route_manifest(_config(2.0)).fingerprint != original.fingerprint
    changed = _config()
    changed.tiers["pro"] = replace(changed.tiers["pro"], max_tokens=101)
    assert build_research_route_manifest(changed).fingerprint != original.fingerprint
    changed_behavior = _config()
    changed_behavior.tiers["pro"] = replace(
        changed_behavior.tiers["pro"], temperature=0.7, context_budget_tokens=2000
    )
    assert build_research_route_manifest(changed_behavior).fingerprint != original.fingerprint


def test_quote_round_trip_and_context_mutations_fail_closed():
    manifest, token, issued = _quote()
    verified = verify_research_quote(
        token, account_id="alice", prompt="question", research_tier="deep",
        manifest=manifest, approved_run_ceiling_usd=2.0, now_ms=2_000,
        verification_keys={"current": KEY},
    )
    assert verified == issued
    mutations = [
        {"account_id": "bob"}, {"prompt": "changed"}, {"research_tier": "fast"},
        {"approved_run_ceiling_usd": 2.01}, {"manifest": build_research_route_manifest(_config(2.0))},
    ]
    base = dict(account_id="alice", prompt="question", research_tier="deep", manifest=manifest, approved_run_ceiling_usd=2.0)
    for mutation in mutations:
        with pytest.raises(ResearchQuoteInvalid):
            verify_research_quote(token, **(base | mutation), now_ms=2_000, verification_keys={"current": KEY})


def test_quote_rejects_tamper_expiry_wrong_key_and_unknown_pricing():
    manifest, token, _ = _quote()
    base = dict(account_id="alice", prompt="question", research_tier="deep", manifest=manifest, approved_run_ceiling_usd=2.0)
    with pytest.raises(ResearchQuoteInvalid, match="signature"):
        verify_research_quote(token[:-1] + ("A" if token[-1] != "A" else "B"), **base, now_ms=2_000, verification_keys={"current": KEY})
    with pytest.raises(ResearchQuoteInvalid, match="currently valid"):
        verify_research_quote(token, **base, now_ms=61_000, verification_keys={"current": KEY})
    recovered = verify_research_quote(
        token,
        **base,
        now_ms=61_000,
        verification_keys={"current": KEY},
        allow_expired=True,
    )
    assert recovered.expires_at_ms == 61_000
    with pytest.raises(ResearchQuoteInvalid, match="signature"):
        verify_research_quote(token, **base, now_ms=2_000, verification_keys={"current": b"x" * 32})
    bad = _config()
    bad.tiers["pro"] = replace(bad.tiers["pro"], pricing=TierPricing())
    with pytest.raises(ResearchQuoteInvalid, match="pricing authority unavailable"):
        build_research_route_manifest(bad)


def test_quote_token_and_receipt_do_not_contain_key_or_prompt():
    _, token, receipt = _quote()
    assert KEY.decode() not in token
    assert "question" not in token
    assert "question" not in repr(receipt)


def test_quote_binds_one_exact_driver_from_the_canonical_manifest():
    manifest = build_research_route_manifest(_config())
    selected = next(
        row
        for row in manifest.routes
        if row.role == "synthesizer" and row.fallback_index == 1
    )
    driver = {
        "selected_driver_role": selected.role,
        "selected_driver_provider": selected.provider,
        "selected_driver_model": selected.model,
        "selected_driver_pricing_fingerprint": selected.pricing_fingerprint,
    }
    token, issued = issue_research_quote(
        account_id="alice",
        prompt="question",
        research_tier="deep",
        manifest=manifest,
        approved_run_ceiling_usd=2.0,
        issued_at_ms=1_000,
        expires_at_ms=61_000,
        nonce="exact-driver",
        key_id="current",
        signing_key=KEY,
        **driver,
    )
    verified = verify_research_quote(
        token,
        account_id="alice",
        prompt="question",
        research_tier="deep",
        manifest=manifest,
        approved_run_ceiling_usd=2.0,
        now_ms=2_000,
        verification_keys={"current": KEY},
        **driver,
    )
    assert verified == issued
    assert verified.selected_driver_role == "synthesizer"
    assert verified.selected_driver_provider == "fallback"
    assert verified.selected_driver_model == "model-b"

    with pytest.raises(ResearchQuoteInvalid, match="selected_driver"):
        verify_research_quote(
            token,
            account_id="alice",
            prompt="question",
            research_tier="deep",
            manifest=manifest,
            approved_run_ceiling_usd=2.0,
            now_ms=2_000,
            verification_keys={"current": KEY},
        )


def test_quote_rejects_incomplete_or_non_manifest_exact_driver():
    manifest = build_research_route_manifest(_config())
    common = dict(
        account_id="alice",
        prompt="question",
        research_tier="deep",
        manifest=manifest,
        approved_run_ceiling_usd=2.0,
        issued_at_ms=1_000,
        expires_at_ms=61_000,
        nonce="invalid-driver",
        key_id="current",
        signing_key=KEY,
    )
    with pytest.raises(ResearchQuoteInvalid, match="incomplete"):
        issue_research_quote(**common, selected_driver_role="synthesizer")
    with pytest.raises(ResearchQuoteInvalid, match="canonical manifest route"):
        issue_research_quote(
            **common,
            selected_driver_role="synthesizer",
            selected_driver_provider="foreign",
            selected_driver_model="model-z",
            selected_driver_pricing_fingerprint="f" * 64,
        )
