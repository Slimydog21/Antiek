"""Reachability-probe gate package (Antiek — Convergence, SPR-01).

The fifth done-bar: a feature is not "done" because a brick (unit test,
mocked harness) passes — it is done when it is REACHABLE FROM THE REAL
PRODUCT. This package installs the gate that asserts that.

Every probe in ``tools/reachability/probes/`` boots the app through the
PRODUCTION ``create_app()`` factory (NO test-fixture dependency injection,
NO ``retrieval_substrate=``, NO stubbed providers), drives one feature
through its real route(s), and asserts an OBSERVABLE OUTCOME — never the
mere presence of a parameter or a mocked dependency.

See ``probe_runner.py`` for the runner, ``README.md`` for the descriptor
contract + the boot-via-real-factory rule + the known-red escape valve,
and ``docs/decisions/reachability-gate.md`` for why the gate is
blocking + pre-merge + outcome-asserting (every weaker form already
failed in this codebase).
"""
