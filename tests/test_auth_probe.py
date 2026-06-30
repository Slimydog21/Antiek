"""Contract tests for the staged magic-link auth probe (SPR-04)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools import auth_probe  # noqa: E402


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_stage_result_json_uses_wire_pass_key():
    result = auth_probe.StageResult(
        name="health",
        layer="A",
        pass_=True,
        http_code=200,
        detail="status ok",
    )

    assert result.to_json() == {
        "name": "health",
        "layer": "A",
        "pass": True,
        "http_code": 200,
        "detail": "status ok",
    }


def test_validate_base_url_normalizes_origin_and_rejects_pathless_host():
    assert (
        auth_probe._validate_base_url(" https://api.antiek.ai/some/path?x=1 ")
        == "https://api.antiek.ai"
    )

    try:
        auth_probe._validate_base_url("api.antiek.ai")
    except ValueError as exc:
        assert "invalid --base-url" in str(exc)
    else:
        raise AssertionError("pathless host without scheme must be rejected")


def test_run_stages_success_contract(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 15.0,
    ) -> tuple[int, dict[str, str], bytes]:
        del timeout
        calls.append((method, url))
        if method == "GET" and url.endswith("/health"):
            return 200, {}, _json_bytes({"status": "ok"})
        if method == "OPTIONS" and url.endswith("/auth/request"):
            assert headers and headers["Origin"] == "https://antiek.ai"
            return (
                204,
                {
                    "access-control-allow-origin": "https://antiek.ai",
                    "access-control-allow-methods": "GET,POST,OPTIONS",
                },
                b"",
            )
        if method == "POST" and url.endswith("/auth/request"):
            assert headers and headers["Origin"] == "https://antiek.ai"
            assert json.loads((body or b"{}").decode("utf-8")) == {
                "email": "probe@example.com"
            }
            return 200, {}, _json_bytes({"sent": True})
        if method == "GET" and url.endswith("/auth/me"):
            return (
                401,
                {},
                _json_bytes({"error": {"code": "operator_auth_required"}}),
            )
        raise AssertionError(f"unexpected request {method} {url}")

    monkeypatch.setattr(auth_probe, "_request", fake_request)

    results = auth_probe.run_stages(
        "https://api.antiek.ai",
        "https://antiek.ai",
        "probe@example.com",
    )

    assert [stage.name for stage in results] == [
        "health",
        "cors_preflight_auth_request",
        "auth_request_dry_run",
        "auth_me_without_cookie",
    ]
    assert [stage.layer for stage in results] == ["A", "A", "B", "B"]
    assert all(stage.pass_ for stage in results)
    assert calls == [
        ("GET", "https://api.antiek.ai/health"),
        ("OPTIONS", "https://api.antiek.ai/auth/request"),
        ("POST", "https://api.antiek.ai/auth/request"),
        ("GET", "https://api.antiek.ai/auth/me"),
    ]


def test_stage_cors_preflight_rejects_origin_mismatch(monkeypatch):
    monkeypatch.setattr(
        auth_probe,
        "_request",
        lambda *a, **kw: (
            204,
            {
                "access-control-allow-origin": "https://wrong.example",
                "access-control-allow-methods": "POST",
            },
            b"",
        ),
    )

    result = auth_probe.stage_cors_preflight(
        "https://api.antiek.ai",
        "https://antiek.ai",
    )

    assert not result.pass_
    assert result.http_code == 204
    assert "Allow-Origin" in result.detail


def test_stage_auth_me_requires_structured_operator_auth_error(monkeypatch):
    monkeypatch.setattr(
        auth_probe,
        "_request",
        lambda *a, **kw: (401, {}, _json_bytes({"error": {"code": "wrong"}})),
    )

    result = auth_probe.stage_auth_me_unauthenticated("https://api.antiek.ai")

    assert not result.pass_
    assert result.http_code == 401
    assert "operator_auth_required" in result.detail


def test_stage_health_transport_error_is_stage_failure(monkeypatch):
    def raise_url_error(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(auth_probe, "_request", raise_url_error)

    result = auth_probe.stage_health("https://api.antiek.ai")

    assert not result.pass_
    assert result.http_code is None
    assert "GET /health failed" in result.detail


def test_main_invalid_base_url_exits_two_and_writes_json_error(capsys):
    rc = auth_probe.main(["--base-url", "api.antiek.ai"])

    captured = capsys.readouterr()
    assert rc == 2
    assert json.loads(captured.err)["error"].startswith("invalid --base-url")


def test_main_outputs_stage_json_and_maps_failure_to_exit_one(monkeypatch, capsys):
    def fake_run_stages(base_url: str, origin: str, email: str) -> list[auth_probe.StageResult]:
        assert base_url == "https://api.antiek.ai"
        assert origin == "https://antiek.ai"
        assert email == "mixed@example.com"
        return [
            auth_probe.StageResult("health", "A", True, 200, "status ok"),
            auth_probe.StageResult("auth_request_dry_run", "B", False, 500, "boom"),
        ]

    monkeypatch.setattr(auth_probe, "run_stages", fake_run_stages)

    rc = auth_probe.main(
        [
            "--base-url",
            "https://api.antiek.ai/path",
            "--origin",
            " https://antiek.ai ",
            "--email",
            " Mixed@Example.COM ",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    lines = [json.loads(line) for line in captured.out.splitlines()]
    assert lines == [
        {
            "name": "health",
            "layer": "A",
            "pass": True,
            "http_code": 200,
            "detail": "status ok",
        },
        {
            "name": "auth_request_dry_run",
            "layer": "B",
            "pass": False,
            "http_code": 500,
            "detail": "boom",
        },
    ]
