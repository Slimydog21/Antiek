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

Missing API keys are NOT errors — they're a degraded posture. The
provider just doesn't register; the router falls back to the next
entry in the tier's fallback chain. ``register_default_providers``
returns the set of provider names actually registered so the caller
can warn / surface in /health.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Set

from ..router import register_provider
from .anthropic import AnthropicProvider
from .openai_compat import OpenAICompatProvider


# (provider_name, factory) — factory returns an instance or None when
# the required env var is missing.
def _maybe_deepseek() -> Optional[OpenAICompatProvider]:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return None
    return OpenAICompatProvider(
        name="deepseek",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
    )


def _maybe_anthropic() -> Optional[AnthropicProvider]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return AnthropicProvider(api_key_env="ANTHROPIC_API_KEY")


def _maybe_openrouter() -> Optional[OpenAICompatProvider]:
    if not os.environ.get("OPENROUTER_API_KEY"):
        return None
    # OpenRouter's base already includes /api/v1; the chat-completions
    # path is /chat/completions (NOT the default /v1/chat/completions
    # which would double-up to /api/v1/v1/chat/completions → 404).
    return OpenAICompatProvider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        chat_completions_path="/chat/completions",
    )


def _maybe_xiaomi() -> Optional[OpenAICompatProvider]:
    # MiMo API. Endpoint per the public docs; ANTIEK_XIAOMI_BASE_URL
    # overrides if Xiaomi changes the path or you're proxying.
    if not os.environ.get("XIAOMI_API_KEY"):
        return None
    return OpenAICompatProvider(
        name="xiaomi",
        base_url=os.environ.get(
            "ANTIEK_XIAOMI_BASE_URL",
            "https://api.mimo.xiaomi.com/v1",
        ),
        api_key_env="XIAOMI_API_KEY",
    )


def _maybe_hermes() -> Optional[OpenAICompatProvider]:
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
    if not os.environ.get("HERMES_API_KEY"):
        return None
    return OpenAICompatProvider(
        name="hermes",
        base_url=os.environ.get(
            "ANTIEK_HERMES_BASE_URL", "http://localhost:8080/v1",
        ),
        api_key_env="HERMES_API_KEY",
        chat_completions_path="/chat/completions",
    )


# Order doesn't matter — register_provider is name-keyed.
_DEFAULT_PROVIDERS = [
    ("deepseek", _maybe_deepseek),
    ("anthropic", _maybe_anthropic),
    ("openrouter", _maybe_openrouter),
    ("xiaomi", _maybe_xiaomi),
    ("hermes", _maybe_hermes),
]


def register_default_providers(
    *,
    quiet: bool = False,
    only: Optional[List[str]] = None,
) -> Set[str]:
    """Instantiate + register every provider whose API key env var is
    present. Returns the set of registered names. Idempotent — calling
    twice re-registers (the router's register_provider is overwrite-
    safe for the same name).

    ``quiet`` suppresses stderr breadcrumbs (used by tests). ``only``
    restricts to a named subset (used by the smoke runner)."""
    registered: Set[str] = set()
    skipped: List[str] = []
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
