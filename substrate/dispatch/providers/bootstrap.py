"""Default provider registration.

The router's ``register_provider`` registry is empty at import time;
nothing instantiates the concrete adapters until someone calls into
this module. ``create_app`` (and any other entry point that needs
real dispatch) calls ``register_default_providers()`` once at
startup.

The provider name → (adapter class, kwargs) mapping lives here
because:

- ``config.yaml`` carries operator-tunable knobs (tiers, models,
  pricing), not the wiring between an opaque provider name and the
  concrete adapter class.
- Adding a new provider is one entry in ``_DEFAULT_PROVIDERS`` and
  the config can immediately reference it by name.

Each provider's API key is resolved **BYOK-first** by
``byok_key_source.resolve_provider_key(handle, env_var)``: the operator's key
stored in the encrypted BYOK store under ``provider:<handle>`` wins, else the
environment variable (unless ``ANTIEK_BYOT_ONLY`` disables the env fallback).
This is what makes "remove my keys, onboard like a user" real — you store the
key in BYOK and the env var is no longer needed.

Missing API keys are NOT errors — they're a degraded posture. The
provider just doesn't register; the router falls back to the next
entry in the tier's fallback chain. ``register_default_providers``
returns the set of provider names actually registered so the caller
can warn / surface in /health.
"""

from __future__ import annotations

import os
import sys

from ..router import register_provider
from .anthropic import AnthropicProvider
from .byok_key_source import resolve_provider_key
from .openai_compat import OpenAICompatProvider


# (provider_name, factory) — factory returns an instance or None when
# the required env var is missing.
def _maybe_deepseek() -> OpenAICompatProvider | None:
    # DeepSeek V4 Pro — the "deep" research tier's primary provider
    # (see substrate/dispatch/research_tier.py). DeepSeek's API speaks
    # the OpenAI chat-completions shape verbatim, so it reuses the
    # OpenAICompatProvider adapter (mirror of the xAI/Hermes bridge at
    # bootstrap.py:_maybe_hermes / providers/openai_compat.py). The
    # concrete model id (``deepseek-v4-pro``) is supplied per-call by the
    # tier in config.yaml, NOT pinned here — one provider endpoint can
    # serve V4-Pro and V4-Flash; the provider is the endpoint, the model
    # is the per-call argument. ``ANTIEK_DEEPSEEK_BASE_URL`` overrides the
    # default if DeepSeek changes the host or the operator is proxying
    # (matches the xiaomi/hermes override convention below).
    #
    # KEY sourced BYOK-first (``provider:deepseek``) then env ``DEEPSEEK_API_KEY``
    # via resolve_provider_key — never hardcoded; registers ONLY when a key is
    # available (degraded-posture, not an error, per this module's docstring +
    # tests/test_dispatch_bootstrap.py).
    key = resolve_provider_key("deepseek", "DEEPSEEK_API_KEY")
    if not key:
        return None
    return OpenAICompatProvider(
        name="deepseek",
        base_url=os.environ.get(
            "ANTIEK_DEEPSEEK_BASE_URL", "https://api.deepseek.com",
        ),
        api_key=key,
    )


def _maybe_anthropic() -> AnthropicProvider | None:
    key = resolve_provider_key("anthropic", "ANTHROPIC_API_KEY")
    if not key:
        return None
    return AnthropicProvider(api_key=key)


def _maybe_openrouter() -> OpenAICompatProvider | None:
    key = resolve_provider_key("openrouter", "OPENROUTER_API_KEY")
    if not key:
        return None
    # OpenRouter's base already includes /api/v1; the chat-completions
    # path is /chat/completions (NOT the default /v1/chat/completions
    # which would double-up to /api/v1/v1/chat/completions → 404).
    return OpenAICompatProvider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
        chat_completions_path="/chat/completions",
    )


def _maybe_xiaomi() -> OpenAICompatProvider | None:
    # Xiaomi MiMo V2.5 Pro — the "fast" research tier's primary provider
    # (see substrate/dispatch/research_tier.py). MiMo's API speaks the
    # OpenAI chat-completions shape, so it reuses the same
    # OpenAICompatProvider adapter as DeepSeek and the xAI/Hermes bridge.
    # The concrete model id (``mimo-v2.5-pro``) is supplied per-call by
    # the tier in config.yaml, not pinned here. ANTIEK_XIAOMI_BASE_URL
    # overrides if Xiaomi changes the path or you're proxying.
    #
    # ASSUMPTION (operator-bound to verify on prod): the MiMo endpoint
    # below is from the public docs as of 2026-01; the base URL already
    # carries ``/v1``, so the adapter's DEFAULT chat_completions_path of
    # ``/v1/chat/completions`` would double-up to ``/v1/v1/...`` — the
    # exact failure the Hermes regression at
    # tests/test_dispatch_bootstrap.py:test_hermes_provider_url_does_not_double_v1
    # locks in. MiMo is therefore given the same ``/chat/completions``
    # override as OpenRouter/Hermes. If MiMo's real base omits ``/v1``,
    # set ANTIEK_XIAOMI_BASE_URL to include it (the path override stays
    # correct either way as long as the base carries the version prefix).
    #
    # KEY sourced BYOK-first (``provider:xiaomi``) then env ``XIAOMI_API_KEY``.
    key = resolve_provider_key("xiaomi", "XIAOMI_API_KEY")
    if not key:
        return None
    return OpenAICompatProvider(
        name="xiaomi",
        base_url=os.environ.get(
            "ANTIEK_XIAOMI_BASE_URL",
            "https://api.mimo.xiaomi.com/v1",
        ),
        api_key=key,
        chat_completions_path="/chat/completions",
    )


def _maybe_hermes() -> OpenAICompatProvider | None:
    # Hermes is the operator's local subscription gateway. Disabled
    # by default; opt-in via HERMES_API_KEY + ANTIEK_HERMES_BASE_URL.
    #
    # ``chat_completions_path="/chat/completions"`` matches the
    # OpenRouter pattern: the base URL carries the API-version prefix
    # (``/v1``) and the path appended by the provider does NOT repeat
    # it. Production caught a double-``/v1/`` 404 here when the env
    # var was ``https://hermes-bridge.antiek.ai/v1`` and the default
    # path of ``/v1/chat/completions`` was appended — the proxy
    # rejected ``/v1/v1/chat/completions`` as path_not_allowed,
    # silently dispatching every call to the OpenRouter fallback for
    # 100% of inference. Fixed 2026-05-18.
    key = resolve_provider_key("hermes", "HERMES_API_KEY")
    if not key:
        return None
    return OpenAICompatProvider(
        name="hermes",
        base_url=os.environ.get(
            "ANTIEK_HERMES_BASE_URL", "http://localhost:8080/v1",
        ),
        api_key=key,
        chat_completions_path="/chat/completions",
    )


def _maybe_zai() -> OpenAICompatProvider | None:
    # Zhipu z.ai — GLM-5.2, the platform's primary AI driver (operator
    # decision 2026-07-06). z.ai's API speaks the OpenAI chat-completions
    # shape, so it reuses OpenAICompatProvider exactly like DeepSeek/xiaomi.
    # The concrete model id (``glm-5.2``) is supplied per-call by the tier in
    # config.yaml, NOT pinned here — one provider endpoint serves the whole
    # GLM family; the provider is the endpoint, the model is the per-call arg.
    #
    # GLM-5.2 is a REASONING model: by default it spends the token budget on a
    # chain-of-thought ``reasoning_content`` field and emits ``content`` only
    # after reasoning completes. The substrate's whole thesis is that quality
    # emerges from VOLUME of dispatches that yield crystallized ANSWERS
    # (notes, extractions, syntheses) — NOT reasoning traces. So the driver
    # runs with ``thinking: {"type": "disabled"}`` (verified live against
    # https://api.z.ai/api/paas/v4): GLM-5.2 returns direct content answers
    # with no reasoning overhead, at high volume and low latency/cost. This
    # also fixes the prior flash-tier defect where deepseek-v4-flash bailed
    # with ``{"notes": []}`` on distillable prose. Enabling thinking for a
    # specific reasoning-heavy role is a one-line extra_body change here.
    #
    # KEY sourced BYOK-first (``provider:zai``) then env ``Z_AI_API_KEY`` —
    # never hardcoded; registers ONLY when a key is available. The `zai` and
    # `zai_reasoning` twins SHARE one z.ai key (one BYOK handle ``provider:zai``).
    # ANTIEK_ZAI_BASE_URL overrides the default endpoint (e.g. the bigmodel.cn host).
    key = resolve_provider_key("zai", "Z_AI_API_KEY")
    if not key:
        return None
    return OpenAICompatProvider(
        name="zai",
        base_url=os.environ.get(
            "ANTIEK_ZAI_BASE_URL", "https://api.z.ai/api/paas/v4",
        ),
        api_key=key,
        chat_completions_path="/chat/completions",
        extra_body={"thinking": {"type": "disabled"}},
    )


def _maybe_zai_reasoning() -> OpenAICompatProvider | None:
    # Zhipu z.ai — GLM-5.2 with thinking ENABLED. The `zai` provider
    # (above) disables thinking for the high-volume volume-thesis tiers;
    # this is the reasoning-enabled twin on the SAME direct endpoint,
    # registered under a distinct name so the synthesis tier can opt into
    # GLM-5.2's native chain-of-thought. The ONLY difference from `zai` is
    # the absence of the thinking-disabled extra_body — GLM-5.2 reasons by
    # default, so omitting the toggle leaves reasoning ON (it emits a
    # `reasoning_content` trace AND the final `content` answer; the adapter
    # reads `content`, so the content path is unchanged). One provider
    # endpoint, two policies, zero extra code in the dispatch hot path.
    #
    # KEY sourced BYOK-first (``provider:zai``, shared with `zai`) then env
    # ``Z_AI_API_KEY`` — never hardcoded; registers ONLY when a key is available.
    key = resolve_provider_key("zai", "Z_AI_API_KEY")
    if not key:
        return None
    return OpenAICompatProvider(
        name="zai_reasoning",
        base_url=os.environ.get(
            "ANTIEK_ZAI_BASE_URL", "https://api.z.ai/api/paas/v4",
        ),
        api_key=key,
        chat_completions_path="/chat/completions",
    )


# Order doesn't matter — register_provider is name-keyed.
_DEFAULT_PROVIDERS = [
    ("zai", _maybe_zai),
    ("zai_reasoning", _maybe_zai_reasoning),
    ("deepseek", _maybe_deepseek),
    ("anthropic", _maybe_anthropic),
    ("openrouter", _maybe_openrouter),
    ("xiaomi", _maybe_xiaomi),
    ("hermes", _maybe_hermes),
]


def register_default_providers(
    *,
    quiet: bool = False,
    only: list[str] | None = None,
) -> set[str]:
    """Instantiate + register every provider whose API key env var is
    present. Returns the set of registered names. Idempotent — calling
    twice re-registers (the router's register_provider is overwrite-
    safe for the same name).

    ``quiet`` suppresses stderr breadcrumbs (used by tests). ``only``
    restricts to a named subset (used by the smoke runner)."""
    registered: set[str] = set()
    skipped: list[str] = []
    selected = _DEFAULT_PROVIDERS
    if only is not None:
        wanted = set(only)
        selected = [(n, f) for n, f in _DEFAULT_PROVIDERS if n in wanted]
    for name, factory in selected:
        instance = factory()
        if instance is None:
            skipped.append(name)
            continue
        register_provider(instance)
        registered.add(name)
    if not quiet:
        if registered:
            print(
                f"dispatch: registered providers {sorted(registered)}",
                file=sys.stderr,
            )
        if skipped:
            print(
                f"dispatch: skipped providers (no API key) {sorted(skipped)}",
                file=sys.stderr,
            )
    return registered
