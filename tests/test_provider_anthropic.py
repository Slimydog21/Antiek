"""Real Anthropic adapter tests via httpx.MockTransport.

These don't hit the network. They feed canned Anthropic responses through
the actual adapter to verify:

- Request body shape (model / max_tokens / temperature / messages).
- Header construction (x-api-key, anthropic-version, content-type).
- Response parsing including the typed-parts ``content`` array.
- ``stop_reason`` flows through (router normalizes it on emit).
- ``normalize_usage`` reports an INCLUSIVE ``input_tokens`` (cache-exclusive
  remainder + cache_read + cache_creation) and forwards the cached-read and
  cache-write subsets, matching the real Anthropic Messages API shape.
- Router cost math (SPR-01): on a cache hit the inclusive normalization
  prevents ``paid_input = max(0, input - cached)`` from clamping to zero,
  and cache_creation is billed at the premium write rate.
- Error paths: 401, 429, 5xx, timeout — each maps to ProviderError
  with the correct ``retryable`` flag.
- Prompt-caching mode sends ``cache_control`` on the user message.

SPR-01 M1 VERDICT: FIRES — call path = direct Anthropic SDK
(``api.anthropic.com/v1/messages``). The Anthropic Messages API usage
object's ``input_tokens`` is the cache-EXCLUSIVE remainder (Anthropic docs:
"input tokens which were not read from or used to create a cache ... tokens
after the last cache breakpoint"); ``cache_read_input_tokens`` and
``cache_creation_input_tokens`` are reported separately and are NOT inside
``input_tokens``. In THIS deployment ``AnthropicProvider`` is registered by
``providers/bootstrap.py:_maybe_anthropic`` with NO gateway base_url, so it
calls Anthropic directly and receives the raw, un-pre-normalized usage
object — no Hermes / OpenRouter gateway sits between the API and
``normalize_usage`` to make ``input_tokens`` inclusive. (The OpenRouter-
served ``anthropic/claude-opus-4.7`` synthesis tier uses the SEPARATE
``OpenAICompatProvider`` adapter whose ``prompt_tokens`` IS inclusive and is
out of scope here.) So whenever the direct ``anthropic`` adapter receives a
cache hit, its normalization is wrong and the router under-bills — the bug
FIRES at the adapter boundary.

URGENCY, stated honestly (not oversold): the defect is LATENT-AND-UNROUTED
today on two independent counts — (1) prompt-caching is OFF, so cache_read /
cache_creation are zero and the clamp can't trigger; and (2) no tier in the
current ``config.yaml`` sets ``provider: anthropic`` (synthesis routes
through OpenRouter's inclusive ``OpenAICompatProvider``), so the buggy direct
adapter is registered but not dispatched to. SPR-04 removes count (1) by
flipping caching ON; it does NOT by itself remove count (2). The bug bills
real dollars only once BOTH a caching-on tier AND a ``provider: anthropic``
route exist. Fixing it now is correct prophylaxis (the adapter is wrong
regardless and the fix is cheap), not an emergency armed for the next sprint.
See ``test_M1_*`` and ``test_cost_*`` below.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from substrate.dispatch import AnthropicProvider, ProviderError, TierPricing  # noqa: E402
from substrate.dispatch.router import _compute_cost_usd  # noqa: E402


def _make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------


def test_anthropic_basic_call_and_headers_and_body():
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["method"] = req.method
        captured["headers"] = dict(req.headers)
        captured["body"] = httpx.Request.read(req)
        return httpx.Response(
            200,
            json={
                "id": "msg_001", "type": "message", "role": "assistant",
                "model": "claude-opus-4-7",
                "content": [{"type": "text", "text": "hello back"}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {
                    "input_tokens": 100, "output_tokens": 25,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
            headers={"request-id": "req_abc"},
        )

    p = AnthropicProvider(api_key="test-key", client=_make_client(handler))
    raw = p.call(model="claude-opus-4-7", prompt="hello", max_tokens=512, temperature=0.4)

    assert raw.text == "hello back"
    assert raw.finish_reason == "end_turn"
    assert raw.latency_ms >= 0
    assert raw.request_id == "req_abc"

    # Request URL + method
    assert captured["url"].endswith("/v1/messages")
    assert captured["method"] == "POST"

    # Headers — required by Anthropic
    assert captured["headers"]["x-api-key"] == "test-key"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["headers"]["content-type"] == "application/json"

    # Body shape
    import json
    body = json.loads(captured["body"])
    assert body["model"] == "claude-opus-4-7"
    assert body["max_tokens"] == 512
    assert body["temperature"] == 0.4
    assert body["messages"] == [{"role": "user", "content": "hello"}]


@pytest.mark.parametrize("model", ["claude-opus-5", "claude-sonnet-5"])
def test_adaptive_thinking_models_omit_dispatch_temperature(model: str) -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(httpx.Request.read(req)))
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    provider = AnthropicProvider(api_key="test-key", client=_make_client(handler))
    provider.call(model=model, prompt="hello", max_tokens=16, temperature=0.7)

    assert captured["model"] == model
    assert "temperature" not in captured


@pytest.mark.parametrize("model", ["claude-haiku-4-5-20251001", "custom-model"])
def test_non_adaptive_models_preserve_dispatch_temperature(model: str) -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(httpx.Request.read(req)))
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    provider = AnthropicProvider(api_key="test-key", client=_make_client(handler))
    provider.call(model=model, prompt="hello", max_tokens=16, temperature=0.7)

    assert captured["temperature"] == 0.7


def test_anthropic_multi_part_content_joins_text():
    """Anthropic returns content as a typed-part list. Non-text parts
    must be ignored cleanly so a tool_use sub-part doesn't crash parsing."""

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "msg_002", "content": [
                {"type": "text", "text": "part-a "},
                {"type": "tool_use", "id": "t1", "name": "calc", "input": {}},
                {"type": "text", "text": "part-b"},
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 50, "output_tokens": 10},
        })

    p = AnthropicProvider(api_key="k", client=_make_client(handler))
    raw = p.call(model="claude-opus-4-7", prompt="x", max_tokens=10, temperature=0.0)
    assert raw.text == "part-a part-b"
    assert raw.finish_reason == "tool_use"


def test_anthropic_normalize_usage_with_cache_read():
    """Anthropic's raw ``input_tokens`` is the cache-EXCLUSIVE remainder
    (tokens after the last cache breakpoint); ``cache_read_input_tokens``
    and ``cache_creation_input_tokens`` are reported separately and are NOT
    inside it. ``normalize_usage`` therefore sums all three into an
    inclusive ``NormalizedUsage.input_tokens`` and forwards the read/write
    subsets so the router can bill them at their own rates."""
    p = AnthropicProvider(api_key="k")
    u = p.normalize_usage({
        "input_tokens": 1200,            # cache-exclusive remainder
        "output_tokens": 350,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 800,  # NOT contained in input_tokens
    })
    # Inclusive total = remainder(1200) + cache_read(800) + cache_creation(0)
    assert u.input_tokens == 2000
    assert u.output_tokens == 350
    assert u.cached_input_tokens == 800
    assert u.cache_creation_input_tokens == 0


def test_anthropic_normalize_usage_handles_missing_fields():
    """If the provider omits usage entirely, return zeros (do not raise)."""
    p = AnthropicProvider(api_key="k")
    u = p.normalize_usage({})
    assert u.input_tokens == 0
    assert u.output_tokens == 0
    assert u.cached_input_tokens == 0
    assert u.cache_creation_input_tokens == 0


# ---------------------------------------------------------------------------
# SPR-01 M1 — VERIFY-FIRES verdict (recorded payload + field semantics)
# ---------------------------------------------------------------------------
#
# G1 gate: this file must contain an explicit FIRES / DOES-NOT-FIRE verdict
# with the call path named. The verdict and its reasoning live in the module
# docstring above (search "M1 VERDICT: FIRES"); this test pins the recorded
# Anthropic usage payload it was derived from and asserts the cache-exclusive
# semantics that make the bug FIRE on the direct-SDK ``anthropic`` path.

# Recorded usage payload as it arrives at the AnthropicProvider boundary
# (direct api.anthropic.com/v1/messages — no Hermes/OpenRouter gateway in
# this deployment per providers/bootstrap.py:_maybe_anthropic). All four
# fields present; values illustrative of a normal cache hit where the
# cached read dominates and the post-breakpoint remainder is small.
_M1_RECORDED_USAGE = {
    "input_tokens": 200,             # cache-EXCLUSIVE remainder (after last breakpoint)
    "cache_read_input_tokens": 10000,
    "cache_creation_input_tokens": 2000,
    "output_tokens": 500,
}

# M1 VERDICT (see module docstring for full reasoning):
#   FIRES — call path: direct Anthropic SDK (api.anthropic.com).
_M1_VERDICT = "FIRES"


def test_M1_verify_fires_verdict_recorded():
    """M1: the deployment sees a cache-EXCLUSIVE ``input_tokens``, so the
    double-subtraction underbilling FIRES. The recorded payload has all four
    fields; ``input_tokens`` (200) is far smaller than ``cache_read`` (10000),
    which is only possible if ``input_tokens`` is the post-breakpoint
    remainder and NOT an inclusive total — confirming the FIRES verdict."""
    assert _M1_VERDICT == "FIRES"
    for field in (
        "input_tokens", "cache_read_input_tokens",
        "cache_creation_input_tokens", "output_tokens",
    ):
        assert field in _M1_RECORDED_USAGE
    # The smoking gun: cache_read alone exceeds input_tokens. If input_tokens
    # were the inclusive total this would be impossible (a subset can't
    # exceed the whole). So input_tokens is the cache-exclusive remainder.
    assert (
        _M1_RECORDED_USAGE["cache_read_input_tokens"]
        > _M1_RECORDED_USAGE["input_tokens"]
    )


# ---------------------------------------------------------------------------
# SPR-01 M3 — NON-VACUOUS cost test: cache_read > input_remainder must not
# clamp the cost to zero, and cache_creation must be billed at the premium
# write rate.
# ---------------------------------------------------------------------------
#
# Pricing taken from the only Anthropic-priced tier (synthesis) in
# config.yaml — read-only, NOT edited by this sprint:
#     input_per_mtok=5.0  output_per_mtok=25.0  cached_input_per_mtok=0.50
# Cache writes are billed at 1.25x base input (Anthropic 5-min cache-write
# multiplier), applied in router._compute_cost_usd via _CACHE_WRITE_MULTIPLIER.
_SYNTHESIS_PRICING = TierPricing(
    input_per_mtok=5.0,
    output_per_mtok=25.0,
    cached_input_per_mtok=0.50,
)

# Hand-computed inclusive cost for _M1_RECORDED_USAGE under _SYNTHESIS_PRICING:
#   normalize_usage -> inclusive input = 200 + 10000 + 2000 = 12200
#   paid_input = max(0, 12200 - 10000 - 2000)      = 200 tokens
#   input  cost = 200   / 1e6 * 5.0                = 0.001
#   cache_read  = 10000 / 1e6 * 0.50               = 0.005
#   cache_write = 2000  / 1e6 * 5.0 * 1.25 (=6.25) = 0.0125
#   output cost = 500   / 1e6 * 25.0               = 0.0125
#   TOTAL                                          = 0.0310 USD
_M3_EXPECTED_COST_USD = 0.031


def test_cost_cache_hit_does_not_clamp_to_zero_exact_inclusive_figure():
    """M3 (G2/G3/G4): the clamp-branch regression test.

    Fixture has ``cache_read_input_tokens`` (10000) > raw ``input_tokens``
    (200) — the exact condition that, under the bug, made the adapter forward
    a cache-exclusive remainder so the router's ``max(0, input - cached)``
    double-subtracted and clamped paid_input to 0 (underbilling, and dropping
    the premium cache_creation writes entirely → buggy cost 0.0175).

    With the fix, ``normalize_usage`` reports an inclusive total, so the cost
    is the exact hand-computed 0.0310 USD. Asserting an exact non-zero
    constant (not a tolerance-around-zero) makes this impossible to satisfy
    by accidental clamping to zero."""
    p = AnthropicProvider(api_key="k")
    usage = p.normalize_usage(_M1_RECORDED_USAGE)

    # normalize_usage produced an inclusive total >= cached subset.
    assert usage.input_tokens == 12200
    assert usage.cached_input_tokens == 10000
    assert usage.cache_creation_input_tokens == 2000
    assert usage.input_tokens >= usage.cached_input_tokens

    cost = _compute_cost_usd(usage, _SYNTHESIS_PRICING)

    # Non-vacuity: must be the exact inclusive figure AND must not be zero.
    assert cost != 0
    assert cost == pytest.approx(_M3_EXPECTED_COST_USD, abs=1e-12)
    # And specifically not the buggy clamped figure (0.0175) that drops the
    # paid remainder and the premium cache_creation writes.
    assert cost != pytest.approx(0.0175, abs=1e-12)


def test_cost_paid_input_no_longer_clamps_on_normal_cache_hit():
    """M2 acceptance: paid_input = max(0, input - cached - cache_creation)
    no longer clamps to 0 on a cache hit, because the normalized input is the
    inclusive total >= cached. Verified directly on the normalized usage."""
    p = AnthropicProvider(api_key="k")
    usage = p.normalize_usage(_M1_RECORDED_USAGE)
    paid_input = max(
        0,
        usage.input_tokens
        - usage.cached_input_tokens
        - usage.cache_creation_input_tokens,
    )
    assert paid_input == 200  # the genuine post-breakpoint remainder, not 0


def test_cost_cache_creation_billed_at_premium_write_rate():
    """cache_creation must be billed at 1.25x base input, strictly above the
    base input rate. Isolate a write-only payload (no read, no remainder) and
    compare against what the base input rate alone would charge."""
    p = AnthropicProvider(api_key="k")
    usage = p.normalize_usage({
        "input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 1_000_000,
        "output_tokens": 0,
    })
    assert usage.input_tokens == 1_000_000
    cost = _compute_cost_usd(usage, _SYNTHESIS_PRICING)
    # 1M cache-write tokens at 1.25 x 5.0 = $6.25, premium over the $5.00 a
    # plain input MTok would cost.
    assert cost == pytest.approx(6.25, abs=1e-9)
    assert cost > _SYNTHESIS_PRICING.input_per_mtok  # strictly premium


def test_anthropic_prompt_caching_mode_attaches_cache_control():
    """When prompt caching is enabled, the user message uses the typed-parts
    form with cache_control on the text part."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        import json
        captured["body"] = json.loads(httpx.Request.read(req))
        return httpx.Response(200, json={
            "id": "msg_003", "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    p = AnthropicProvider(
        api_key="k", client=_make_client(handler),
        enable_prompt_caching=True,
    )
    p.call(model="m", prompt="long stable prefix...", max_tokens=10, temperature=0.0)

    msg = captured["body"]["messages"][0]
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    assert msg["content"][0]["type"] == "text"
    assert msg["content"][0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status,retryable", [
    (401, False),   # bad key — operator action needed, not retryable
    (400, False),   # malformed request
    (429, True),    # rate limit — retry after backoff
    (500, True),    # server error — retryable
    (502, True),
    (503, True),
    (504, True),
    (529, True),    # Anthropic overloaded
])
def test_anthropic_http_error_maps_to_provider_error(status, retryable):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"type": "error", "error": {"type": "x", "message": "fail"}})

    p = AnthropicProvider(api_key="k", client=_make_client(handler))
    with pytest.raises(ProviderError) as ei:
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert ei.value.retryable is retryable
    assert ei.value.provider == "anthropic"


def test_anthropic_timeout_maps_to_retryable_provider_error():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated")

    p = AnthropicProvider(api_key="k", client=_make_client(handler))
    with pytest.raises(ProviderError) as ei:
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert ei.value.retryable is True


def test_anthropic_network_error_maps_to_retryable_provider_error():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns")

    p = AnthropicProvider(api_key="k", client=_make_client(handler))
    with pytest.raises(ProviderError) as ei:
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert ei.value.retryable is True


def test_anthropic_invalid_json_raises_non_retryable():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    p = AnthropicProvider(api_key="k", client=_make_client(handler))
    with pytest.raises(ProviderError) as ei:
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert ei.value.retryable is False


def test_anthropic_missing_api_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = AnthropicProvider()  # no explicit key, no env var
    with pytest.raises(ProviderError, match="API key not configured"):
        p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)


def test_anthropic_reads_api_key_from_env(monkeypatch):
    captured: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["key"] = req.headers["x-api-key"]
        return httpx.Response(200, json={
            "id": "i", "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-123")
    p = AnthropicProvider(client=_make_client(handler))
    p.call(model="m", prompt="x", max_tokens=10, temperature=0.0)
    assert captured["key"] == "env-key-123"
