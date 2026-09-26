"""``dispatch(operator_lineup=False)`` skips the operator's AI Role Lineup.

Owner-paid callers (``interfaces/research/api/owner_byot_dispatch.py``) build
an exact config whose tier primary IS the owner's keyed rung, with no fallback.
The router's lineup consult fires whenever the caller passes no explicit
override, so an operator assignment for the role silently swapped that primary
for the house provider: the house adapter was called and paid on an owner-paid
dispatch. The opt-out keeps the primary, and because no override is applied the
route receipt records none — an owner's pinned route must not read as an
``operator_override`` in the audit trail.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from substrate.dispatch import (
    NormalizedUsage,
    RawProviderResponse,
    lineup_override,
    register_provider,
    reset_provider_registry,
    router,
)
from substrate.dispatch.router import DispatchConfig, TierConfig, TierPricing, dispatch
from substrate.schemas.events import RouteReceipt


class _Provider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model: str, prompt: str, max_tokens: int, temperature: float) -> RawProviderResponse:
        self.calls.append({"model": model, "prompt": prompt})
        return RawProviderResponse(
            text=f"{self.name} answer",
            raw_usage={"input_tokens": 1, "output_tokens": 1},
            finish_reason="stop",
            latency_ms=1,
            request_id=f"{self.name}-req",
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(
            input_tokens=int(raw_usage["input_tokens"]),
            output_tokens=int(raw_usage["output_tokens"]),
        )


def _config() -> DispatchConfig:
    # The owner-paid shape: the primary is the owner's rung and there is no fallback.
    tier = TierConfig("pro", "owner-key", "owner-model", 100, 0.1, 1000, TierPricing(), None)
    return DispatchConfig({"thought_partner": "pro"}, {"pro": tier})


@pytest.fixture(autouse=True)
def _providers() -> Any:
    reset_provider_registry()
    owner = _Provider("owner-key")
    house = _Provider("house")
    register_provider(owner)
    register_provider(house)
    yield owner, house
    reset_provider_registry()


@pytest.fixture
def house_lineup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "lineup.json"
    path.write_text(json.dumps({
        "owners": {"__operator__": {
            "general": {},
            "advanced": {"thought_partner": {"provider_id": "house", "model_id": "house-model"}},
        }},
    }), encoding="utf-8")
    monkeypatch.setenv("ANTIEK_LINEUP_PATH", str(path))
    lineup_override._registry_cache.clear()
    # Control: the registry resolves this role to the house provider. Without
    # this, every assertion below would pass because there was no lineup at all.
    resolved = lineup_override.effective_override_for_dispatch_role("thought_partner")
    assert resolved is not None and resolved.provider_id == "house"


@pytest.fixture
def receipts(monkeypatch: pytest.MonkeyPatch) -> list[RouteReceipt | None]:
    captured: list[RouteReceipt | None] = []

    def _record(**kwargs: Any) -> str:
        captured.append(kwargs.get("route_receipt"))
        return "evt-test"

    monkeypatch.setattr(router, "_emit_dispatch_call", _record)
    return captured


def test_lineup_applies_by_default(
    _providers: Any, house_lineup: None, receipts: list[RouteReceipt | None],
) -> None:
    """Control for the opt-out: with the default, the lineup DOES re-route."""
    owner, house = _providers
    result = dispatch("p", "thought_partner", investigation_id="inv", config=_config())
    assert result.provider == "house"
    assert len(house.calls) == 1 and owner.calls == []
    receipt = receipts[-1]
    assert receipt is not None
    assert receipt.override == "manual"
    assert receipt.selected.reason_code == "operator_override"


def test_opt_out_keeps_the_primary_and_records_no_override(
    _providers: Any, house_lineup: None, receipts: list[RouteReceipt | None],
) -> None:
    owner, house = _providers
    result = dispatch(
        "p", "thought_partner", investigation_id="inv", config=_config(), operator_lineup=False,
    )
    assert (result.provider, result.model) == ("owner-key", "owner-model")
    assert house.calls == [], "the operator lineup re-routed an opted-out dispatch"
    assert len(owner.calls) == 1
    assert result.fallback_chain_index == 0
    receipt = receipts[-1]
    assert receipt is not None
    assert receipt.override == "none"
    assert receipt.objective == "balanced"
    assert receipt.selected.reason_code == "primary"


def test_explicit_caller_override_still_wins_when_opted_out(
    _providers: Any, house_lineup: None,
) -> None:
    """The switch governs the registry consult only; precedence 1 is untouched."""
    owner, house = _providers
    result = dispatch(
        "p", "thought_partner", investigation_id="inv", config=_config(),
        provider_override="house", model_override="house-model", operator_lineup=False,
    )
    assert result.provider == "house"
    assert len(house.calls) == 1 and owner.calls == []
