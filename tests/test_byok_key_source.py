"""Tests for BYOK-first provider key resolution (``byok_key_source``).

Exercises the real resolver logic; the BYOK store's ``list_credentials`` /
``load_credential`` are monkeypatched (no artifact / master key needed) and the
environment is controlled per test.
"""

from __future__ import annotations

import pytest

from runtime.byok import store as byok_store
from runtime.byok.secret_str import SecretStr
from substrate.dispatch.providers import byok_key_source as ks


def _meta(pipeline_kind: str, cred_id: str = "c1") -> byok_store.CredentialMetadata:
    return byok_store.CredentialMetadata(
        cred_id=cred_id, account_handle="operator", pipeline_kind=pipeline_kind
    )


@pytest.fixture(autouse=True)
def _clean_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default posture in every test: BYOT-only OFF (env fallback active) unless
    # a test opts in explicitly.
    monkeypatch.delenv("ANTIEK_BYOT_ONLY", raising=False)


def test_env_fallback_when_no_byok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(byok_store, "list_credentials", lambda **k: [])
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "env-key"


def test_byok_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        byok_store, "list_credentials", lambda **k: [_meta("provider:deepseek")]
    )
    monkeypatch.setattr(
        byok_store, "load_credential", lambda cred_id, **k: SecretStr("byok-key")
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "byok-key"


def test_byot_only_no_byok_refuses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(byok_store, "list_credentials", lambda **k: [])
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    monkeypatch.setenv("ANTIEK_BYOT_ONLY", "1")
    # Env key present but flag says BYOT-only + nothing onboarded → honest None,
    # NOT a silent spend on the env key the operator meant to retire.
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") is None


def test_byot_only_uses_byok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        byok_store, "list_credentials", lambda **k: [_meta("provider:deepseek")]
    )
    monkeypatch.setattr(
        byok_store, "load_credential", lambda cred_id, **k: SecretStr("byok-key")
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("ANTIEK_BYOT_ONLY", "true")
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "byok-key"


def test_handle_namespacing_ignores_other_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A stored credential for a DIFFERENT provider must not leak into deepseek.
    monkeypatch.setattr(
        byok_store, "list_credentials", lambda **k: [_meta("provider:anthropic")]
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "env-key"


def test_non_provider_pipeline_kinds_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An ingest/tool credential (e.g. pipeline_kind="x_ingest") is never treated
    # as a dispatch key.
    monkeypatch.setattr(
        byok_store, "list_credentials", lambda **k: [_meta("x_ingest"), _meta("deepseek")]
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    # Neither "x_ingest" nor bare "deepseek" (missing the provider: prefix) match.
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "env-key"


def test_unreadable_store_degrades_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**k):
        raise RuntimeError("no artifact / permission denied")

    monkeypatch.setattr(byok_store, "list_credentials", boom)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    # A broken store must never take down provider bootstrap.
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "env-key"


def test_undecryptable_credential_degrades_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        byok_store, "list_credentials", lambda **k: [_meta("provider:deepseek")]
    )

    def boom(cred_id, **k):
        raise ValueError("master key missing / rotated")

    monkeypatch.setattr(byok_store, "load_credential", boom)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    # Ciphertext present but undecryptable → warn + env fallback, never crash.
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "env-key"


def test_no_key_anywhere_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(byok_store, "list_credentials", lambda **k: [])
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") is None


def test_byot_only_flag_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    for truthy in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("ANTIEK_BYOT_ONLY", truthy)
        assert ks.byot_only_enabled() is True
    for falsy in ("0", "false", "no", "", "off"):
        monkeypatch.setenv("ANTIEK_BYOT_ONLY", falsy)
        assert ks.byot_only_enabled() is False
