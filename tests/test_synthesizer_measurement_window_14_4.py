"""§14.4 measurement-window regression — the SCHEMA-DEFAULT research tier
must never displace the Opus-pinned synthesizer.

Why this test exists (the fake-green it replaces):
``test_research_tier_dispatch.py`` asserts deepseek is the DESIRED deep-tier
target against a synthetic config, and *no* test loaded the real
``config.yaml`` or exercised the synthesizer's ``_research_tier_override``
read path. So the silent displacement shipped green — the moment
``DEEPSEEK_API_KEY`` is set, a schema-default ``research_tier="deep"`` persisted
on every investigation start would override the §14.4-pinned
``openrouter/anthropic/claude-opus-4.7`` synthesizer primary with DeepSeek,
corrupting the Sprint-20 Opus-vs-Grok measurement.

The fix (two sites): the request model (``app.InvestigationStartRequest``) and
the persisted payload (``InvestigationStartRequestedPayload``) now default
``research_tier`` to ``None``. A tier is recorded — and the synthesizer
override fires — ONLY on an explicit operator pick. These tests load the REAL
config and drive the REAL override path with DeepSeek registered.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.app import InvestigationStartRequest  # noqa: E402
from interfaces.research.api.synthesizer import _research_tier_override  # noqa: E402
from substrate.dispatch.providers import register_default_providers  # noqa: E402
from substrate.dispatch.router import reset_provider_registry  # noqa: E402
from substrate.event_log import emit_typed  # noqa: E402
from substrate.schemas import InvestigationStartRequestedPayload  # noqa: E402

_CONFIG = Path(_REPO) / "substrate" / "dispatch" / "config.yaml"
_ALL_KEYS = (
    "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
    "XIAOMI_API_KEY", "HERMES_API_KEY", "OPENAI_API_KEY",
)


@pytest.fixture
def events_dir(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-14-4-test-")
    ed = os.path.join(tmp, "events")
    os.makedirs(ed, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ed)
    yield ed


@pytest.fixture
def deepseek_live(monkeypatch):
    """Register DeepSeek (and only DeepSeek) — the displacement precondition.
    If the tier override is going to fire wrongly, this is when it would."""
    reset_provider_registry()
    for k in _ALL_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-fake")
    registered = register_default_providers(quiet=True)
    assert "deepseek" in registered, "precondition: DeepSeek must be live"
    yield
    reset_provider_registry()


def test_real_config_pins_synthesizer_to_opus():
    """The §14.4 invariant itself: the REAL config.yaml routes the synthesizer
    to openrouter/anthropic/claude-opus-4.7. Catches config drift."""
    cfg = yaml.safe_load(_CONFIG.read_text())
    syn = cfg["tiers"]["synthesis"]
    assert syn["provider"] == "openrouter"
    assert syn["model"] == "anthropic/claude-opus-4.7"


def test_default_investigation_does_not_displace_opus(events_dir, deepseek_live):
    """A default investigation records NO tier → the synthesizer override
    returns (None, None) → synthesis routes through the config-pinned Opus
    primary even though DeepSeek is live. This is the displacement fix."""
    emit_typed(
        "inv-default-14-4",
        InvestigationStartRequestedPayload(question="A cold question?"),
        role="operator",
    )
    assert _research_tier_override("inv-default-14-4") == (None, None)


def test_explicit_deep_still_overrides_to_deepseek(events_dir, deepseek_live):
    """An EXPLICIT operator 'deep' pick still records + overrides — the fix
    scopes off the schema default, it does not remove the feature."""
    emit_typed(
        "inv-explicit-deep",
        InvestigationStartRequestedPayload(
            question="A cold question?", research_tier="deep"
        ),
        role="operator",
    )
    assert _research_tier_override("inv-explicit-deep") == (
        "deepseek",
        "deepseek-v4-pro",
    )


def test_start_request_model_defaults_tier_to_none():
    """Write-site half of the fix: the API request no longer coerces an
    un-picked tier to 'deep'."""
    assert InvestigationStartRequest(question="A cold question?").research_tier is None


def test_start_payload_defaults_tier_to_none():
    """Persist-site half: the event payload no longer defaults to 'deep', so
    a default run carries a falsy tier the override skips."""
    assert InvestigationStartRequestedPayload(question="A cold question?").research_tier is None
