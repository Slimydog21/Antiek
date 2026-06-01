"""SPR-11 M6 — the NON-VACUITY seed-and-catch for the flywheel assertion.

The flywheel-liveness assertion is the rigor gate of this sprint. An assert
that always greens defends nothing. This test proves the extension is
NON-VACUOUS end-to-end: it stands up a real local HTTP stub serving
``/health`` and points the SHIPPED checker (``tools/prod_parity/check.py``)
at it through its real ``fetch_health`` GET (no monkeypatch of the fetch) —

  * stub ``flywheel_ready: false`` → ``run`` exits 1 with a flywheel-NAMED
    failure message (fail-BEFORE), and
  * stub ``flywheel_ready: true``  → ``run`` exits 0 (pass-AFTER),

with SHA + providers held in parity in BOTH cases so the ONLY thing that
flips the exit code is the flywheel signal. This is the proof the spec's
"Parity non-vacuity (seed-and-catch)" gate demands.

No live prod, no operator credentials: the stub is a local
``http.server`` on 127.0.0.1. (The LIVE probe vs https://api.antiek.ai is
operator-gated and best-effort — see the handoff; this seed-and-catch is the
non-negotiable.)
"""

from __future__ import annotations

import json
import os
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools.prod_parity import check as parity  # noqa: E402

_SHA = "c" * 40


def _health_body(*, flywheel_ready: bool) -> dict:
    return {
        "status": "ok",
        "param_version": "x",
        "schema_version": 1,
        "subscriber_count": 0,
        "registered_providers": ["openrouter"],
        "build_sha": _SHA,
        "flywheel_ready": flywheel_ready,
        "knowledge_reuse_count": 2 if flywheel_ready else 0,
    }


@contextmanager
def _stub_health_server(*, flywheel_ready: bool):
    """Serve ``/health`` (the stub body) on an ephemeral localhost port."""
    body = json.dumps(_health_body(flywheel_ready=flywheel_ready)).encode("utf-8")

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server API)
            if self.path.rstrip("/").endswith("/health") or self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):  # silence the test log
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_seed_and_catch_dead_flywheel_then_live():
    # FAIL-BEFORE: stub flywheel_ready=false → exit 1 with a flywheel message.
    with _stub_health_server(flywheel_ready=False) as url:
        rc_dead = parity.run(url, expected_sha=_SHA)
    assert rc_dead == 1, (
        "a stub /health with flywheel_ready=false must exit 1 (SHA + providers "
        "are in parity, so the ONLY failing condition is the flywheel)"
    )

    # The failure message NAMES the flywheel condition (not just SHA/providers).
    failures = parity.assert_parity(
        _health_body(flywheel_ready=False), expected_sha=_SHA
    )
    assert any("flywheel" in f.lower() for f in failures), (
        "the red must name the flywheel condition"
    )

    # PASS-AFTER: flip the stub to flywheel_ready=true → exit 0.
    with _stub_health_server(flywheel_ready=True) as url:
        rc_live = parity.run(url, expected_sha=_SHA)
    assert rc_live == 0, (
        "flipping the stub to flywheel_ready=true (SHA + providers still in "
        "parity) must exit 0 — proving the new assert is NOT a no-op"
    )
