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


@pytest.mark.parametrize(
    "usage",
    [None, {}, {"prompt_tokens": 10}],
    ids=["omitted", "empty", "no-completion-count"],
)
def test_openai_compat_unreported_usage_is_billed_at_ceiling(usage) -> None:
    body = dict(_OPENAI_TEXT)
    if usage is not None:
        body["usage"] = usage
    register_provider(_openai(body))
    result = dispatch(
        _PROMPT, "thought_partner", investigation_id="inv-usage",
        config=_config("oc", "deepseek-chat"),
    )
    assert result.text == "a long paid answer"
    assert result.usage.reported is False
    assert result.usage.input_tokens == len(_PROMPT.encode("utf-8"))
    assert result.usage.output_tokens == _MAX_TOKENS
    assert result.cost_usd == pytest.approx(_CEILING_USD)


def test_anthropic_unreported_usage_is_billed_at_ceiling() -> None:
    register_provider(_anthropic(dict(_ANTHROPIC_TEXT)))
    result = dispatch(
        _PROMPT, "thought_partner", investigation_id="inv-usage",
        config=_config("anthropic", "claude-sonnet-5"),
    )
    assert result.usage.reported is False
    assert result.cost_usd == pytest.approx(_CEILING_USD)


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


def test_owner_byot_missing_usage_settles_at_reserved_ceiling_not_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """End to end through dispatch_talk_to_book_byot: the owner's key used_cents
    must move by the reserved ceiling when the provider hides its usage."""
    import test_talk_to_book_owner_byot as T

    app, record, _, fake, _house = T._authority_fixture(monkeypatch)
    real = _openai(dict(_OPENAI_TEXT), name=record.id)
    real._user_model_authority_fingerprint = fake._user_model_authority_fingerprint  # type: ignore[attr-defined]
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
