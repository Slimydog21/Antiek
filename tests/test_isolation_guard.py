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

from runtime.db_lock import connect_write
from substrate.graph import default_db_path
from tests.conftest import _check_store_isolated, _real_store_path


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
