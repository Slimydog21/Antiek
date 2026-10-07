from __future__ import annotations

import json

import pytest

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


def _login_attempt() -> dict[str, object]:
    return {
        "sent": True,
        "attempt_id": "attempt-id-value-for-unit-test-01",
        "claim_secret": "claim-secret-value-for-unit-test-01",
    }


def _request_stage(monkeypatch, payload: object, *, code: int = 200):
    def request(method, url, *, headers, body):
        assert method == "POST"
        assert url == "https://api.antiek.ai/auth/request"
        assert headers["Origin"] == "https://antiek.ai"
        assert json.loads(body) == {"email": "probe@example.invalid"}
        return _response(payload, code=code)

    monkeypatch.setattr(auth_probe, "_request", request)
    return auth_probe.stage_auth_request(
        "https://api.antiek.ai", "https://antiek.ai", "probe@example.invalid"
    )


def test_auth_request_accepts_current_response_model(monkeypatch):
    from interfaces.research.api.auth import AuthRequestResponse

    payload = AuthRequestResponse(**_login_attempt()).model_dump()
    result = _request_stage(monkeypatch, payload)

    assert result.pass_ is True
    assert result.http_code == 200
    assert payload["claim_secret"] not in json.dumps(result.to_json())
    assert payload["attempt_id"] not in json.dumps(result.to_json())


def test_auth_request_allows_additive_response_fields(monkeypatch):
    result = _request_stage(monkeypatch, {**_login_attempt(), "future_field": "value"})

    assert result.pass_ is True


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"sent": True},
        {**_login_attempt(), "sent": False},
        {**_login_attempt(), "sent": 1},
        {**_login_attempt(), "sent": "true"},
        {**_login_attempt(), "attempt_id": None},
        {**_login_attempt(), "attempt_id": 32},
        {**_login_attempt(), "attempt_id": "a" * 15},
        {**_login_attempt(), "attempt_id": "a" * 201},
        {**_login_attempt(), "claim_secret": None},
        {**_login_attempt(), "claim_secret": True},
        {**_login_attempt(), "claim_secret": "s" * 15},
        {**_login_attempt(), "claim_secret": "s" * 201},
    ],
)
def test_auth_request_refuses_unusable_login_attempt_without_disclosure(monkeypatch, payload):
    result = _request_stage(monkeypatch, payload)

    assert result.pass_ is False
    serialized = json.dumps(result.to_json())
    assert _login_attempt()["claim_secret"] not in serialized
    assert _login_attempt()["attempt_id"] not in serialized


@pytest.mark.parametrize("code", [401, 403, 429, 500, 503])
def test_auth_request_rejects_failed_status_without_logging_response(monkeypatch, code):
    result = _request_stage(monkeypatch, _login_attempt(), code=code)

    assert result.pass_ is False
    assert result.http_code == code
    assert _login_attempt()["claim_secret"] not in json.dumps(result.to_json())


def test_auth_request_cli_failure_output_excludes_attempt_credentials(monkeypatch, capsys):
    result = _request_stage(monkeypatch, {**_login_attempt(), "sent": False})
    monkeypatch.setattr(auth_probe, "run_stages", lambda *args: [result])

    assert auth_probe.main([]) == 1
    captured = capsys.readouterr()
    assert _login_attempt()["claim_secret"] not in captured.out + captured.err
    assert _login_attempt()["attempt_id"] not in captured.out + captured.err
    assert json.loads(captured.out)["pass"] is False
