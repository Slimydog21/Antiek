"""Computed ``status`` for ``GET /health`` — worst of the measured checks.

Prod incident 2026-10-02/03 (measured in
``.audit/2026-10-01-anatomy/GRADE-2026-10-01.md`` and
``LITERAL-STATUS-AUDIT.md``): ``POST /api/ad/frame-telemetry`` was refused
with retryable 503s for **28,562 of 33,776 writes = 84.6%** over ~28 hours
(and again 9,926 of 11,103 = 89.4% in a 6-hour window at audit time) while
``/health`` returned ``{"status": "ok"}`` the whole time. The audit
classified that literal as the only DANGEROUS constant status in the tree:
the handler had no branch that could return anything else, so no failure
of a function the API exists to perform could ever move it.

This module makes ``status`` a computed summary instead:

- each contributing check reports ``"ok"`` / ``"degraded"`` /
  ``"not_measured"`` / ``"error"``;
- ``status`` is ``"degraded"`` when any measured check is degraded or
  unreadable, and ``"ok"`` otherwise — including when NOTHING is measured,
  which is the documented liveness fallback (the literal's old meaning,
  now explicit in ``status_checks`` instead of hidden);
- the HTTP status code is untouched (always 200): uptime monitors and the
  reading app's reachability probe consume the transport code, and a
  flapping 5xx would pull a live process out of rotation.

Which checks contribute, and why the others do not (derivation, not taste):

- ``frame_write`` — INCLUDED when the route's recorder is wired onto
  ``app.state`` (PR #3663). It is the only LIVE, per-request measurement
  of a function-level failure that exists today, its trip condition is
  derived from measured anchors (healthy 3.1% vs tolerated 19.4% vs
  incident 84.6%, threshold 0.25 over 900s with >=30 attempts — see
  ``frame_write_health.py``), and it is exactly the failure class that
  was invisible for 28 hours. This module consumes the recorder's own
  ``alert_recommended`` verdict; the threshold has one definition site.
- ``duckdb_*`` / ``turbopuffer_*`` — EXCLUDED: startup-frozen snapshots
  (LITERAL-STATUS-AUDIT §1.2/§1.3). Folding a frozen value into
  ``status`` would make ``status`` a boot-time constant of a new kind,
  and a transient boot-time lock conflict (a legitimate bulk sync holds
  the write lock) would pin ``status`` at "degraded" for the process
  lifetime after the contention cleared. Their own fields carry the
  truth.
- ``flywheel_ready`` — EXCLUDED: ``False`` is the honest state of any box
  that has not compounded yet, not a failure (its field docstring says
  so). Degrading on it would red every fresh deploy.
- ``backup_fresh`` — EXCLUDED: backup staleness is a data-durability
  risk, not this process's ability to serve; it has its own probe and
  alert channel (``antiek-backup-freshness-probe``).
- ``note_taker_replay`` — EXCLUDED: the projection is the worker's last
  reported phase with no timestamp, so a dead worker serves a stale
  "current" forever (LITERAL-STATUS-AUDIT §1.5). Without a liveness bit
  it cannot distinguish "transiently waiting for the writer" from
  "wedged", and there is no measured basis for a dwell threshold.
- ``providers_ready`` — EXCLUDED: it is a live registry read, but an
  empty registry is the normal state of test apps and fresh dev boxes,
  and the deploy gate already asserts a non-empty registry on the
  candidate. The incident class that motivated computed status is the
  write path; widening the contributor set is a one-line change here
  once a second LIVE measurement exists.

An unreadable sensor fails CLOSED (check verdict ``"error"`` degrades
``status``), the same rule ``/ops/provider-ratio`` documents: "an alarm
whose sensor is unplugged must page, not report health".
"""

from __future__ import annotations

from dataclasses import dataclass, field

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"

CHECK_OK = "ok"
CHECK_DEGRADED = "degraded"
CHECK_NOT_MEASURED = "not_measured"
CHECK_ERROR = "error"

CHECK_FRAME_WRITE = "frame_write"


@dataclass(frozen=True)
class HealthStatusReport:
    """The computed ``status`` plus the per-check evidence behind it."""

    status: str
    checks: dict[str, str] = field(default_factory=dict)
    detail: str | None = None


def _frame_write_verdict(app: object) -> tuple[str, str | None]:
    """Read the frame-telemetry write-path recorder, if one is wired.

    Duck-typed against the public contract of
    ``interfaces.research.api.frame_write_health.FrameWriteHealth``
    (PR #3663): an object on ``app.state.frame_write_health`` exposing
    ``snapshot()`` with ``attempts``, ``alert_recommended`` and
    ``alert_reason``. The duck typing is deliberate: this module must
    work on a tree where the recorder does not exist yet (the check is
    then honestly ``not_measured``) and pick it up automatically on a
    tree where it does, in either merge order.
    """
    state = getattr(app, "state", None)
    recorder = getattr(state, "frame_write_health", None) if state is not None else None
    if recorder is None:
        return CHECK_NOT_MEASURED, None
    snapshot = getattr(recorder, "snapshot", None)
    if not callable(snapshot):
        return (
            CHECK_ERROR,
            "frame_write_health is wired but exposes no snapshot(); "
            "the write-path sensor is unreadable",
        )
    try:
        snap = snapshot()
    except Exception as exc:
        return (
            CHECK_ERROR,
            f"frame_write snapshot raised {type(exc).__name__}: {exc}; "
            "the write-path sensor is unreadable",
        )
    attempts = getattr(snap, "attempts", None)
    if not attempts:  # None or 0 — no traffic in the window, nothing measured
        return CHECK_NOT_MEASURED, None
    if bool(getattr(snap, "alert_recommended", False)):
        reason = getattr(snap, "alert_reason", None)
        return CHECK_DEGRADED, reason or "frame-telemetry write path is refusing writes"
    return CHECK_OK, None


def compute_health_status(app: object) -> HealthStatusReport:
    """Compute the ``/health`` ``status`` value from live sub-checks.

    ``"degraded"`` iff any contributing check is degraded or unreadable;
    ``"ok"`` otherwise — including the nothing-measured case, which is
    the liveness fallback the literal used to claim implicitly. The
    per-check verdicts ride on ``status_checks`` so a consumer can tell
    "ok because measured and green" from "ok because nothing is
    measured".
    """
    checks: dict[str, str] = {}
    details: list[str] = []

    verdict, detail = _frame_write_verdict(app)
    checks[CHECK_FRAME_WRITE] = verdict
    if detail:
        details.append(detail)

    degraded = any(v in (CHECK_DEGRADED, CHECK_ERROR) for v in checks.values())
    return HealthStatusReport(
        status=STATUS_DEGRADED if degraded else STATUS_OK,
        checks=checks,
        detail="; ".join(details) if details else None,
    )
