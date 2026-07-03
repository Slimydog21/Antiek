"""Process-wide test isolation.

Two autouse fixtures, both function-scoped:

* ``_isolate_default_breaker`` — resets the dispatch circuit-breaker singleton
  between tests (nygard SPR-04), so a chaos test that trips a provider's
  breaker cannot leak into a later test.
* ``_isolate_antiek_store`` (DOGFOOD SPR-04) — points every substrate-touching
  test at a TMP store so no test can mutate the real ``~/.antiek`` store. This
  is the test/prod firewall that closes the test-residue pollution gap at its
  source.

``substrate.dispatch.breaker.default_breaker`` is a process-wide singleton the
router consults on every dispatch. Without isolation, any test that exercises
real provider failures (e.g. the chaos paths in
``tests/test_dispatch_fallback_chain.py``) records failures that trip a
provider's breaker for every LATER test in the same process — the exact
cross-test leak that made
``test_synthesis_falls_through_to_hermes_when_openopenrouter_dies`` red on CI
(hermes breaker OPEN from a sibling test) while passing solo. Tests that need
their own breaker semantics construct a private ``CircuitBreaker`` and
monkeypatch it in (see ``tests/test_dispatch_breaker_integration.py``); this
fixture only guarantees the shared default starts every test CLOSED.
"""

import os

import pytest

from substrate.dispatch.breaker import default_breaker
from substrate.graph import default_db_path


def _real_store_path() -> str:
    """Canonical real operator store, symlinks resolved (realpath)."""
    return os.path.realpath(os.path.expanduser("~/.antiek/research_graph.duckdb"))


def _check_store_isolated(db_path: str, real: str, *, node_id: str = "") -> None:
    """Raise ``AssertionError`` iff ``db_path`` resolves to the real store.

    Resolve-and-compare (``realpath``), never string-compare, so a symlink that
    aliases the real store is still caught. Extracted from the autouse fixture
    so the isolation guard is unit-testable hermetically (see
    ``tests/test_isolation_guard.py``) — the detection contract lives here, the
    wiring lives in the fixture, and both are exercised.
    """
    if os.path.realpath(os.path.expanduser(str(db_path))) == real:
        loc = f" for {node_id!r}" if node_id else ""
        raise AssertionError(
            "DOGFOOD SPR-04 isolation guard: the graph DB resolves to the REAL "
            f"store ({real}){loc} — a substrate leak. Set ANTIEK_DUCKDB_PATH to "
            "a tmp path, or mark @pytest.mark.real_store_read for a read-only "
            "real-store test."
        )


@pytest.fixture(autouse=True)
def _isolate_default_breaker():
    default_breaker.reset()
    yield
    default_breaker.reset()


@pytest.fixture(autouse=True)
def _isolate_antiek_store(request, monkeypatch, tmp_path):
    """DOGFOOD SPR-04 — hermetic store isolation (test/prod firewall).

    Every substrate-touching test runs against a TMP store, never the real
    ``~/.antiek/research_graph.duckdb``. Autouse so the whole suite inherits
    isolation without rewrite. ``ANTIEK_DUCKDB_PATH`` is the load-bearing
    override (``default_db_path`` consults it first); we set it (plus
    ``ANTIEK_HOME``) so the resolution redirects for every caller, including
    those that imported ``connect_write`` by name (env beats import binding).

    The self-check at setup proves the provided tmp home actually redirects; the
    teardown check fails any test that re-pointed at the real store mid-body.

    Opt out with ``@pytest.mark.real_store_read`` for the small set of
    legitimate read-only real-store tests (the marker is opt-in and registered
    in ``pyproject.toml``); such a test owns its read-only posture.
    """
    if request.node.get_closest_marker("real_store_read"):
        return
    real = _real_store_path()
    tmp_db = tmp_path / "graph.duckdb"
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_db))
    _check_store_isolated(default_db_path(), real, node_id=request.node.nodeid)
    yield
    _check_store_isolated(default_db_path(), real, node_id=request.node.nodeid)
