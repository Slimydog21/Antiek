"""Process-wide test isolation.

Three autouse fixtures, all function-scoped:

* ``_isolate_default_breaker`` — resets the dispatch circuit-breaker singleton
  between tests (nygard SPR-04), so a chaos test that trips a provider's
  breaker cannot leak into a later test.
* ``_isolate_antiek_store`` (DOGFOOD SPR-04) — points every substrate-touching
  test at a TMP store so no test can mutate the real ``~/.antiek`` store. This
  is the test/prod firewall that closes the test-residue pollution gap at its
  source.
* ``_isolate_arxiv_governor`` (SPR-05 Task 1) — the same firewall for the arXiv
  governor's two files: the throttle JSON state AND the sidecar flock that
  serializes it. The state was already redirected wherever a test opted in; the
  lock never was, so test runs took ``fcntl.LOCK_EX`` on the operator's live
  ``~/.antiek/arxiv_throttle.json.governor.lock``.

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
import shutil

import pytest

from acquisition.arxiv.rate_governor import default_lock_path
from acquisition.arxiv.throttle import default_state_path as arxiv_default_state_path
from runtime.test_store_guard import real_operator_graph_db_path
from substrate.dispatch.breaker import default_breaker
from substrate.graph import default_db_path
from substrate.graph.insight_question import graph_db_path
from substrate.graph.schema import init_database_at_path


def _real_store_path() -> str:
    """Canonical real operator store, symlinks resolved (realpath)."""
    return real_operator_graph_db_path()


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


@pytest.fixture(scope="session")
def _antiek_schema_template(tmp_path_factory):
    """An empty-schema DuckDB built once per session. Each test copies it
    (~ms) instead of re-running ``init_database_at_path`` (~72ms) per test,
    which pushed the full pytest suite past its CI job timeout. pytest-xdist
    scopes this per worker, so the build cost is paid a handful of times."""
    template = tmp_path_factory.mktemp("schema-template") / "template.duckdb"
    init_database_at_path(str(template))
    return template


@pytest.fixture(autouse=True)
def _isolate_antiek_store(request, monkeypatch, tmp_path, _antiek_schema_template):
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
    in ``pyproject.toml``). Opt-out skips env redirect **and** the
    ``connect_write`` enforcement flag — the test author owns a read-only,
    no-write posture (honest escape hatch, not a write license).

    Opt out with ``@pytest.mark.store_isolation_contract`` for tests that
    intentionally ``delenv('ANTIEK_DUCKDB_PATH')`` to probe env fallback.
    """
    if request.node.get_closest_marker("real_store_read"):
        yield
        return
    if request.node.get_closest_marker("store_isolation_contract"):
        yield
        return
    real = _real_store_path()
    tmp_db = tmp_path / "graph.duckdb"
    monkeypatch.setenv("ANTIEK_ENFORCE_TEST_STORE_ISOLATION", "1")
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_db))

    # Copy the session-bootstrapped schema template (~ms) so substrate
    # tables exist for the test. Re-running init_database_at_path per test
    # (72ms each) pushed the full pytest suite past the CI job timeout, so
    # the empty schema is built once per session (per xdist worker) and
    # copied per test.
    shutil.copyfile(str(_antiek_schema_template), str(tmp_db))

    _check_store_isolated(default_db_path(), real, node_id=request.node.nodeid)
    _check_store_isolated(graph_db_path(), real, node_id=request.node.nodeid)
    yield
    _check_store_isolated(default_db_path(), real, node_id=request.node.nodeid)
    _check_store_isolated(graph_db_path(), real, node_id=request.node.nodeid)


# ── SPR-05 Task 1: the arXiv governor test/prod firewall ───────────────────
#
# ``_isolate_antiek_store`` above redirects the graph store. It cannot redirect
# the arXiv governor, because neither ``acquisition.arxiv.throttle`` nor
# ``acquisition.arxiv.rate_governor`` consults ``ANTIEK_HOME`` — each has its
# own env lever. Proven empirically: running ``default_lock_path()`` under
# ``ANTIEK_HOME=/tmp/FAKEHOME`` returns the operator's real
# ``~/.antiek/arxiv_throttle.json.governor.lock``.


def _real_arxiv_paths() -> tuple[str, str]:
    """The operator's real arXiv ``(state, lock)`` files, symlinks resolved.

    Resolved from ``~`` directly, NEVER by calling ``arxiv_default_state_path()``
    / ``default_lock_path()``: those consult the very env vars the fixture
    overrides, so asking them for the reference would compare tmp against tmp
    and the guard would pass over an empty set. Each path is realpath'd
    independently rather than appending ``.governor.lock`` to the resolved state,
    so a symlinked state file cannot skew the lock's reference.
    """
    state = os.path.realpath(os.path.expanduser("~/.antiek/arxiv_throttle.json"))
    lock = os.path.realpath(os.path.expanduser("~/.antiek/arxiv_throttle.json.governor.lock"))
    return state, lock


def _arxiv_isolation_env(tmp_path) -> dict[str, str]:
    """The env redirect the fixture installs, as data so it is unit-testable.

    Both levers, always together: redirecting only ``ANTIEK_ARXIV_THROTTLE_PATH``
    (what fourteen test files do) leaves ``default_lock_path()`` resolving to the
    real ``~/.antiek`` sidecar, which is the hole this fixture closes.
    """
    return {
        "ANTIEK_ARXIV_THROTTLE_PATH": str(tmp_path / "arxiv_throttle.json"),
        "ANTIEK_ARXIV_GOVERNOR_LOCK_PATH": str(tmp_path / "arxiv_throttle.json.governor.lock"),
    }


def _check_arxiv_path_isolated(path: str, real: str, *, label: str, node_id: str = "") -> None:
    """Raise ``AssertionError`` iff ``path`` resolves to the real operator file.

    Resolve-and-compare (``realpath``), never string-compare, so a symlink that
    aliases the operator's file is still caught — the same discipline as
    ``_check_store_isolated``.
    """
    if os.path.realpath(os.path.expanduser(str(path))) == real:
        loc = f" for {node_id!r}" if node_id else ""
        raise AssertionError(
            f"SPR-05 arXiv isolation guard: the governor {label} resolves to the "
            f"REAL operator file ({real}){loc} — a test/prod firewall breach. A "
            "test that flocks that path blocks up to 300s behind a live harvest, "
            "stalls the harvest for its own length, and lets _stale_pid_check "
            "unlink the operator's live lock. Set ANTIEK_ARXIV_THROTTLE_PATH and "
            "ANTIEK_ARXIV_GOVERNOR_LOCK_PATH to tmp paths, or mark "
            "@pytest.mark.arxiv_governor_contract for a test that deliberately "
            "probes the default resolution."
        )


def _check_arxiv_governor_isolated(real_state: str, real_lock: str, *, node_id: str = "") -> None:
    """Resolve BOTH arXiv paths through the production resolvers and reject
    either landing on the operator's real file. Extracted from the fixture so
    the detection contract is unit-testable hermetically (see
    ``tests/test_isolation_guard.py``)."""
    _check_arxiv_path_isolated(
        arxiv_default_state_path(), real_state, label="throttle state", node_id=node_id
    )
    _check_arxiv_path_isolated(default_lock_path(), real_lock, label="lock path", node_id=node_id)


@pytest.fixture(autouse=True)
def _isolate_arxiv_governor(request, monkeypatch, tmp_path):
    """SPR-05 Task 1 — hermetic arXiv governor isolation.

    Sibling of ``_isolate_antiek_store``. Fourteen test files already redirect
    the throttle *state* via ``ANTIEK_ARXIV_THROTTLE_PATH``, but the governor's
    sidecar flock resolves separately through ``ANTIEK_ARXIV_GOVERNOR_LOCK_PATH``
    (``rate_governor.default_lock_path``), and passing ``state_path=`` to
    ``ArxivThrottle`` does not redirect it. Six test files did exactly that, so
    an ``ArxivRateGovernor(lock_path=None)`` reached from e.g.
    ``oai_pmh._fetch_page`` took ``fcntl.LOCK_EX`` on the operator's live
    ``~/.antiek/arxiv_throttle.json.governor.lock``. Measured on 2026-09-21: the
    six-file arXiv selection moved that file's mtime and stamped the pytest PID
    into it.

    Autouse so the whole suite inherits isolation without rewrite, and so a test
    added tomorrow through a *new* arXiv path is covered without anyone
    remembering to opt in. The setup check proves the redirect took; the teardown
    check fails any test that re-pointed at the real file mid-body.

    Opt out with ``@pytest.mark.arxiv_governor_contract`` for a test that
    deliberately probes the default (``~/.antiek``) resolution. The opt-out skips
    the redirect *and* both checks — such a test must not actually open either
    file.
    """
    if request.node.get_closest_marker("arxiv_governor_contract"):
        yield
        return
    real_state, real_lock = _real_arxiv_paths()
    for key, value in _arxiv_isolation_env(tmp_path).items():
        monkeypatch.setenv(key, value)
    _check_arxiv_governor_isolated(real_state, real_lock, node_id=request.node.nodeid)
    yield
    _check_arxiv_governor_isolated(real_state, real_lock, node_id=request.node.nodeid)
