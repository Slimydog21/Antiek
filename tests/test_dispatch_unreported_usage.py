"""A paid provider response that omits its usage block is not a free call.

Audit C06: ``OpenAICompatProvider`` / ``AnthropicProvider`` normalized a
missing usage block to ``NormalizedUsage(0, 0)``, the router priced that at
``cost_usd=0.0``, and the owner-BYOT path settled the operation at 0 cents,
so a real paid 200 on the owner's key never reached ``used_cents`` and the
budget ceiling never saw it. "Usage unknown" and "zero tokens" were the same
value. These tests drive the real adapters over ``httpx.MockTransport``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import httpx
import pytest

from interfaces.research.api import settings_models_admin as models_admin
from interfaces.research.api.owner_byot_dispatch import dispatch_talk_to_book_byot
from substrate.byot_usage.ledger import ByotUsageLedger
from substrate.dispatch import register_provider, reset_provider_registry
from substrate.dispatch.providers.anthropic import AnthropicProvider
from substrate.dispatch.providers.openai_compat import OpenAICompatProvider
from substrate.dispatch.router import (
    DispatchConfig,
    TierConfig,
    TierPricing,
    dispatch,
)

_PROMPT = "x " * 4000  # 8000 UTF-8 bytes
_MAX_TOKENS = 1000
_PRICING = TierPricing(input_per_mtok=1.0, output_per_mtok=4.0, cached_input_per_mtok=0.1)
_CEILING_USD = (8000 / 1_000_000) * 1.0 + (_MAX_TOKENS / 1_000_000) * 4.0
# Anthropic can bill prompt-cache writes at 1.25x base input, so its ceiling
# prices the whole input term as writes (codex critic on #3415: the base-rate
# ceiling was $0.012 against a real $0.014 for 8,000 cache-write tokens).
_CEILING_USD_ANTHROPIC = (8000 / 1_000_000) * 1.0 * 1.25 + (_MAX_TOKENS / 1_000_000) * 4.0


@pytest.fixture(autouse=True)
def _registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    reset_provider_registry()
    yield
    reset_provider_registry()


def _openai(body: dict[str, Any], *, name: str = "oc") -> OpenAICompatProvider:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    return OpenAICompatProvider(
        name=name, base_url="https://api.deepseek.com", api_key="k-test",
        client=httpx.Client(transport=transport), expose_error_body=False,
    )


def _anthropic(body: dict[str, Any]) -> AnthropicProvider:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    return AnthropicProvider(
        api_key="k-test", client=httpx.Client(transport=transport),
        expose_error_body=False,
    )


def _config(provider: str, model: str) -> DispatchConfig:
    tier = TierConfig(
        name="pro", provider=provider, model=model, max_tokens=_MAX_TOKENS,
        temperature=0.1, context_budget_tokens=32000, pricing=_PRICING,
    )
    return DispatchConfig(role_tiers={"thought_partner": "pro"}, tiers={"pro": tier})


_OPENAI_TEXT = {"choices": [{"message": {"content": "a long paid answer"}, "finish_reason": "stop"}]}
_ANTHROPIC_TEXT = {
    "content": [{"type": "text", "text": "a long paid answer"}],
    "stop_reason": "end_turn",
}


# A count that is present but is not an int is "usage unknown" too. JSON null
# arrives as None and a blank count as "", and ``int(x or 0)`` would launder
# either into a definite 0 that prices the call as free.
_OPENAI_UNREPORTED = [
    pytest.param(None, id="omitted"),
    pytest.param({}, id="empty"),
    pytest.param({"prompt_tokens": 10}, id="no-completion-count"),
    pytest.param({"prompt_tokens": None, "completion_tokens": None}, id="null-counts"),
    pytest.param({"prompt_tokens": 10, "completion_tokens": None}, id="null-completion"),
    pytest.param({"prompt_tokens": "", "completion_tokens": ""}, id="blank-counts"),
]

# Valid primaries with a present-but-invalid cache count. prompt_tokens is
# INCLUSIVE of cached tokens, so the split being unknown is not the call being
# unknown (codex critic round 2 on #3415: the whole-call ceiling billed a
# $0.00003 call $0.012). Bill every input token at the full rate, flag it,
# never 0 for the cache and never an int() that raises.
_OPENAI_CACHE_UNKNOWN = [
    pytest.param({"prompt_tokens_details": {"cached_tokens": None}}, id="null-cached"),
    pytest.param({"prompt_tokens_details": {"cached_tokens": "abc"}}, id="string-cached"),
    pytest.param({"prompt_tokens_details": "abc"}, id="non-object-details"),
    pytest.param({"prompt_tokens_details": None}, id="null-details"),
    pytest.param({"prompt_cache_hit_tokens": None}, id="null-cache-hit"),
    pytest.param({"prompt_cache_hit_tokens": -3}, id="negative-cache-hit"),
]
_ANTHROPIC_UNREPORTED = [
    pytest.param(None, id="omitted"),
    pytest.param({"input_tokens": None, "output_tokens": None}, id="null-counts"),
    pytest.param({"input_tokens": 10, "output_tokens": None}, id="null-output"),
    pytest.param({"input_tokens": "", "output_tokens": ""}, id="blank-counts"),
    pytest.param({"input_tokens": 10, "output_tokens": 5,
                  "cache_creation_input_tokens": None}, id="null-cache-write"),
    pytest.param({"input_tokens": 10, "output_tokens": 5,
                  "cache_creation_input_tokens": "abc"}, id="string-cache-write"),
    pytest.param({"input_tokens": 10, "output_tokens": 5,
                  "cache_read_input_tokens": None}, id="null-cache-read"),
    pytest.param({"input_tokens": 10, "output_tokens": 5,
                  "cache_read_input_tokens": 1.5}, id="float-cache-read"),
]


def _with_usage(text_body: dict[str, Any], usage: dict[str, Any] | None) -> dict[str, Any]:
    body = dict(text_body)
    if usage is not None:
        body["usage"] = usage
    return body


@pytest.mark.parametrize("usage", _OPENAI_UNREPORTED)
def test_openai_compat_unreported_usage_is_billed_at_ceiling(usage) -> None:
    register_provider(_openai(_with_usage(_OPENAI_TEXT, usage)))
    result = dispatch(
        _PROMPT, "thought_partner", investigation_id="inv-usage",
        config=_config("oc", "deepseek-chat"),
    )
    assert result.text == "a long paid answer"
    assert result.usage.reported is False
    assert result.usage.input_tokens == len(_PROMPT.encode("utf-8"))
    assert result.usage.output_tokens == _MAX_TOKENS
    assert result.cost_usd == pytest.approx(_CEILING_USD)


@pytest.mark.parametrize("cache_fields", _OPENAI_CACHE_UNKNOWN)
def test_openai_compat_unknown_cache_split_bills_primaries_at_full_rate(cache_fields) -> None:
    body = dict(_OPENAI_TEXT)
    body["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, **cache_fields}
    register_provider(_openai(body))
    result = dispatch(
        _PROMPT, "thought_partner", investigation_id="inv-usage",
        config=_config("oc", "deepseek-chat"),
    )
    assert result.usage.reported is True
    assert result.usage.cache_unknown is True
    assert (result.usage.input_tokens, result.usage.output_tokens) == (10, 5)
    assert result.usage.cached_input_tokens == 0
    assert result.cost_usd == pytest.approx(10 / 1e6 * 1.0 + 5 / 1e6 * 4.0)
    assert result.cost_usd < _CEILING_USD


@pytest.mark.parametrize("usage", _ANTHROPIC_UNREPORTED)
def test_anthropic_unreported_usage_is_billed_at_ceiling(usage) -> None:
    register_provider(_anthropic(_with_usage(_ANTHROPIC_TEXT, usage)))
    result = dispatch(
        _PROMPT, "thought_partner", investigation_id="inv-usage",
        config=_config("anthropic", "claude-sonnet-5"),
    )
    assert result.usage.reported is False
    assert result.cost_usd == pytest.approx(_CEILING_USD_ANTHROPIC)


def test_anthropic_ceiling_bounds_a_cache_write_heavy_call() -> None:
    """The ceiling is an upper bound only if it covers the dearest shape the
    provider can bill: every prompt token written to the cache at 1.25x."""
    body = dict(_ANTHROPIC_TEXT)
    body["usage"] = {"input_tokens": 0, "cache_creation_input_tokens": 8000,
                     "output_tokens": _MAX_TOKENS}
    register_provider(_anthropic(body))
    actual = dispatch(
        _PROMPT, "thought_partner", investigation_id="inv-usage",
        config=_config("anthropic", "claude-sonnet-5"),
    )
    assert actual.usage.reported is True
    assert actual.cost_usd == pytest.approx(0.014)
    assert actual.cost_usd <= _CEILING_USD_ANTHROPIC + 1e-12


def test_valid_cache_counts_are_priced_not_ceilinged() -> None:
    """Positive control for the cache hardening: real cache counts price as
    reported, in both adapters."""
    body = dict(_OPENAI_TEXT)
    body["usage"] = {"prompt_tokens": 100, "completion_tokens": 50,
                     "prompt_tokens_details": {"cached_tokens": 40}}
    register_provider(_openai(body))
    oc = dispatch(_PROMPT, "thought_partner", investigation_id="inv-usage",
                  config=_config("oc", "deepseek-chat"))
    assert oc.usage.reported is True and oc.usage.cached_input_tokens == 40
    assert oc.cost_usd == pytest.approx(60 / 1e6 * 1.0 + 40 / 1e6 * 0.1 + 50 / 1e6 * 4.0)

    body = dict(_ANTHROPIC_TEXT)
    body["usage"] = {"input_tokens": 10, "cache_read_input_tokens": 20,
                     "cache_creation_input_tokens": 30, "output_tokens": 5}
    reset_provider_registry()
    register_provider(_anthropic(body))
    an = dispatch(_PROMPT, "thought_partner", investigation_id="inv-usage",
                  config=_config("anthropic", "claude-sonnet-5"))
    assert an.usage.reported is True
    assert an.cost_usd == pytest.approx(
        10 / 1e6 * 1.0 + 20 / 1e6 * 0.1 + 30 / 1e6 * 1.0 * 1.25 + 5 / 1e6 * 4.0
    )


def test_reported_usage_is_billed_as_reported() -> None:
    """Positive control: a real usage block is priced exactly, not at the ceiling."""
    body = dict(_OPENAI_TEXT)
    body["usage"] = {"prompt_tokens": 100, "completion_tokens": 50}
    register_provider(_openai(body))
    result = dispatch(
        _PROMPT, "thought_partner", investigation_id="inv-usage",
        config=_config("oc", "deepseek-chat"),
    )
    assert getattr(result.usage, "reported", True) is True
    assert (result.usage.input_tokens, result.usage.output_tokens) == (100, 50)
    assert result.cost_usd == pytest.approx(100 / 1e6 * 1.0 + 50 / 1e6 * 4.0)


def test_router_does_not_trust_zero_usage_from_an_empty_raw_block() -> None:
    """Allowlist: an adapter that maps an empty raw usage block to confident
    zeros (the pre-fix contract) is still billed at the ceiling."""

    from substrate.dispatch import NormalizedUsage, RawProviderResponse

    class _Legacy:
        name = "legacy"

        def call(self, *, model, prompt, max_tokens, temperature):
            return RawProviderResponse(
                text="paid", raw_usage={}, finish_reason="stop", latency_ms=1,
            )

        def normalize_usage(self, raw_usage):
            return NormalizedUsage(input_tokens=0, output_tokens=0)

    register_provider(_Legacy())
    result = dispatch(
        _PROMPT, "thought_partner", investigation_id="inv-usage",
        config=_config("legacy", "m"),
    )
    assert result.usage.reported is False
    assert result.cost_usd == pytest.approx(_CEILING_USD)


@pytest.mark.parametrize(
    ("adapter", "usage"),
    [
        pytest.param("openai", None, id="openai-omitted"),
        pytest.param(
            "openai", {"prompt_tokens": None, "completion_tokens": None},
            id="openai-null-counts",
        ),
        pytest.param(
            "anthropic", {"input_tokens": None, "output_tokens": None},
            id="anthropic-null-counts",
        ),
    ],
)
def test_owner_byot_missing_usage_settles_at_reserved_ceiling_not_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, adapter: str,
    usage: dict[str, Any] | None,
) -> None:
    """End to end through dispatch_talk_to_book_byot: the owner's key used_cents
    must move by the reserved ceiling when the provider hides its usage."""
    import test_talk_to_book_owner_byot as T

    app, record, _, fake, _house = T._authority_fixture(monkeypatch)
    real: Any
    if adapter == "openai":
        real = _openai(_with_usage(_OPENAI_TEXT, usage), name=record.id)
    else:
        # The owner route resolves its provider by the record id, so the real
        # Anthropic adapter is registered under that name to drive its
        # normalize_usage through the same reserve/settle path.
        real = _anthropic(_with_usage(_ANTHROPIC_TEXT, usage))
        real.name = record.id
    real._user_model_authority_fingerprint = fake._user_model_authority_fingerprint
    register_provider(real)
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    result, _authority = dispatch_talk_to_book_byot(
        app=app, request_owner_user_id="owner-a", resource_owner_user_id="owner-a",
        document_id="doc-a",
        choice=models_admin.UserModelChoice(
            authority="user_model", provider_id=record.id, model_id=record.model_id,
        ),
        prompt=_PROMPT, investigation_id="read-doc-a", logical_operation_id="turn-1",
        config=T._config(), usage_ledger=ledger,
    )
    row = ledger.operation("owner-a", "turn-1")
    usage = ledger.key_usage(record.id, "owner-a")
    assert result.text == "a long paid answer"
    assert row is not None and row.state == "settled"
    assert row.actual_cents is not None and row.actual_cents > 0
    # The settle is the same upper bound the reservation held (float vs
    # Decimal rounding may differ by at most one cent, upward-safe).
    assert math.isclose(row.actual_cents, row.reserved_cents, abs_tol=1)
    assert row.actual_cents >= row.reserved_cents
    assert usage.used_cents == row.actual_cents


def test_dispatch_call_event_carries_the_ceiling_not_zero(tmp_path: Path) -> None:
    """The durable DispatchCall event is what cost reports read; it must not
    record a definite 0.0 for an unmetered paid call."""
    from substrate.event_log import trajectory

    register_provider(_openai(dict(_OPENAI_TEXT)))
    dispatch(
        _PROMPT, "thought_partner", investigation_id="inv-usage-evt",
        config=_config("oc", "deepseek-chat"),
    )
    calls = [
        r for r in trajectory("inv-usage-evt")
        if r.get("action_type") == "dispatch.call"
    ]
    assert len(calls) == 1
    payload = calls[0]["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload["cost_usd"] == pytest.approx(_CEILING_USD)
    assert payload["output_tokens"] == _MAX_TOKENS
