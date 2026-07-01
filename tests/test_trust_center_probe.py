from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tools.ops import trust_center_probe


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/trust":
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<!doctype html><title>Antiek Trust Center</title>")
            return
        if self.path == "/trust-center":
            payload = {
                "differential_privacy_epsilon_budgets": {
                    "query_content_telemetry": 1.0,
                },
                "deletion_sla_days": 30,
                "substrate_controls": ["retrieval-time policy_tag gating"],
                "compliance_frameworks": ["GDPR Article 13/14 transparency"],
                "loop_3_unlock_status": {"trajectory_volume": False},
            }
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
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


def test_trust_center_probe_passes_for_public_page_and_api():
    server = _server()
    base_url = next(server)
    try:
        result = trust_center_probe.probe_trust_center(
            app_url=f"{base_url}/trust",
            api_url=f"{base_url}/trust-center",
            timeout_s=2,
        )
    finally:
        next(server, None)

    assert result.status == "PASS"
    checks = {check.name: check for check in result.checks}
    assert checks["app_not_auth_redirect"].passed is True
    assert checks["api_publication_shape"].passed is True
    assert checks["api_dp_budgets_present"].passed is True


def test_trust_center_probe_fails_auth_route():
    server = _server()
    base_url = next(server)
    try:
        result = trust_center_probe.probe_trust_center(
            app_url=f"{base_url}/login",
            api_url=None,
            timeout_s=2,
        )
    finally:
        next(server, None)

    assert result.status == "FAIL"
    checks = {check.name: check for check in result.checks}
    assert checks["app_not_auth_redirect"].passed is False


def test_trust_center_probe_reports_unreachable_url():
    result = trust_center_probe.probe_trust_center(
        app_url="http://127.0.0.1:9/trust",
        api_url=None,
        timeout_s=0.2,
    )

    assert result.status == "FAIL"
    checks = {check.name: check for check in result.checks}
    assert checks["app_http_2xx"].detail.startswith("status=0")


def test_trust_center_probe_json_cli(capsys):
    server = _server()
    base_url = next(server)
    try:
        exit_code = trust_center_probe.main(
            [
                "--app-url",
                f"{base_url}/trust",
                "--api-url",
                f"{base_url}/trust-center",
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
    assert payload["does_not_close_oa013"] is True
