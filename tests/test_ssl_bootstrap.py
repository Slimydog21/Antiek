from __future__ import annotations

import types

from runtime.ssl_bootstrap import ensure_ssl_cert_env


def test_ssl_bootstrap_preserves_operator_env() -> None:
    env = {
        "SSL_CERT_FILE": "/operator/certs.pem",
        "SSL_CERT_DIR": "/operator",
    }

    result = ensure_ssl_cert_env(env)

    assert result.configured is True
    assert result.source == "env"
    assert env["SSL_CERT_FILE"] == "/operator/certs.pem"
    assert env["SSL_CERT_DIR"] == "/operator"


def test_ssl_bootstrap_sets_certifi_when_env_missing(monkeypatch) -> None:
    fake_certifi = types.SimpleNamespace(where=lambda: "/tmp/certs/cacert.pem")
    monkeypatch.setitem(__import__("sys").modules, "certifi", fake_certifi)
    env: dict[str, str] = {}

    result = ensure_ssl_cert_env(env)

    assert result.configured is True
    assert result.source == "certifi"
    assert env == {
        "SSL_CERT_FILE": "/tmp/certs/cacert.pem",
        "SSL_CERT_DIR": "/tmp/certs",
    }


def test_ssl_bootstrap_does_not_raise_when_certifi_missing(monkeypatch) -> None:
    real_import_module = __import__("importlib").import_module

    def fake_import_module(name: str):
        if name == "certifi":
            raise ModuleNotFoundError("certifi")
        return real_import_module(name)

    monkeypatch.setattr("runtime.ssl_bootstrap.importlib.import_module", fake_import_module)
    env: dict[str, str] = {}

    result = ensure_ssl_cert_env(env)

    assert result.configured is False
    assert result.source == "missing"
    assert "certifi unavailable" in (result.reason or "")
    assert env == {}
