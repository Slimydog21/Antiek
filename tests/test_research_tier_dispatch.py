"""SPR-01 (Living Roadmap) — DeepSeek/MiMo provider registration + the
curated fast/deep research-tier map.

Covers:
  M1 — DeepSeek V4 Pro + MiMo V2.5 Pro register as OpenAI-compat
       providers from env-read keys; UNSET key → NOT registered (no
       crash, no hardcoded key); a MOCKED smoke routes a prompt to each
       and asserts a completion (the live equivalent is operator-bound).
  M3 — the closed fast/deep tier resolves to a single (provider, model)
       in ONE place; selecting a tier changes which provider is targeted;
       closed set + sensible default; unknown values fall back honestly.

The keys-absent case is the case under test (it is the original bug:
``register_default_providers`` silently registers nothing without keys).
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.dispatch import OpenAICompatProvider  # noqa: E402
from substrate.dispatch.providers import register_default_providers  # noqa: E402
from substrate.dispatch.research_tier import (  # noqa: E402
    DEFAULT_RESEARCH_TIER,
    RESEARCH_TIERS,
    normalize_research_tier,
    resolve_research_tier,
)
from substrate.dispatch.router import (  # noqa: E402
    _PROVIDER_REGISTRY,
    get_provider,
    register_provider,
    reset_provider_registry,
)

_ALL_KEYS = (
    "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
    "XIAOMI_API_KEY", "HERMES_API_KEY", "OPENAI_API_KEY",
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """Each test starts from an empty registry AND every provider key
    unset, so a key leaking in from the runner's environment cannot make
    a 'keys-absent' assertion pass for the wrong reason."""
    reset_provider_registry()
    for k in _ALL_KEYS:
        monkeypatch.delenv(k, raising=False)
    yield
    reset_provider_registry()


# ── M1: registration from env, keys-absent path ────────────────────────


def test_keys_absent_registers_nothing():
    """THE case under test (the original bug). With no provider key set,
    register_default_providers must register NOTHING — no crash, no
    hardcoded key sneaking a provider in."""
    registered = register_default_providers(quiet=True)
    assert registered == set()
    assert len(_PROVIDER_REGISTRY) == 0


def test_deepseek_registers_only_when_its_key_present(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-fake")
    registered = register_default_providers(quiet=True)
    assert "deepseek" in registered
    # No other provider rode in on DeepSeek's key.
    assert registered == {"deepseek"}
    assert get_provider("deepseek").name == "deepseek"


def test_mimo_registers_only_when_its_key_present(monkeypatch):
    monkeypatch.setenv("XIAOMI_API_KEY", "sk-mimo-fake")
    registered = register_default_providers(quiet=True)
    assert "xiaomi" in registered
    assert registered == {"xiaomi"}
    assert get_provider("xiaomi").name == "xiaomi"


def test_both_deep_and_fast_register_together(monkeypatch):
    """The two research-tier providers register side-by-side from their
    own env-read keys."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-fake")
    monkeypatch.setenv("XIAOMI_API_KEY", "sk-mimo-fake")
    registered = register_default_providers(quiet=True)
    assert {"deepseek", "xiaomi"} <= registered


def test_mimo_url_does_not_double_v1(monkeypatch):
    """MiMo's base carries /v1, so the adapter's default
    /v1/chat/completions would double up to /v1/v1/... — the same silent
    fallthrough the Hermes regression locks in. The bootstrap gives MiMo
    the /chat/completions override; assert the constructed URL has exactly
    one /v1/."""
    monkeypatch.setenv("XIAOMI_API_KEY", "sk-mimo-fake")
    register_default_providers(quiet=True)
    mimo = get_provider("xiaomi")
    constructed = mimo.base_url + mimo.chat_completions_path
    assert constructed.endswith("/v1/chat/completions")
    assert "/v1/v1/" not in constructed
    assert mimo.chat_completions_path == "/chat/completions"


def test_deepseek_base_url_is_env_overridable(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-fake")
    monkeypatch.setenv(
        "ANTIEK_DEEPSEEK_BASE_URL", "https://proxy.example.com",
    )
    register_default_providers(quiet=True)
    assert get_provider("deepseek").base_url == "https://proxy.example.com"


# ── M1: MOCKED smoke — a prompt routes to each + a completion comes back.
#    (The live-on-prod equivalent is operator-bound: it needs real keys.)


def _mock_client(text: str) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": 10, "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


@pytest.mark.parametrize("provider_name,model,base", [
    ("deepseek", "deepseek-v4-pro", "https://api.deepseek.com"),
    ("xiaomi", "mimo-v2.5-pro", "https://api.mimo.xiaomi.com/v1"),
])
def test_smoke_completion_routes_to_each(provider_name, model, base):
    """MOCKED smoke: a prompt sent to each research-tier provider returns
    a parsed completion. Proves the adapter wiring + response parse for
    DeepSeek V4 Pro and MiMo V2.5 Pro; it does NOT prove a live key works
    (that is operator-bound)."""
    p = OpenAICompatProvider(
        name=provider_name, base_url=base, api_key="mock-key",
        client=_mock_client(f"completion from {model}"),
        chat_completions_path=(
            "/chat/completions" if provider_name == "xiaomi"
            else "/v1/chat/completions"
        ),
    )
    register_provider(p)
    raw = get_provider(provider_name).call(
        model=model, prompt="ping", max_tokens=16, temperature=0.2,
    )
    assert raw.text == f"completion from {model}"
    assert raw.finish_reason == "stop"
    usage = p.normalize_usage(raw.raw_usage)
    assert usage.input_tokens == 10
    assert usage.output_tokens == 5


# ── M3: the curated fast/deep tier map ──────────────────────────────────


def test_research_tiers_is_closed_two_value_set():
    assert set(RESEARCH_TIERS) == {"fast", "deep"}
    assert len(RESEARCH_TIERS) == 2


def test_default_tier_is_deep():
    assert DEFAULT_RESEARCH_TIER == "deep"


def test_fast_maps_to_mimo_deep_maps_to_deepseek():
    """Selecting a tier changes WHICH provider is targeted — the core M3
    behavior. The provider names must match the ones bootstrap registers."""
    fast = resolve_research_tier("fast")
    deep = resolve_research_tier("deep")
    assert fast.provider == "xiaomi"  # MiMo
    assert fast.model == "mimo-v2.5-pro"
    assert deep.provider == "deepseek"  # DeepSeek V4 Pro
    assert deep.model == "deepseek-v4-pro"
    # Different tier ⇒ different provider (the selector actually selects).
    assert fast.provider != deep.provider


def test_every_tier_has_a_why_rationale():
    """Defensibility: the map's WHY must travel with the entry, not rot in
    a comment somewhere else."""
    for t in RESEARCH_TIERS:
        target = resolve_research_tier(t)
        assert target.why and target.why.strip()


def test_resolved_provider_matches_a_bootstrap_registerable_name(monkeypatch):
    """The tier→provider map must point at providers bootstrap can
    actually register — a tier mapping to an unregistered provider name is
    a named failure mode (see handoff). With both keys set, both tier
    targets resolve to a registered provider."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-fake")
    monkeypatch.setenv("XIAOMI_API_KEY", "sk-mimo-fake")
    register_default_providers(quiet=True)
    for t in RESEARCH_TIERS:
        target = resolve_research_tier(t)
        # Does not raise ⇒ the tier's provider is registered.
        assert get_provider(target.provider).name == target.provider


def test_unknown_tier_normalizes_to_default_not_crash():
    """Honest-failure: a malformed/unknown tier falls back to the default
    (a registered, high-value target) rather than raising or routing to an
    arbitrary provider."""
    assert normalize_research_tier("turbo") == DEFAULT_RESEARCH_TIER
    assert normalize_research_tier(None) == DEFAULT_RESEARCH_TIER
    assert normalize_research_tier(123) == DEFAULT_RESEARCH_TIER
    assert resolve_research_tier("nonsense").tier == DEFAULT_RESEARCH_TIER


# ── M3: the route-override genuinely changes the routed provider ────────


class _NamedStubProvider:
    """Minimal provider that records which (name, model) it was called as,
    so a test can prove the override actually re-routed the call."""

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


def _tier_config_for_override():
    """A minimal DispatchConfig: a 'synthesis' tier whose primary is the
    config default ('hermes'), with both override-target providers also
    available so we can prove the swap routes elsewhere."""
    from substrate.dispatch import DispatchConfig, TierConfig

    synth = TierConfig(
        name="synthesis", provider="hermes", model="grok-4.3",
        max_tokens=64, temperature=0.2, context_budget_tokens=1000,
    )
    return DispatchConfig(
        role_tiers={"synthesizer": "synthesis"},
        tiers={"synthesis": synth},
    )


def test_route_override_changes_which_provider_is_called(monkeypatch):
    """The core M3 behavior end-to-end at the router: with no override the
    call routes to the config primary ('hermes'); WITH the override
    resolved from the 'deep' tier it routes to DeepSeek instead — proving
    'selecting a tier changes which provider Hermes routes to'."""
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")  # no event-log I/O
    from substrate.dispatch import dispatch

    hermes = _NamedStubProvider("hermes")
    deepseek = _NamedStubProvider("deepseek")
    register_provider(hermes)
    register_provider(deepseek)
    config = _tier_config_for_override()

    # No override → config primary (hermes).
    r1 = dispatch(
        "q", "synthesizer", investigation_id="inv-x", config=config,
    )
    assert r1.provider == "hermes"
    assert hermes.calls and not deepseek.calls

    # Override resolved from the 'deep' tier → DeepSeek V4 Pro.
    target = resolve_research_tier("deep")
    r2 = dispatch(
        "q", "synthesizer", investigation_id="inv-x", config=config,
        provider_override=target.provider, model_override=target.model,
    )
    assert r2.provider == "deepseek"
    assert r2.model == "deepseek-v4-pro"
    assert deepseek.calls == ["deepseek-v4-pro"]


def test_partial_override_is_ignored_not_guessed(monkeypatch):
    """A half-specified override (provider but no model) is a caller bug;
    the router refuses to guess the missing half and uses the config
    primary."""
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")
    from substrate.dispatch import dispatch

    hermes = _NamedStubProvider("hermes")
    register_provider(hermes)
    config = _tier_config_for_override()
    r = dispatch(
        "q", "synthesizer", investigation_id="inv-x", config=config,
        provider_override="deepseek",  # no model_override
    )
    assert r.provider == "hermes"  # override ignored


def test_override_falls_back_when_override_provider_unregistered(monkeypatch):
    """If the override provider isn't registered, the call falls through
    the SAME fallback chain as a normal primary failure — the override is
    a preference, not a single point of failure."""
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")
    from substrate.dispatch import DispatchConfig, TierConfig, dispatch

    # Primary 'synthesis' overridden to an unregistered provider, with a
    # registered 'hermes' fallback.
    fallback = TierConfig(
        name="synthesis__fallback", provider="hermes", model="grok-4.3",
        max_tokens=64, temperature=0.2, context_budget_tokens=1000,
    )
    synth = TierConfig(
        name="synthesis", provider="hermes", model="grok-4.3",
        max_tokens=64, temperature=0.2, context_budget_tokens=1000,
        fallback=fallback,
    )
    config = DispatchConfig(
        role_tiers={"synthesizer": "synthesis"},
        tiers={"synthesis": synth},
    )
    register_provider(_NamedStubProvider("hermes"))
    # 'deepseek' deliberately NOT registered.
    r = dispatch(
        "q", "synthesizer", investigation_id="inv-x", config=config,
        provider_override="deepseek", model_override="deepseek-v4-pro",
    )
    # Override primary raised KeyError (unregistered) → fell back to hermes.
    assert r.provider == "hermes"
    assert r.fallback_chain_index == 1


# ── M3 SEAM: a recorded research_tier → the synthesizer dispatch ───────────
#    The findings above each prove ONE link in the chain:
#      • test_fast_maps_to_mimo_deep_maps_to_deepseek  → the MAP resolves.
#      • test_route_override_changes_which_provider_is_called → the ROUTER
#        honors an override.
#      • tests/test_investigation_endpoints.py             → the API RECORDS
#        the tier on the start event.
#    What was asserted only by inspection is the WIRE between them: that the
#    synthesizer's _research_tier_override reads the persisted tier off the
#    real start event and turns it into the (provider, model) the dispatch
#    actually routes to. These tests exercise that seam directly through
#    interfaces.research.api.synthesizer._dispatch_once — the production
#    call site — asserting the dispatched provider/model, not merely
#    no-crash.


class _StartEventStub:
    """Stands in for the synthesize.requested Event that _dispatch_once
    receives. _dispatch_once touches exactly two attributes:
    ``investigation_id`` (which the override reads the trajectory for) and
    ``event_id`` (the dispatch parent). A full Event with its discriminated
    payload union would add nothing the seam exercises."""

    def __init__(self, investigation_id: str):
        self.investigation_id = investigation_id
        self.event_id = f"evt-{investigation_id}"


def _emit_start_with_tier(investigation_id: str, tier: str) -> None:
    """Persist a REAL INVESTIGATION_START_REQUESTED event carrying the
    chosen research_tier — the same shape the POST /investigations path
    writes — so the synthesizer's override reads it back off the trajectory
    exactly as it would in production."""
    from substrate.event_log import emit_typed
    from substrate.schemas import InvestigationStartRequestedPayload

    emit_typed(
        investigation_id,
        InvestigationStartRequestedPayload(
            question="seam test", context="", topic_slug=None,
            max_sub_questions=4, research_tier=tier,  # type: ignore[arg-type]
        ),
        role="operator",
    )


def _synthesizer_config_with_hermes_primary():
    """A DispatchConfig whose synthesizer primary is 'hermes' (the config
    default), so a test can tell the difference between 'the override
    re-routed' (→ deepseek/xiaomi) and 'the override was inert, config
    primary used' (→ hermes)."""
    from substrate.dispatch import DispatchConfig, TierConfig

    synth = TierConfig(
        name="synthesis", provider="hermes", model="grok-4.3",
        max_tokens=64, temperature=0.2, context_budget_tokens=1000,
    )
    return DispatchConfig(
        role_tiers={"synthesizer": "synthesis"},
        tiers={"synthesis": synth},
    )


@pytest.fixture
def _seam_events_dir(tmp_path, monkeypatch):
    """Route event I/O to a temp dir so the emitted start event is readable
    by the override's trajectory() call, isolated from any real store."""
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    yield


def test_seam_recorded_deep_tier_dispatches_to_deepseek(
    monkeypatch, _seam_events_dir,
):
    """SEAM case 1: a recorded research_tier='deep' + DeepSeek registered →
    the synthesizer dispatch actually targets deepseek/deepseek-v4-pro
    (NOT the config's 'hermes' primary). Proves the recorded tier flows all
    the way through _research_tier_override into the routed call."""
    from interfaces.research.api import synthesizer as synth_mod
    import substrate.dispatch.router as router

    monkeypatch.setattr(
        router.DispatchConfig, "from_yaml",
        classmethod(lambda cls, path: _synthesizer_config_with_hermes_primary()),
    )
    hermes = _NamedStubProvider("hermes")
    deepseek = _NamedStubProvider("deepseek")
    register_provider(hermes)
    register_provider(deepseek)

    _emit_start_with_tier("inv-seam-deep", "deep")
    text, policy_id = synth_mod._dispatch_once(
        "synthesize this", _StartEventStub("inv-seam-deep"),
    )
    # The override re-routed the synthesizer to DeepSeek V4 Pro.
    assert policy_id == "deepseek/deepseek-v4-pro"
    assert deepseek.calls == ["deepseek-v4-pro"]
    assert not hermes.calls  # config primary was displaced by the live tier
    assert text == "deepseek:deepseek-v4-pro"


def test_seam_recorded_fast_tier_dispatches_to_mimo(
    monkeypatch, _seam_events_dir,
):
    """SEAM case 2: a recorded research_tier='fast' + MiMo registered →
    the synthesizer dispatch targets xiaomi/mimo-v2.5-pro."""
    from interfaces.research.api import synthesizer as synth_mod
    import substrate.dispatch.router as router

    monkeypatch.setattr(
        router.DispatchConfig, "from_yaml",
        classmethod(lambda cls, path: _synthesizer_config_with_hermes_primary()),
    )
    hermes = _NamedStubProvider("hermes")
    mimo = _NamedStubProvider("xiaomi")
    register_provider(hermes)
    register_provider(mimo)

    _emit_start_with_tier("inv-seam-fast", "fast")
    text, policy_id = synth_mod._dispatch_once(
        "synthesize this", _StartEventStub("inv-seam-fast"),
    )
    assert policy_id == "xiaomi/mimo-v2.5-pro"
    assert mimo.calls == ["mimo-v2.5-pro"]
    assert not hermes.calls
    assert text == "xiaomi:mimo-v2.5-pro"


def test_seam_recorded_tier_provider_unregistered_uses_config_primary(
    monkeypatch, _seam_events_dir,
):
    """SEAM case 3 — THE regression guard, proved directly: a recorded tier
    whose provider is NOT registered must NOT displace the config's own
    primary/fallback. _research_tier_override returns (None, None) in that
    case, so the synthesizer dispatches through the config primary ('hermes')
    unchanged — a research-tier choice never re-routes a working config
    route onto an absent provider (and the schema's default 'deep' never
    silently re-routes every run onto an unregistered DeepSeek key)."""
    from interfaces.research.api import synthesizer as synth_mod
    import substrate.dispatch.router as router

    monkeypatch.setattr(
        router.DispatchConfig, "from_yaml",
        classmethod(lambda cls, path: _synthesizer_config_with_hermes_primary()),
    )
    hermes = _NamedStubProvider("hermes")
    register_provider(hermes)
    # 'deepseek' (the 'deep' tier's provider) deliberately NOT registered.

    # Prove the override itself declines to override (the seam's decision).
    assert synth_mod._research_tier_override.__name__  # symbol exists
    _emit_start_with_tier("inv-seam-absent", "deep")
    prov, model = synth_mod._research_tier_override("inv-seam-absent")
    assert (prov, model) == (None, None)

    # And prove the downstream effect: the synthesizer dispatch lands on the
    # config primary, NOT on an absent deepseek that would have failed over.
    text, policy_id = synth_mod._dispatch_once(
        "synthesize this", _StartEventStub("inv-seam-absent"),
    )
    assert policy_id == "hermes/grok-4.3"
    assert hermes.calls == ["grok-4.3"]
    assert text == "hermes:grok-4.3"
