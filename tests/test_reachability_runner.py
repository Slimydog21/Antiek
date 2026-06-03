"""Non-vacuity self-test for the reachability-probe runner (SPR-01 M2).

A reachability gate that can only ever exit 0 is worse than nothing — it is
the exact false-confidence disease this whole gate exists to cure. These
tests prove the runner's exit semantics are real:

  * a trivial ALWAYS-TRUE probe -> [REACHABLE], exit 0
  * a trivial ALWAYS-FALSE probe -> [BLOCKED], exit 1
  * a BLOCKED probe under an UNEXPIRED known-red entry -> exit 0 (valve open)
  * a BLOCKED probe under an EXPIRED known-red entry -> exit 1 (valve closed)
  * the per-probe failure modes (boot_fail / timeout / error) are surfaced

Fail-before / pass-after is observed in one run: the same runner reports
BLOCKED on a false outcome and REACHABLE on a true one, so the gate
demonstrably distinguishes the two (it does not always-green).
"""

from __future__ import annotations

import datetime as _dt
import io
import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools.reachability.probe_runner import (  # noqa: E402
    KnownRed,
    Probe,
    ProbeResult,
    run_probes,
)

# Two trivial probes — the minimum proof the runner distinguishes pass/fail.
_ALWAYS_TRUE = Probe(
    id="_selftest_true",
    feature="self-test always-true",
    run=lambda: ProbeResult(ok=True),
)
_ALWAYS_FALSE = Probe(
    id="_selftest_false",
    feature="self-test always-false",
    run=lambda: ProbeResult(ok=False, reason="outcome is false by construction", failure_mode="feature_dead"),
)


def _run(probes, known_red=None, today=None) -> tuple[int, str]:
    buf = io.StringIO()
    code = run_probes(probes, known_red or {}, today=today, out=buf)
    return code, buf.getvalue()


def test_always_true_probe_is_reachable_and_exits_zero():
    code, out = _run([_ALWAYS_TRUE])
    assert code == 0
    assert "[REACHABLE] self-test always-true" in out
    assert "[BLOCKED]" not in out


def test_always_false_probe_is_blocked_and_exits_one():
    code, out = _run([_ALWAYS_FALSE])
    assert code == 1
    assert "[BLOCKED] self-test always-false" in out
    assert "outcome is false by construction" in out
    assert "feature_dead" in out


def test_mixed_run_reports_both_and_fails_on_the_false_one():
    # Fail-before / pass-after in ONE run: the runner greens the true probe
    # and reds the false one, proving it does not always-green.
    code, out = _run([_ALWAYS_TRUE, _ALWAYS_FALSE])
    assert code == 1  # any BLOCKED fails the run
    assert "[REACHABLE] self-test always-true" in out
    assert "[BLOCKED] self-test always-false" in out


def test_unexpired_known_red_keeps_the_run_green():
    # A BLOCKED probe with an UNEXPIRED known-red entry does not fail the run
    # (the intentional fix-window valve) but is still printed as known-red.
    future = (_dt.date(2030, 1, 1)).isoformat()
    kr = {
        _ALWAYS_FALSE.id: KnownRed(
            probe_id=_ALWAYS_FALSE.id,
            until_issue_link="https://example/issue/SPR-02",
            until_date=future,
        )
    }
    code, out = _run([_ALWAYS_FALSE], known_red=kr, today=_dt.date(2026, 6, 3))
    assert code == 0
    assert "known-red" in out
    assert "escape valve" in out


def test_expired_known_red_closes_the_valve_and_fails():
    # An EXPIRED known-red entry must FAIL the run (the valve self-closes so
    # the red can never be ignored forever) and say so explicitly.
    past = (_dt.date(2026, 1, 1)).isoformat()
    kr = {
        _ALWAYS_FALSE.id: KnownRed(
            probe_id=_ALWAYS_FALSE.id,
            until_issue_link="https://example/issue/SPR-02",
            until_date=past,
        )
    }
    code, out = _run([_ALWAYS_FALSE], known_red=kr, today=_dt.date(2026, 6, 3))
    assert code == 1
    assert "EXPIRED" in out
    assert "valve has CLOSED" in out


def test_malformed_known_red_date_is_treated_as_expired():
    kr = {
        _ALWAYS_FALSE.id: KnownRed(
            probe_id=_ALWAYS_FALSE.id,
            until_issue_link="https://example/issue/SPR-02",
            until_date="not-a-date",
        )
    }
    code, _out = _run([_ALWAYS_FALSE], known_red=kr, today=_dt.date(2026, 6, 3))
    assert code == 1  # fail-closed on an unparseable expiry


def test_probe_that_raises_is_blocked_not_crashed():
    def _boom() -> ProbeResult:
        raise RuntimeError("kaboom")

    raising = Probe(id="_selftest_raise", feature="self-test raising", run=_boom)
    code, out = _run([raising])
    assert code == 1
    assert "[BLOCKED] self-test raising" in out
    assert "RuntimeError" in out
    assert "error" in out  # failure_mode


def test_probe_that_times_out_is_blocked():
    import time

    def _slow() -> ProbeResult:
        time.sleep(5.0)
        return ProbeResult(ok=True)

    slow = Probe(id="_selftest_slow", feature="self-test slow", run=_slow, timeout_s=0.2)
    code, out = _run([slow])
    assert code == 1
    assert "[BLOCKED] self-test slow" in out
    assert "timeout" in out
