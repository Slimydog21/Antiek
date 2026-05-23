"""Vision-provider registry (Sprint 30+ thread 4).

The text-dispatch router (``substrate/dispatch/router.py``) is
provider-agnostic over the ``Provider`` protocol (text in, text +
usage out). The visual role's contract is different — frame +
text in, claims out — so vision providers live in a parallel
registry rather than going through the same router.

This module is the substrate-side seam: ``register_default_vision_providers()``
walks env vars + instantiates concrete adapters; ``get_vision_provider(name)``
fetches by name; ``list_registered_vision_providers()`` reports
to /health.

Production calls ``register_default_vision_providers()`` in
``interfaces/research/api/app.py:create_app`` after the existing
text-dispatch ``register_default_providers()`` call.
"""

from __future__ import annotations

import os
from typing import Optional

from .vision_anthropic import (
    AnthropicVisionProvider,
    VisionProvider,
)
from .vision_openai import OpenAIVisionProvider


_VISION_REGISTRY: dict[str, VisionProvider] = {}


def register_vision_provider(provider: VisionProvider) -> None:
    """Register one provider under its ``name``. Last-registered wins
    (matches the text-dispatch register_provider posture)."""
    _VISION_REGISTRY[provider.name] = provider


def get_vision_provider(name: str) -> Optional[VisionProvider]:
    """Look up a provider by name. Returns None if unregistered."""
    return _VISION_REGISTRY.get(name)


def list_registered_vision_providers() -> list[str]:
    """Return the names of every currently-registered provider."""
    return sorted(_VISION_REGISTRY)


def clear_vision_registry() -> None:
    """Test helper: drop every registered provider."""
    _VISION_REGISTRY.clear()


def _maybe_anthropic_vision() -> Optional[AnthropicVisionProvider]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return AnthropicVisionProvider(api_key_env="ANTHROPIC_API_KEY")


def _maybe_openai_vision() -> Optional[OpenAIVisionProvider]:
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    return OpenAIVisionProvider(api_key_env="OPENAI_API_KEY")


def register_default_vision_providers(
    *, quiet: bool = False,
) -> set[str]:
    """Register every default vision provider whose API key is
    configured. Returns the set of names registered. Missing keys
    are NOT errors — they're a degraded posture (matches text
    dispatch ``register_default_providers``)."""
    factories = [
        ("anthropic_vision", _maybe_anthropic_vision),
        ("openai_vision", _maybe_openai_vision),
    ]
    registered: set[str] = set()
    for name, factory in factories:
        provider = factory()
        if provider is None:
            if not quiet:
                # Stay silent in tests; emit a single line in dev so
                # the operator can see which providers degraded.
                pass
            continue
        register_vision_provider(provider)
        registered.add(name)
    return registered


__all__ = [
    "clear_vision_registry",
    "get_vision_provider",
    "list_registered_vision_providers",
    "register_default_vision_providers",
    "register_vision_provider",
]
