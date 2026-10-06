"""Tests for the computed ``/health`` ``status`` (fix/health-status-computed-20261003).

What this file proves:

1. ``status`` is DEGRADED on the measured incident shape — the exact
   frame-telemetry refusal rates that ran behind ``{"status": "ok"}``
   for 28+ hours: 84.6% (28,562 of 33,776 over 28h, 2026-10-02/03) and
   89.4% (9,926 of 11,103 in the 6h window at audit time, 2026-10-03).
2. ``status`` stays OK on the measured healthy baseline (3.1%, 2 of 65)
   and on the highest refusal level ever accepted as correct behaviour
   (19.4% over 24h, operator-reviewed).
3. The nothing-measured cases are honest: no recorder wired, or zero
   attempts in the window, report ``not_measured`` in ``status_checks``
   and leave ``status`` at the documented liveness fallback "ok" — never
   a fabricated "the write path is healthy".
4. An unreadable sensor fails CLOSED (``error`` degrades ``status``),
   the rule ``/ops/provider-ratio`` documents.
5. The HTTP status code is untouched: a degraded body still answers 200,
   so uptime monitors and the deploy gate's transport conjunct are not
   flapped by a health verdict.
6. When the real PR #3663 recorder exists on the tree, the integration
   test at the bottom drives ``status`` from IT (skipped otherwise — the
   duck-typed contract is what makes both merge orders work).

The stand-in recorder mirrors the PUBLIC CONTRACT of PR #3663's
``FrameWriteHealth`` (``snapshot()`` exposing ``attempts`` /
``refusal_rate`` / ``alert_recommended`` / ``alert_reason``) and its
derived constants (0.25 threshold over 900s, >=30 attempts — derived in
frame_write_health.py from the measured anchors above). The merged-tree
verification runs this same suite against the REAL recorder.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections import deque
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import create_app  # noqa: E402
from interfaces.research.api.health_status import (  # noqa: E402
    CHECK_DEGRADED,
    CHECK_ERROR,
    CHECK_FRAME_WRITE,
    CHECK_NOT_MEASURED,
    CHECK_OK,
    STATUS_DEGRADED,
    STATUS_OK,
    compute_health_status,
)

# ── The measured anchors (do not "round" these — they are the evidence) ──
INCIDENT_28H_REFUSED, INCIDENT_28H_ATTEMPTS = 28_562, 33_776   # 84.6%, 2026-10-02/03
INCIDENT_6H_REFUSED, INCIDENT_6H_ATTEMPTS = 9_926, 11_103      # 89.4%, audit window
HEALTHY_REFUSED, HEALTHY_ATTEMPTS = 2, 65                      # 3.1%, post-fix
TOLERATED_REFUSED, TOLERATED_ATTEMPTS = 194, 1_000             # 19.4%, accepted 2026-10-01

# PR #3663's derived constants, mirrored so the stand-in implements the
# same verdict; test_constants_match_their_derivation pins them.
STAND_IN_WINDOW_S = 900.0
STAND_IN_ALERT_THRESHOLD = 0.25
STAND_IN_MIN_ATTEMPTS = 30


class _StandInFrameWriteHealth:
    """Minimal stand-in for PR #3663's ``FrameWriteHealth`` public contract.

    Same rolling-window semantics, same derived constants, same snapshot
    field names. Exists so this branch's logic is provable on a tree
    where the recorder itself has not merged yet; the importorskip test
    at the bottom re-proves the integration against the real class.
    """

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._events: deque[tuple[float, bool]] = deque()
        self._lock = threading.Lock()

    def record(self, *, refused: bool) -> None:
        now = self._clock()
        with self._lock:
            self._events.append((now, refused))
            self._prune(now)

    def snapshot(self):
        now = self._clock()
        with self._lock:
            self._prune(now)
            attempts = len(self._events)
            refused = sum(1 for _, r in self._events if r)
        rate = (refused / attempts) if attempts else None
        alert = (
            rate is not None
            and attempts >= STAND_IN_MIN_ATTEMPTS
            and rate > STAND_IN_ALERT_THRESHOLD
        )
        reason = (
            f"frame-telemetry refused {refused}/{attempts} writes "
            f"({rate:.1%}) in the last {int(STAND_IN_WINDOW_S)}s "
            f"(threshold {STAND_IN_ALERT_THRESHOLD:.0%})"
            if alert
            else None
        )
        return SimpleNamespace(
            window_seconds=int(STAND_IN_WINDOW_S),
            attempts=attempts,
            refused=refused,
            refusal_rate=rate,
            alert_recommended=alert,
            alert_reason=reason,
        )

    def _prune(self, now: float) -> None:
        cutoff = now - STAND_IN_WINDOW_S
        while self._events and self._events[0][0] <= cutoff:
            self._events.popleft()


def _recorder_with(refused: int, attempts: int) -> _StandInFrameWriteHealth:
    rec = _StandInFrameWriteHealth()
    outcomes = [True] * refused + [False] * (attempts - refused)
    for outcome in outcomes:
        rec.record(refused=outcome)
    return rec


def _app_with(recorder) -> object:
    return SimpleNamespace(state=SimpleNamespace(frame_write_health=recorder))


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


# ── constants pinned to their derivation ─────────────────────────────


def test_constants_match_their_derivation_anchors():
    # 0.25: ~8x the measured healthy rate (3.1%), above the highest
    # tolerated (19.4%), under a third of the incident rate (84.6%).
    assert STAND_IN_ALERT_THRESHOLD == 0.25
    assert STAND_IN_ALERT_THRESHOLD > TOLERATED_REFUSED / TOLERATED_ATTEMPTS
    assert STAND_IN_ALERT_THRESHOLD > 8 * (HEALTHY_REFUSED / HEALTHY_ATTEMPTS) - 0.002
    assert STAND_IN_ALERT_THRESHOLD < INCIDENT_28H_REFUSED / INCIDENT_28H_ATTEMPTS / 3
    # 30: ~8x below the quietest measured 15-minute traffic (~240).
    assert STAND_IN_MIN_ATTEMPTS == 30
    assert STAND_IN_WINDOW_S == 900.0


# ── wrong when refusing, right when healthy ──────────────────────────


def test_incident_shape_28h_degrades_status():
    report = compute_health_status(
        _app_with(_recorder_with(INCIDENT_28H_REFUSED, INCIDENT_28H_ATTEMPTS))
    )
    assert report.status == STATUS_DEGRADED
    assert report.checks[CHECK_FRAME_WRITE] == CHECK_DEGRADED
    assert "84.6%" in report.detail
    assert "28562/33776" in report.detail


def test_incident_shape_6h_audit_window_degrades_status():
    report = compute_health_status(
        _app_with(_recorder_with(INCIDENT_6H_REFUSED, INCIDENT_6H_ATTEMPTS))
    )
    assert report.status == STATUS_DEGRADED
    assert report.checks[CHECK_FRAME_WRITE] == CHECK_DEGRADED
    assert "89.4%" in report.detail


def test_healthy_baseline_keeps_status_ok():
    report = compute_health_status(
        _app_with(_recorder_with(HEALTHY_REFUSED, HEALTHY_ATTEMPTS))
    )
    assert report.status == STATUS_OK
    assert report.checks[CHECK_FRAME_WRITE] == CHECK_OK
    assert report.detail is None


def test_tolerated_degradation_keeps_status_ok():
    report = compute_health_status(
        _app_with(_recorder_with(TOLERATED_REFUSED, TOLERATED_ATTEMPTS))
    )
    assert report.status == STATUS_OK
    assert report.checks[CHECK_FRAME_WRITE] == CHECK_OK


def test_below_min_attempts_does_not_degrade():
    # 29 of 29 refused = 100%, but under the derived 30-attempt floor the
    # rate is unmeasurable (this only happens when traffic has stopped).
    report = compute_health_status(_app_with(_recorder_with(29, 29)))
    assert report.status == STATUS_OK
    assert report.checks[CHECK_FRAME_WRITE] == CHECK_OK


# ── honest nothing-measured and fail-closed ──────────────────────────


def test_no_recorder_wired_is_not_measured_fallback_ok():
    report = compute_health_status(SimpleNamespace(state=SimpleNamespace()))
    assert report.status == STATUS_OK
    assert report.checks[CHECK_FRAME_WRITE] == CHECK_NOT_MEASURED
    assert report.detail is None


def test_empty_window_is_not_measured_never_fabricated_health():
    report = compute_health_status(_app_with(_StandInFrameWriteHealth()))
    assert report.status == STATUS_OK
    assert report.checks[CHECK_FRAME_WRITE] == CHECK_NOT_MEASURED


def test_raising_sensor_fails_closed():
    class _Broken:
        def snapshot(self):
            raise RuntimeError("lock book-keeping exploded")

    report = compute_health_status(_app_with(_Broken()))
    assert report.status == STATUS_DEGRADED
    assert report.checks[CHECK_FRAME_WRITE] == CHECK_ERROR
    assert "RuntimeError" in report.detail


def test_malformed_sensor_fails_closed():
    report = compute_health_status(_app_with(object()))
    assert report.status == STATUS_DEGRADED
    assert report.checks[CHECK_FRAME_WRITE] == CHECK_ERROR


@pytest.mark.parametrize("snapshot", [
    SimpleNamespace(),
    SimpleNamespace(attempts=1),
    SimpleNamespace(attempts=0),
    SimpleNamespace(attempts=-1, alert_recommended=False, alert_reason=None),
    SimpleNamespace(attempts=True, alert_recommended=False, alert_reason=None),
    SimpleNamespace(attempts=1, alert_recommended="false", alert_reason=None),
    SimpleNamespace(attempts=1, alert_recommended=True, alert_reason={}),
])
def test_malformed_returned_snapshot_fails_closed(snapshot):
    recorder = SimpleNamespace(snapshot=lambda: snapshot)
    report = compute_health_status(_app_with(recorder))
    assert report.status == STATUS_DEGRADED
    assert report.checks[CHECK_FRAME_WRITE] == CHECK_ERROR
    assert "malformed" in report.detail


# ── the /health route end to end ─────────────────────────────────────


def test_health_route_reports_not_measured_without_recorder():
    client = TestClient(create_app())
    body = client.get("/health").json()
    assert body["status"] == STATUS_OK
    assert body["status_checks"][CHECK_FRAME_WRITE] == CHECK_NOT_MEASURED
    assert body["status_detail"] is None


def test_health_route_degrades_on_incident_shape_and_keeps_http_200():
    app = create_app()
    app.state.frame_write_health = _recorder_with(
        INCIDENT_6H_REFUSED, INCIDENT_6H_ATTEMPTS
    )
    client = TestClient(app)
    resp = client.get("/health")
    # The transport claim and the health claim are different axes: a
    # degraded body still answers 200 so uptime monitors and the reading
    # app's reachability probe (r.status < 500) are not flapped.
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == STATUS_DEGRADED
    assert body["status_checks"][CHECK_FRAME_WRITE] == CHECK_DEGRADED
    assert "89.4%" in body["status_detail"]


def test_health_route_stays_ok_on_healthy_baseline():
    app = create_app()
    app.state.frame_write_health = _recorder_with(HEALTHY_REFUSED, HEALTHY_ATTEMPTS)
    body = TestClient(app).get("/health").json()
    assert body["status"] == STATUS_OK
    assert body["status_checks"][CHECK_FRAME_WRITE] == CHECK_OK


def test_health_route_keeps_http_200_when_real_sensor_is_unreadable(monkeypatch):
    from interfaces.research.api.frame_write_health import FrameWriteHealth

    def unreadable(self):
        raise RuntimeError("sensor unavailable")

    monkeypatch.setattr(FrameWriteHealth, "snapshot", unreadable)
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == STATUS_DEGRADED
    assert body["status_checks"][CHECK_FRAME_WRITE] == CHECK_ERROR
    assert body["frame_write"] is None


# ── integration against the REAL PR #3663 recorder ───────────────────


def test_real_frame_write_health_drives_status_when_present():
    """On a tree where PR #3663 has merged (either order), the REAL
    recorder — not the stand-in — must drive ``status``. Skipped on a
    tree without it: that skip IS the duck-typed contract working.
    """
    fwh = pytest.importorskip("interfaces.research.api.frame_write_health")
    app = create_app()  # PR #3663 wires the real recorder at startup
    recorder = app.state.frame_write_health
    assert isinstance(recorder, fwh.FrameWriteHealth)
    for _ in range(INCIDENT_6H_REFUSED):
        recorder.record(refused=True)
    for _ in range(INCIDENT_6H_ATTEMPTS - INCIDENT_6H_REFUSED):
        recorder.record(refused=False)
    body = TestClient(app).get("/health").json()
    assert body["frame_write"]["alert_recommended"] is True
    assert body["status"] == STATUS_DEGRADED
    assert body["status_checks"][CHECK_FRAME_WRITE] == CHECK_DEGRADED
