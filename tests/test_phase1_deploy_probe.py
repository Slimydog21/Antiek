from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tools.ops import phase1_deploy_probe

_SHA = "0123456789abcdef0123456789abcdef01234567"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            payload = {
                "status": "ok",
                "param_version": "test-param-version",
                "schema_version": 7,
                "subscriber_count": 12,
                "registered_providers": ["openrouter"],
                "build_sha": _SHA,
                "flywheel_ready": False,
                "knowledge_reuse_count": 0,
            }
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return
        if self.path == "/marketplace":
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<!doctype html><title>Antiek Marketplace</title>")
            return
        if self.path == "/login":
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"login")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt, *args):
        return


def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()


def test_phase1_deploy_probe_passes_for_health_and_marketplace():
    server = _server()
    base_url = next(server)
    try:
        result = phase1_deploy_probe.probe_phase1_deploy(
            api_url=base_url,
            marketplace_url=f"{base_url}/marketplace",
            expected_sha=_SHA,
            timeout_s=2,
        )
    finally:
        next(server, None)

    assert result.status == "PASS"
    checks = {check.name: check for check in result.checks}
    assert checks["health_post_sprint21_shape"].passed is True
    assert checks["health_expected_sha"].passed is True
    assert checks["marketplace_not_auth_redirect"].passed is True


def test_phase1_deploy_probe_fails_sha_mismatch():
    server = _server()
    base_url = next(server)
    try:
        result = phase1_deploy_probe.probe_phase1_deploy(
            api_url=base_url,
            marketplace_url=f"{base_url}/marketplace",
            expected_sha="abcdef",
            timeout_s=2,
        )
    finally:
        next(server, None)

    assert result.status == "FAIL"
    checks = {check.name: check for check in result.checks}
    assert checks["health_expected_sha"].passed is False


def test_phase1_deploy_probe_fails_auth_marketplace_route():
    server = _server()
    base_url = next(server)
    try:
        result = phase1_deploy_probe.probe_phase1_deploy(
            api_url=base_url,
            marketplace_url=f"{base_url}/login",
            timeout_s=2,
        )
    finally:
        next(server, None)

    assert result.status == "FAIL"
    checks = {check.name: check for check in result.checks}
    assert checks["marketplace_not_auth_redirect"].passed is False


def test_phase1_deploy_probe_json_cli(capsys):
    server = _server()
    base_url = next(server)
    try:
        exit_code = phase1_deploy_probe.main(
            [
                "--api-url",
                base_url,
                "--marketplace-url",
                f"{base_url}/marketplace",
                "--expected-sha",
                _SHA,
                "--timeout",
                "2",
                "--json",
            ]
        )
    finally:
        next(server, None)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["does_not_close_oa009"] is True
