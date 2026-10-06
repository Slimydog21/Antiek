"""Dev-login transport contract using disposable credentials and the real API app."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.auth import SESSION_COOKIE_NAME

_TOKEN = "synthetic-dev-login-" + "q" * 40
_SECRET = "synthetic-session-secret-" + "x" * 48
_PATH = "/auth/dev-login"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ANTIEK_DEV_LOGIN_TOKEN", _TOKEN)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "operator@example.com")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_FRONTEND_BASE_URL", "http://testserver")
    for key in (
        "ANTIEK_OPERATOR_TOKEN", "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET", "ANTIEK_COOKIE_DOMAIN",
    ):
        monkeypatch.delenv(key, raising=False)
    return TestClient(
        create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    )


def _no_grant(response) -> None:
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert SESSION_COOKIE_NAME not in response.cookies
    assert "set-cookie" not in response.headers
    assert "location" not in response.headers


def test_get_query_credential_never_authenticates(client: TestClient) -> None:
    response = client.get(_PATH, params={"token": _TOKEN}, follow_redirects=False)
    _no_grant(response)
    assert client.get("/auth/me").status_code == 401


def test_get_bootstrap_is_token_free_and_does_not_mint_cookie(client: TestClient) -> None:
    response = client.get(_PATH, params={"next": "/memory"}, follow_redirects=False)
    assert response.status_code == 200
    assert 'method="post"' in response.text
    assert 'name="token"' in response.text
    assert 'type="password"' in response.text
    assert _TOKEN not in response.text
    assert SESSION_COOKIE_NAME not in response.cookies
    assert "set-cookie" not in response.headers
    assert client.get("/auth/me").status_code == 401


def test_form_post_sets_browser_cookie_without_url_credential(client: TestClient) -> None:
    response = client.post(
        _PATH, data={"token": _TOKEN, "next": "/memory"}, follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.request.url.path == _PATH
    assert not response.request.url.query
    assert _TOKEN not in response.headers.get("location", "")
    assert _TOKEN not in response.text
    assert SESSION_COOKIE_NAME in response.cookies
    assert response.headers["location"] == "http://testserver/memory"
    identity = client.get("/auth/me")
    assert identity.status_code == 200
    assert identity.json()["auth_method"] == "antiek_session_cookie"


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        ({"next": "/"}, None),
        ({"token": "wrong-synthetic-token"}, None),
        ({"token": _TOKEN, "next": "//evil.example/x"}, "application/json"),
        (f"token={_TOKEN}&token=duplicate", "application/x-www-form-urlencoded"),
        (f"token={_TOKEN}%GG", "application/x-www-form-urlencoded"),
        ("token=%C3%A9", "application/x-www-form-urlencoded"),
        ("token=%FF", "application/x-www-form-urlencoded"),
        ("token=" + "x" * 8192, "application/x-www-form-urlencoded"),
    ],
    ids=[
        "missing", "wrong", "wrong-mime", "duplicate", "bad-percent",
        "non-ascii", "bad-utf8", "oversized",
    ],
)
def test_refused_form_never_reflects_credential(
    client: TestClient, body: object, content_type: str | None,
) -> None:
    kwargs = {"headers": {"Content-Type": content_type}} if content_type else {}
    response = client.post(_PATH, data=body, follow_redirects=False, **kwargs)
    _no_grant(response)
    assert _TOKEN not in response.text


def test_form_post_disabled_and_missing_secret_are_indistinguishable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("ANTIEK_DEV_LOGIN_TOKEN", "ANTIEK_AUTH_SECRET"):
        with monkeypatch.context() as absent:
            absent.delenv(key)
            response = client.post(_PATH, data={"token": _TOKEN}, follow_redirects=False)
            _no_grant(response)


def test_form_post_restricts_next_redirect(client: TestClient) -> None:
    response = client.post(
        _PATH, data={"token": _TOKEN, "next": "//evil.example/x"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "http://testserver/"
    assert "evil.example" not in response.headers["location"]


def test_form_post_rejects_query_even_with_valid_body(client: TestClient) -> None:
    response = client.post(
        _PATH, params={"token": _TOKEN}, data={"token": _TOKEN},
        follow_redirects=False,
    )
    _no_grant(response)


def test_non_ascii_configured_token_refuses_before_comparison(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_DEV_LOGIN_TOKEN", "synthetic-nonascii-\u00e9")
    response = client.post(_PATH, data={"token": "ascii-probe"})
    _no_grant(response)


def test_get_form_escapes_next_and_never_uses_query_credential(client: TestClient) -> None:
    response = client.get(_PATH, params={"next": '/"><script>alert(1)</script>'})
    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&quot;&gt;&lt;script&gt;" in response.text
    refused = client.get(_PATH, params={"token": _TOKEN, "next": "/"})
    _no_grant(refused)


def test_mac_mini_curl_mode_sends_token_only_in_body(tmp_path: Path) -> None:
    observed: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if observed.get("deny"):
                self.send_response(404)
                self.end_headers()
                return
            observed["target"] = self.path
            observed["body"] = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(302)
            self.send_header("Location", "/memory")
            self.end_headers()

        def do_GET(self) -> None:
            observed["get_count"] = int(observed.get("get_count", 0)) + 1
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"auth_method":"antiek_session_cookie"}')

        def log_message(self, format: str, *args: object) -> None:
            observed.setdefault("access_lines", []).append(format % args)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        real_curl = shutil.which("curl")
        python3 = shutil.which("python3")
        assert real_curl is not None
        assert python3 is not None
        argv_log = tmp_path / "curl-argv.jsonl"
        curl_wrapper = tmp_path / "curl-capture"
        curl_wrapper.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            f"with open({str(argv_log)!r}, 'a', encoding='utf-8') as log:\n"
            "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            f"os.execv({real_curl!r}, [{real_curl!r}, *sys.argv[1:]])\n"
        )
        curl_wrapper.chmod(0o700)
        bash_env = tmp_path / "bash-env"
        bash_env.write_text(f'curl() {{ {shlex.quote(str(curl_wrapper))} "$@"; }}\n')
        (tmp_path / ".curlrc").write_text("")
        env = {
            "PATH": os.pathsep.join((str(Path(python3).parent), "/usr/bin", "/bin")),
            "CURL_HOME": str(tmp_path),
            "BASH_ENV": str(bash_env),
            "ANTIEK_PLATFORM": str(tmp_path),
            "ANTIEK_API_BASE_URL": f"http://127.0.0.1:{server.server_port}",
            "ANTIEK_OWNER_LOGIN_MODE": "curl",
            "ANTIEK_COOKIE_JAR": str(tmp_path / "cookies"),
            "ANTIEK_DEV_LOGIN_TOKEN": _TOKEN,
            "ANTIEK_AUTH_SECRET": _SECRET,
        }
        script = Path(__file__).resolve().parents[1] / "scripts/mac-mini-owner-dev-login.sh"
        completed = subprocess.run(
            ["bash", str(script), "/memory"], env=env,
            capture_output=True, text=True, timeout=15, check=False,
        )
        assert completed.returncode == 0
        assert observed["target"] == _PATH
        body = parse_qs(observed["body"].decode("ascii"))
        assert body["token"] == [_TOKEN]
        assert body["next"] == ["/memory"]
        curl_argv = [json.loads(line) for line in argv_log.read_text().splitlines()]
        dev_login_url = f"{env['ANTIEK_API_BASE_URL']}{_PATH}"
        post_argv = [argv for argv in curl_argv if dev_login_url in argv]
        assert len(post_argv) == 1
        assert post_argv[0][post_argv[0].index("--data-binary") + 1] == "@-"
        assert _TOKEN not in json.dumps(curl_argv)
        assert _TOKEN not in completed.stdout + completed.stderr
        assert _TOKEN not in "\n".join(observed["access_lines"])
        assert not list(tmp_path.glob("*.html"))

        # A stale cookie jar must not make a denied bootstrap look successful.
        (tmp_path / "cookies").write_text(
            "# Netscape HTTP Cookie File\n"
            "127.0.0.1\tFALSE\t/\tFALSE\t0\tANTIEK_SESSION\tstale\n"
        )
        observed["deny"] = True
        denied = subprocess.run(
            ["bash", str(script), "/memory"], env=env,
            capture_output=True, text=True, timeout=15, check=False,
        )
        assert denied.returncode != 0
        assert observed["get_count"] == 1
        assert "auth_method" not in denied.stdout
        assert _TOKEN not in denied.stdout + denied.stderr
        assert _TOKEN not in argv_log.read_text()
        assert _TOKEN not in "\n".join(observed["access_lines"])
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
