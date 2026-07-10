from __future__ import annotations

import json

from tools import auth_probe


def _response(payload: object, *, code: int = 200) -> tuple[int, dict[str, str], bytes]:
    return code, {}, json.dumps(payload).encode()


def test_passkey_status_accepts_public_privacy_preserving_shape(monkeypatch):
    monkeypatch.setattr(
        auth_probe,
        "_request",
        lambda method, url: _response({"available": True, "count": None}),
    )

    result = auth_probe.stage_passkey_status_unauthenticated("https://api.antiek.ai")

    assert result.pass_ is True
    assert result.http_code == 200


def test_passkey_status_rejects_auth_middleware_interception(monkeypatch):
    monkeypatch.setattr(
        auth_probe,
        "_request",
        lambda method, url: _response(
            {"error": {"code": "operator_auth_required"}},
            code=401,
        ),
    )

    result = auth_probe.stage_passkey_status_unauthenticated("https://api.antiek.ai")

    assert result.pass_ is False
    assert result.http_code == 401


def test_passkey_status_rejects_logged_out_credential_count_leak(monkeypatch):
    monkeypatch.setattr(
        auth_probe,
        "_request",
        lambda method, url: _response({"available": True, "count": 2}),
    )

    result = auth_probe.stage_passkey_status_unauthenticated("https://api.antiek.ai")

    assert result.pass_ is False
