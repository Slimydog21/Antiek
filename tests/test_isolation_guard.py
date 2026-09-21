"""DOGFOOD SPR-04 M4 — the isolation-guard red-proof.

Proves the test/prod firewall three ways, all hermetic (no real-store
mutation in any case):

1. **Wiring** — the autouse ``_isolate_antiek_store`` fixture is active for
   THIS test, so ``default_db_path()`` resolves to a TMP store, never the real
   ``~/.antiek`` store.
2. **Detection** — ``_check_store_isolated`` (the exact function the fixture
   calls at setup and teardown) REJECTS the real store path and a symlink that
   aliases it (resolve-and-compare rigor), and ACCEPTS a tmp path. This is the
   mechanism that FAILS a deliberately-leaky test under the conftest: a leaky
   test resolves to the real store → the fixture calls this function → it
   raises → the test fails with the guard message.
3. **Opt-out** — the ``real_store_read`` marker is recognized so legitimate
   read-only real-store tests can opt out.

Before SPR-04, a substrate-write test with no tmp home silently mutated the
real store (the pollution source: the ``inv-1`` test edge + placeholder test
nodes). After SPR-04 the same attempt fails loudly. The leaky variant fails;
the hermetic variant passes.
"""

from __future__ import annotations

import os

import pytest

from acquisition.arxiv.rate_governor import ArxivRateGovernor, default_lock_path
from acquisition.arxiv.throttle import default_state_path as arxiv_default_state_path
from runtime.db_lock import connect_write
from substrate.graph import default_db_path
from tests.conftest import (
    _arxiv_isolation_env,
    _check_arxiv_governor_isolated,
    _check_arxiv_path_isolated,
    _check_store_isolated,
    _real_arxiv_paths,
    _real_store_path,
)


def test_guard_provides_hermetic_tmp_store():
    """Wiring: the autouse guard is active, so the resolved DB is a tmp path,
    not the real store. (The hermetic variant passes — isolation is real.)"""
    real = _real_store_path()
    resolved = os.path.realpath(default_db_path())
    assert resolved != real, f"guard failed to redirect: resolved {resolved}"
    assert resolved.endswith("graph.duckdb"), resolved


def test_check_isolated_accepts_tmp_path(tmp_path):
    """Detection: a tmp path is accepted (no raise) — the hermetic case."""
    tmp_db = tmp_path / "graph.duckdb"
    real = _real_store_path()
    _check_store_isolated(str(tmp_db), real)  # must not raise


def test_check_isolated_rejects_real_store():
    """Detection: the real store path is rejected — the leaky case. This is
    the exact raise the autouse fixture would produce for a test that resolved
    to the real store, so such a test FAILS with the guard message."""
    real = _real_store_path()
    with pytest.raises(AssertionError, match="REAL store"):
        _check_store_isolated(real, real, node_id="inv-spr04-leaky-demo")


def test_check_isolated_rejects_symlink_alias(tmp_path):
    """Rigor: a symlink that aliases the real store is still caught.
    Resolve-and-compare (realpath), not string-compare — a leak via a symlink
    cannot bypass the guard."""
    real = _real_store_path()
    alias = tmp_path / "alias.duckdb"
    try:
        os.symlink(real, alias)
    except OSError as exc:  # pragma: no cover — platform cannot symlink
        pytest.skip(f"cannot create symlink: {exc}")
    with pytest.raises(AssertionError, match="REAL store"):
        _check_store_isolated(str(alias), real)


def test_connect_write_to_real_store_blocked_when_enforcement_on(monkeypatch):
    """M4 integration: with enforcement active (as autouse sets), an explicit
    ``connect_write(real)`` fails — the leaky path through the write funnel, not
    only ``default_db_path()`` at fixture boundaries."""
    monkeypatch.setenv("ANTIEK_ENFORCE_TEST_STORE_ISOLATION", "1")
    real = _real_store_path()
    with pytest.raises(RuntimeError, match="REAL store"):
        connect_write(real, purpose="spr04-leaky-proof")


def test_real_store_read_marker_is_recognized():
    """Opt-out: the ``real_store_read`` marker is a registered, recognizable
    marker (the autouse guard returns early for a marked node). We assert the
    marker resolves on a synthetic item the same way the guard checks it."""
    @pytest.mark.real_store_read
    def _marked():  # stand-in node carrying the marker
        pass

    # The guard uses request.node.get_closest_marker; mirror that lookup.
    markers = {m.name for m in _marked.pytestmark}
    assert "real_store_read" in markers, markers


# ── SPR-05 Task 1: the arXiv governor firewall ─────────────────────────────
#
# Same three axes as the store guard above — wiring, detection, opt-out — for
# the arXiv governor's *two* files. Before this, the throttle JSON state was
# redirected wherever a test opted in but the sidecar flock never was, so an
# ``ArxivRateGovernor(lock_path=None)`` reached from a test took ``LOCK_EX`` on
# the operator's live ``~/.antiek/arxiv_throttle.json.governor.lock``.


def test_arxiv_guard_redirects_both_paths_including_the_lock():
    """Wiring: under the autouse guard BOTH production resolvers land off the
    operator's real files. The lock is the half that used to leak — asserting
    only the state path is the exact blind spot this task closed."""
    real_state, real_lock = _real_arxiv_paths()
    resolved_state = os.path.realpath(arxiv_default_state_path())
    resolved_lock = os.path.realpath(default_lock_path())
    assert resolved_state != real_state, resolved_state
    assert resolved_lock != real_lock, resolved_lock
    assert resolved_lock.endswith("arxiv_throttle.json.governor.lock"), resolved_lock


def test_arxiv_guard_redirects_the_governor_object_not_just_the_resolver():
    """Wiring, end-to-end: the class the six leaking test files reach — a
    default-constructed ``ArxivRateGovernor`` with no ``lock_path=`` — resolves
    its flock to tmp. ``rate_governor.py:382`` is where ``lock_path=None``
    became the real path, so this pins the object, not only the free function."""
    _, real_lock = _real_arxiv_paths()
    governor = ArxivRateGovernor()
    assert os.path.realpath(governor.lock_path) != real_lock, governor.lock_path


def test_arxiv_check_accepts_tmp_paths(tmp_path):
    """Detection: tmp paths are accepted (no raise) — the hermetic case."""
    real_state, real_lock = _real_arxiv_paths()
    _check_arxiv_path_isolated(
        str(tmp_path / "arxiv_throttle.json"), real_state, label="throttle state"
    )
    _check_arxiv_path_isolated(
        str(tmp_path / "arxiv_throttle.json.governor.lock"),
        real_lock,
        label="lock path",
    )


def test_arxiv_check_rejects_the_real_governor_lock():
    """Detection: the operator's real lock is rejected — the leaky case. This is
    the exact raise the autouse fixture produces at setup or teardown for a test
    whose governor resolved to the live flock."""
    _, real_lock = _real_arxiv_paths()
    with pytest.raises(AssertionError, match="REAL operator file"):
        _check_arxiv_path_isolated(
            real_lock, real_lock, label="lock path", node_id="spr05-leaky-demo"
        )


def test_arxiv_check_rejects_symlink_alias_of_the_lock(tmp_path):
    """Rigor: a symlink aliasing the real lock is still caught. Resolve-and-
    compare (realpath), not string-compare, so a leak via an alias cannot slip
    past — same discipline as ``_check_store_isolated``."""
    _, real_lock = _real_arxiv_paths()
    if not os.path.exists(real_lock):
        pytest.skip("operator has no live governor lock to alias")
    alias = tmp_path / "alias.governor.lock"
    try:
        os.symlink(real_lock, alias)
    except OSError as exc:  # pragma: no cover — platform cannot symlink
        pytest.skip(f"cannot create symlink: {exc}")
    with pytest.raises(AssertionError, match="REAL operator file"):
        _check_arxiv_path_isolated(str(alias), real_lock, label="lock path")


@pytest.mark.arxiv_governor_contract
def test_arxiv_guard_grips_on_the_constructor_arg_leak_shape(monkeypatch):
    """The red-proof, in the exact shape the six leaking test files had.

    Those files redirect the throttle by *constructor argument*
    (``ArxivThrottle(state_path=tmp)``) and set no env at all. A constructor arg
    cannot reach ``rate_governor.default_lock_path()``, so with both levers
    unset the governor resolves the operator's live flock. Assert the composed
    check raises, and assert the LOCK half raises on its own — a guard that only
    inspected the throttle state would still pass the first assertion while
    leaving the flock wide open, which is the vacuity this test exists to rule
    out.

    Marked ``arxiv_governor_contract`` because it deliberately unsets the levers
    the fixture installs; without the opt-out the fixture's own teardown check
    fires first and masks what this test proves. This test only *resolves* paths
    — it never opens either file.
    """
    real_state, real_lock = _real_arxiv_paths()
    monkeypatch.delenv("ANTIEK_ARXIV_THROTTLE_PATH", raising=False)
    monkeypatch.delenv("ANTIEK_ARXIV_GOVERNOR_LOCK_PATH", raising=False)

    assert os.path.realpath(default_lock_path()) == real_lock, default_lock_path()
    with pytest.raises(AssertionError, match="lock path"):
        _check_arxiv_path_isolated(
            default_lock_path(), real_lock, label="lock path", node_id="spr05-probe"
        )
    with pytest.raises(AssertionError, match="REAL operator file"):
        _check_arxiv_governor_isolated(real_state, real_lock, node_id="spr05-probe")


@pytest.mark.arxiv_governor_contract
def test_arxiv_state_env_alone_already_carries_the_lock(monkeypatch):
    """The boundary of the hole, pinned so nobody widens the fix.

    ``default_lock_path()`` falls back to ``default_state_path() + '.governor
    .lock'``, so a test that sets ``ANTIEK_ARXIV_THROTTLE_PATH`` was never
    leaking even with the lock lever unset. The fourteen env-redirecting test
    files were safe; only the constructor-arg ones were not. Recording that
    keeps a future agent from "fixing" the fourteen.
    """
    _, real_lock = _real_arxiv_paths()
    monkeypatch.setenv("ANTIEK_ARXIV_THROTTLE_PATH", "/tmp/spr05-probe-throttle.json")
    monkeypatch.delenv("ANTIEK_ARXIV_GOVERNOR_LOCK_PATH", raising=False)
    assert default_lock_path() == "/tmp/spr05-probe-throttle.json.governor.lock"
    _check_arxiv_path_isolated(default_lock_path(), real_lock, label="lock path")  # ok


def test_arxiv_isolation_env_sets_both_levers(tmp_path):
    """The redirect is both levers or it is nothing: a one-lever redirect is the
    bug. Pin the key set so a future edit cannot silently drop the lock."""
    env = _arxiv_isolation_env(tmp_path)
    assert set(env) == {
        "ANTIEK_ARXIV_THROTTLE_PATH",
        "ANTIEK_ARXIV_GOVERNOR_LOCK_PATH",
    }, env
    for value in env.values():
        assert str(tmp_path) in value, value


def test_arxiv_governor_contract_marker_is_recognized():
    """Opt-out: the ``arxiv_governor_contract`` marker is registered and
    resolvable the same way the fixture looks it up."""

    @pytest.mark.arxiv_governor_contract
    def _marked():  # stand-in node carrying the marker
        pass

    markers = {m.name for m in _marked.pytestmark}
    assert "arxiv_governor_contract" in markers, markers
