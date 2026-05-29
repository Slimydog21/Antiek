"""SPR-01 (Foundation) M3 — the §14.4 synthesis-pin regression guard.

THE non-vacuous regression test. Unlike the seam tests in
``test_research_tier_dispatch.py`` (which monkeypatch a synthetic
hermes-primary config), this one loads the REAL
``substrate/dispatch/config.yaml`` — the same file production routes
through — sets ``DEEPSEEK_API_KEY`` (the literal "turn the AI on"
deploy), drives the DEFAULT-deep synthesizer dispatch path, and asserts
the resolved synthesis primary stays ``openrouter / anthropic/
claude-opus-4.7``.

WHY a separate file from the synthetic-config seam tests: the defect that
hid here for a whole sprint was a FAKE-GREEN test that asserted DeepSeek
as *desired* against a synthetic ``'hermes'`` config and never loaded the
real ``config.yaml``. A guard that does not load the real pin cannot
catch a regression of the real pin. This test is proved non-vacuous in
the SPR-01 handoff: it FAILS on the pre-fix code (schema-default "deep"
displaces Opus once DeepSeek is registered) and PASSES on the fix.

The test asserts on RESOLUTION, never a live API call: every provider in
the chain is a recording stub, so no network traffic leaves the process
even though DEEPSEEK_API_KEY is set.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.dispatch.router import (  # noqa: E402
    _PROVIDER_REGISTRY,
    register_provider,
    reset_provider_registry,
)

# The real config — the one production loads. Not a fixture, not an inline
# dict. If this path or its synthesis pin ever moves, this test must be the
# thing that breaks.
_REAL_CONFIG_PATH = Path(_REPO) / "substrate" / "dispatch" / "config.yaml"

_ALL_KEYS = (
    "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
    "XIAOMI_API_KEY", "HERMES_API_KEY", "OPENAI_API_KEY",
)


class _RecordingStubProvider:
    """Records the (name, model) it was called as so the test can assert
    WHICH provider/model the router resolved to — without any network I/O.
    Stands in for every real provider in the synthesis fallback chain."""

    def __init__(self, name: str):
        self.name = name
        self.calls: list[str] = []

    def call(self, *, model, prompt, max_tokens, temperature):
        from substrate.dispatch import RawProviderResponse
        self.calls.append(model)
        return RawProviderResponse(
            text=f"{self.name}:{model}", raw_usage={}, finish_reason="stop",
            latency_ms=1,
        )

    def normalize_usage(self, raw_usage):
        from substrate.dispatch import NormalizedUsage
        return NormalizedUsage(input_tokens=0, output_tokens=0)


@pytest.fixture(autouse=True)
def _clean_registry_and_env(monkeypatch):
    """Start from an empty registry and no provider keys, so nothing leaks
    in from the runner's environment."""
    reset_provider_registry()
    for k in _ALL_KEYS:
        monkeypatch.delenv(k, raising=False)
    yield
    reset_provider_registry()


@pytest.fixture
def _events_dir(tmp_path, monkeypatch):
    """Isolate event I/O to a temp dir so the emitted start event is read
    back by the override's ``trajectory()`` call, not from any real store."""
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    yield


def _register_real_synthesis_chain_as_stubs():
    """Register recording stubs for every provider the REAL synthesis tier
    references — ``openrouter`` (primary) and ``hermes`` (fallback) — plus
    ``deepseek`` (the 'deep' research-tier provider). All three are LIVE in
    the registry, so the test exercises the keys-PRESENT case: the §14.4
    guard must hold even though deepseek is fully registered."""
    openrouter = _RecordingStubProvider("openrouter")
    hermes = _RecordingStubProvider("hermes")
    deepseek = _RecordingStubProvider("deepseek")
    register_provider(openrouter)
    register_provider(hermes)
    register_provider(deepseek)
    return openrouter, hermes, deepseek


def _emit_start(investigation_id: str, **kwargs) -> None:
    """Emit a real INVESTIGATION_START_REQUESTED event through the same
    schema the POST /investigations path uses. ``kwargs`` lets a caller set
    (or omit) ``research_tier`` to exercise the default / explicit cases."""
    from substrate.event_log import emit_typed
    from substrate.schemas import InvestigationStartRequestedPayload

    emit_typed(
        investigation_id,
        InvestigationStartRequestedPayload(
            question="pin test", context="", topic_slug=None,
            max_sub_questions=4, **kwargs,
        ),
        role="operator",
    )


# ── THE regression guard ────────────────────────────────────────────────


def test_default_deep_synthesizer_stays_pinned_to_opus_with_deepseek_live(
    monkeypatch, _events_dir,
):
    """§14.4 — the load-bearing assertion.

    A DEFAULT investigation (no explicit research tier) + DEEPSEEK_API_KEY
    set + the REAL config.yaml loaded → the synthesizer dispatch resolves to
    the config-pinned ``openrouter / anthropic/claude-opus-4.7``, NOT to
    deepseek. This is exactly the "turn the AI on" deploy that voided §14.4
    before the fix.
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-dummy")  # keys-PRESENT
    from interfaces.research.api import synthesizer as synth_mod

    openrouter, hermes, deepseek = _register_real_synthesis_chain_as_stubs()
    # Sanity: the keys-present condition is genuinely true.
    assert "deepseek" in _PROVIDER_REGISTRY

    # A DEFAULT investigation: research_tier omitted ⇒ schema default (None).
    _emit_start("inv-default-deep")

    class _Evt:
        investigation_id = "inv-default-deep"
        event_id = "evt-inv-default-deep"

    # The override declines to swap the synthesizer's pin.
    prov, model = synth_mod._research_tier_override("inv-default-deep")
    assert (prov, model) == (None, None)

    # And the dispatch — through the REAL config — lands on the Opus pin.
    text, policy_id = synth_mod._dispatch_once("synthesize this", _Evt())
    assert policy_id == "openrouter/anthropic/claude-opus-4.7", policy_id
    assert openrouter.calls == ["anthropic/claude-opus-4.7"]
    assert not deepseek.calls  # the live deepseek key did NOT displace Opus
    assert not hermes.calls    # fallback not reached; primary succeeded
    assert text == "openrouter:anthropic/claude-opus-4.7"


def test_explicit_deep_also_stays_pinned_to_opus(monkeypatch, _events_dir):
    """§14.4 covers operator-EXPLICIT "deep" too: during the window the pin
    does not yield to a per-role deep override. (The research lane still gets
    deepseek — that is asserted in test_research_tier_dispatch.py; here we
    only guard the synthesis voice.)"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-dummy")
    from interfaces.research.api import synthesizer as synth_mod

    openrouter, hermes, deepseek = _register_real_synthesis_chain_as_stubs()
    _emit_start("inv-explicit-deep", research_tier="deep")

    class _Evt:
        investigation_id = "inv-explicit-deep"
        event_id = "evt-inv-explicit-deep"

    prov, model = synth_mod._research_tier_override("inv-explicit-deep")
    assert (prov, model) == (None, None)

    text, policy_id = synth_mod._dispatch_once("synthesize this", _Evt())
    assert policy_id == "openrouter/anthropic/claude-opus-4.7", policy_id
    assert not deepseek.calls


def test_explicit_fast_also_stays_pinned_to_opus(monkeypatch, _events_dir):
    """§14.4 — the sharpen-round completion. An operator who explicitly
    chose "fast" still gets Opus for the synthesis VOICE during the window;
    the fast lane only routes the RESEARCH-RUNNER to MiMo (asserted in
    test_research_tier_dispatch.py::test_explicit_fast_keeps_research_lane_
    but_not_synthesizer). Both the fast PROVIDER (xiaomi) and deepseek are
    live here, so the test fails if the guard ever lets a non-default tier
    displace synthesis."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-dummy")
    monkeypatch.setenv("XIAOMI_API_KEY", "sk-mimo-dummy")
    from interfaces.research.api import synthesizer as synth_mod

    openrouter, hermes, deepseek = _register_real_synthesis_chain_as_stubs()
    xiaomi = _RecordingStubProvider("xiaomi")
    register_provider(xiaomi)  # the 'fast' tier provider IS live
    _emit_start("inv-explicit-fast", research_tier="fast")

    class _Evt:
        investigation_id = "inv-explicit-fast"
        event_id = "evt-inv-explicit-fast"

    prov, model = synth_mod._research_tier_override("inv-explicit-fast")
    assert (prov, model) == (None, None)

    text, policy_id = synth_mod._dispatch_once("synthesize this", _Evt())
    assert policy_id == "openrouter/anthropic/claude-opus-4.7", policy_id
    assert openrouter.calls == ["anthropic/claude-opus-4.7"]
    assert not xiaomi.calls   # the live MiMo key did NOT displace Opus
    assert not deepseek.calls


def test_legacy_run_no_tier_recorded_stays_pinned(monkeypatch, _events_dir):
    """Edge case — a legacy start event written before the field existed
    (no research_tier key at all): the override returns (None, None) and the
    synthesizer keeps the Opus pin. Honest-absent, never fabricated."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-dummy")
    from interfaces.research.api import synthesizer as synth_mod
    from substrate.event_log import log_event
    from substrate.schemas import ActionType

    openrouter, hermes, deepseek = _register_real_synthesis_chain_as_stubs()
    # Raw pre-field row — no research_tier key on the payload.
    log_event(
        "inv-legacy-pin",
        ActionType.INVESTIGATION_START_REQUESTED.value,
        payload={
            "action_type": ActionType.INVESTIGATION_START_REQUESTED.value,
            "question": "legacy", "context": "", "topic_slug": None,
            "max_sub_questions": 4,
        },
        role="operator",
    )

    prov, model = synth_mod._research_tier_override("inv-legacy-pin")
    assert (prov, model) == (None, None)

    class _Evt:
        investigation_id = "inv-legacy-pin"
        event_id = "evt-inv-legacy-pin"

    _text, policy_id = synth_mod._dispatch_once("synthesize this", _Evt())
    assert policy_id == "openrouter/anthropic/claude-opus-4.7", policy_id


def test_deepseek_key_absent_stays_pinned(monkeypatch, _events_dir):
    """Edge case — DeepSeek key ABSENT (the pre-deploy common case): the
    synthesizer is on the Opus pin for the obvious reason (deepseek not
    registered) too. This is the case the OLD guard already handled; we keep
    it so the fix is proven to not REGRESS the previously-covered path."""
    # DEEPSEEK_API_KEY intentionally NOT set.
    from interfaces.research.api import synthesizer as synth_mod

    openrouter = _RecordingStubProvider("openrouter")
    hermes = _RecordingStubProvider("hermes")
    register_provider(openrouter)
    register_provider(hermes)
    assert "deepseek" not in _PROVIDER_REGISTRY

    _emit_start("inv-key-absent")  # default tier

    class _Evt:
        investigation_id = "inv-key-absent"
        event_id = "evt-inv-key-absent"

    _text, policy_id = synth_mod._dispatch_once("synthesize this", _Evt())
    assert policy_id == "openrouter/anthropic/claude-opus-4.7", policy_id
