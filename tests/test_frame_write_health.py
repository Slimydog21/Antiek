"""Write-path health signal: fires on the 2026-10-02/03 incident shape,
stays silent on the measured healthy shape.

Fixtures are the MEASURED production numbers (recorded in
``.audit/2026-10-01-anatomy/GRADE-2026-10-01.md``):

- incident: 84.6% of frame-telemetry flushes refused (28,562 of 33,776)
  over ~28h, 1,000-1,700 refusals every hour, ``/health`` reporting "ok";
- healthy (post-fix, sync running): 2 of 65 refused = 3.1% over 4 minutes;
- tolerated degradation (2026-10-01, sync at full duty): 19.4% of flushes
  not served over 24h — the highest refusal level ever accepted as correct.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.frame_write_health import (
    FRAME_WRITE_ALERT_THRESHOLD,
    FRAME_WRITE_MIN_ATTEMPTS,
    FRAME_WRITE_WINDOW_S,
    FrameWriteHealth,
)

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "ops" / "health_probe.sh"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


# ── counter math ─────────────────────────────────────────────────────


def test_empty_window_is_honest_null_never_zero_percent() -> None:
    snap = FrameWriteHealth(clock=FakeClock()).snapshot()
    assert snap.attempts == 0
    assert snap.refusal_rate is None
    assert snap.alert_recommended is False
    assert snap.alert_reason is None


def test_all_refused_below_min_attempts_does_not_alert() -> None:
    """A burst of 503s on near-zero traffic is unmeasurable, not an incident."""
    h = FrameWriteHealth(clock=FakeClock())
    for _ in range(FRAME_WRITE_MIN_ATTEMPTS - 1):
        h.record(refused=True)
    snap = h.snapshot()
    assert snap.refusal_rate == 1.0
    assert snap.alert_recommended is False


def test_incident_shape_alerts() -> None:
    """85% refusal over a filled window — the incident's measured shape."""
    h = FrameWriteHealth(clock=FakeClock())
    for i in range(200):
        h.record(refused=(i % 20) != 0)  # 95% — well past the measured 84.6%
    snap = h.snapshot()
    assert snap.attempts == 200
    assert snap.refusal_rate == pytest.approx(0.95)
    assert snap.alert_recommended is True
    assert "95.0%" in snap.alert_reason


def test_incident_exact_measured_rate_alerts() -> None:
    """The exact measured 84.6% (846 of 1000) must fire."""
    h = FrameWriteHealth(clock=FakeClock())
    for i in range(1000):
        h.record(refused=i < 846)
    snap = h.snapshot()
    assert snap.refusal_rate == pytest.approx(0.846)
    assert snap.alert_recommended is True


def test_healthy_shape_does_not_alert() -> None:
    """The measured post-fix healthy rate: 2 of 65 = 3.1%."""
    h = FrameWriteHealth(clock=FakeClock())
    for i in range(65):
        h.record(refused=i < 2)
    snap = h.snapshot()
    assert snap.refusal_rate == pytest.approx(2 / 65)
    assert snap.alert_recommended is False


def test_tolerated_degradation_does_not_alert() -> None:
    """2026-10-01, sync at full duty, operator-accepted: 19.4% unserved.
    The threshold must sit above the highest refusal level ever reviewed
    and accepted as correct — anything lower cries wolf on a known state."""
    h = FrameWriteHealth(clock=FakeClock())
    for i in range(1000):
        h.record(refused=i < 194)
    snap = h.snapshot()
    assert snap.refusal_rate == pytest.approx(0.194)
    assert snap.alert_recommended is False


def test_window_prunes_old_events() -> None:
    clock = FakeClock()
    h = FrameWriteHealth(clock=clock)
    for _ in range(100):
        h.record(refused=True)
    clock.now += FRAME_WRITE_WINDOW_S + 1
    for _ in range(100):
        h.record(refused=False)
    snap = h.snapshot()
    assert snap.attempts == 100
    assert snap.refusal_rate == 0.0
    assert snap.alert_recommended is False


def test_threshold_constants_match_their_derivation_anchors() -> None:
    """Guard the derived constants against silent drift: threshold must sit
    strictly between the tolerated-degradation anchor (19.4%) and the
    incident anchor (84.6%)."""
    assert 0.194 < FRAME_WRITE_ALERT_THRESHOLD < 0.846
    assert FRAME_WRITE_ALERT_THRESHOLD == 0.25
    assert FRAME_WRITE_MIN_ATTEMPTS == 30
    assert FRAME_WRITE_WINDOW_S == 900.0


# ── route integration: the route records real outcomes ───────────────


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-frame-write-health-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    # The operator's shell may export these (they gate the auth middleware);
    # the route tests exercise the write path, not auth. Same hermetic-env
    # pattern as test_ad_routes.py's config-conflict test.
    for var in (
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
    ):
        monkeypatch.delenv(var, raising=False)
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _seed_earner(db_path: str) -> None:
    from runtime.db_lock import connect_write
    from substrate.books import ingest as bingest
    from substrate.graph.ops import insert_document

    with connect_write(db_path, purpose="test:seed_book") as con:
        insert_document(
            con,
            document_id="pd-earner",
            source_tier=2,
            document_type="book",
            title="Earner",
            author="A",
            raw_text="public domain body",
        )
        bingest.register_book(
            con,
            document_id="pd-earner",
            content_class="public_domain",
            rights_holder_name="Earner Estate",
        )


def _batch(window_id: str = "win-1") -> dict:
    from substrate.ad_inventory.frame_attention import FRAME_TELEMETRY_SCHEMA_VERSION

    return {
        "window_id": window_id,
        "schema_version": FRAME_TELEMETRY_SCHEMA_VERSION,
        "seconds": [
            {
                "second_index": 0,
                "lens": "read",
                "samples": [
                    {
                        "asset_id": "pd-earner",
                        "viewport_area_fraction": 0.8,
                        "prominence": 0.9,
                        "focused_dwell_ms": 800,
                    }
                ],
            }
        ],
    }


def _health_frame_write(client: TestClient) -> dict:
    resp = client.get("/health")
    assert resp.status_code == 200, resp.text
    return resp.json()["frame_write"]


_HOLD_DB_SCRIPT = (
    "import duckdb, sys, time\n"
    "con = duckdb.connect(sys.argv[1])\n"
    "print('held', flush=True)\n"
    "time.sleep(float(sys.argv[2]))\n"
    "con.close()\n"
)


def test_route_records_successes_and_lock_refusals(isolated_db, monkeypatch):
    """The route itself feeds the window: a 202 counts as an attempt, a
    WriteLockTimeout 503 counts as a refusal, and /health reports both."""
    from interfaces.research.api import ad_routes
    from runtime import db_lock

    _seed_earner(isolated_db)
    client = TestClient(create_app(register_wrestling=False, register_providers=False))

    resp = client.post("/api/ad/frame-telemetry", json=_batch("win-ok"))
    assert resp.status_code == 202, resp.text
    snap = _health_frame_write(client)
    assert snap["attempts"] == 1
    assert snap["refused"] == 0
    assert snap["refusal_rate"] == 0.0
    assert snap["alert_recommended"] is False

    # External holder forces the route's bounded-wait 503 (the incident's
    # response shape), same pattern as test_ad_routes.py.
    monkeypatch.setattr(ad_routes, "_FRAME_WRITE_TIMEOUT_S", 0.4)
    db_lock.flush_warm_writers(isolated_db)
    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLD_DB_SCRIPT, isolated_db, "30"],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "held"
        db_lock.flush_warm_writers(isolated_db)
        t0 = time.monotonic()
        resp = client.post("/api/ad/frame-telemetry", json=_batch("win-refused"))
        assert time.monotonic() - t0 < 5.0
        assert resp.status_code == 503, resp.text
        assert resp.json()["detail"] == "ad_frame_writer_busy"
    finally:
        holder.terminate()
        holder.wait(timeout=10)

    snap = _health_frame_write(client)
    assert snap["attempts"] == 2
    assert snap["refused"] == 1
    assert snap["refusal_rate"] == pytest.approx(0.5)
    # Two attempts is below min_attempts: no alert on an unmeasurable sample.
    assert snap["alert_recommended"] is False


def test_route_does_not_count_validation_rejections(isolated_db):
    """A 422 (malformed batch) never reached the write path; counting it
    would dilute the refusal rate with client faults."""
    _seed_earner(isolated_db)
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    bad = _batch("win-bad")
    bad["seconds"][0]["samples"][0]["viewport_area_fraction"] = 1.7
    resp = client.post("/api/ad/frame-telemetry", json=bad)
    assert resp.status_code == 422, resp.text
    snap = _health_frame_write(client)
    assert snap["attempts"] == 0
    assert snap["refusal_rate"] is None


def test_health_reports_incident_shape_as_alert(isolated_db):
    """End to end: drive the recorder to the incident's measured shape
    through the app, and /health recommends the alert the 2026-10-02/03
    incident never got."""
    _seed_earner(isolated_db)
    app = create_app(register_wrestling=False, register_providers=False)
    recorder = app.state.frame_write_health
    # Incident shape, measured: 84.6% of 33,776 flushes. Scaled fixture:
    # 846 refused of 1000, inside one window.
    for i in range(1000):
        recorder.record(refused=i < 846)
    client = TestClient(app)
    snap = _health_frame_write(client)
    assert snap["refusal_rate"] == pytest.approx(0.846)
    assert snap["alert_recommended"] is True
    assert "84.6%" in snap["alert_reason"]


def test_health_reports_healthy_shape_as_quiet(isolated_db):
    """End to end: the measured post-fix healthy shape (2 of 65 = 3.1%)
    must NOT recommend an alert."""
    _seed_earner(isolated_db)
    app = create_app(register_wrestling=False, register_providers=False)
    recorder = app.state.frame_write_health
    for i in range(650):
        recorder.record(refused=i < 20)  # 3.1%
    client = TestClient(app)
    snap = _health_frame_write(client)
    assert snap["refusal_rate"] == pytest.approx(20 / 650)
    assert snap["alert_recommended"] is False


# ── the probe forwards the signal to the configured webhook ──────────


def _stub_bin(tmp_path: Path, health_body: str, ratio_body: str) -> Path:
    """A curl stub that serves fixture bodies per URL and records any
    webhook POST to ``$STUB_POST_LOG``. Real jq does the parsing."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    tmp_path / "posted.json"
    curl = bindir / "curl"
    curl.write_text(
        "#!/usr/bin/env bash\n"
        "url=''\n"
        "method='GET'\n"
        "data=''\n"
        "while [ $# -gt 0 ]; do\n"
        '  case "$1" in\n'
        '    -X) method="$2"; shift 2;;\n'
        '    -d) data="$2"; shift 2;;\n'
        "    -H) shift 2;;\n"
        '    -f|-s|-S|-fsS|--max-time) if [ "$1" = --max-time ]; then shift 2; else shift; fi;;\n'
        '    *) url="$1"; shift;;\n'
        "  esac\n"
        "done\n"
        'if [ "$method" = POST ]; then printf \'%s\' "$data" > "$STUB_POST_LOG"; exit 0; fi\n'
        'case "$url" in\n'
        f"  *provider-ratio*) printf '%s' '{ratio_body}';;\n"
        f"  *api.antiek.ai/health) printf '%s' '{health_body}';;\n"
        "  *hermes-bridge*) printf '%s' '{\"authenticated\": true}';;\n"
        "  *) exit 1;;\n"
        "esac\n"
    )
    curl.chmod(curl.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def _run_probe(tmp_path: Path, health_body: str, ratio_body: str) -> subprocess.CompletedProcess:
    if shutil.which("jq") is None:
        pytest.skip("jq not installed")
    bindir = _stub_bin(tmp_path, health_body, ratio_body)
    env = dict(os.environ)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
    env["ANTIEK_ALERT_WEBHOOK"] = "https://hooks.example.invalid/alert"
    env["STUB_POST_LOG"] = str(tmp_path / "posted.json")
    return subprocess.run(
        ["bash", str(PROBE)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


_HEALTHY_HEALTH = json.dumps(
    {
        "status": "ok",
        "frame_write": {
            "window_seconds": 900,
            "attempts": 650,
            "refused": 20,
            "refusal_rate": 0.0308,
            "alert_threshold": 0.25,
            "min_attempts": 30,
            "alert_recommended": False,
            "alert_reason": None,
        },
    }
)

_INCIDENT_HEALTH = json.dumps(
    {
        "status": "ok",
        "frame_write": {
            "window_seconds": 900,
            "attempts": 1000,
            "refused": 846,
            "refusal_rate": 0.846,
            "alert_threshold": 0.25,
            "min_attempts": 30,
            "alert_recommended": True,
            "alert_reason": (
                "frame-telemetry refused 846/1000 writes (84.6%) in the last 900s (threshold 25%)"
            ),
        },
    }
)

_QUIET_RATIO = json.dumps({"alert_recommended": False})


def test_probe_posts_webhook_on_incident_shape(tmp_path: Path) -> None:
    """The alert the incident never got: 84.6% refusal -> exit 1 and one
    webhook POST carrying the measured rate."""
    result = _run_probe(tmp_path, _INCIDENT_HEALTH, _QUIET_RATIO)
    print(result.stderr)
    assert result.returncode == 1
    assert "WRITE PATH DEGRADED" in result.stderr
    assert "84.6%" in result.stderr
    posted = tmp_path / "posted.json"
    assert posted.exists(), "the configured webhook was never POSTed"
    payload = json.loads(posted.read_text())
    assert "WRITE PATH DEGRADED" in payload["text"]
    assert "84.6%" in payload["text"]


def test_probe_stays_silent_on_healthy_shape(tmp_path: Path) -> None:
    """The healthy shape (3.1% — the measured post-fix rate) -> exit 0,
    no webhook POST: the probe must not cry wolf on correct refusals."""
    result = _run_probe(tmp_path, _HEALTHY_HEALTH, _QUIET_RATIO)
    print(result.stderr)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "posted.json").exists()


@pytest.mark.parametrize("verdict", ["error", "degraded"])
def test_probe_alerts_on_explicit_write_verdict_with_empty_details(tmp_path: Path, verdict: str) -> None:
    health = json.dumps({
        "status": "degraded",
        "status_checks": {"frame_write": verdict},
        "status_detail": "frame_write details unavailable",
        "frame_write": {},
    })
    result = _run_probe(tmp_path, health, _QUIET_RATIO)
    assert result.returncode == 1
    assert "WRITE PATH DEGRADED: frame_write details unavailable" in result.stderr
    posted = json.loads((tmp_path / "posted.json").read_text())
    assert "WRITE PATH DEGRADED: frame_write details unavailable" in posted["text"]


def test_probe_stays_silent_when_write_path_is_not_measured(tmp_path: Path) -> None:
    health = json.dumps({
        "status": "ok",
        "status_checks": {"frame_write": "not_measured"},
        "frame_write": {"attempts": 0, "refusal_rate": None, "alert_recommended": False},
    })
    result = _run_probe(tmp_path, health, _QUIET_RATIO)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "posted.json").exists()
