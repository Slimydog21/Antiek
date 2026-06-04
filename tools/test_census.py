"""Read-only test census over ``tests/`` — real-vs-mock + Beck 'predictive' flag.

WHY THIS EXISTS
===============
Kent Beck's Test Desiderata name ten properties a good test owes its reader.
The one the Antiek suite most violates is **predictive** — "if the tests pass,
the production code works." An execution-trajectory autopsy of the run ledgers
found a green-on-mocks pattern: ``mock`` / ``stub`` / ``fake`` machinery
outnumbers any real-model gate, and a large fraction of test FILES mock the AI
collaborator they are nominally verifying. That finding lived only in prose.

This tool turns the prose into a reproducible instrument. It walks
``tests/`` with the standard-library ``ast`` module and records, per test file
and per test function, three things:

  1. ``uses_mock``  — does the test use mocking machinery at all?
  2. ``mock_targets`` + behavioral-vs-environmental tagging — WHAT kind of
     collaborator is mocked? Mocking a *behavioral collaborator* (the provider /
     dispatch / LLM / DB-writer the test is supposed to verify) is the
     predictiveness risk; mocking an *environmental nuisance* (``time.sleep``,
     a logger, a temp ``os.environ``) is ordinary, correct isolation.
  3. ``predictive``  — do the test's assertions check BEHAVIOR (the unit's
     output: a returned value, a raised exception, an emitted event, a DB row,
     a parsed result) or only STRUCTURE (a mock's call shape:
     ``assert_called*``, ``call_count``, ``call_args``, ``assert_awaited*``)?

The census **REPORTS**. It never judges, runs, fixes, rewrites, skips, or
deletes a test; it picks no "acceptable" ratio and fails on no number (that is
SPR-05's mock-budget gate, locked against THIS measured baseline). It exits 0
always. It is the substrate SPR-05 (mock budget) and SPR-02 (mutant
prioritization, fed the lowest-predictiveness modules) build on.

WHAT IT IS NOT
==============
It is a STATIC proxy for predictiveness, not a measurement of it. The only
ground truth for "do the tests predict production correctness" is a real run
against a real model (first-light) or a mutation campaign (SPR-02). This tool
cannot, and does not claim to, distinguish a behavioral-collaborator mock that
is *correct isolation* (a dispatch-routing unit test SHOULD mock the provider —
the provider is out of the unit's scope) from one that is *disease* (a test
that mocks the very provider whose behavior it purports to verify). It records
the signal both share — ``uses_mock`` against a behavioral surface — and leaves
the disease/isolation judgement to a reader with the unit's intent in hand.
This is a KNOWN, DOCUMENTED limit, surfaced in the report, not hidden.

THE JSON SHAPE (the contract SPR-02 / SPR-05 read)
==================================================
``--json`` emits one object::

    {
      "generated_at": "<ISO-8601 UTC>",   # ONLY when SOURCE_DATE_EPOCH is set;
                                           # OMITTED otherwise (see DETERMINISM)
      "tree_sha": "<git rev-parse HEAD, or 'unknown'>",
      "modules": [ ModuleRecord, ... ],    # sorted by module path
      "tests":   [ TestFnRecord, ... ],    # sorted by (file, lineno)
      "totals":  { ... }                   # suite-wide rollup (see TOTALS)
    }

``ModuleRecord`` fields: ``module`` (the test file's repo-relative path),
``n_tests``, ``n_mock_tests``, ``mock_ratio`` (n_mock_tests / n_tests, 4dp),
``n_structure_only`` (predictive == "structure" or "none"... no: structure-only
counts ``predictive == "structure"`` tests; see ModuleRecord), and
``predictive_ratio`` ((behavior + mixed) / n_tests, 4dp).

``TestFnRecord`` fields: ``file`` (repo-relative), ``name``, ``lineno``,
``uses_mock`` (bool), ``mock_targets`` (tuple of dotted patch targets, or the
sentinel ``"<dynamic>"`` for a non-string-literal target, or a behavioral/
environmental fake/monkeypatch token), ``predictive``
(``"behavior"`` | ``"structure"`` | ``"mixed"`` | ``"none"``),
``assert_count``, ``mock_setup_lines`` (count of statements that establish a
mock: ``with patch(...)``, ``monkeypatch.set*`` calls, ``Mock()``/``MagicMock()``
construction, project-local fake construction).

TOTALS block fields: ``n_test_functions``, ``n_test_files``,
``n_mock_tests``, ``n_mock_files`` (distinct files with ≥1 mock test),
``n_behavioral_mock_files`` (distinct files with ≥1 test mocking a behavioral
surface), ``suite_mock_ratio`` (4dp), ``suite_predictive_ratio`` (4dp),
``n_structure_tests``, ``n_none_tests``, ``n_asserts_own_mock_return``.

CLASSIFICATION RULES (defensible; read these before disputing a flag)
=====================================================================
A *test function* is any ``def`` / ``async def`` whose name starts with
``test``, whether module-level or a method of a ``Test*``-style class. Its body
is analysed together with module-level context that applies to it (module-level
``@patch`` decorators on the function, ``monkeypatch`` parameters, autouse
fixtures, mock-establishing fixtures it depends on by parameter name, and
module-level mock-factory helpers it calls). NB: the bare presence of a
``from unittest.mock import …`` line is NOT itself a signal — detection is
BODY-driven (a construction / call / decorator / inherited fixture in scope of
the function), so importing ``Mock`` without using it does not flag a test.

uses_mock is True when ANY of:
  - the function CONSTRUCTS a ``unittest.mock`` symbol via a BARE name —
    ``Mock()`` / ``MagicMock()`` / ``AsyncMock()`` / ``patch(...)`` /
    ``mock_open()`` / ``PropertyMock()``. (An ATTRIBUTE call such as
    ``p.call(...)`` / ``client.seal()`` is an ordinary method call that merely
    shares a symbol's spelling and is NOT a construction — see
    ``_call_is_mock_construction``; conflating the two was defect B1.);
  - the function (or a decorator on it) calls ``patch(...)`` /
    ``patch.object(...)`` / ``patch.dict(...)`` / ``mock.patch(...)``;
  - the function takes a ``monkeypatch`` parameter, OR calls
    ``monkeypatch.setattr`` / ``.setenv`` / ``.delattr`` / ``.delenv`` /
    ``.setitem`` / ``.delitem`` / ``.syspath_prepend`` / ``.chdir``;
  - the function constructs a project-local fake — a class defined in the
    module whose name matches ``Fake* / Stub* / _Mock* / Mock* / *Fake / *Stub``
    (the suite uses ``FakeFetcher``, ``_MockAnthropicProvider``,
    ``_StubNoteTaker``; ``MockTransport`` matches too) reached by bare name OR
    attribute tail — or takes a fixture parameter whose name suggests one
    (``*fake* / *stub* / stub_embedder``);
  - the function CALLS a module-level mock-factory helper — a plain (non-test,
    non-fixture) module function that itself builds a mock, e.g.
    ``_make_client(handler)`` returning ``httpx.MockTransport`` — inheriting the
    helper's targets (defect B2: provider-adapter tests mock the HTTP surface
    only through such a factory and were otherwise invisible);
  - a mock-establishing fixture it depends on (by parameter name), or an autouse
    fixture in the module, establishes a mock (so functions that name no mock
    still inherit one).

A mock target is tagged BEHAVIORAL when its dotted name / fake-class name /
monkeypatch target contains a token in ``BEHAVIORAL_TARGET_HINTS`` (below) and
ENVIRONMENTAL when it matches ``ENVIRONMENTAL_TARGET_HINTS`` and no behavioral
token. A target matching neither is recorded but tagged neither (it counts for
``uses_mock`` and ``mock_targets`` but not toward ``n_behavioral_mock_files``).
Dotted ``patch("a.b.c")`` targets are resolved ONLY when the argument is a
string literal; an interpolated / name / attribute argument is recorded as the
sentinel ``"<dynamic>"`` rather than guessed.

predictive is decided from the assert statements and the mock-shape calls in
the function body:
  - STRUCTURE  — the only meaningful assertions are mock-call-shape checks:
    a ``.assert_called* / .assert_awaited* / .assert_not_called / .assert_any_call``
    method call, OR an ``assert`` whose compared/operand expression reads a
    ``.call_count`` / ``.call_args`` / ``.call_args_list`` / ``.await_count`` /
    ``.mock_calls`` attribute. (NB: in THIS suite the call-shape signal is
    almost entirely ``.call_count`` attribute reads on hand-rolled fakes, NOT
    ``unittest.mock`` ``.assert_called*`` methods, which are absent — the rule
    catches both since both observe call shape rather than the unit's output.)
  - BEHAVIOR   — at least one assertion checks the unit's output: an ``assert``
    on a non-call-shape value, a ``with pytest.raises(...)`` /
    ``pytest.warns(...)`` block, a ``pytest.fail`` / explicit ``raise`` guard,
    an ``assert`` reading an emitted-event / parsed-result expression, OR a call
    to an ASSERT-HELPER — a function whose name matches ``assert* / _assert* /
    check_* / expect_* / verify_*`` (see ``ASSERT_HELPER_PREFIXES``), which
    raises on failure so the call IS the check (``_assert_conserved(shares)``,
    ``log.assert_phase_completed(8)``). This is a documented heuristic, added in
    round 2 (defect MAJOR): the suite delegates many behavior checks to such
    helpers, and treating them as ``none`` wrongly dominated the lowest-
    predictiveness list. The ``unittest.mock`` ``assert_called*`` family is
    EXCLUDED (it is structure, matched first). Any behavior assertion present ⇒
    at least ``mixed``.
  - MIXED      — both a behavior assertion AND a structure assertion are present.
  - NONE       — no meaningful assertion (a smoke test: it constructs and calls
    but asserts nothing, or asserts only a trivially-true ``assert True``).

THE CANONICAL FAKE GATE (Beck 'predictive' in its purest failure):
  A test that asserts ONLY on a value produced by a mock IT ITSELF configured —
  ``m.return_value = 7; assert f() == 7`` where ``f`` returns ``m()`` — proves
  only that the mock returns what it was told to. The census flags this
  ``structure`` with the reason ``"asserts-own-mock-return"``. Detected when a
  mock object in the function has ``.return_value`` / ``.side_effect`` assigned
  AND every behavior-looking assertion in the function reads (transitively) only
  from that same mock object. This is rare in the current suite (the
  ``m.return_value = ...`` idiom is nearly absent) but is the exact pattern the
  flag exists to surface, so it is detected and unit-tested via fixtures.

EXCLUDES (documented constant ``EXCLUDE_DIR_PARTS``)
====================================================
``.caffenagent`` (spec-execution scratch worktrees — running specs litter the
tree with copies of OTHER sprints' tests; counting them would double-count and
make the census non-reproducible across concurrent runs) and ``htmlspec`` under
``docs/`` (HTML spec-execution scratch, not the product suite). Any path with a
component named ``.caffenagent`` or matching ``docs/.../htmlspec`` is skipped.
This is why the census is read against the PRODUCT ``tests/`` tree only.

DETERMINISM (Beck 'predictive' is worthless without it; SPR-05 diffs this)
==========================================================================
Two runs on an unchanged tree MUST produce byte-identical ``census.json``:
  - records are sorted by a total order (modules by ``module``; tests by
    ``(file, lineno)``); tuples inside a record are sorted;
  - all floats are rounded to 4 decimal places with the stdlib ``round`` on a
    ratio computed as ``a / b`` (never locale-formatted). NB: Python's ``round``
    IS banker's (round-half-to-even); that does NOT affect determinism — the
    SAME rounding is applied on every run, so two runs on an unchanged tree are
    byte-identical regardless of the tie-breaking policy;
  - ``generated_at`` is NON-deterministic by nature, so it is included ONLY when
    the caller sets ``SOURCE_DATE_EPOCH`` (a fixed reproducible-build clock) and
    is OMITTED entirely otherwise — it never enters the hashed core of an
    unstamped run. ``tree_sha`` is stable for a fixed tree.
  - JSON is emitted with ``sort_keys=True``, ``ensure_ascii=False``,
    ``indent=2``, and a trailing newline.

STDLIB ONLY. Imports nothing from Antiek product code; reads test files as
text and parses them with ``ast`` — it never imports or executes a test module.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import datetime as _dt
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

#: The suite-wide / per-call totals rollup. Values are ints or 4dp floats.
Totals = dict[str, "int | float"]
#: A serialized census payload (mixed-value JSON object).
JsonObj = dict[str, object]

# ---------------------------------------------------------------------------
# Documented constants
# ---------------------------------------------------------------------------

#: Path components that mark spec-execution scratch, never the product suite.
#: ``.caffenagent`` = caffenagent worktrees (concurrent runs copy OTHER sprints'
#: tests into the tree; counting them double-counts and breaks reproducibility).
#: ``htmlspec`` under ``docs/`` = HTML spec scratch. See module docstring.
EXCLUDE_DIR_PARTS: tuple[str, ...] = (".caffenagent",)
EXCLUDE_PATH_SUBSTRINGS: tuple[str, ...] = ("docs/htmlspec/", "docs/specs/",)

#: A test FILE is a file under the scan root named ``test_*.py`` or ``*_test.py``.
TEST_FILE_PREFIX = "test_"
TEST_FILE_SUFFIX = "_test.py"

#: A test FUNCTION is a ``def``/``async def`` whose name starts with this.
TEST_FN_PREFIX = "test"

#: Tokens that mark a mocked collaborator as BEHAVIORAL — the predictiveness
#: risk surface. Each is here because the suite mocks it AS the thing under
#: test (not merely to isolate the unit):
#:   provider / dispatch / llm / anthropic / openai — the model-call surface
#:     (the AI the autopsy found ~63% of files mock); ``complete``/``client``
#:     are the call methods/objects on it.
#:   db_lock / event_log / trajectory / substrate — the persistence + event
#:     surface whose writes ARE the unit's observable behavior.
#:   retriever / embedder / synthesiz / decompos / note_taker / orchestrat —
#:     the cognitive roles whose output a research test is supposed to verify.
#:   fetcher / httpx / requests / transport — network clients; behavioral when
#:     the unit's job is to parse/route what comes back, environmental when the
#:     unit merely needs the network out of the way (the census cannot tell
#:     these apart — see the KNOWN LIMIT in the docstring; it tags behavioral).
BEHAVIORAL_TARGET_HINTS: tuple[str, ...] = (
    "provider", "dispatch", "llm", "anthropic", "openai", "deepseek", "mimo",
    "complete", "client", "db_lock", "event_log", "trajectory", "substrate",
    "retriev", "embedder", "embed", "synthesiz", "decompos", "note_taker",
    "notetaker", "orchestrat", "fetcher", "httpx", "requests", "transport",
    "stripe", "agentmail", "exa", "browserbase", "router", "runner",
)

#: Tokens that mark a mocked collaborator as ENVIRONMENTAL — ordinary isolation,
#: not a predictiveness risk. A target matching one of these AND no behavioral
#: token is tagged environmental.
ENVIRONMENTAL_TARGET_HINTS: tuple[str, ...] = (
    "time", "sleep", "logger", "logging", "os.environ", "environ", "setenv",
    "delenv", "datetime", "tempfile", "tmp_path", "random", "uuid", "monotonic",
    "clock", "now", "stderr", "stdout", "print", "chdir", "syspath",
)

#: ``unittest.mock`` symbols whose construction/use marks a function as mocking.
#: Matched ONLY through a BARE ``ast.Name`` callee (``call(...)`` after
#: ``from unittest.mock import call``). The low-entropy names ``call`` / ``ANY``
#: / ``seal`` / ``sentinel`` collide with ordinary product method names
#: (``provider.call(...)``, ``client.seal()``); the BLOCKER-1 fix in
#: ``_call_is_mock_construction`` ensures an ATTRIBUTE call to one of these is an
#: ordinary method call, never a ``unittest.mock`` construction.
MOCK_SYMBOLS: frozenset[str] = frozenset(
    {"Mock", "MagicMock", "AsyncMock", "NonCallableMock", "NonCallableMagicMock",
     "PropertyMock", "patch", "mock_open", "sentinel", "call", "ANY", "seal"}
)

#: Method names on a mock that assert its CALL SHAPE — pure structure signal.
MOCK_ASSERT_METHODS: frozenset[str] = frozenset(
    {"assert_called", "assert_called_once", "assert_called_with",
     "assert_called_once_with", "assert_any_call", "assert_has_calls",
     "assert_not_called", "assert_awaited", "assert_awaited_once",
     "assert_awaited_with", "assert_awaited_once_with", "assert_any_await",
     "assert_has_awaits", "assert_not_awaited"}
)

#: Attribute names that, when read inside an ``assert``, are call-shape — structure.
MOCK_SHAPE_ATTRS: frozenset[str] = frozenset(
    {"call_count", "call_args", "call_args_list", "await_count", "await_args",
     "await_args_list", "mock_calls", "method_calls", "called"}
)

#: monkeypatch methods that establish a mock/override.
MONKEYPATCH_METHODS: frozenset[str] = frozenset(
    {"setattr", "setenv", "delattr", "delenv", "setitem", "delitem",
     "syspath_prepend", "chdir"}
)

#: A call whose function name matches one of these shapes is a BEHAVIOR
#: assertion delegated to an assert-helper — the helper raises on failure, so
#: the call IS the check (``_assert_conserved(shares)``,
#: ``_assert_pdf_body_quality(pdf)``, ``log.assert_phase_completed(8)``,
#: ``publish_gate.assert_claim_publishable(con, id)``, ``check_invariant(...)``,
#: ``verify_round_trip(...)``, ``expect_equal(...)``). The suite delegates a
#: behavior check to such a helper and asserts nothing else; without this rule
#: those tests read as ``none`` and wrongly dominate the lowest-predictiveness
#: list (the explicit SPR-02 input). The match is on the call's bare name OR the
#: TAIL of its attribute chain (so ``log.assert_ready_for_completion()`` counts).
#: It excludes the ``unittest.mock`` ``assert_called*`` / ``assert_awaited*``
#: family (those are CALL-SHAPE structure, handled by ``MOCK_ASSERT_METHODS``).
#: It is a documented heuristic, not a proof the helper truly asserts — a
#: ``verify_email_sent`` helper that itself only checks a mock's call shape would
#: be miscounted; in THIS suite the matched helpers all raise on a real value
#: (hand-verified on the eight ``none``-flagged tests it reclassifies).
ASSERT_HELPER_PREFIXES: tuple[str, ...] = (
    "assert_", "_assert_", "assert", "_assert",
    "check_", "_check_", "expect_", "_expect_", "verify_", "_verify_",
)

ROUND_DP = 4
_FAKE_RETURN_REASON = "asserts-own-mock-return"

Predictive = Literal["behavior", "structure", "mixed", "none"]


# ---------------------------------------------------------------------------
# Schema — the contract SPR-02 / SPR-05 read. FROZEN dataclasses.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TestFnRecord:
    """One test function. ``mock_targets`` is the sorted set of dotted patch
    targets / fake-class tokens / monkeypatch targets; ``"<dynamic>"`` for a
    non-string-literal patch target. ``reason`` explains a ``structure`` /
    ``none`` flag (``"asserts-own-mock-return"`` | ``"asserts-call-shape"`` |
    ``"no-meaningful-assertion"``); it is empty for ``behavior`` / ``mixed``."""

    # pytest collects classes named ``Test*``; this is a data record, not a
    # test class — opt out of collection so the warning stays out of the suite.
    __test__ = False

    file: str
    name: str
    lineno: int
    uses_mock: bool
    mock_targets: tuple[str, ...]
    predictive: Predictive
    assert_count: int
    mock_setup_lines: int
    reason: str


@dataclass(frozen=True)
class ModuleRecord:
    """One test FILE rolled up. ``mock_ratio`` = n_mock_tests / n_tests;
    ``predictive_ratio`` = (behavior + mixed) / n_tests; both 4dp."""

    module: str
    n_tests: int
    n_mock_tests: int
    mock_ratio: float
    n_structure_only: int
    predictive_ratio: float


def _ratio(numer: int, denom: int) -> float:
    """Deterministic 4dp ratio. Empty denominator ⇒ 0.0 (a module with no test
    functions has no predictiveness to report; it never divides by zero)."""
    if denom == 0:
        return 0.0
    return round(numer / denom, ROUND_DP)


# ---------------------------------------------------------------------------
# Per-function AST analysis
# ---------------------------------------------------------------------------


def _attr_chain(node: ast.AST) -> str:
    """Render a dotted attribute/name chain as text, or '' if not a chain.
    ``foo.bar.baz`` -> 'foo.bar.baz'; a call/subscript/literal -> ''."""
    parts: list[str] = []
    cur: ast.AST | None = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        parts.reverse()
        return ".".join(parts)
    return ""


#: Env-var name fragments that mark a multi-word-shaped but underscore-free
#: target as still environmental. Empty today: every env var in this tree is
#: multi-word (carries an underscore), so the underscore test alone suffices.
#: Kept as the documented extension point so a future single-word env var
#: (e.g. ``PATH``, ``HOME``) can be admitted WITHOUT re-loosening the rule to
#: demote every dotless SCREAMING token.
ENV_VAR_KNOWN_PREFIXES: tuple[str, ...] = ()


def _is_env_var_name(target: str) -> bool:
    """An ENV-VAR-shaped target — SCREAMING_SNAKE_CASE with no dotted attribute
    path AND at least one underscore (a multi-word name) OR a known env prefix
    (e.g. ``ANTIEK_EVENT_LOG_DIR``, ``EXA_API_KEY``). Setting an env var
    configures the ENVIRONMENT; it cannot mock a collaborator's behavior. Such a
    target is environmental REGARDLESS of any behavioral token it happens to
    contain (``EVENT_LOG`` inside ``ANTIEK_EVENT_LOG_DIR`` is a path var, not the
    event_log writer). Without this rule the behavioral count is inflated by
    temp-DB / API-key env overrides — a fairness defect, not a measurement.

    TIGHTENED (round-2 MINOR): a BARE dotless SCREAMING token with no underscore
    (``CLIENT``, ``PROVIDER``, ``EVENT``) is NO LONGER demoted. Such a token is a
    plausible module-level behavioral CONSTANT — a future
    ``monkeypatch.setattr(mod, "CLIENT", fake)`` swaps a real collaborator and
    MUST stay tag-able as behavioral; demoting it would silently hide the swap.
    All 70 real env vars in this tree are multi-word (carry an underscore), so
    this preserves the 92→63 correction exactly while closing the future hole.
    A genuine single-word env var must be listed in ENV_VAR_KNOWN_PREFIXES."""
    if "." in target:
        return False
    if not target or not (target[0].isupper() or target[0] == "_"):
        return False
    core = target.replace("_", "")
    if not (core.isupper() and core.isalnum() and any(c.isalpha() for c in core)):
        return False
    if "_" in target.strip("_"):
        return True
    return any(target.startswith(p) for p in ENV_VAR_KNOWN_PREFIXES)


def _tag_target(target: str) -> str | None:
    """Return 'behavioral' / 'environmental' / None for a dotted target token.
    Behavioral wins ties (the risk surface is what we must not under-count),
    EXCEPT an env-var-shaped target is always environmental (see above)."""
    if _is_env_var_name(target):
        return "environmental"
    low = target.lower()
    if any(tok in low for tok in BEHAVIORAL_TARGET_HINTS):
        return "behavioral"
    if any(tok in low for tok in ENVIRONMENTAL_TARGET_HINTS):
        return "environmental"
    return None


class _FnVisitor(ast.NodeVisitor):
    """Walks ONE test function body. Collects mock usage, mock targets,
    assertion shape, and the asserts-own-mock-return signal. Does not descend
    into nested function defs (a closure's body is the closure's, not the
    test's call shape) — but DOES descend into ``with`` / loops / ``async with``."""

    def __init__(self, local_fakes: frozenset[str], mock_helpers: dict[str, tuple[str, ...]]):
        self._local_fakes = local_fakes
        #: name -> targets for module-level mock-factory helpers (e.g.
        #: ``_make_client`` building ``MockTransport``). A body call to one
        #: makes the test mock-using and inherits the helper's targets.
        self._mock_helpers = mock_helpers
        self.uses_mock = False
        self.mock_targets: set[str] = set()
        self.behavioral_mock = False
        self.assert_count = 0
        self.mock_setup_lines = 0
        self.has_behavior_assert = False
        self.has_structure_assert = False
        self.has_meaningful_assert = False
        # asserts-own-mock-return tracking
        self._mock_names: set[str] = set()          # local names bound to a mock
        self._configured_returns: set[str] = set()   # mocks given .return_value/.side_effect
        self._behavior_assert_only_from_mock = True   # provisional; set False on any
        #   behavior assert that reads a non-mock value
        self._saw_behavior_assert = False

    # -- helpers -----------------------------------------------------------

    def _note_mock_use(self) -> None:
        self.uses_mock = True

    def _record_target(self, target: str) -> None:
        self.mock_targets.add(target)
        if _tag_target(target) == "behavioral":
            self.behavioral_mock = True

    def _expr_reads_only_mock(self, node: ast.AST) -> bool:
        """True if every Name leaf reachable in ``node`` is a known mock name.
        Used for asserts-own-mock-return: an assert whose value derives solely
        from a configured mock proves only the mock's configuration."""
        names = [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]
        if not names:
            return False
        return all(n in self._mock_names for n in names)

    # -- visitors ----------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Do not descend into nested defs (helpers/closures inside the test).
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_Assign(self, node: ast.Assign) -> None:
        # Detect ``m.return_value = ...`` / ``m.side_effect = ...`` on a known mock,
        # and ``x = Mock()`` / ``x = FakeProvider()`` binding a mock to a name.
        value = node.value
        # binding: x = <mock construction>
        bound_mock = self._call_is_mock_construction(value)
        if bound_mock is not None:
            self._record_target(bound_mock)
            self.mock_setup_lines += 1
            self._note_mock_use()
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    self._mock_names.add(tgt.id)
        # configuration: m.return_value = ... / m.side_effect = ...
        for tgt in node.targets:
            if isinstance(tgt, ast.Attribute) and tgt.attr in ("return_value", "side_effect"):
                base = _attr_chain(tgt.value)
                if base:
                    self._configured_returns.add(base.split(".")[0])
                    self._mock_names.add(base.split(".")[0])
                    self._note_mock_use()
        # derivation: ``result = m.something()`` / ``result = m`` binds a name
        # whose value flows ENTIRELY from a known mock — it carries the mock
        # taint so an assert on ``result`` counts as reading only the mock.
        if bound_mock is None and self._value_is_mock_derived(value):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    self._mock_names.add(tgt.id)
        self.generic_visit(node)

    def _value_is_mock_derived(self, value: ast.AST) -> bool:
        """True if ``value`` (an RHS expression) reads only from known mock
        names — e.g. ``m.total()`` or ``m.attr`` where ``m`` is a mock. Used to
        propagate mock-taint across local bindings for the canonical fake gate."""
        if not self._mock_names:
            return False
        names = [n.id for n in ast.walk(value) if isinstance(n, ast.Name)]
        return bool(names) and all(n in self._mock_names for n in names)

    def _call_is_mock_construction(self, value: ast.AST) -> str | None:
        """If ``value`` constructs a mock or project-local fake, return the
        dotted token naming it; else None.

        A ``MOCK_SYMBOLS`` construction is recognised ONLY through a BARE
        ``ast.Name`` callee (``Mock()`` / ``patch(...)`` / ``MagicMock()``).
        An attribute call (``p.call(...)``, ``client.seal()``, ``x.ANY``) is an
        ORDINARY method call on a product object that merely happens to share a
        ``unittest.mock`` symbol's spelling — it is NOT a mock construction.
        Treating ``func.attr`` as a construction misread ``provider.call(...)``
        as building ``unittest.mock.call`` and falsely flagged the archetypal
        provider-adapter tests (B1). A project-local fake (``FakeProvider()``,
        ``client._make_stub()``) is still recognised through either a bare name
        or an attribute tail, because a fake-class name is the construction
        token regardless of how it is reached."""
        if not isinstance(value, ast.Call):
            return None
        func = value.func
        if isinstance(func, ast.Name):
            name = func.id
            if name in MOCK_SYMBOLS:
                return name
            if name in self._local_fakes or self._is_fake_name(name):
                return name
            return None
        if isinstance(func, ast.Attribute):
            # Only a fake-class spelling counts through an attribute callee;
            # MOCK_SYMBOLS via ``obj.<symbol>(...)`` is an ordinary method call.
            name = func.attr
            if name in self._local_fakes or self._is_fake_name(name):
                return name
        return None

    @staticmethod
    def _is_fake_name(name: str) -> bool:
        return (
            name.startswith("Fake")
            or name.startswith("Stub")
            or name.startswith("_Mock")
            or name.startswith("Mock")
            or name.endswith("Fake")
            or name.endswith("Stub")
        )

    @staticmethod
    def _is_assert_helper(name: str) -> bool:
        """A call name that is a BEHAVIOR-asserting helper (raises on failure),
        not a ``unittest.mock`` call-shape assertion. See ASSERT_HELPER_PREFIXES.
        ``unittest.mock`` ``assert_called*`` / ``assert_awaited*`` are excluded —
        those are structure and are handled by the ``MOCK_ASSERT_METHODS`` branch
        BEFORE this is consulted; the explicit exclusion keeps the heuristic
        honest even if the call order ever changes."""
        if name in MOCK_ASSERT_METHODS:
            return False
        return any(name.startswith(p) for p in ASSERT_HELPER_PREFIXES)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        # patch(...) / patch.object(...) / patch.dict(...) / mock.patch(...)
        head = _attr_chain(func)
        if head:
            tail = head.split(".")[-1]
            root = head.split(".")[0]
            if tail == "patch" or head in ("patch", "mock.patch") or root == "patch" or (tail in ("object", "dict") and "patch" in head):
                self._note_mock_use()
                self.mock_setup_lines += 1
                self._record_patch_target(node)
            elif root == "monkeypatch" and tail in MONKEYPATCH_METHODS:
                self._note_mock_use()
                self.mock_setup_lines += 1
                tgt = self._monkeypatch_target(node)
                if tgt:
                    self._record_target(tgt)
            elif tail in MOCK_ASSERT_METHODS:
                # m.assert_called_once_with(...) — pure structure signal.
                self.has_structure_assert = True
                self.has_meaningful_assert = True
            elif self._is_assert_helper(tail):
                # _assert_conserved(...) / log.assert_phase_completed(8) — a
                # behavior check delegated to a raising assert-helper (MAJOR).
                self.has_behavior_assert = True
                self.has_meaningful_assert = True
                self._saw_behavior_assert = True
                if not self._expr_reads_only_mock(node):
                    self._behavior_assert_only_from_mock = False
        # bare Mock()/MagicMock()/FakeX() construction not bound to a name
        cons = self._call_is_mock_construction(node)
        if cons is not None:
            self._record_target(cons)
            self.mock_setup_lines += 1
            self._note_mock_use()
        # A call to a module-level mock-factory helper (``_make_client(...)``):
        # the test inherits the helper's mock usage and targets (B2).
        if isinstance(func, ast.Name) and func.id in self._mock_helpers:
            self._note_mock_use()
            self.mock_setup_lines += 1
            for tgt in self._mock_helpers[func.id]:
                self._record_target(tgt)
        self.generic_visit(node)

    def _record_patch_target(self, node: ast.Call) -> None:
        if not node.args:
            self._record_target("<dynamic>")
            return
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            self._record_target(first.value)
        else:
            chain = _attr_chain(first)
            self._record_target(chain if chain else "<dynamic>")

    def _monkeypatch_target(self, node: ast.Call) -> str | None:
        if not node.args:
            return None
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        chain = _attr_chain(first)
        return chain if chain else "<dynamic>"

    def visit_With(self, node: ast.With) -> None:
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self.assert_count += 1
        self._classify_assert(node.test)
        self.generic_visit(node)

    def _classify_assert(self, test: ast.AST) -> None:
        # Structure: the assert reads a call-shape attribute (.call_count etc).
        if self._reads_shape_attr(test):
            self.has_structure_assert = True
            self.has_meaningful_assert = True
            return
        # Trivially-true: ``assert True`` / ``assert 1`` — not meaningful.
        if isinstance(test, ast.Constant) and bool(test.value):
            return
        # Otherwise it is a behavior assertion (checks a value, membership, etc).
        self.has_behavior_assert = True
        self.has_meaningful_assert = True
        self._saw_behavior_assert = True
        if not self._expr_reads_only_mock(test):
            self._behavior_assert_only_from_mock = False

    def _reads_shape_attr(self, node: ast.AST) -> bool:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute) and sub.attr in MOCK_SHAPE_ATTRS:
                return True
        return False


def _pytest_raises_present(fn: ast.AST) -> bool:
    """True if the function body uses ``pytest.raises(...)`` / ``pytest.warns(...)``
    (as a ``with`` item or a call) — a behavior assertion on a raised exception."""
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Call):
            chain = _attr_chain(sub.func)
            if chain.endswith("pytest.raises") or chain.endswith("pytest.warns"):
                return True
            if chain in ("raises", "warns"):
                # ``from pytest import raises`` then ``with raises(...)``
                return True
    return False


# ---------------------------------------------------------------------------
# Module-level context that applies to the functions in a file
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ModuleContext:
    """Module-level facts that bear on every test function in the file.

    ``mock_fixtures`` maps the name of a module-level fixture that establishes a
    mock/monkeypatch (e.g. ``isolated_db(monkeypatch)`` calling
    ``monkeypatch.setenv``) to the tuple of targets it overrides. A test that
    takes such a fixture as a parameter inherits its mock usage AND its targets
    — this is how the suite wires a temp-DB / patched-config fixture into many
    tests without naming ``monkeypatch`` in each one. The tag (behavioral vs
    environmental) flows from the fixture's targets, so an env-only temp-DB
    fixture bumps ``uses_mock`` but NOT ``n_behavioral_mock_files``.

    ``mock_helpers`` maps the name of a module-level PLAIN helper function (NOT a
    fixture) that builds a mock — most importantly ``_make_client(handler)``
    returning ``httpx.Client(transport=httpx.MockTransport(handler))`` — to the
    targets it constructs. A test body that CALLS such a helper
    (``p = AnthropicProvider(client=_make_client(handler))``) inherits the
    helper's mock usage and targets. Without this, the archetypal provider-
    adapter files that mock the HTTP model-call surface through a shared
    ``_make_client`` factory were invisible to the census (B2) — their only
    in-body token was the env-var API key, so they never entered
    ``n_behavioral_mock_files`` despite being THE files the census is about."""

    local_fakes: frozenset[str]
    local_fake_fixtures: frozenset[str]
    autouse_mock: bool
    mock_fixtures: dict[str, tuple[str, ...]]
    mock_helpers: dict[str, tuple[str, ...]]


def _collect_module_context(tree: ast.Module) -> _ModuleContext:
    local_fakes: set[str] = set()
    local_fake_fixtures: set[str] = set()
    autouse_mock = False
    mock_fixtures: dict[str, tuple[str, ...]] = {}
    plain_helpers: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if _FnVisitor._is_fake_name(node.name):
                local_fakes.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_fixture(node):
            # a fixture (decorated @pytest.fixture) returning/yielding a fake,
            # OR named like a fake (stub_embedder), OR establishing a mock.
            if _fixture_yields_fake(node) or _looks_like_fake_name(node.name):
                local_fake_fixtures.add(node.name)
            if _fixture_establishes_mock(node):
                targets = _fixture_mock_targets(node, frozenset(local_fakes))
                mock_fixtures[node.name] = targets
                if _fixture_is_autouse(node):
                    autouse_mock = True
        elif (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith(TEST_FN_PREFIX)
        ):
            # A plain module-level helper (not a fixture, not a test). It may be
            # a mock factory like ``_make_client(handler) -> MockTransport``.
            plain_helpers.append(node)

    # A helper's targets are resolved AFTER local_fakes is fully known (a helper
    # may build a fake declared later in the module).
    frozen_fakes = frozenset(local_fakes)
    mock_helpers: dict[str, tuple[str, ...]] = {}
    for helper in plain_helpers:
        targets = _helper_mock_targets(helper, frozen_fakes)
        if targets:
            mock_helpers[helper.name] = targets

    return _ModuleContext(
        local_fakes=frozen_fakes,
        local_fake_fixtures=frozenset(local_fake_fixtures),
        autouse_mock=autouse_mock,
        mock_fixtures=mock_fixtures,
        mock_helpers=mock_helpers,
    )


def _helper_mock_targets(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, local_fakes: frozenset[str]
) -> tuple[str, ...]:
    """Targets a PLAIN module-level helper constructs — its ``patch(...)`` /
    ``Mock()`` / ``MagicMock()`` / ``MockTransport(...)`` / fake-class calls and
    its ``monkeypatch.set*`` overrides. Empty tuple ⇒ the helper builds no mock
    (so a test calling it inherits nothing). Mirrors ``_fixture_mock_targets``
    but for non-fixture factories; the dominant case is the provider suites'
    ``_make_client(handler)`` returning ``httpx.MockTransport``."""
    targets: set[str] = set()
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Call):
            continue
        chain = _attr_chain(sub.func)
        tail = chain.split(".")[-1] if chain else ""
        root = chain.split(".")[0] if chain else ""
        if (root == "monkeypatch" and tail in MONKEYPATCH_METHODS) or tail == "patch" or chain in ("mock.patch",):
            if sub.args and isinstance(sub.args[0], ast.Constant) and isinstance(sub.args[0].value, str):
                targets.add(sub.args[0].value)
            elif sub.args:
                ch = _attr_chain(sub.args[0])
                targets.add(ch if ch else "<dynamic>")
            continue
        f = sub.func
        nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        # A bare-Name MOCK_SYMBOL construction (Mock()/MagicMock()) OR a
        # fake-class spelling (MockTransport, FakeX) reachable by name-or-attr.
        bare_mock_symbol = isinstance(f, ast.Name) and nm in MOCK_SYMBOLS
        if bare_mock_symbol or nm in local_fakes or _FnVisitor._is_fake_name(nm):
            targets.add(nm)
    return tuple(sorted(targets))


def _fixture_mock_targets(fn: ast.FunctionDef | ast.AsyncFunctionDef, local_fakes: frozenset[str]) -> tuple[str, ...]:
    """The override targets a mock-establishing fixture sets — its
    ``monkeypatch.set*`` / ``patch(...)`` first-arguments and any fake it builds.
    Used to tag whether a test depending on the fixture inherits a BEHAVIORAL or
    merely ENVIRONMENTAL mock."""
    targets: set[str] = set()
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Call):
            chain = _attr_chain(sub.func)
            tail = chain.split(".")[-1] if chain else ""
            root = chain.split(".")[0] if chain else ""
            if (root == "monkeypatch" and tail in MONKEYPATCH_METHODS) or tail == "patch" or chain in ("mock.patch",):
                if sub.args and isinstance(sub.args[0], ast.Constant) and isinstance(sub.args[0].value, str):
                    targets.add(sub.args[0].value)
                elif sub.args:
                    ch = _attr_chain(sub.args[0])
                    targets.add(ch if ch else "<dynamic>")
            else:
                f = sub.func
                nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
                if nm in local_fakes or _FnVisitor._is_fake_name(nm):
                    targets.add(nm)
    return tuple(sorted(targets))


def _is_fixture(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in fn.decorator_list:
        chain = _attr_chain(dec) or _attr_chain(getattr(dec, "func", dec))
        if chain.endswith("fixture"):
            return True
    return False


def _fixture_is_autouse(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call):
            for kw in dec.keywords:
                if kw.arg == "autouse" and isinstance(kw.value, ast.Constant) and kw.value.value:
                    return True
    return False


def _looks_like_fake_name(name: str) -> bool:
    low = name.lower()
    return "fake" in low or "stub" in low


def _fixture_yields_fake(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Call):
            f = sub.func
            nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
            if _FnVisitor._is_fake_name(nm):
                return True
    return False


def _fixture_establishes_mock(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    args = {a.arg for a in fn.args.args}
    if "monkeypatch" in args:
        return True
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Call):
            chain = _attr_chain(sub.func)
            tail = chain.split(".")[-1] if chain else ""
            if chain.startswith("monkeypatch.") or chain in ("patch", "mock.patch"):
                return True
            if tail == "patch" or (tail in ("object", "dict") and "patch" in chain):
                return True
    return False


# ---------------------------------------------------------------------------
# File-level walk: produce TestFnRecords for one file
# ---------------------------------------------------------------------------


def _iter_test_functions(tree: ast.Module) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Yield every test function — a ``def``/``async def`` named ``test_*``,
    module-level or a method of a class (the suite collects ``Test*`` classes
    and bare functions alike). A bare ``def test():`` with no underscore is not
    a pytest test by convention, so the ``test_`` prefix is required."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                yield node
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith("test_"):
                    yield sub


def analyse_file(path: Path, rel: str) -> tuple[list[TestFnRecord], str | None]:
    """Parse one test file and return its TestFnRecords. On a syntax error,
    return ([], reason) — the file is reported as unparseable, never crashes
    the census (a census that dies on one bad file is not a measurement)."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [], f"read-error: {exc}"
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [], f"syntax-error: {exc}"

    ctx = _collect_module_context(tree)
    # Module-level patch decorators reach the functions they decorate; the
    # function-level decorator scan below handles that. Autouse fixtures and
    # the unittest.mock import inform every function.
    records: list[TestFnRecord] = []
    for fn in _iter_test_functions(tree):
        records.append(_analyse_fn(fn, rel, ctx))
    return records, None


def _decorator_mock_targets(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, list[str], int]:
    """Inspect @patch / @patch.object decorators on the function. Returns
    (uses_mock, targets, setup_lines)."""
    uses = False
    targets: list[str] = []
    setup = 0
    for dec in fn.decorator_list:
        call = dec if isinstance(dec, ast.Call) else None
        chain = _attr_chain(call.func) if call else _attr_chain(dec)
        if not chain:
            continue
        tail = chain.split(".")[-1]
        root = chain.split(".")[0]
        if tail == "patch" or root == "patch" or chain in ("mock.patch",) or (
            tail in ("object", "dict") and "patch" in chain
        ):
            uses = True
            setup += 1
            if call and call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                targets.append(call.args[0].value)
            elif call and call.args:
                ch = _attr_chain(call.args[0])
                targets.append(ch if ch else "<dynamic>")
            else:
                targets.append("<dynamic>")
    return uses, targets, setup


def _has_monkeypatch_param(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(a.arg == "monkeypatch" for a in fn.args.args)


def _fake_fixture_params(fn: ast.FunctionDef | ast.AsyncFunctionDef, ctx: _ModuleContext) -> list[str]:
    out: list[str] = []
    for a in fn.args.args:
        if a.arg in ctx.local_fake_fixtures or _looks_like_fake_name(a.arg):
            out.append(a.arg)
    return out


def _analyse_fn(fn: ast.FunctionDef | ast.AsyncFunctionDef, rel: str, ctx: _ModuleContext) -> TestFnRecord:
    v = _FnVisitor(ctx.local_fakes, ctx.mock_helpers)
    for stmt in fn.body:
        v.visit(stmt)

    # Decorator-level patches reach this function.
    dec_uses, dec_targets, dec_setup = _decorator_mock_targets(fn)
    if dec_uses:
        v.uses_mock = True
        v.mock_setup_lines += dec_setup
        for t in dec_targets:
            v._record_target(t)

    # monkeypatch parameter ⇒ the function is wired for environment override,
    # even if it never names a setattr in this body (it may pass it on).
    if _has_monkeypatch_param(fn):
        v.uses_mock = True

    # A fixture parameter that is a project-local fake.
    for p in _fake_fixture_params(fn, ctx):
        v.uses_mock = True
        v._record_target(p)

    # A fixture parameter that is a module-level mock-establishing fixture
    # (e.g. an ``isolated_db(monkeypatch)`` temp-DB fixture): the test inherits
    # both the mock usage and the fixture's targets, so the behavioral vs
    # environmental tag is faithful to what the fixture actually overrides.
    param_names = {a.arg for a in fn.args.args}
    for fix_name, fix_targets in ctx.mock_fixtures.items():
        if fix_name in param_names:
            v.uses_mock = True
            for t in fix_targets:
                v._record_target(t)

    # Autouse mock fixture in the module reaches every function.
    if ctx.autouse_mock:
        v.uses_mock = True

    # pytest.raises / warns anywhere in the body ⇒ behavior assertion.
    if _pytest_raises_present(fn):
        v.has_behavior_assert = True
        v.has_meaningful_assert = True

    predictive, reason = _decide_predictive(v)

    targets = tuple(sorted(v.mock_targets))
    return TestFnRecord(
        file=rel,
        name=fn.name,
        lineno=fn.lineno,
        uses_mock=bool(v.uses_mock),
        mock_targets=targets,
        predictive=predictive,
        assert_count=v.assert_count,
        mock_setup_lines=v.mock_setup_lines,
        reason=reason,
    )


def _decide_predictive(v: _FnVisitor) -> tuple[Predictive, str]:
    """Apply the documented rules to one analysed function, returning the flag
    and a reason string (empty for behavior/mixed)."""
    # Canonical fake gate: a behavior assert exists, it reads ONLY a configured
    # mock, and no structure assert — it proves the mock's own configuration.
    if (
        v._saw_behavior_assert
        and v._configured_returns
        and v._behavior_assert_only_from_mock
        and not v.has_structure_assert
    ):
        return "structure", _FAKE_RETURN_REASON
    if v.has_behavior_assert and v.has_structure_assert:
        return "mixed", ""
    if v.has_behavior_assert:
        return "behavior", ""
    if v.has_structure_assert:
        return "structure", "asserts-call-shape"
    return "none", "no-meaningful-assertion"


# ---------------------------------------------------------------------------
# Tree walk + rollup
# ---------------------------------------------------------------------------


def _is_excluded(rel_posix: str) -> bool:
    parts = rel_posix.split("/")
    if any(p in EXCLUDE_DIR_PARTS for p in parts):
        return True
    return any(sub in rel_posix for sub in EXCLUDE_PATH_SUBSTRINGS)


def _is_test_file(name: str) -> bool:
    return (name.startswith(TEST_FILE_PREFIX) and name.endswith(".py")) or name.endswith(TEST_FILE_SUFFIX)


def discover_test_files(root: Path, scan_dir: Path) -> list[tuple[Path, str]]:
    """All product test files under ``scan_dir``, as (abs_path, repo-rel-posix),
    sorted by rel path, excludes applied."""
    out: list[tuple[Path, str]] = []
    for path in scan_dir.rglob("*.py"):
        if not _is_test_file(path.name):
            continue
        rel = path.relative_to(root).as_posix()
        if _is_excluded(rel):
            continue
        out.append((path, rel))
    out.sort(key=lambda t: t[1])
    return out


def _module_rollup(rel: str, fns: list[TestFnRecord]) -> ModuleRecord:
    n = len(fns)
    n_mock = sum(1 for f in fns if f.uses_mock)
    n_struct = sum(1 for f in fns if f.predictive in ("structure", "none"))
    n_predictive = sum(1 for f in fns if f.predictive in ("behavior", "mixed"))
    return ModuleRecord(
        module=rel,
        n_tests=n,
        n_mock_tests=n_mock,
        mock_ratio=_ratio(n_mock, n),
        n_structure_only=n_struct,
        predictive_ratio=_ratio(n_predictive, n),
    )


@dataclass(frozen=True)
class Census:
    tree_sha: str
    modules: tuple[ModuleRecord, ...]
    tests: tuple[TestFnRecord, ...]
    totals: Totals
    unparseable: tuple[tuple[str, str], ...]
    behavioral_files: frozenset[str]
    structure_tests: tuple[TestFnRecord, ...]
    none_tests: tuple[TestFnRecord, ...]


def build_census(root: Path, scan_dir: Path) -> Census:
    files = discover_test_files(root, scan_dir)
    all_fns: list[TestFnRecord] = []
    modules: list[ModuleRecord] = []
    unparseable: list[tuple[str, str]] = []
    behavioral_files: set[str] = set()

    for path, rel in files:
        fns, err = analyse_file(path, rel)
        if err is not None:
            unparseable.append((rel, err))
            continue
        all_fns.extend(fns)
        modules.append(_module_rollup(rel, fns))
        # behavioral-mock file = any test in it mocks a behavioral surface.
        if any(_tag_target(t) == "behavioral" for f in fns for t in f.mock_targets):
            behavioral_files.add(rel)

    all_fns.sort(key=lambda r: (r.file, r.lineno, r.name))
    modules.sort(key=lambda m: m.module)

    n_fns = len(all_fns)
    n_mock = sum(1 for f in all_fns if f.uses_mock)
    n_structure = sum(1 for f in all_fns if f.predictive == "structure")
    n_none = sum(1 for f in all_fns if f.predictive == "none")
    n_predictive = sum(1 for f in all_fns if f.predictive in ("behavior", "mixed"))
    mock_files = {f.file for f in all_fns if f.uses_mock}
    n_aomr = sum(1 for f in all_fns if f.reason == _FAKE_RETURN_REASON)

    totals: Totals = {
        "n_test_functions": n_fns,
        "n_test_files": len(files),
        "n_parsed_files": len(modules),
        "n_unparseable_files": len(unparseable),
        "n_mock_tests": n_mock,
        "n_mock_files": len(mock_files),
        "n_behavioral_mock_files": len(behavioral_files),
        "n_structure_tests": n_structure,
        "n_none_tests": n_none,
        "n_asserts_own_mock_return": n_aomr,
        "suite_mock_ratio": _ratio(n_mock, n_fns),
        "suite_predictive_ratio": _ratio(n_predictive, n_fns),
    }

    structure_tests = tuple(f for f in all_fns if f.predictive == "structure")
    none_tests = tuple(f for f in all_fns if f.predictive == "none")

    return Census(
        tree_sha=_tree_sha(root),
        modules=tuple(modules),
        tests=tuple(all_fns),
        totals=totals,
        unparseable=tuple(unparseable),
        behavioral_files=frozenset(behavioral_files),
        structure_tests=structure_tests,
        none_tests=none_tests,
    )


# ---------------------------------------------------------------------------
# tree_sha
# ---------------------------------------------------------------------------


def _tree_sha(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        sha = out.stdout.strip()
        return sha if sha else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# ---------------------------------------------------------------------------
# Serialization (deterministic)
# ---------------------------------------------------------------------------


def census_to_dict(c: Census, *, include_generated_at: bool) -> JsonObj:
    payload: JsonObj = {}
    if include_generated_at:
        epoch = os.environ.get("SOURCE_DATE_EPOCH")
        # epoch is set whenever include_generated_at is True (see main); the
        # explicit guard keeps the type checker honest and never crashes.
        if epoch is not None:
            ts = _dt.datetime.fromtimestamp(int(epoch), tz=_dt.UTC)
            payload["generated_at"] = ts.isoformat()
    payload["tree_sha"] = c.tree_sha
    payload["modules"] = [dataclasses.asdict(m) for m in c.modules]
    payload["tests"] = [dataclasses.asdict(t) for t in c.tests]
    payload["totals"] = c.totals
    payload["unparseable"] = [{"module": m, "reason": r} for m, r in c.unparseable]
    return payload


def dumps(c: Census, *, include_generated_at: bool) -> str:
    payload = census_to_dict(c, include_generated_at=include_generated_at)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------------------
# Human report
# ---------------------------------------------------------------------------


def render_report(c: Census) -> str:
    t = c.totals
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("TEST CENSUS — real-vs-mock + Beck 'predictive' flag (read-only)")
    lines.append("=" * 78)
    lines.append(f"tree_sha: {c.tree_sha}")
    lines.append("")
    lines.append("TOTALS")
    lines.append(f"  total test functions   : {t['n_test_functions']}")
    lines.append(f"  total test files        : {t['n_test_files']}  "
                 f"(parsed {t['n_parsed_files']}, unparseable {t['n_unparseable_files']})")
    lines.append(f"  mock test functions     : {t['n_mock_tests']}")
    lines.append(f"  mock files              : {t['n_mock_files']}")
    lines.append(f"  behavioral-mock files   : {t['n_behavioral_mock_files']}")
    lines.append(f"  structure-flagged tests : {t['n_structure_tests']}")
    lines.append(f"  none-flagged tests      : {t['n_none_tests']}")
    lines.append(f"  suite mock-ratio        : {t['suite_mock_ratio']:.4f}")
    lines.append(f"  suite predictive-ratio  : {t['suite_predictive_ratio']:.4f}")
    lines.append("")
    lines.append("MODULES — ascending by predictive-ratio (worst predictiveness first)")
    lines.append(f"  {'predictive':>10}  {'mock':>6}  {'n':>4}  module")
    worst = sorted(c.modules, key=lambda m: (m.predictive_ratio, -m.mock_ratio, m.module))
    for m in worst:
        lines.append(
            f"  {m.predictive_ratio:>10.4f}  {m.mock_ratio:>6.4f}  {m.n_tests:>4}  {m.module}"
        )
    lines.append("")
    lines.append("STRUCTURE / NONE tests — path:line  flag  reason  (reported, never acted on)")
    for rec in sorted(c.structure_tests, key=lambda r: (r.file, r.lineno)):
        lines.append(f"  {rec.file}:{rec.lineno}  structure  {rec.reason}  ({rec.name})")
    for rec in sorted(c.none_tests, key=lambda r: (r.file, r.lineno)):
        lines.append(f"  {rec.file}:{rec.lineno}  none  {rec.reason}  ({rec.name})")
    lines.append("")
    lines.append("KNOWN LIMIT (rigor #2, fairness): a behavioral-mock file is NOT")
    lines.append("automatically diseased — a dispatch-routing unit test SHOULD mock the")
    lines.append("provider (correct isolation). This static census cannot distinguish")
    lines.append("'mocks the collaborator it is supposed to verify' (disease) from 'mocks")
    lines.append("an out-of-scope collaborator to isolate the unit' (good). It reports the")
    lines.append("signal both share; the disease/isolation call needs the unit's intent.")
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _write_out(target: str, text: str) -> None:
    if target == "-":
        sys.stdout.write(text)
    else:
        Path(target).write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.test_census",
        description="Read-only census of tests/ — real-vs-mock + Beck predictive flag. "
                    "Reports only; never runs, fixes, or gates a test. Exit 0 always.",
    )
    default_root = Path(__file__).resolve().parent.parent
    parser.add_argument("--root", default=str(default_root),
                        help="repo root (default: parent of tools/)")
    parser.add_argument("--tests-dir", default=None,
                        help="directory to scan (default: <root>/tests)")
    parser.add_argument("--json", default=None,
                        help="write census JSON here ('-' for stdout)")
    parser.add_argument("--report", default=None,
                        help="write human report here ('-' for stdout)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    scan_dir = Path(args.tests_dir).resolve() if args.tests_dir else (root / "tests")

    census = build_census(root, scan_dir)

    # generated_at enters output ONLY when SOURCE_DATE_EPOCH is set (determinism).
    include_ga = os.environ.get("SOURCE_DATE_EPOCH") is not None

    if args.json is None and args.report is None:
        # Default action: print the report to stdout.
        _write_out("-", render_report(census))
    if args.json is not None:
        _write_out(args.json, dumps(census, include_generated_at=include_ga))
    if args.report is not None:
        _write_out(args.report, render_report(census))

    return 0  # the census REPORTS; it never gates.


if __name__ == "__main__":
    raise SystemExit(main())
