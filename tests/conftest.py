"""Process-wide test isolation.

Three autouse fixtures, all function-scoped:

* ``_isolate_default_breaker`` — resets the dispatch circuit-breaker singleton
  between tests (nygard SPR-04), so a chaos test that trips a provider's
  breaker cannot leak into a later test.
* ``_isolate_provider_credentials`` — removes the DISPATCH provider credentials
  from the environment. ``substrate/dispatch`` registers a LIVE provider
  whenever it finds a key, so a test reaching dispatch on a developer's machine
  opens a real socket to a real vendor: the suite's result then depends on which
  keys that machine happens to export, and the run can spend real money. CI
  already blanks these (enforced by ``tools/lint/provider_env_isolation.py``);
  this fixture makes a local run match CI instead of diverging from it. Tests
  that want a provider still set one explicitly — ``monkeypatch.setenv`` runs
  after this fixture.

  The set is DERIVED from ``substrate/dispatch`` rather than hand-listed, so it
  cannot drift, and it is deliberately narrower than "every ``*_API_KEY``".
  Keys outside dispatch — ``EXA_API_KEY`` is the live example — gate opt-in
  operator tests that skip at MODULE level when the key is absent. A
  function-scoped fixture runs after module import, so stripping those would let
  the module decline to skip and then fail the body. Opt-in tests own their own
  guard; this fixture does not second-guess it.
* ``_isolate_antiek_store`` (DOGFOOD SPR-04) — points every substrate-touching
  test at a TMP store so no test can mutate the real ``~/.antiek`` store. This
  is the test/prod firewall that closes the test-residue pollution gap at its
  source.
* ``_isolate_provider_keys`` — removes real provider API keys from the
  environment. Same firewall, egress side: without it a developer who has
  ``XIAOMI_API_KEY`` (or any of six siblings) exported gets REAL network
  providers registered by ``register_default_providers``, which then outrank a
  test's own stubs. Measured: ``tests/test_loop_one_orchestrator.py`` — whose
  docstring says "the fixtures stub every role's provider" — dispatched to the
  live ``api.mimo.xiaomi.com`` and failed, while passing in CI where no key
  exists. Three tests behaved that way. A test that reaches a real provider
  bills a real key and egresses real data, so this is a cost and privacy
  boundary, not only a flakiness one.

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

from runtime.test_store_guard import real_operator_graph_db_path
from substrate.dispatch.breaker import default_breaker
from substrate.graph import default_db_path
from substrate.graph.insight_question import graph_db_path
from substrate.graph.schema import init_database_at_path
from tools.lint.provider_env_isolation import provider_env_vars


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


# Computed once per worker process: an AST scan of substrate/dispatch, the same
# source of truth the CI lint uses, so the two can never disagree.
_DISPATCH_PROVIDER_KEYS = frozenset(provider_env_vars())


@pytest.fixture(autouse=True)
def _isolate_provider_credentials(monkeypatch):
    """No test may inherit a real dispatch credential from the host environment."""
    for name in _DISPATCH_PROVIDER_KEYS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _isolate_default_breaker():
    default_breaker.reset()
    yield
    default_breaker.reset()


# Every env var `substrate/dispatch/providers/bootstrap.py` consults via
# `resolve_provider_key(handle, env_var)`. tests/test_provider_key_isolation.py
# re-derives this set FROM THAT SOURCE and fails if the two drift, so adding a
# provider cannot silently reopen the hole.
PROVIDER_KEY_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "HERMES_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "XIAOMI_API_KEY",
    "Z_AI_API_KEY",
)


@pytest.fixture(autouse=True)
def _isolate_provider_keys(request, monkeypatch):
    """No test reaches a real provider because the developer happens to have keys.

    `register_default_providers()` registers every provider whose key resolves,
    and a registered real provider outranks a stub the test installed. On CI no
    key exists so the stubs win; on a developer machine they do not. That is a
    test that passes in CI and fails locally for a reason the author never sees
    — and worse, one that silently bills a live API from a unit test.

    BYOK lookups already land in the tmp store via `_isolate_antiek_store`, so
    the environment is the remaining channel.

    Opt out with `@pytest.mark.live_provider` for a test that genuinely needs
    real credentials (a live smoke check). The marker is opt-in, registered in
    pyproject.toml, and grants exactly nothing else.
    """
    if request.node.get_closest_marker("live_provider"):
        return
    for var in PROVIDER_KEY_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


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
