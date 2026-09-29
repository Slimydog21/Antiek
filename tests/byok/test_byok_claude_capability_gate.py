"""Capability-gate tests for Anthropic (Claude) BYOK.

``runtime/byok/anthropic_oauth.py`` performs a Claude.ai credential flow, which
Anthropic's terms do not permit collecting, storing or intermediating.  The
module is therefore retired behind ``ANTIEK_BYOK_CLAUDE`` and carries no
client_id of its own.  These tests pin that contract:

(a) the module holds no hardcoded client id — not as a constant, a string
    literal, or a signature default;
(b) with the flag off the flow fails CLOSED with a typed disabled error, and no
    credential is accepted and no token request is sent;
(c) with the flag on but the operator's registration missing, the error names the
    registration step instead of surfacing a generic auth failure;
(d) with the flag on and a complete registration, the flow constructs normally.

The sibling conftest opts this directory into the capability; these tests clear
it deliberately to observe the closed state.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import httpx
import pytest

from runtime.byok import anthropic_oauth as mod
from runtime.byok.anthropic_oauth import (
    BYOK_CLAUDE_CLIENT_ID_ENV,
    BYOK_CLAUDE_CLIENT_SECRET_ENV,
    BYOK_CLAUDE_FLAG,
    AnthropicAuthError,
    AnthropicAuthFailure,
    AnthropicTokens,
    assert_byok_claude_configured,
    build_authorize_url,
    byok_claude_enabled,
    exchange_authorization_code,
    generate_pkce_pair,
    load_anthropic_tokens,
    refresh_anthropic_token,
    resolve_client_id,
    resolve_client_secret,
    store_anthropic_tokens,
)

# The retired identifier, assembled from fragments rather than stored whole.
#
# The assertion below is "this value must not appear in the module", which is only
# checkable if the test knows the value.  Keeping it as five fragments means the
# literal itself is absent from the tree (the point of the change) while the
# regression test can still detect a reintroduction.  Do not "simplify" this into
# a single literal: that would put the string back into a file on main.
RETIRED_CLIENT_ID = "-".join(("9d1c250a", "e61b", "44d9", "88ed", "5944d1962f5e"))


def _module_source() -> str:
    return Path(mod.__file__).read_text(encoding="utf-8")


def _mock_client(status: int = 200, body: dict[str, Any] | None = None) -> httpx.Client:
    payload = body if body is not None else {
        "access_token": "sk-ant-oat-access",
        "refresh_token": "sk-ant-ort-refresh",
        "expires_in": 3600,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


class TestNoHardcodedRegistration:
    """(a) The module must not carry anyone else's client registration."""

    def test_retired_client_id_literal_absent_from_source(self) -> None:
        source = _module_source()
        assert RETIRED_CLIENT_ID not in source

    def test_constant_is_deleted(self) -> None:
        assert not hasattr(mod, "ANTHROPIC_OAUTH_CLIENT_ID")

    def test_no_signature_defaults_a_client_id(self) -> None:
        for fn in (build_authorize_url, exchange_authorization_code, refresh_anthropic_token):
            default = inspect.signature(fn).parameters["client_id"].default
            assert default is None, f"{fn.__name__} still defaults client_id to {default!r}"

    def test_export_list_names_only_that_which_exists(self) -> None:
        """``__all__`` is a contract: naming a deleted symbol breaks ``import *``."""
        missing = [name for name in mod.__all__ if not hasattr(mod, name)]
        assert missing == [], f"__all__ names missing attributes: {missing}"
        assert "ANTHROPIC_OAUTH_CLIENT_ID" not in mod.__all__

    def test_gate_helpers_are_exported(self) -> None:
        for name in ("byok_claude_enabled", "require_byok_claude", "resolve_client_id",
                     "resolve_client_secret", "assert_byok_claude_configured",
                     "BYOK_CLAUDE_FLAG", "BYOK_CLAUDE_CLIENT_ID_ENV",
                     "BYOK_CLAUDE_CLIENT_SECRET_ENV"):
            assert name in mod.__all__, f"{name} must be part of the public contract"

    def test_no_other_literal_survives_in_the_module(self) -> None:
        """A UUID-shaped literal is a client id by another name."""
        import re

        pattern = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        hits = pattern.findall(_module_source())
        assert hits == [], f"uuid-shaped literal(s) in module source: {hits}"


class TestFlagOff:
    """(b) Fail closed: typed error, nothing accepted, nothing sent."""

    @pytest.fixture(autouse=True)
    def _disable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv(BYOK_CLAUDE_FLAG, raising=False)

    def test_enabled_predicate_is_exact(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert byok_claude_enabled() is False
        for value in ("0", "true", "yes", "", " 1"):
            monkeypatch.setenv(BYOK_CLAUDE_FLAG, value)
            assert byok_claude_enabled() is False, f"{value!r} must not arm the flow"
        monkeypatch.setenv(BYOK_CLAUDE_FLAG, "1")
        assert byok_claude_enabled() is True

    def test_build_authorize_url_raises_typed_disabled(self) -> None:
        with pytest.raises(AnthropicAuthError) as exc:
            build_authorize_url()
        assert exc.value.failure is AnthropicAuthFailure.CAPABILITY_DISABLED
        assert exc.value.terminal is True
        # Local refusal: no HTTP request happened, so there is no status code.
        assert exc.value.status_code == 0
        assert BYOK_CLAUDE_FLAG in exc.value.detail

    def test_exchange_refuses_before_sending_any_request(self) -> None:
        sent: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(request)
            return httpx.Response(200, json={})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(AnthropicAuthError) as exc:
            exchange_authorization_code("code-abc", generate_pkce_pair(), client=client)
        assert exc.value.failure is AnthropicAuthFailure.CAPABILITY_DISABLED
        assert sent == [], "no token request may leave the process while disabled"

    def test_refresh_refuses_before_sending_any_request(self) -> None:
        sent: list[httpx.Request] = []
        client = httpx.Client(transport=httpx.MockTransport(
            lambda request: (sent.append(request), httpx.Response(200, json={}))[1]))
        with pytest.raises(AnthropicAuthError) as exc:
            refresh_anthropic_token("refresh-abc", client=client)
        assert exc.value.failure is AnthropicAuthFailure.CAPABILITY_DISABLED
        assert sent == []

    def test_no_token_row_is_created(self, tmp_path: Path) -> None:
        tokens = AnthropicTokens(access_token="a", refresh_token="r", id_token=None,
                                 expires_at=0.0)
        with pytest.raises(AnthropicAuthError) as exc:
            store_anthropic_tokens(tokens, "user-1",
                                   artifact_path=str(tmp_path / "byok.json"),
                                   key_bytes=b"k" * 32)
        assert exc.value.failure is AnthropicAuthFailure.CAPABILITY_DISABLED
        assert not (tmp_path / "byok.json").exists(), "no store write may happen while disabled"

    def test_load_is_refused_too(self) -> None:
        # A stored token must not be usable while the capability is retired.
        with pytest.raises(AnthropicAuthError) as exc:
            load_anthropic_tokens("cred-1")
        assert exc.value.failure is AnthropicAuthFailure.CAPABILITY_DISABLED


class TestFlagOnWithoutRegistration:
    """(c) Missing registration names the registration step."""

    @pytest.fixture(autouse=True)
    def _enable_no_registration(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(BYOK_CLAUDE_FLAG, "1")
        monkeypatch.delenv(BYOK_CLAUDE_CLIENT_ID_ENV, raising=False)
        monkeypatch.delenv(BYOK_CLAUDE_CLIENT_SECRET_ENV, raising=False)

    def test_missing_client_id_raises_registration_error(self) -> None:
        with pytest.raises(AnthropicAuthError) as exc:
            resolve_client_id()
        assert exc.value.failure is AnthropicAuthFailure.CLIENT_ID_NOT_REGISTERED
        assert BYOK_CLAUDE_CLIENT_ID_ENV in exc.value.detail
        assert "console.anthropic.com" in exc.value.detail, "must point at the registration step"

    def test_missing_client_secret_raises_registration_error(self) -> None:
        with pytest.raises(AnthropicAuthError) as exc:
            resolve_client_secret()
        assert exc.value.failure is AnthropicAuthFailure.CLIENT_ID_NOT_REGISTERED
        assert BYOK_CLAUDE_CLIENT_SECRET_ENV in exc.value.detail

    def test_blank_values_count_as_missing(self) -> None:
        with pytest.raises(AnthropicAuthError):
            resolve_client_id({"ANTIEK_ANTHROPIC_OAUTH_CLIENT_ID": "   "})

    def test_blocked_error_is_not_the_disabled_error(self) -> None:
        # A misconfigured deployment must be distinguishable from a disabled one.
        with pytest.raises(AnthropicAuthError) as exc:
            build_authorize_url()
        assert exc.value.failure is AnthropicAuthFailure.CLIENT_ID_NOT_REGISTERED
        assert exc.value.failure is not AnthropicAuthFailure.CAPABILITY_DISABLED

    def test_startup_check_raises(self) -> None:
        with pytest.raises(AnthropicAuthError) as exc:
            assert_byok_claude_configured()
        assert exc.value.failure is AnthropicAuthFailure.CLIENT_ID_NOT_REGISTERED

    def test_client_secret_alone_is_not_enough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(BYOK_CLAUDE_CLIENT_SECRET_ENV, "secret")
        with pytest.raises(AnthropicAuthError) as exc:
            assert_byok_claude_configured()
        assert BYOK_CLAUDE_CLIENT_ID_ENV in exc.value.detail


class TestFlagOnWithRegistration:
    """(d) A complete registration constructs normally."""

    def test_authorize_url_uses_the_supplied_registration(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(BYOK_CLAUDE_CLIENT_ID_ENV, "operator-client-id")
        monkeypatch.setenv(BYOK_CLAUDE_CLIENT_SECRET_ENV, "operator-secret")
        url, pkce = build_authorize_url()
        assert "client_id=operator-client-id" in url
        assert pkce.code_challenge in url

    def test_explicit_client_id_still_wins(self) -> None:
        url, _ = build_authorize_url(client_id="explicit-id")
        assert "client_id=explicit-id" in url

    def test_startup_check_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(BYOK_CLAUDE_CLIENT_ID_ENV, "operator-client-id")
        monkeypatch.setenv(BYOK_CLAUDE_CLIENT_SECRET_ENV, "operator-secret")
        assert assert_byok_claude_configured() is None

    def test_startup_check_is_a_noop_when_disabled(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(BYOK_CLAUDE_FLAG, raising=False)
        monkeypatch.delenv(BYOK_CLAUDE_CLIENT_ID_ENV, raising=False)
        assert assert_byok_claude_configured() is None

    def test_exchange_completes_with_the_supplied_registration(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(BYOK_CLAUDE_CLIENT_ID_ENV, "operator-client-id")
        monkeypatch.setenv(BYOK_CLAUDE_CLIENT_SECRET_ENV, "operator-secret")
        with _mock_client() as client:
            tokens = exchange_authorization_code("code-abc", generate_pkce_pair(), client=client)
        assert isinstance(tokens, AnthropicTokens)
        assert tokens.access_token == "sk-ant-oat-access"

    def test_exchange_sends_the_resolved_client_id(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(BYOK_CLAUDE_CLIENT_ID_ENV, "operator-client-id")
        monkeypatch.setenv(BYOK_CLAUDE_CLIENT_SECRET_ENV, "operator-secret")
        seen: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _json

            seen.append(_json.loads(request.content))
            return httpx.Response(200, json={"access_token": "a", "refresh_token": "r",
                                             "expires_in": 60})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            exchange_authorization_code("code-abc", generate_pkce_pair(), client=client)
        assert seen and seen[0]["client_id"] == "operator-client-id"
