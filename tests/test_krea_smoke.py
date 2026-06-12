"""Offline tests for tools/krea_smoke.py (ALC SPR-02).

The smoke script's secret-safety is a CLAIM; these tests are its proof
(rigor #3 — "it obviously can't leak" is the anti-pattern that produced
the 2026-06-12 leaked-ledger incident):

  - A mocked LOCAL stdlib HTTP server (never api.krea.ai) exercises BOTH
    rendering paths — the 200 SceneArt path (fresh → cached repeat) and
    the 503 DisabledResponse path (no_key, no_api_balance) — by running
    the real script as a subprocess, exactly as an operator would.
  - STDOUT SNAPSHOTS: every captured stdout is scanned for token-like
    material — the fake operator bearer we DID put in the subprocess
    env, an id:secret Krea-shaped pattern, a signed query param the mock
    server deliberately embeds in image_url, and any "Bearer <...>"
    echo. The mock server separately RECORDS that the Authorization
    header arrived, proving the secret was used yet never printed.
  - STATIC CHECKS: the script source never reads KREA_API_TOKEN, only
    accesses an allowlisted set of env names, and routes every print
    through the scrubber.

No network beyond 127.0.0.1; no venv deps beyond pytest; no live Krea
call anywhere (first live execution is SPR-09's capped smoke).
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "tools" / "krea_smoke.py"

# An obviously-fake operator bearer. It goes INTO the subprocess env; the
# tests then assert it never comes OUT on stdout.
_FAKE_OPERATOR_TOKEN = "tok-FAKE-OPERATOR-0a1b2c3d4e5f-not-real"
# A token-like signed query param the mock server embeds in image_url —
# the script must strip the query string before printing.
_FAKE_SIGNED_QUERY = "X-Krea-Signature=FAKESIGNEDVALUE1234567890abcdef"

# Token-like shapes that must NEVER appear in any smoke stdout:
#   - an id:secret pair (the Krea key format observed in the 2026-06-12
#     leak): 8+ word chars, a colon, 16+ word chars, no whitespace.
#   - any Bearer echo.
_TOKEN_LIKE = re.compile(r"[A-Za-z0-9_-]{8,}:[A-Za-z0-9_-]{16,}")
_BEARER_ECHO = re.compile(r"(?i)bearer\s+[A-Za-z0-9_.:-]{8,}")


def _assert_no_secrets(stdout: str) -> None:
    """The snapshot assertion every scenario runs."""
    assert _FAKE_OPERATOR_TOKEN not in stdout
    assert "FAKESIGNEDVALUE" not in stdout, "signed query param leaked"
    assert not _TOKEN_LIKE.search(stdout), (
        f"token-like pattern in stdout: {_TOKEN_LIKE.search(stdout).group(0)!r}"
    )
    assert not _BEARER_ECHO.search(stdout), "Authorization header echoed"


# ── Mock proxy server (stdlib; 127.0.0.1 only) ──────────────────────────


class _MockProxy:
    """A scripted /health + /krea/scene server. ``scene_responses`` is a
    list of (status, json_body) consumed one per call; the last entry
    repeats. Records each request's Authorization header + path."""

    def __init__(self, scene_responses):
        self.scene_responses = list(scene_responses)
        self.requests: list[tuple[str, str | None]] = []
        self._calls = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep test output clean
                pass

            def do_GET(self):
                outer.requests.append(
                    (self.path, self.headers.get("Authorization"))
                )
                if self.path.startswith("/health"):
                    self._send(200, {"status": "ok"})
                    return
                if self.path.startswith("/krea/scene"):
                    idx = min(outer._calls, len(outer.scene_responses) - 1)
                    outer._calls += 1
                    status, body = outer.scene_responses[idx]
                    self._send(status, body)
                    return
                self._send(404, {"error": "not found"})

            def _send(self, status, body):
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *a):
        self._server.shutdown()
        self._server.server_close()


def _run_smoke(port: int, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--base-url",
            f"http://127.0.0.1:{port}",
            *extra_args,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": "/usr/bin:/bin",
            "ANTIEK_OPERATOR_TOKEN": _FAKE_OPERATOR_TOKEN,
            # Deliberately present so a buggy read WOULD have something
            # to leak — the assertions prove it never surfaces:
            "KREA_API_TOKEN": "fakeid-0000-fake:FAKESECRETVALUE-abcdef0123456789",
        },
        cwd=str(_REPO),
    )


_SCENE_KEY = "calm|day|summer"
_FRESH_200 = {
    "enabled": True,
    "isFallback": False,
    "image_url": f"https://cdn.example.test/scene.png?{_FAKE_SIGNED_QUERY}",
    "scene_key": _SCENE_KEY,
    "cached": False,
}
_CACHED_200 = dict(_FRESH_200, cached=True)


def _disabled(reason: str) -> dict:
    return {
        "enabled": False,
        "isFallback": True,
        "reason": reason,
        "scene_key": _SCENE_KEY,
    }


# ── Rendering path 1: 200 fresh → cached repeat (the de-bill proof) ─────


def test_200_path_fresh_then_cached_exits_0_and_leaks_nothing():
    with _MockProxy([(200, _FRESH_200), (200, _CACHED_200)]) as mock:
        proc = _run_smoke(mock.port)
    out = proc.stdout
    assert proc.returncode == 0, out + proc.stderr
    # Pretty-printed 200 shape:
    assert "HTTP 200 — SceneArt" in out
    assert "cached:     false" in out and "cached:     true" in out
    assert _SCENE_KEY in out
    # Query string stripped from the printed URL:
    assert "https://cdn.example.test/scene.png" in out
    assert "query string stripped" in out
    # De-bill proof + dashboard-decrement reminder:
    assert "de-bill proven" in out
    assert "https://www.krea.ai/app/api" in out
    assert "exactly 1 unit(s)" in out
    # The bearer was USED (server saw it) yet never PRINTED:
    scene_auth = [a for p, a in mock.requests if p.startswith("/krea/scene")]
    assert scene_auth == [f"Bearer {_FAKE_OPERATOR_TOKEN}"] * 2
    _assert_no_secrets(out)
    assert proc.stderr == ""


def test_non_str_image_url_prints_type_name_only_never_the_value():
    """A dict-shaped image_url embedding a signed URL would bypass
    strip_query if its repr were printed — the script must print only
    the TYPE NAME for any non-str image_url, never the value."""
    dict_url = {
        "url": f"https://cdn.example.test/scene.png?{_FAKE_SIGNED_QUERY}"
    }
    fresh = dict(_FRESH_200, image_url=dict_url)
    cached = dict(_CACHED_200, image_url=dict_url)
    with _MockProxy([(200, fresh), (200, cached)]) as mock:
        proc = _run_smoke(mock.port)
    out = proc.stdout
    assert proc.returncode == 0, out + proc.stderr
    assert "image_url:  <unexpected type: dict — not printed>" in out
    assert "cdn.example.test" not in out  # the embedded URL never surfaces
    _assert_no_secrets(out)  # in particular: FAKESIGNEDVALUE marker absent


def test_repeat_not_cached_is_a_rebill_failure_exit_1():
    with _MockProxy([(200, _FRESH_200), (200, _FRESH_200)]) as mock:
        proc = _run_smoke(mock.port)
    assert proc.returncode == 1, proc.stdout
    assert "NOT served from" in proc.stdout
    assert "re-bill" in proc.stdout
    _assert_no_secrets(proc.stdout)


# ── Rendering path 2: typed 503 fallback ────────────────────────────────


def test_503_no_key_exits_3_with_decision_row():
    with _MockProxy([(503, _disabled("no_key"))]) as mock:
        proc = _run_smoke(mock.port)
    out = proc.stdout
    assert proc.returncode == 3, out + proc.stderr
    assert "HTTP 503 — DisabledResponse" in out
    assert "reason:     no_key" in out
    assert "KREA_API_TOKEN is not set" in out  # decision-table meaning
    assert "EXPECTED state before a token/balance is wired" in out
    _assert_no_secrets(out)


def test_503_no_api_balance_points_at_the_money_step():
    with _MockProxy([(503, _disabled("no_api_balance"))]) as mock:
        proc = _run_smoke(mock.port)
    out = proc.stdout
    assert proc.returncode == 3
    assert "reason:     no_api_balance" in out
    assert "SEPARATE from any web subscription" in out
    assert "https://www.krea.ai/app/api" in out
    _assert_no_secrets(out)


def test_unknown_reason_is_admitted_not_guessed():
    with _MockProxy([(503, _disabled("a_future_reason"))]) as mock:
        proc = _run_smoke(mock.port)
    assert "UNKNOWN reason 'a_future_reason'" in proc.stdout
    _assert_no_secrets(proc.stdout)


# ── --help works offline + carries the full decision table ──────────────


def test_help_offline_lists_full_post_spr01_vocabulary():
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": "/usr/bin:/bin"},
        cwd=str(_REPO),
    )
    assert proc.returncode == 0
    for reason in (
        "no_key", "kill_switch", "over_daily_budget", "rate_limited",
        "upstream_error", "upstream_timeout", "upstream_bad_response",
        "job_failed", "job_timeout", "job_cancelled", "no_api_balance",
    ):
        assert reason in proc.stdout, f"--help missing reason {reason}"
    _assert_no_secrets(proc.stdout)


def test_decision_table_matches_krea_routes_vocabulary_exactly():
    """The table must track interfaces/research/api/krea_routes.py's
    _REASON_* constants (post-SPR-01) — no missing, no invented."""
    spec = importlib.util.spec_from_file_location("krea_smoke", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    routes_src = (
        _REPO / "interfaces" / "research" / "api" / "krea_routes.py"
    ).read_text()
    served = set(
        re.findall(r'^_REASON_\w+\s*=\s*"([^"]+)"', routes_src, re.M)
    )
    assert served, "could not parse _REASON_* constants — file moved?"
    assert set(mod.DECISION_TABLE) == served


# ── Static secret-safety checks (milestone 3 acceptance) ────────────────


def test_static_script_never_reads_krea_api_token():
    src = _SCRIPT.read_text()
    assert not re.search(r"environ(?:\.get)?[\[(]\s*['\"]KREA_API_TOKEN", src)
    assert "getenv" not in src  # one env-access idiom, easy to audit


def test_static_env_access_is_allowlisted():
    """Every os.environ access names a non-secret knob or the operator
    bearer (which is scrubbed). dict(os.environ) passthrough exists only
    to hand the --serve subprocess its own env — it is never formatted."""
    src = _SCRIPT.read_text()
    for name in re.findall(r"os\.environ\.get\(\s*['\"]([^'\"]+)['\"]", src):
        assert name in {"ANTIEK_OPERATOR_TOKEN", "KREA_DAILY_UNIT_CAP"}, name
    assert not re.search(r"os\.environ\[", src)
    # The ONE wholesale read is the --serve subprocess-env passthrough:
    assert src.count("dict(os.environ)") == 1
    assert "print(os.environ" not in src


def test_static_all_output_routes_through_the_scrubber():
    src = _SCRIPT.read_text()
    # Exactly one print() call — inside say(), behind the scrubber.
    assert len(re.findall(r"(?<![\w.])print\(", src)) == 1
    assert "_SCRUBBER.clean" in src


def test_build_server_env_forces_cap_3_unless_overridden():
    spec = importlib.util.spec_from_file_location("krea_smoke2", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.build_server_env({})["KREA_DAILY_UNIT_CAP"] == "3"
    assert mod.build_server_env({"KREA_DAILY_UNIT_CAP": ""})[
        "KREA_DAILY_UNIT_CAP"
    ] == "3"
    env = mod.build_server_env(
        {"KREA_DAILY_UNIT_CAP": "7", "OTHER": "kept"}
    )
    assert env["KREA_DAILY_UNIT_CAP"] == "7"  # explicit override respected
    assert env["OTHER"] == "kept"  # parent env passes through


def test_strip_query_drops_signed_params():
    spec = importlib.util.spec_from_file_location("krea_smoke3", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = mod.strip_query(f"https://cdn.x.test/a.png?{_FAKE_SIGNED_QUERY}#f")
    assert "FAKESIGNEDVALUE" not in out
    assert out.startswith("https://cdn.x.test/a.png")
    assert mod.strip_query("https://cdn.x.test/a.png") == "https://cdn.x.test/a.png"


# ── Transport failures stay secret-free too ─────────────────────────────


def test_unreachable_base_exits_2_cleanly():
    # Port 1 on localhost: nothing listens there (refused immediately).
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--base-url", "http://127.0.0.1:1"],
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": "/usr/bin:/bin", "ANTIEK_OPERATOR_TOKEN": _FAKE_OPERATOR_TOKEN},
        cwd=str(_REPO),
    )
    assert proc.returncode == 2
    assert "UNREACHABLE" in proc.stdout
    _assert_no_secrets(proc.stdout)


def test_401_explains_operator_auth_without_echoing_anything():
    with _MockProxy([(401, {"error": {"code": "operator_auth_required"}})]) as mock:
        proc = _run_smoke(mock.port)
    assert proc.returncode == 2
    assert "operator auth required" in proc.stdout
    assert "ANTIEK_OPERATOR_TOKEN" in proc.stdout  # names the VAR, not the value
    _assert_no_secrets(proc.stdout)
