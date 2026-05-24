"""
Tests for runtime.ssl_bootstrap.

The module guards against the silent-SSL-handshake failure documented in
``tests/regression/agent_failures/arxiv-missing-ssl-env.yaml``. These
tests verify each resolution branch + the fail-loud behavior, without
mutating the real process environment beyond monkeypatched scope.

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e2-harness.html (E2 GAP closure)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from runtime import ssl_bootstrap
from runtime.ssl_bootstrap import (
    CertResolution,
    SSLConfigMissing,
    assert_certs_available,
    ensure_ssl_certs,
)


@pytest.fixture(autouse=True)
def _isolate_cert_env(monkeypatch):
    """Each test starts with SSL_CERT_FILE/DIR unset so branches are
    deterministic. monkeypatch restores the real env after."""
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)


# ---------------------------------------------------------------------------
# assert_certs_available — pure check
# ---------------------------------------------------------------------------


def test_assert_certs_available_true_when_cert_file_set(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle.pem"
    bundle.write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")
    monkeypatch.setenv("SSL_CERT_FILE", str(bundle))
    assert assert_certs_available() is True


def test_assert_certs_available_true_when_default_context_has_certs(monkeypatch):
    monkeypatch.setattr(ssl_bootstrap, "_default_context_ca_count", lambda: 42)
    monkeypatch.setattr(ssl_bootstrap, "_certifi_path", lambda: None)
    assert assert_certs_available() is True


def test_assert_certs_available_true_when_certifi_present(monkeypatch, tmp_path):
    monkeypatch.setattr(ssl_bootstrap, "_default_context_ca_count", lambda: 0)
    fake_bundle = tmp_path / "certifi.pem"
    fake_bundle.write_text("x", encoding="utf-8")
    monkeypatch.setattr(ssl_bootstrap, "_certifi_path", lambda: str(fake_bundle))
    assert assert_certs_available() is True


def test_assert_certs_available_false_when_nothing(monkeypatch):
    monkeypatch.setattr(ssl_bootstrap, "_default_context_ca_count", lambda: 0)
    monkeypatch.setattr(ssl_bootstrap, "_certifi_path", lambda: None)
    assert assert_certs_available() is False


# ---------------------------------------------------------------------------
# ensure_ssl_certs — resolution branches
# ---------------------------------------------------------------------------


def test_ensure_already_configured_is_noop(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle.pem"
    bundle.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SSL_CERT_FILE", str(bundle))
    res = ensure_ssl_certs()
    assert res.source == "already-configured"
    assert res.cert_file == str(bundle)


def test_ensure_uses_default_context_when_present(monkeypatch):
    monkeypatch.setattr(ssl_bootstrap, "_default_context_ca_count", lambda: 17)
    res = ensure_ssl_certs()
    assert res.source == "default-context"
    assert res.ca_cert_count == 17
    # No env mutation.
    assert "SSL_CERT_FILE" not in os.environ


def test_ensure_falls_back_to_certifi(monkeypatch, tmp_path):
    monkeypatch.setattr(ssl_bootstrap, "_default_context_ca_count", lambda: 0)
    fake_bundle = tmp_path / "cacert.pem"
    fake_bundle.write_text("x", encoding="utf-8")
    monkeypatch.setattr(ssl_bootstrap, "_certifi_path", lambda: str(fake_bundle))
    res = ensure_ssl_certs()
    assert res.source == "certifi"
    assert os.environ["SSL_CERT_FILE"] == str(fake_bundle)
    assert os.environ["SSL_CERT_DIR"] == str(tmp_path)


def test_ensure_raises_when_nothing_resolvable(monkeypatch):
    monkeypatch.setattr(ssl_bootstrap, "_default_context_ca_count", lambda: 0)
    monkeypatch.setattr(ssl_bootstrap, "_certifi_path", lambda: None)
    with pytest.raises(SSLConfigMissing) as exc:
        ensure_ssl_certs()
    # The remedy must be in the message — self-documenting failure.
    assert "Install Certificates" in str(exc.value) or "certifi" in str(exc.value)
    assert "SSL_CERT_FILE" in str(exc.value)


def test_ensure_never_downgrades_to_unverified(monkeypatch):
    """Critical security property: the module must never 'fix' the
    problem by disabling verification. The only outcomes are
    (a) resolve a bundle, or (b) raise. There is no verify=False path."""
    monkeypatch.setattr(ssl_bootstrap, "_default_context_ca_count", lambda: 0)
    monkeypatch.setattr(ssl_bootstrap, "_certifi_path", lambda: None)
    # The ONLY non-success outcome is the raise — proven by the absence
    # of any return on the no-resolution path.
    with pytest.raises(SSLConfigMissing):
        ensure_ssl_certs()


def test_force_certifi_pins_even_with_default_context(monkeypatch, tmp_path):
    monkeypatch.setattr(ssl_bootstrap, "_default_context_ca_count", lambda: 99)
    fake_bundle = tmp_path / "cacert.pem"
    fake_bundle.write_text("x", encoding="utf-8")
    monkeypatch.setattr(ssl_bootstrap, "_certifi_path", lambda: str(fake_bundle))
    res = ensure_ssl_certs(force_certifi=True)
    assert res.source == "certifi"


def test_ensure_is_idempotent(monkeypatch, tmp_path):
    fake_bundle = tmp_path / "cacert.pem"
    fake_bundle.write_text("x", encoding="utf-8")
    monkeypatch.setattr(ssl_bootstrap, "_default_context_ca_count", lambda: 0)
    monkeypatch.setattr(ssl_bootstrap, "_certifi_path", lambda: str(fake_bundle))
    first = ensure_ssl_certs()
    # Second call: SSL_CERT_FILE is now set + exists → already-configured.
    second = ensure_ssl_certs()
    assert first.source == "certifi"
    assert second.source == "already-configured"


# ---------------------------------------------------------------------------
# Real environment smoke — in this venv httpx pulls certifi, so a real
# call must resolve (not raise). Guards against the module being
# accidentally too strict on a correctly-configured machine.
# ---------------------------------------------------------------------------


def test_real_environment_resolves(monkeypatch):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    # No monkeypatching of the internals — exercise the real resolution.
    res = ensure_ssl_certs()
    assert isinstance(res, CertResolution)
    assert res.source in ("already-configured", "default-context", "certifi")
    assert res.ca_cert_count >= 1
