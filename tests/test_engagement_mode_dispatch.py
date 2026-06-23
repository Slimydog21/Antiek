"""Engagement policy wiring on router.dispatch (operator 2026-06-23)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.dispatch import (  # noqa: E402
    DispatchConfig,
    TierConfig,
    TierPricing,
    dispatch,
    register_provider,
    reset_provider_registry,
)
from substrate.dispatch.engagement_mode import (  # noqa: E402
    EngagementPolicy,
    resolve_latency_mode,
    resolve_tier_name,
)
from tests.test_dispatch import _MockOpenAICompatProvider  # noqa: E402


def _speed_tier_config() -> DispatchConfig:
    pricing = TierPricing()
    speed = TierConfig(
        name="speed",
        provider="mock-openai-compat",
        model="glm5",
        max_tokens=8192,
        temperature=0.3,
        context_budget_tokens=128000,
        pricing=pricing,
        fallback=None,
    )
    synthesis = TierConfig(
        name="synthesis",
        provider="mock-openai-compat",
        model="opus",
        max_tokens=16384,
        temperature=0.4,
        context_budget_tokens=256000,
        pricing=pricing,
        fallback=None,
    )
    policy = EngagementPolicy(
        default_mode="autonomous",
        interactive_overrides={"synthesizer": "speed"},
        autonomous_overrides={"synthesizer": "synthesis"},
    )
    return DispatchConfig(
        role_tiers={"synthesizer": "synthesis"},
        tiers={"speed": speed, "synthesis": synthesis},
        engagement_policy=policy,
    )


@pytest.fixture(autouse=True)
def _registry():
    reset_provider_registry()
    yield
    reset_provider_registry()


@pytest.fixture
def _events_dir(tmp_path, monkeypatch):
    d = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(d))
    return d


def test_resolve_latency_mode_explicit_wins():
    policy = EngagementPolicy(
        default_mode="autonomous",
        interactive_overrides={},
        autonomous_overrides={},
    )
    assert resolve_latency_mode("interactive", policy=policy) == "interactive"


def test_resolve_tier_name_interactive_override():
    policy = EngagementPolicy(
        default_mode="autonomous",
        interactive_overrides={"synthesizer": "speed"},
        autonomous_overrides={},
    )
    assert (
        resolve_tier_name("synthesizer", "synthesis", mode="interactive", policy=policy)
        == "speed"
    )
    assert (
        resolve_tier_name("synthesizer", "synthesis", mode="autonomous", policy=policy)
        == "synthesis"
    )


def test_dispatch_interactive_routes_synthesizer_to_speed(_events_dir):
    register_provider(_MockOpenAICompatProvider())
    result = dispatch(
        "draft memo",
        "synthesizer",
        investigation_id="inv-eng-1",
        config=_speed_tier_config(),
        latency_mode="interactive",
    )
    assert result.tier == "speed"
    assert result.model == "glm5"


def test_dispatch_autonomous_keeps_synthesis_tier(_events_dir):
    register_provider(_MockOpenAICompatProvider())
    result = dispatch(
        "draft memo",
        "synthesizer",
        investigation_id="inv-eng-2",
        config=_speed_tier_config(),
        latency_mode="autonomous",
    )
    assert result.tier == "synthesis"
    assert result.model == "opus"


def test_config_yaml_loads_engagement_policy():
    path = Path(__file__).resolve().parents[1] / "substrate" / "dispatch" / "config.yaml"
    cfg = DispatchConfig.from_yaml(path)
    assert cfg.engagement_policy is not None
    assert cfg.engagement_policy.interactive_overrides["synthesizer"] == "speed"
    assert cfg.engagement_policy.autonomous_overrides["decomposer"] == "research_pro"
    assert "research_synthesis" in cfg.tiers