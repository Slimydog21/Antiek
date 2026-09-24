"""Non-vacuity tests for the prod-parity assertion (SPR-07).

A parity check that only ever exits ``0`` is worse than nothing — it
manufactures false confidence and would have missed the original
stale-SPA drift just as silently. These tests prove the assertion can
fail: a SHA mismatch reds, an empty provider registry reds, and the
in-parity case greens — fail-before / pass-after observed in one run.

The test names are chosen so the spec's verification gates resolve:
``-k empty_providers`` selects the empty-registry red, and
``-k providers_present`` selects the in-parity green.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools.prod_parity import check as parity  # noqa: E402  (intentional: sys.path bootstrap above)

_GOOD_SHA = "a" * 40
_OTHER_SHA = "b" * 40


def _fake_health(
    *,
    build_sha: str,
    providers: list[str],
    flywheel_ready: bool = True,
    knowledge_reuse_count: int = 1,
) -> dict:
    """A stand-in /health body, shaped like the real HealthResponse.

    ``flywheel_ready`` defaults to True (the in-parity case) so the
    pre-SPR-11 tests that only vary SHA/providers stay meaningful: they
    isolate the condition they name. The SPR-11 flywheel cases pass
    ``flywheel_ready=False`` explicitly.
    """
    return {
        "status": "ok",
        "param_version": "x",
        "schema_version": 1,
        "subscriber_count": 0,
        "registered_providers": providers,
        "build_sha": build_sha,
        "flywheel_ready": flywheel_ready,
        "knowledge_reuse_count": knowledge_reuse_count,
    }


# ── assert_parity unit-level (no network) ───────────────────────────────


def test_assert_parity_sha_mismatch_reports_failure():
    failures = parity.assert_parity(
        _fake_health(build_sha=_OTHER_SHA, providers=["openrouter"]),
        expected_sha=_GOOD_SHA,
    )
    assert failures, "a SHA mismatch must produce a failure message"
    assert any("SHA mismatch" in f for f in failures)


def test_assert_parity_providers_present_and_sha_match_is_clean():
    failures = parity.assert_parity(
        _fake_health(build_sha=_GOOD_SHA, providers=["openrouter", "deepseek"]),
        expected_sha=_GOOD_SHA,
    )
    assert failures == [], "in-parity input must produce no failures"


def test_assert_parity_empty_providers_reports_failure():
    failures = parity.assert_parity(
        _fake_health(build_sha=_GOOD_SHA, providers=[]),
        expected_sha=_GOOD_SHA,
    )
    assert failures, "an empty provider registry must produce a failure message"
    assert any("provider registry" in f for f in failures)


# ── SPR-11: flywheel liveness — INFORMATIONAL by default ────────────────
#
# Flywheel liveness is NOT a deploy-correctness invariant (it is gated on a
# corpus + real research activity, not on the shipped code), so it lives in
# flywheel_warnings — NOT assert_parity — and only blocks the run when
# require_flywheel=True. These prove: assert_parity ignores the flywheel,
# flywheel_warnings names a dead one, and the run-level default is
# warn-but-pass. See docs/decisions/prod-parity-flywheel-informational.md.


def test_assert_parity_ignores_flywheel():
    # A dead flywheel is NOT an assert_parity failure — SHA + providers only.
    failures = parity.assert_parity(
        _fake_health(
            build_sha=_GOOD_SHA,
            providers=["openrouter"],
            flywheel_ready=False,
            knowledge_reuse_count=0,
        ),
        expected_sha=_GOOD_SHA,
    )
    assert failures == [], "assert_parity must gate only SHA + providers, not the flywheel"


def test_flywheel_warnings_dead_flywheel_names_it():
    warnings = parity.flywheel_warnings(
        _fake_health(
            build_sha=_GOOD_SHA,
            providers=["openrouter"],
            flywheel_ready=False,
            knowledge_reuse_count=0,
        )
    )
    assert warnings, "a dead flywheel must produce a warning message"
    assert any("flywheel" in w.lower() for w in warnings), (
        "the warning must NAME the flywheel condition, not just SHA/providers"
    )


def test_flywheel_warnings_absent_field_warns():
    # An older build that predates the SPR-11 /health field: flywheel_ready
    # is ABSENT. The safe warn — we cannot prove the flywheel is live.
    body = _fake_health(build_sha=_GOOD_SHA, providers=["openrouter"])
    del body["flywheel_ready"]
    del body["knowledge_reuse_count"]
    warnings = parity.flywheel_warnings(body)
    assert warnings, "an absent flywheel_ready field must warn (cannot prove liveness)"
    assert any("flywheel" in w.lower() for w in warnings)


def test_flywheel_warnings_live_flywheel_is_clean():
    warnings = parity.flywheel_warnings(
        _fake_health(
            build_sha=_GOOD_SHA,
            providers=["openrouter"],
            flywheel_ready=True,
            knowledge_reuse_count=3,
        )
    )
    assert warnings == [], "a live flywheel must produce no warnings"


def test_run_dead_flywheel_informational_exits_zero(monkeypatch):
    # The behaviour fix: a dead flywheel is INFORMATIONAL by default. SHA +
    # providers are fine, so a correct code deploy onto an unfed box passes
    # (exit 0) and only emits a warning — it does not red the deploy.
    monkeypatch.setattr(
        parity,
        "fetch_health",
        lambda url, **kw: _fake_health(
            build_sha=_GOOD_SHA,
            providers=["openrouter"],
            flywheel_ready=False,
            knowledge_reuse_count=0,
        ),
    )
    rc = parity.run("http://fake.invalid", expected_sha=_GOOD_SHA)
    assert rc == 0, "a dead flywheel must be informational by default (exit 0), not block"


def test_run_require_flywheel_dead_exits_one(monkeypatch):
    # Opt-in (post-corpus): with require_flywheel=True a dead flywheel is a
    # blocking failure again — the original SPR-11 intent, correctly sequenced.
    monkeypatch.setattr(
        parity,
        "fetch_health",
        lambda url, **kw: _fake_health(
            build_sha=_GOOD_SHA,
            providers=["openrouter"],
            flywheel_ready=False,
            knowledge_reuse_count=0,
        ),
    )
    rc = parity.run("http://fake.invalid", expected_sha=_GOOD_SHA, require_flywheel=True)
    assert rc == 1, "--require-flywheel must promote a dead flywheel back to a blocking failure"


def test_run_live_flywheel_all_clean_exits_zero(monkeypatch):
    monkeypatch.setattr(
        parity,
        "fetch_health",
        lambda url, **kw: _fake_health(
            build_sha=_GOOD_SHA,
            providers=["openrouter"],
            flywheel_ready=True,
            knowledge_reuse_count=2,
        ),
    )
    rc = parity.run("http://fake.invalid", expected_sha=_GOOD_SHA)
    assert rc == 0, "SHA match + providers + live flywheel must exit 0"


# ── run() exit-code level: the load-bearing "it must red, not log" cases ─
#
# These monkeypatch the network fetch so no live call is made, and assert
# on the *exit code* returned by run() — proving the check literally
# fails (non-zero) rather than merely emitting a log line.


def test_run_sha_mismatch_exits_nonzero(monkeypatch):
    monkeypatch.setattr(
        parity,
        "fetch_health",
        lambda url, **kw: _fake_health(build_sha=_OTHER_SHA, providers=["openrouter"]),
    )
    rc = parity.run("http://fake.invalid", expected_sha=_GOOD_SHA)
    assert rc != 0, "a SHA mismatch must exit non-zero, not log-and-pass"


def test_run_providers_present_and_sha_match_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(
        parity,
        "fetch_health",
        lambda url, **kw: _fake_health(build_sha=_GOOD_SHA, providers=["openrouter"]),
    )
    rc = parity.run("http://fake.invalid", expected_sha=_GOOD_SHA)
    assert rc == 0, "matching SHA + providers present must exit 0"
    output = capsys.readouterr().out
    assert f"build_sha {_GOOD_SHA} matches expected_sha {_GOOD_SHA}" in output
    assert "matches main" not in output


def test_run_converging_success_reports_observed_sha(monkeypatch, capsys):
    monkeypatch.delenv("ANTIEK_API_BASE", raising=False)
    monkeypatch.setattr(
        parity,
        "fetch_health",
        lambda url, **kw: _fake_health(
            build_sha=_OTHER_SHA, providers=["openrouter"]
        ),
    )
    monkeypatch.setattr(parity, "staleness_failures", lambda *args, **kw: [])

    rc = parity.run("http://fake.invalid", expected_sha=_GOOD_SHA, max_lag_hours=720)
    output = capsys.readouterr().out

    assert rc == 0
    assert f"build_sha {_OTHER_SHA}" in output
    assert f"expected_sha {_GOOD_SHA}" in output
    assert "converging" in output
    assert "matches main" not in output


def test_run_empty_providers_exits_nonzero(monkeypatch):
    monkeypatch.setattr(
        parity,
        "fetch_health",
        lambda url, **kw: _fake_health(build_sha=_GOOD_SHA, providers=[]),
    )
    rc = parity.run("http://fake.invalid", expected_sha=_GOOD_SHA)
    assert rc != 0, "empty provider registry must exit non-zero"


def test_run_unreachable_endpoint_exits_two(monkeypatch):
    def _boom(url, **kw):
        raise OSError("connection refused")

    monkeypatch.setattr(parity, "fetch_health", _boom)
    rc = parity.run("http://fake.invalid", expected_sha=_GOOD_SHA)
    assert rc == 2, "an unreachable endpoint must exit 2 (could-not-check), not 0"


# ── main() CLI wiring: the --expected-sha defaulting path (M1 criterion) ─
#
# M1 requires --expected-sha to DEFAULT to `git rev-parse origin/main` when
# omitted. These tests pin that wiring without a live call or a git
# dependency: subprocess + fetch are monkeypatched. They are non-vacuous —
# if main() stopped falling back to default_expected_sha() (e.g. someone
# made --expected-sha required), the first test reds; if a failed
# default_expected_sha() stopped mapping to exit 2, the second reds.


def test_main_defaults_expected_sha_to_origin_main(monkeypatch):
    # --expected-sha omitted → main() must compute it via
    # default_expected_sha() and pass it through to the comparison.
    monkeypatch.setattr(parity, "default_expected_sha", lambda: _GOOD_SHA)
    seen = {}

    def _capture(
        url,
        expected_sha,
        *,
        auth_probe=False,
        auth_origin="https://antiek.ai",
        require_flywheel=False,
        # Tolerate kwargs the real run() grows; this test asserts only that
        # expected_sha defaults to origin/main, not run()'s full signature.
        **_kw,
    ):
        seen["url"] = url
        seen["expected_sha"] = expected_sha
        seen["auth_probe"] = auth_probe
        seen["auth_origin"] = auth_origin
        seen["require_flywheel"] = require_flywheel
        return 0

    monkeypatch.setattr(parity, "run", _capture)
    rc = parity.main(["--url", "http://fake.invalid"])
    assert rc == 0
    assert seen["expected_sha"] == _GOOD_SHA, (
        "main() must default --expected-sha to default_expected_sha() "
        "(git rev-parse origin/main)"
    )


def test_main_unresolvable_expected_sha_exits_two(monkeypatch):
    # default_expected_sha() blowing up (no git / no origin/main) must map
    # to exit 2 (could-not-check), never a false green.
    def _boom():
        raise RuntimeError("git rev-parse origin/main failed")

    monkeypatch.setattr(parity, "default_expected_sha", _boom)
    rc = parity.main(["--url", "http://fake.invalid"])
    assert rc == 2, "an uncomputable expected SHA must exit 2, not 0"


def test_default_expected_sha_returns_rev_parse_output(monkeypatch):
    # The helper must surface the trimmed stdout of a successful
    # `git rev-parse origin/main`, not swallow it.
    class _Done:
        returncode = 0
        stdout = _GOOD_SHA + "\n"
        stderr = ""

    monkeypatch.setattr(parity.subprocess, "run", lambda *a, **kw: _Done())
    assert parity.default_expected_sha() == _GOOD_SHA


def test_default_expected_sha_raises_on_git_failure(monkeypatch):
    # A non-zero `git rev-parse` must raise (→ exit 2 upstream), never
    # return an empty/garbage SHA that could spuriously match.
    class _Fail:
        returncode = 128
        stdout = ""
        stderr = "fatal: ambiguous argument 'origin/main'"

    monkeypatch.setattr(parity.subprocess, "run", lambda *a, **kw: _Fail())
    with pytest.raises(RuntimeError):
        parity.default_expected_sha()


# ── end-to-end against the real /health route ───────────────────────────
#
# Proves build_sha is actually populated on the real HealthResponse and
# that the check reds/greens against the live route. Uses register_
# providers=False so no operator credentials are touched and no live API
# call is made (the in-parity case stamps a known SHA via the env).


@pytest.fixture
def _app_client(monkeypatch):
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    def _make(build_sha: str, *, register_providers: bool):
        monkeypatch.setenv("ANTIEK_BUILD_SHA", build_sha)
        application = create_app(
            register_wrestling=False,
            register_providers=register_providers,
            cors_origins=[],
        )
        return TestClient(application)

    return _make


def test_health_exposes_build_sha_from_env(_app_client):
    client = _app_client(_GOOD_SHA, register_providers=False)
    body = client.get("/health").json()
    assert "build_sha" in body, "/health must expose build_sha (SPR-07 M1)"
    assert body["build_sha"] == _GOOD_SHA


def test_run_against_live_route_sha_mismatch_reds(_app_client, monkeypatch):
    # The route reports _GOOD_SHA; we expect _OTHER_SHA → mismatch reds.
    client = _app_client(_GOOD_SHA, register_providers=False)
    monkeypatch.setattr(parity, "fetch_health", lambda url, **kw: client.get("/health").json())
    rc = parity.run("http://testserver", expected_sha=_OTHER_SHA)
    assert rc != 0, "live-route SHA mismatch must red"


def test_run_against_live_route_providers_present_greens(_app_client, monkeypatch):
    # register_providers=False makes the registry empty — to prove the
    # in-parity green we monkeypatch the route body's registry to be
    # non-empty (the credential-gated registry is operator-only; we never
    # touch real keys). SHA matches what the route reports.
    #
    # SPR-11: the live flywheel is likewise a runtime signal a fresh test
    # box does not have (no graph DB, zero knowledge.reused events), so the
    # real route reports flywheel_ready=false. We stamp it true here for
    # the SAME reason we stamp providers — we are proving the in-parity
    # GREEN path, and the flywheel-dead RED is proven by the dedicated
    # seed-and-catch tests above (test_run_dead_flywheel_exits_one) and in
    # test_check_seed_and_catch.py. We never fabricate a real prod curve.
    client = _app_client(_GOOD_SHA, register_providers=False)

    def _health_with_providers(url, **kw):
        body = client.get("/health").json()
        body["registered_providers"] = ["openrouter"]
        body["flywheel_ready"] = True
        body["knowledge_reuse_count"] = 1
        return body

    monkeypatch.setattr(parity, "fetch_health", _health_with_providers)
    rc = parity.run("http://testserver", expected_sha=_GOOD_SHA)
    assert rc == 0, "live-route in-parity (SHA match + providers present) must green"


# ── scheduled drift-alarm mode (staleness, not exact equality) ──────────────
#
# `assert_parity` demands build_sha == expected_sha. That is the right
# contract straight after a deploy — you shipped X, prod must report X — and
# these tests do not change it. It is the wrong contract for the DAILY probe,
# where `expected_sha` defaults to main's tip: with automatic deploys main
# advances while a deploy is in flight, so equality is false for a window
# after every merge. Measured 2026-09-21: the scheduled job had failed 30 of
# its last 100 runs and 13 of its last 15, with production provably healthy
# and converging (prod an ancestor of main, oldest unshipped commit 0.6h old).
# An alarm that reds on correct operation stops being read.


def _commits(repo_shas):
    """Fake `git` so these tests never depend on real repo history."""
    return repo_shas


def test_staleness_exact_match_is_clean():
    from tools.prod_parity.check import staleness_failures

    assert staleness_failures("abc", "abc", max_lag_hours=6) == []


def test_staleness_missing_build_sha_fails():
    from tools.prod_parity.check import staleness_failures

    out = staleness_failures("", "abc", max_lag_hours=6)
    assert out and "no build_sha" in out[0]


def test_staleness_non_ancestor_fails_regardless_of_budget(monkeypatch):
    """A fork or rollback is never correct, however generous the budget.

    This is the assertion that keeps the alarm honest: relaxing the TIME
    budget must not make prod-on-a-different-history acceptable.
    """
    import subprocess as sp

    from tools.prod_parity import check as mod

    def fake_run(args, **kw):
        if args[:2] == ["git", "cat-file"]:
            return sp.CompletedProcess(args, 0, "commit", "")
        if args[:2] == ["git", "merge-base"]:
            return sp.CompletedProcess(args, 1, "", "")  # NOT an ancestor
        return sp.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    out = mod.staleness_failures("dead", "beef", max_lag_hours=10**9)
    assert out and "NOT an ancestor" in out[0]


def test_staleness_recent_lag_passes_but_old_lag_fails(monkeypatch):
    """The budget must actually bite: same ancestry, only the age differs."""
    import subprocess as sp

    from tools.prod_parity import check as mod

    now = 1_700_000_000.0
    monkeypatch.setattr(mod.time, "time", lambda: now)

    def make(age_hours):
        ts = int(now - age_hours * 3600)

        def fake_run(args, **kw):
            if args[:2] == ["git", "cat-file"]:
                return sp.CompletedProcess(args, 0, "commit", "")
            if args[:2] == ["git", "merge-base"]:
                return sp.CompletedProcess(args, 0, "", "")  # IS an ancestor
            if args[1] == "log":
                return sp.CompletedProcess(args, 0, f"{ts}\n", "")
            if args[1] == "rev-list":
                return sp.CompletedProcess(args, 0, "2\n", "")
            return sp.CompletedProcess(args, 0, "", "")

        return fake_run

    monkeypatch.setattr(mod.subprocess, "run", make(0.5))
    assert mod.staleness_failures("a", "b", max_lag_hours=6) == []

    monkeypatch.setattr(mod.subprocess, "run", make(48))
    out = mod.staleness_failures("a", "b", max_lag_hours=6)
    assert out and "stale deploy" in out[0]
