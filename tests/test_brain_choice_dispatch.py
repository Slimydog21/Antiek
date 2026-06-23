"""Brain toggle (glm vs premium) on dispatch routing."""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.dispatch import (
    DispatchConfig,
    TierConfig,
    TierPricing,
    dispatch,
    register_provider,
    reset_provider_registry,
)
from substrate.dispatch.brain_choice import normalize_brain_choice
from substrate.dispatch.engagement_mode import EngagementPolicy, resolve_tier_name
from substrate.event_log import trajectory
from substrate.schemas import ActionType, DispatchCallPayload, Event
from tests.test_dispatch import _MockOpenAICompatProvider


def _config_with_engagement() -> DispatchConfig:
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


def test_normalize_brain_defaults_to_glm():
    assert normalize_brain_choice(None) == "glm"
    assert normalize_brain_choice("PREMIUM") == "premium"


def test_premium_interactive_keeps_synthesis_tier():
    policy = EngagementPolicy(
        default_mode="autonomous",
        interactive_overrides={"synthesizer": "speed"},
        autonomous_overrides={},
    )
    tier = resolve_tier_name(
        "synthesizer",
        "synthesis",
        mode="interactive",
        policy=policy,
        brain="premium",
    )
    assert tier == "synthesis"


def test_dispatch_premium_brain_uses_opus_model(_events_dir):
    register_provider(_MockOpenAICompatProvider())
    result = dispatch(
        "memo",
        "synthesizer",
        investigation_id="inv-brain-1",
        config=_config_with_engagement(),
        latency_mode="interactive",
        brain="premium",
    )
    assert result.tier == "synthesis"
    assert result.model == "opus"


def test_dispatch_glm_brain_uses_speed_tier(_events_dir):
    register_provider(_MockOpenAICompatProvider())
    result = dispatch(
        "memo",
        "synthesizer",
        investigation_id="inv-brain-2",
        config=_config_with_engagement(),
        latency_mode="interactive",
        brain="glm",
    )
    assert result.tier == "speed"
    assert result.model == "glm5"


def _dispatch_call_from_trajectory(investigation_id: str) -> DispatchCallPayload:
    rows = [
        r
        for r in trajectory(investigation_id)
        if r.get("action_type") == ActionType.DISPATCH_CALL.value
    ]
    assert rows, "expected at least one dispatch.call in trajectory"
    event = Event.model_validate(rows[-1])
    assert isinstance(event.payload, DispatchCallPayload)
    return event.payload


def test_trajectory_stamps_speed_tier_for_glm_interactive_synthesizer(_events_dir):
    register_provider(_MockOpenAICompatProvider())
    dispatch(
        "memo",
        "synthesizer",
        investigation_id="inv-traj-glm",
        config=_config_with_engagement(),
        latency_mode="interactive",
        brain="glm",
    )
    payload = _dispatch_call_from_trajectory("inv-traj-glm")
    assert payload.tier == "speed"
    assert payload.model == "glm5"


def test_trajectory_stamps_synthesis_tier_for_premium_interactive(_events_dir):
    register_provider(_MockOpenAICompatProvider())
    dispatch(
        "memo",
        "synthesizer",
        investigation_id="inv-traj-prem",
        config=_config_with_engagement(),
        latency_mode="interactive",
        brain="premium",
    )
    payload = _dispatch_call_from_trajectory("inv-traj-prem")
    assert payload.tier == "synthesis"
    assert payload.model == "opus"


def test_deliverable_speed_preference_on_autonomous_routes_synthesizer_to_speed():
    policy = EngagementPolicy(
        default_mode="autonomous",
        interactive_overrides={"synthesizer": "speed"},
        autonomous_overrides={"synthesizer": "synthesis"},
    )
    tier = resolve_tier_name(
        "synthesizer",
        "synthesis",
        mode="autonomous",
        policy=policy,
        brain="glm",
        deliverable_speed_preference=True,
    )
    assert tier == "speed"


def test_dispatch_deliverable_speed_on_autonomous(_events_dir):
    register_provider(_MockOpenAICompatProvider())
    result = dispatch(
        "memo",
        "synthesizer",
        investigation_id="inv-speed-pref",
        config=_config_with_engagement(),
        latency_mode="autonomous",
        brain="glm",
        deliverable_speed_preference=True,
    )
    assert result.tier == "speed"
    assert result.model == "glm5"