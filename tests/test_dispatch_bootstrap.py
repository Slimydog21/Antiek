"""Tests for substrate.dispatch.providers.bootstrap (Sprint 10 hotfix).

The bug this guards against: real-LLM cold-question runs failing at
phase 1 because no Provider implementation was registered with the
router. The bootstrap module wires config.yaml provider names to
concrete adapter instances at create_app() startup; this test suite
locks in that contract.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.dispatch.providers import register_default_providers
from substrate.dispatch.router import (
    _PROVIDER_REGISTRY,
    get_provider,
    reset_provider_registry,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test starts from an empty registry so order doesn't matter."""
    reset_provider_registry()
    yield
    reset_provider_registry()


def test_no_keys_registers_nothing(monkeypatch):
    """Missing API keys → no providers registered. Degraded posture,
    not an error."""
    for k in (
        "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
        "XIAOMI_API_KEY", "HERMES_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    registered = register_default_providers(quiet=True)
    assert registered == set()
    assert len(_PROVIDER_REGISTRY) == 0


def test_deepseek_key_registers_deepseek_only(monkeypatch):
    for k in (
        "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
        "XIAOMI_API_KEY", "HERMES_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-1")
    registered = register_default_providers(quiet=True)
    assert registered == {"deepseek"}
    assert get_provider("deepseek").name == "deepseek"


def test_both_keys_registers_both(monkeypatch):
    for k in ("OPENROUTER_API_KEY", "XIAOMI_API_KEY", "HERMES_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-1")
    registered = register_default_providers(quiet=True)
    assert registered == {"deepseek", "anthropic"}


def test_idempotent(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-1")
    register_default_providers(quiet=True)
    first_instance = get_provider("deepseek")
    register_default_providers(quiet=True)
    second_instance = get_provider("deepseek")
    # Same name → registry replaces but doesn't error.
    assert second_instance.name == "deepseek"


def test_only_filter(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-1")
    registered = register_default_providers(quiet=True, only=["deepseek"])
    assert registered == {"deepseek"}
    assert "anthropic" not in _PROVIDER_REGISTRY


def test_hermes_provider_url_does_not_double_v1(monkeypatch):
    """Regression for the 2026-05-18 production incident.

    The Hermes bootstrap shipped without ``chat_completions_path``
    override, so it used the default ``/v1/chat/completions``. With
    ``ANTIEK_HERMES_BASE_URL=https://hermes-bridge.antiek.ai/v1`` (the
    natural posture matching OpenRouter), the constructed URL became
    ``/v1/v1/chat/completions`` and the Cloudflare-tunneled proxy 404'd
    every single call as ``path_not_allowed``. The substrate's
    fallback chain silently routed 100% of inference to OpenRouter
    while ``/health.registered_providers`` still reported ``hermes`` —
    a true silent-failure-via-fallback case.

    Lock in: Hermes URL must end with exactly one ``/v1/chat/completions``
    when the env var carries the ``/v1`` suffix."""
    monkeypatch.setenv("HERMES_API_KEY", "hb_test")
    monkeypatch.setenv(
        "ANTIEK_HERMES_BASE_URL", "https://hermes-bridge.antiek.ai/v1",
    )
    for k in (
        "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY", "XIAOMI_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    register_default_providers(quiet=True)
    hermes = get_provider("hermes")
    constructed = hermes.base_url + hermes.chat_completions_path
    assert constructed == "https://hermes-bridge.antiek.ai/v1/chat/completions", (
        f"Hermes URL is {constructed!r}; expected exactly one /v1/. "
        f"Double-/v1/ would route every call to the proxy's 'path_not_allowed' "
        f"branch and silently fail through to fallback."
    )
    assert hermes.chat_completions_path == "/chat/completions", (
        "Hermes must override chat_completions_path so the env var carries "
        "the /v1 prefix (matching OpenRouter's pattern). The provider's "
        "default of /v1/chat/completions is unsafe for Hermes deployments "
        "whose base URL already includes /v1."
    )


def test_create_app_auto_registers_in_default_mode(monkeypatch):
    """The bug we hit on 2026-05-17: production create_app() must
    register providers. Without this wiring, /health.registered_providers
    is [] and the first dispatch raises Provider 'deepseek' not
    registered."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-1")
    from interfaces.research.api.app import create_app

    app = create_app(register_wrestling=False)
    assert "deepseek" in app.state.registered_providers
    assert "anthropic" in app.state.registered_providers


def test_create_app_register_providers_false_skips(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-1")
    from interfaces.research.api.app import create_app

    app = create_app(
        register_wrestling=False, register_providers=False,
    )
    assert app.state.registered_providers == set()


def test_health_endpoint_reports_registered_providers(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-1")
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    app = create_app(register_wrestling=False)
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert sorted(body["registered_providers"]) == ["anthropic", "deepseek"]
