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


# ── SPR-11: the THIRD assertion — flywheel liveness ─────────────────────
#
# These prove the extension is non-vacuous at the assert_parity level: a
# dead flywheel (flywheel_ready false, or the field absent) reds with a
# flywheel-NAMED message, while an otherwise-in-parity body with a LIVE
# flywheel is clean.


def test_assert_parity_dead_flywheel_reports_failure():
    # SHA matches + providers present, but the flywheel is DEAD.
    failures = parity.assert_parity(
        _fake_health(
            build_sha=_GOOD_SHA,
            providers=["openrouter"],
            flywheel_ready=False,
            knowledge_reuse_count=0,
        ),
        expected_sha=_GOOD_SHA,
    )
    assert failures, "a dead flywheel must produce a failure message"
    assert any("flywheel" in f.lower() for f in failures), (
        "the failure message must NAME the flywheel condition, not just SHA/providers"
    )


def test_assert_parity_absent_flywheel_field_reports_failure():
    # An older build that predates the SPR-11 /health field: flywheel_ready
    # is ABSENT. The safe red — we cannot prove the flywheel is live.
    body = _fake_health(build_sha=_GOOD_SHA, providers=["openrouter"])
    del body["flywheel_ready"]
    del body["knowledge_reuse_count"]
    failures = parity.assert_parity(body, expected_sha=_GOOD_SHA)
    assert failures, "an absent flywheel_ready field must red (cannot prove liveness)"
    assert any("flywheel" in f.lower() for f in failures)


def test_assert_parity_live_flywheel_and_all_clean_is_clean():
    # SHA match + providers present + flywheel LIVE → no failures.
    failures = parity.assert_parity(
        _fake_health(
            build_sha=_GOOD_SHA,
            providers=["openrouter", "deepseek"],
            flywheel_ready=True,
            knowledge_reuse_count=3,
        ),
        expected_sha=_GOOD_SHA,
    )
    assert failures == [], "in-parity input with a live flywheel must produce no failures"


def test_run_dead_flywheel_exits_one(monkeypatch):
    # The load-bearing exit-code case: a dead flywheel must exit 1, not
    # log-and-pass. SHA + providers are fine; only the flywheel is dead.
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
    assert rc == 1, "a dead flywheel must exit 1 (a parity failure), not 0"


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


def test_run_providers_present_and_sha_match_exits_zero(monkeypatch):
    monkeypatch.setattr(
        parity,
        "fetch_health",
        lambda url, **kw: _fake_health(build_sha=_GOOD_SHA, providers=["openrouter"]),
    )
    rc = parity.run("http://fake.invalid", expected_sha=_GOOD_SHA)
    assert rc == 0, "matching SHA + providers present must exit 0"


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

    def _capture(url, expected_sha, *, auth_probe=False, auth_origin="https://antiek.ai"):
        seen["url"] = url
        seen["expected_sha"] = expected_sha
        seen["auth_probe"] = auth_probe
        seen["auth_origin"] = auth_origin
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
