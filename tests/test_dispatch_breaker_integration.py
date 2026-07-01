"""nygard SPR-04 — breaker ↔ router integration: an OPEN provider is skipped
fast and the tier-fallback chain carries the call (no retry, no new control flow).
"""

from __future__ import annotations

import pytest

import substrate.dispatch.router as router
from substrate.dispatch.base import (
    NormalizedUsage,
    ProviderError,
    RawProviderResponse,
)
from substrate.dispatch.breaker import CircuitBreaker
from substrate.dispatch.router import (
    DispatchConfig,
    TierConfig,
    TierPricing,
    dispatch,
    register_provider,
    reset_provider_registry,
)


class _StubProvider:
    def __init__(self, name: str, *, fail: bool) -> None:
        self.name = name
        self.fail = fail
        self.calls = 0

    def call(self, *, model, prompt, max_tokens, temperature):
        self.calls += 1
        if self.fail:
            raise ProviderError(
                f"{self.name}: injected HTTP 503",
                provider=self.name, model=model, latency_ms=1, retryable=True,
            )
        return RawProviderResponse(
            text="ok", raw_usage={}, finish_reason="end_turn", latency_ms=1,
        )

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(input_tokens=0, output_tokens=0)


def _config() -> DispatchConfig:
    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    backup = TierConfig(
        name="pro", provider="backup", model="m", max_tokens=256,
        temperature=0.0, context_budget_tokens=128_000, pricing=pricing,
        fallback=None,
    )
    primary = TierConfig(
        name="pro", provider="flaky", model="m", max_tokens=256,
        temperature=0.0, context_budget_tokens=128_000, pricing=pricing,
        fallback=backup,
    )
    return DispatchConfig(role_tiers={"synthesizer": "pro"}, tiers={"pro": primary})


@pytest.fixture
def wired(monkeypatch):
    reset_provider_registry()
    flaky = _StubProvider("flaky", fail=True)
    backup = _StubProvider("backup", fail=False)
    register_provider(flaky)
    register_provider(backup)
    # A private breaker with a low threshold + no cooldown window, so the test is
    # deterministic and independent of the process-wide default_breaker.
    brk = CircuitBreaker(failure_threshold=2, cooldown_s=10_000, clock=lambda: 0.0)
    monkeypatch.setattr(router, "default_breaker", brk)
    try:
        yield flaky, backup, brk
    finally:
        reset_provider_registry()


def _one(cfg):
    return dispatch("p", "synthesizer", investigation_id="inv", config=cfg)


def test_open_provider_is_skipped_and_fallback_carries(wired):
    flaky, backup, brk = wired
    cfg = _config()

    # Calls 1 & 2: flaky is tried (and fails) → fallback 'backup' succeeds.
    r1 = _one(cfg)
    assert r1.provider == "backup"
    r2 = _one(cfg)
    assert r2.provider == "backup"
    assert flaky.calls == 2  # flaky was actually called twice
    assert brk.is_open("flaky") is True  # 2 failures == threshold → OPEN

    # Call 3: flaky's breaker is OPEN → it is SKIPPED (its .call is NOT invoked)
    # and 'backup' still carries the request.
    r3 = _one(cfg)
    assert r3.provider == "backup"
    assert flaky.calls == 2  # unchanged — the open provider was skipped, not called
    assert backup.calls == 3


def test_success_keeps_healthy_provider_closed(wired):
    _flaky, backup, brk = wired
    # A config whose PRIMARY is the healthy provider — it should never open.
    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    tier = TierConfig(
        name="pro", provider="backup", model="m", max_tokens=256,
        temperature=0.0, context_budget_tokens=128_000, pricing=pricing,
        fallback=None,
    )
    cfg = DispatchConfig(role_tiers={"synthesizer": "pro"}, tiers={"pro": tier})
    for _ in range(5):
        assert _one(cfg).provider == "backup"
    assert brk.is_open("backup") is False
    assert brk.failure_count("backup") == 0
