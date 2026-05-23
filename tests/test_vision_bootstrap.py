"""Vision-provider bootstrap tests."""

from __future__ import annotations

import os

import pytest

from substrate.dispatch.providers.vision_bootstrap import (
    clear_vision_registry,
    get_vision_provider,
    list_registered_vision_providers,
    register_default_vision_providers,
    register_vision_provider,
)


@pytest.fixture(autouse=True)
def _isolate_registry():
    clear_vision_registry()
    yield
    clear_vision_registry()


def test_empty_registry_returns_none():
    assert get_vision_provider("anthropic_vision") is None
    assert list_registered_vision_providers() == []


def test_register_then_lookup():
    from substrate.dispatch.providers.vision_anthropic import (
        MockVisionProvider,
    )

    p = MockVisionProvider(name="anthropic_vision")
    register_vision_provider(p)
    assert get_vision_provider("anthropic_vision") is p
    assert "anthropic_vision" in list_registered_vision_providers()


def test_register_default_with_no_keys_returns_empty(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    registered = register_default_vision_providers(quiet=True)
    assert registered == set()


def test_register_default_with_anthropic_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-anthropic")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    registered = register_default_vision_providers(quiet=True)
    assert "anthropic_vision" in registered
    assert get_vision_provider("anthropic_vision") is not None


def test_register_default_with_both_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-openai")
    registered = register_default_vision_providers(quiet=True)
    assert registered == {"anthropic_vision", "openai_vision"}


def test_clear_registry_drops_everything():
    from substrate.dispatch.providers.vision_anthropic import (
        MockVisionProvider,
    )

    register_vision_provider(MockVisionProvider(name="anthropic_vision"))
    register_vision_provider(MockVisionProvider(name="openai_vision"))
    assert len(list_registered_vision_providers()) == 2
    clear_vision_registry()
    assert list_registered_vision_providers() == []
