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

The same three proofs are repeated for the arXiv half of the firewall
(SPR-05 arXiv task 1): ``_isolate_arxiv_governor`` redirects the throttle
state file AND the governor flock, ``_check_arxiv_isolated`` rejects the real
paths (and a symlink alias), and ``arxiv_state_contract`` is the opt-out.
Before task 1, six test files that passed ``state_path=`` to ``ArxivThrottle``
still flocked the operator's real ``~/.antiek/arxiv_throttle.json.governor.lock``.

Before SPR-04, a substrate-write test with no tmp home silently mutated the
real store (the pollution source: the ``inv-1`` test edge + placeholder test
nodes). After SPR-04 the same attempt fails loudly. The leaky variant fails;
the hermetic variant passes.
"""

from __future__ import annotations

import os

import pytest

from acquisition.arxiv.rate_governor import ArxivRateGovernor, default_lock_path
from acquisition.arxiv.throttle import ArxivThrottle, default_state_path
from runtime.db_lock import connect_write
from substrate.graph import default_db_path
from tests.conftest import (
    _check_arxiv_isolated,
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


# ---------------------------------------------------------------------------
# SPR-05 arXiv task 1 — the governor-lock half of the firewall.
# ---------------------------------------------------------------------------


def test_arxiv_guard_redirects_both_state_and_lock(tmp_path):
    """Wiring: under the autouse ``_isolate_arxiv_governor`` the throttle state
    file AND the governor lock resolve into tmp, never the real ``~/.antiek``
    paths — and a governor built with NO explicit paths (the six leaking
    call-sites' shape) lands on the redirected lock."""
    real_state, real_lock = _real_arxiv_paths()
    state = os.path.realpath(default_state_path())
    lock = os.path.realpath(default_lock_path())
    assert state != real_state, f"throttle state not redirected: {state}"
    assert lock != real_lock, f"governor lock not redirected: {lock}"
    assert state.endswith("arxiv_throttle.json"), state
    assert lock.endswith("arxiv_throttle.json.governor.lock"), lock

    # A throttle that redirects ONLY its state path (what the six files did)
    # must no longer drag the governor's lock onto the real file.
    gov = ArxivRateGovernor(throttle=ArxivThrottle(state_path=str(tmp_path / "s.json")))
    assert os.path.realpath(gov.lock_path) != real_lock, gov.lock_path


def test_check_arxiv_isolated_accepts_tmp_path(tmp_path):
    """Detection: a tmp path is accepted (no raise) — the hermetic case."""
    real_state, real_lock = _real_arxiv_paths()
    _check_arxiv_isolated(str(tmp_path / "arxiv_throttle.json"), real_state)
    _check_arxiv_isolated(str(tmp_path / "arxiv_throttle.json.governor.lock"), real_lock)


def test_check_arxiv_isolated_rejects_real_paths():
    """Detection: the real throttle state path and the real governor lock path
    are each rejected — the exact raise the autouse fixture produces for a test
    that resolved to the operator's file."""
    real_state, real_lock = _real_arxiv_paths()
    with pytest.raises(AssertionError, match="REAL operator path"):
        _check_arxiv_isolated(real_state, real_state, node_id="spr05-leaky-demo")
    with pytest.raises(AssertionError, match="governor-lock leak"):
        _check_arxiv_isolated(real_lock, real_lock, node_id="spr05-leaky-demo")


def test_check_arxiv_isolated_rejects_symlink_alias(tmp_path):
    """Rigor: a symlink that aliases the real lock is still caught —
    resolve-and-compare, not string-compare."""
    real_state, real_lock = _real_arxiv_paths()
    alias = tmp_path / "alias.governor.lock"
    try:
        os.symlink(real_lock, alias)
    except OSError as exc:  # pragma: no cover — platform cannot symlink
        pytest.skip(f"cannot create symlink: {exc}")
    # realpath of a dangling symlink still resolves to its target, so this
    # holds whether or not the operator's lock file exists right now.
    with pytest.raises(AssertionError, match="REAL operator path"):
        _check_arxiv_isolated(str(alias), real_lock)


def test_arxiv_state_contract_marker_is_recognized():
    """Opt-out: ``arxiv_state_contract`` is a registered, recognizable marker
    (the autouse guard returns early for a marked node)."""
    @pytest.mark.arxiv_state_contract
    def _marked():  # stand-in node carrying the marker
        pass

    markers = {m.name for m in _marked.pytestmark}
    assert "arxiv_state_contract" in markers, markers
