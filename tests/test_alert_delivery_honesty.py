"""Alert-delivery honesty for tools/ops/health_probe.sh.

The defect this pins down (audit: .audit/2026-10-01-anatomy/
LITERAL-STATUS-AUDIT.md section 1.9): the probe's webhook POST was
``curl -sS ... || true`` — no ``-f``, no ``--max-time``, exit code
discarded. Measured before the fix (real curl, local sink):

- sink answers HTTP 500          -> probe exit 1, ZERO delivery-failure
  trace (curl without -f treats an HTTP error as success);
- sink connection refused        -> probe exit 1, only curl's incidental
  "curl: (7)" line; the run is indistinguishable from a delivered one;
- sink accepts, never responds   -> the POST had no timeout: the probe
  hung past 60s (systemd's TimeoutStartSec would SIGTERM it);
- sink answers 200 (delivered)   -> probe exit 1, same observable record
  as every failure above.

A failed alert looked exactly like a delivered one — the same defect
PR #3663's write-path alert would have ridden. These tests run the real
script with real curl and real jq against a real local HTTP sink, the
pattern from tests/test_frame_write_health.py's probe end-to-end tests.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "ops" / "health_probe.sh"
MARKER = "ALERT DELIVERY FAILED"


class _Sink(BaseHTTPRequestHandler):
    """Local stand-in for the API, the bridge, and the webhook sink.

    Class attributes are set per test before the server starts.
    """

    hook_status: int = 200
    fail_first_n_posts: int = 0
    posts: list[str] = []
    bridge_authenticated: bool = False  # False -> BRIDGE UNAUTH alert fires
    ratio_alert: bool = False

    def log_message(self, *args: object) -> None:  # keep test output clean
        pass

    def _json(self, body: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/bridge/health"):
            auth = "true" if type(self).bridge_authenticated else "false"
            self._json(f'{{"status":"ok","authenticated":{auth}}}'.encode())
        elif self.path.startswith("/ops/provider-ratio"):
            alert = "true" if type(self).ratio_alert else "false"
            self._json(f'{{"alert_recommended":{alert}}}'.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        cls = type(self)
        length = int(self.headers.get("Content-Length") or 0)
        cls.posts.append(self.rfile.read(length).decode())
        if cls.fail_first_n_posts > 0:
            cls.fail_first_n_posts -= 1
            self._json(b'{"error":"transient"}', status=500)
            return
        self._json(b"ok", status=cls.hook_status)


def _start_sink(**attrs: object) -> tuple[HTTPServer, int]:
    for key, value in attrs.items():
        setattr(_Sink, key, value)
    server = HTTPServer(("127.0.0.1", 0), _Sink)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _closed_port() -> int:
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _run_probe(port: int, webhook_url: str | None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["ANTIEK_BRIDGE_URL"] = f"http://127.0.0.1:{port}/bridge"
    env["ANTIEK_API_URL"] = f"http://127.0.0.1:{port}"
    env["ANTIEK_ALERT_RETRY_DELAY"] = "0"  # keep the failure tests fast
    if webhook_url is None:
        env.pop("ANTIEK_ALERT_WEBHOOK", None)
    else:
        env["ANTIEK_ALERT_WEBHOOK"] = webhook_url
    return subprocess.run(
        ["bash", str(PROBE)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture(autouse=True)
def _require_tools():
    for tool in ("curl", "jq"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} not installed")
    _Sink.posts = []
    _Sink.fail_first_n_posts = 0
    _Sink.hook_status = 200
    _Sink.bridge_authenticated = False
    _Sink.ratio_alert = False
    yield


def test_sink_http_error_is_an_observable_delivery_failure() -> None:
    """The defect class: sink answers 500. Before the fix this left zero
    trace (curl had no -f and || true ate the rest). Now: exit 2 plus a
    greppable journal marker, and the alert text still lands on stderr."""
    server, port = _start_sink(hook_status=500)
    try:
        result = _run_probe(port, f"http://127.0.0.1:{port}/hook")
    finally:
        server.shutdown()
        server.server_close()
    print(result.stderr)
    assert result.returncode == 2
    assert MARKER in result.stderr
    assert "BRIDGE UNAUTH" in result.stderr  # the alert still has a record
    assert len(_Sink.posts) == 2  # one bounded retry, not a storm


def test_sink_unreachable_is_an_observable_delivery_failure() -> None:
    """Connection refused: before the fix, exit 1 with only curl's
    incidental error line. Now: exit 2 plus the marker."""
    server, port = _start_sink(hook_status=200)
    dead = _closed_port()
    try:
        result = _run_probe(port, f"http://127.0.0.1:{dead}/hook")
    finally:
        server.shutdown()
        server.server_close()
    print(result.stderr)
    assert result.returncode == 2
    assert MARKER in result.stderr
    assert "BRIDGE UNAUTH" in result.stderr


def test_delivery_failure_marker_never_leaks_the_webhook_path() -> None:
    """Slack-style webhook URLs carry a secret in the path. The journal
    marker may name the origin, never the path."""
    server, port = _start_sink(hook_status=500)
    secret = "T000SECRET/B000SECRET/secret-token-value"
    try:
        result = _run_probe(port, f"http://127.0.0.1:{port}/hook/{secret}")
    finally:
        server.shutdown()
        server.server_close()
    print(result.stderr)
    assert result.returncode == 2
    assert MARKER in result.stderr
    assert secret not in result.stderr
    assert "/hook/" not in result.stderr.split(MARKER)[1].splitlines()[0]


def test_delivered_alert_exits_1_with_no_false_alarm() -> None:
    """Success must not cry delivery-wolf: exit 1 (alert fired, delivered),
    no marker, and the sink received the alert text."""
    server, port = _start_sink(hook_status=200)
    try:
        result = _run_probe(port, f"http://127.0.0.1:{port}/hook")
    finally:
        server.shutdown()
        server.server_close()
    print(result.stderr)
    assert result.returncode == 1
    assert MARKER not in result.stderr
    assert len(_Sink.posts) == 1
    payload = json.loads(_Sink.posts[0])
    assert "BRIDGE UNAUTH" in payload["text"]


def test_transient_sink_failure_recovers_on_the_bounded_retry() -> None:
    """First POST 500s, second succeeds: delivered on retry -> exit 1,
    no marker. Transient hiccups must not page as delivery failures."""
    server, port = _start_sink(hook_status=200, fail_first_n_posts=1)
    try:
        result = _run_probe(port, f"http://127.0.0.1:{port}/hook")
    finally:
        server.shutdown()
        server.server_close()
    print(result.stderr)
    assert result.returncode == 1
    assert MARKER not in result.stderr
    assert len(_Sink.posts) == 2


def test_healthy_run_exits_0_and_posts_nothing() -> None:
    """No false alarm on the quiet path: exit 0, no POST, no marker."""
    server, port = _start_sink(bridge_authenticated=True, ratio_alert=False)
    try:
        result = _run_probe(port, f"http://127.0.0.1:{port}/hook")
    finally:
        server.shutdown()
        server.server_close()
    print(result.stderr)
    assert result.returncode == 0
    assert result.stderr == ""
    assert _Sink.posts == []


def test_unset_webhook_keeps_the_documented_stderr_fallback() -> None:
    """Webhook unset is the documented degraded mode: the alert goes to
    stderr with exit 1 and NO delivery-failure marker — a missing config
    is not a failed delivery."""
    server, port = _start_sink(hook_status=200)
    try:
        result = _run_probe(port, None)
    finally:
        server.shutdown()
        server.server_close()
    print(result.stderr)
    assert result.returncode == 1
    assert "BRIDGE UNAUTH" in result.stderr
    assert MARKER not in result.stderr


def test_delivery_failure_never_leaks_webhook_user_info() -> None:
    server, port = _start_sink(hook_status=500)
    username = "synthetic-webhook-user"
    password = "synthetic-webhook-password"
    try:
        result = _run_probe(port, f"http://{username}:{password}@127.0.0.1:{port}/hook")
    finally:
        server.shutdown()
        server.server_close()
    assert result.returncode == 2
    assert len(_Sink.posts) == 2
    assert MARKER in result.stderr
    assert "BRIDGE UNAUTH" in result.stderr
    assert username not in result.stderr
    assert password not in result.stderr
    assert "webhook POST to configured sink failed" in result.stderr


def test_delivery_failure_never_leaks_query_without_url_path() -> None:
    server, port = _start_sink(hook_status=500)
    secret = "synthetic-webhook-query-secret"
    try:
        result = _run_probe(port, f"http://127.0.0.1:{port}?token={secret}")
    finally:
        server.shutdown()
        server.server_close()
    assert result.returncode == 2
    assert len(_Sink.posts) == 2
    assert MARKER in result.stderr
    assert "BRIDGE UNAUTH" in result.stderr
    assert secret not in result.stderr
    assert "?token=" not in result.stderr
    assert "webhook POST to configured sink failed" in result.stderr
