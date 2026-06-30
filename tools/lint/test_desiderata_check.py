#!/usr/bin/env python3
"""Test-desiderata lint — flag three STATICALLY-checkable Kent Beck desiderata
violations in test source. A pure ``ast`` static analyzer over ``tests/``: it
reads test files, RUNS NOTHING, and touches no product code. It reports a
worklist; it never rewrites, reformats, or auto-fixes a test (that is a
product-test owner's call — a behavior change to a product test, out of scope).

Modeled EXACTLY on ``tools/lint/serve_invariants_check.py`` /
``tools/lint/boundary_check.py``: same ``<path>:<line>: [rule] message`` stdout,
same exit-code contract (0 = clean, 1 = violations; SPR-06 overrides to
informational on CI), same single ``ast.walk`` over a path set, same documented
allowlist constant, same explicit "KNOWN, ACCEPTED LIMITATION" note.

THE THREE RULES (each maps 1:1 onto a named Beck desideratum — the citation is
in this docstring AND in every emitted message, so a maintainer in 60 days reads
a rubric finding, not the author's taste):

  [structure]    Beck: STRUCTURE-INSENSITIVE — "a test should not change its
                 result when behavior is preserved but the code's structure
                 changes." A test whose ONLY meaningful assertions are
                 mock-call-shape checks (``m.assert_called_with(...)`` /
                 ``m.call_args ...``) breaks on any behavior-preserving refactor
                 of HOW the unit calls its collaborator, and asserts nothing
                 about the unit's output. THE NARROWING (rigor #2, the retry-count
                 steelman): a bare ``m.call_count == N`` is NOT flagged — for a
                 retry wrapper / a threshold counter, "how many times the inner
                 thing was invoked" IS the behavior under test, not incidental
                 structure (see ``_structure_signal_is_count_only``). The
                 violation is an assertion on the call's SHAPE/ARGUMENTS
                 (``assert_called_with`` / ``call_args``), which couples to the
                 internal call mechanics. Coupling to a BEHAVIORAL collaborator
                 (provider / dispatch / db — the SPR-01 census
                 ``BEHAVIORAL_TARGET_HINTS``) is the violation; call-shape on an
                 out-of-scope nuisance (logger / ``time.sleep`` — the census
                 ``ENVIRONMENTAL_TARGET_HINTS``) is downgraded to a [note].

  [isolation]    Beck: ISOLATED — "a test should be order-independent; its result
                 must not depend on another test having run first." A
                 ``@pytest.fixture(scope="module"|"session"|"package")`` that
                 yields/returns a MUTABLE object (list / dict / set / a non-frozen
                 dataclass / a mutable container) AND is consumed by >= 2 tests
                 leaks mutations across those tests, making order matter. A test
                 that does ``global X; X = ...`` or mutates a module-level mutable
                 (``X.append(...)`` / ``X[k] = ...``) likewise leaks state.
                 NOT flagged: a function-scoped fixture (the default — correctly
                 isolated) or an immutable module constant (a frozen dataclass /
                 a literal int/str/tuple used read-only).

  [determinism]  Beck: DETERMINISTIC — "a test should give the same result every
                 run." Three nondeterminism sources, each NARROWED to its real
                 smell (rigor #2, #3 — do not cry wolf):
                   * TIME — ``datetime.now()`` / ``datetime.utcnow()`` /
                     ``time.time()`` whose result FLOWS INTO AN ASSERTION
                     (``assert claims.issued_at <= int(time.time())`` — flaky at a
                     boundary). A clock used only for a poll deadline
                     (``while time.time() < deadline``) or an un-asserted
                     timestamp is NOT flagged; a frozen clock (freezegun
                     ``freeze_time`` / a ``monkeypatch`` / ``patch`` of the clock
                     in scope) is NOT flagged.
                   * RNG — ``random.*`` / ``uuid.uuid4()`` / ``secrets.*`` whose
                     result FLOWS INTO AN ASSERTION without a seed set in the
                     test or an in-scope fixture. The pervasive
                     ``f"doc-{uuid.uuid4().hex[:10]}"`` UNIQUE-ID idiom (the value
                     is a fresh key, never asserted) is NOT flagged — asserting ON
                     a random value is the smell, generating a unique key is not.
                   * NETWORK — a real network call (``httpx`` / ``requests`` /
                     ``socket`` / ``urllib.request``) NOT behind a mock/patch AND
                     NOT under the declared ``@pytest.mark.integration`` marker
                     (``pyproject.toml`` declares it; 0 tests currently use it).
                     The message RECOMMENDS the marker so a genuinely-networked
                     test is honestly labeled rather than silently nondeterministic
                     — the lint does NOT add it (a product-test change).

KNOWN, ACCEPTED LIMITATION (rigor #1 — name the blind spot; do not pretend
completeness). This is STATIC AST analysis. It CANNOT see:
  * a clock built at runtime via ``getattr(datetime, "now")()`` or returned by a
    config-resolved provider — the ``now``/``time`` token never appears as a
    static call;
  * a network call behind a config-resolved client (``self.client.get(url)``
    where ``client`` is injected) — no ``httpx``/``requests`` token in the body;
  * RNG seeded in a TRANSITIVE fixture two levels up, or a clock frozen by an
    autouse fixture in a sibling ``conftest.py`` this single-file walk does not
    join.
This is the SAME accepted-risk class the other AST lints carry (see
``serve_invariants_check.py``'s "INTERPOLATED at runtime" note). SPR-04's dynamic
re-runs (order-shuffle, frozen-vs-live clock diff, network-deny sandbox) exist
precisely to catch the dynamic cases this static check structurally cannot. A
lint that claimed to catch ALL nondeterminism, then silently missed the dynamic
forms, would be worse than one that names its blind spot.

EXCLUDES (documented constant ``EXCLUDE_DIR_PARTS`` / ``EXCLUDE_PATH_SUBSTRINGS``,
matching the SPR-01 census exactly): any path with a ``.caffenagent`` component
(caffenagent spec-execution scratch worktrees — concurrent runs copy OTHER
sprints' tests into the tree; counting them double-counts) and ``docs/htmlspec/``
/ ``docs/specs/`` (HTML spec scratch, not the product suite).

CLI: ``python -m tools.lint.test_desiderata_check [--paths tests/ ...]
[--rule structure|isolation|determinism|all]``. Exit 0 = clean, 1 = violations.
STDLIB ONLY. Imports nothing from Antiek product code; never executes a test.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Documented constants
# ---------------------------------------------------------------------------

#: Path components / substrings that mark spec-execution scratch, never the
#: product suite. IDENTICAL to the SPR-01 census's EXCLUDE_* so the two
#: instruments scan the same tree (see the census docstring's EXCLUDES section).
EXCLUDE_DIR_PARTS: tuple[str, ...] = (".caffenagent",)
EXCLUDE_PATH_SUBSTRINGS: tuple[str, ...] = ("docs/htmlspec/", "docs/specs/")

#: A test FILE: ``test_*.py`` or ``*_test.py`` under the scan root.
_TEST_FILE_PREFIX = "test_"
_TEST_FILE_SUFFIX = "_test.py"
#: A test FUNCTION: a ``def``/``async def`` named ``test_*``.
_TEST_FN_PREFIX = "test_"

# --- structure rule -------------------------------------------------------

#: ``unittest.mock`` methods that assert the SHAPE/ARGUMENTS of a call — pure
#: structure-coupling (they pin HOW the collaborator was invoked, so they break
#: on a behavior-preserving refactor of the call site). Mirrors the census
#: ``MOCK_ASSERT_METHODS``. ``assert_called`` / ``assert_called_once`` /
#: ``assert_not_called`` (no ``_with``) assert only that a call HAPPENED — a
#: COUNT signal, handled by the retry-count narrowing below, NOT here.
_SHAPE_ASSERT_METHODS: frozenset[str] = frozenset(
    {
        "assert_called_with",
        "assert_called_once_with",
        "assert_any_call",
        "assert_has_calls",
        "assert_awaited_with",
        "assert_awaited_once_with",
        "assert_any_await",
        "assert_has_awaits",
    }
)

#: ``unittest.mock`` methods that assert only that a call DID / DID NOT happen, N
#: times — a COUNT, not a shape. Per the retry-count steelman (rigor #2) these
#: are NOT a structure violation on their own: for a retry wrapper / threshold
#: counter the count IS the behavior under test.
_COUNT_ASSERT_METHODS: frozenset[str] = frozenset(
    {
        "assert_called",
        "assert_called_once",
        "assert_not_called",
        "assert_awaited",
        "assert_awaited_once",
        "assert_not_awaited",
    }
)

#: Attribute reads that pin a call's SHAPE/ARGUMENTS — structure-coupling.
_SHAPE_ATTRS: frozenset[str] = frozenset(
    {"call_args", "call_args_list", "await_args", "await_args_list", "mock_calls", "method_calls"}
)

#: Attribute reads that are a COUNT/HAPPENED signal — the retry-count case.
_COUNT_ATTRS: frozenset[str] = frozenset({"call_count", "await_count", "called"})

#: Behavior-asserting helper prefixes (a call that RAISES on failure, so the
#: call IS the check). Mirrors the census ``ASSERT_HELPER_PREFIXES``; a test that
#: delegates its behavior check to ``_assert_conserved(...)`` is NOT structure-only.
_ASSERT_HELPER_PREFIXES: tuple[str, ...] = (
    "assert_",
    "_assert_",
    "check_",
    "_check_",
    "expect_",
    "_expect_",
    "verify_",
    "_verify_",
)

#: Tokens marking a mocked collaborator BEHAVIORAL — call-shape coupling to one
#: of these is the violation. IDENTICAL to the SPR-01 census
#: ``BEHAVIORAL_TARGET_HINTS`` (the structure rule "reads the census's
#: classification; it does not re-classify mocks" — spec §Dependencies).
_BEHAVIORAL_TARGET_HINTS: tuple[str, ...] = (
    "provider",
    "dispatch",
    "llm",
    "anthropic",
    "openai",
    "deepseek",
    "mimo",
    "complete",
    "client",
    "db_lock",
    "event_log",
    "trajectory",
    "substrate",
    "retriev",
    "embedder",
    "embed",
    "synthesiz",
    "decompos",
    "note_taker",
    "notetaker",
    "orchestrat",
    "fetcher",
    "httpx",
    "requests",
    "transport",
    "stripe",
    "agentmail",
    "exa",
    "browserbase",
    "router",
    "runner",
)

#: Tokens marking a mocked collaborator ENVIRONMENTAL — call-shape on one of
#: these is a [note], not a violation. IDENTICAL to the census
#: ``ENVIRONMENTAL_TARGET_HINTS``.
_ENVIRONMENTAL_TARGET_HINTS: tuple[str, ...] = (
    "time",
    "sleep",
    "logger",
    "logging",
    "os.environ",
    "environ",
    "setenv",
    "delenv",
    "datetime",
    "tempfile",
    "tmp_path",
    "random",
    "uuid",
    "monotonic",
    "clock",
    "now",
    "stderr",
    "stdout",
    "print",
    "chdir",
    "syspath",
)

# --- isolation rule -------------------------------------------------------

_SHARED_SCOPES: frozenset[str] = frozenset({"module", "session", "package"})

# --- determinism rule -----------------------------------------------------

#: Clock-call attribute tails whose result, asserted-upon, is wall-clock-flaky.
_CLOCK_CALL_TAILS: frozenset[str] = frozenset({"now", "utcnow", "time", "time_ns", "monotonic"})
#: Names that freeze a clock when present in the function body / a decorator.
_FREEZE_TOKENS: tuple[str, ...] = ("freeze_time", "freezegun")

#: Network call roots and their network-making attribute tails.
_NET_CALLS: dict[str, frozenset[str]] = {
    "httpx": frozenset(
        {
            "get",
            "post",
            "put",
            "patch",
            "delete",
            "head",
            "options",
            "request",
            "stream",
            "Client",
            "AsyncClient",
        }
    ),
    "requests": frozenset(
        {"get", "post", "put", "patch", "delete", "head", "options", "request", "Session"}
    ),
    "socket": frozenset({"socket", "create_connection"}),
    "urllib": frozenset({"urlopen"}),  # urllib.request.urlopen
}


# ---------------------------------------------------------------------------
# Violation record + the same output contract as the other AST lints
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Violation:
    """One finding. ``severity`` is ``"violation"`` (counts for the exit code)
    or ``"note"`` (a downgraded, informational call-shape-on-a-nuisance finding —
    printed but does NOT fail the run, matching the spec's downgrade rule)."""

    __test__ = False  # not a pytest test class

    path: str
    line: int
    rule: str  # "structure" | "isolation" | "determinism"
    message: str
    severity: str = "violation"

    def render(self) -> str:
        """``<path>:<line>: [<rule>] <message>`` — the repo's lint contract.
        A note carries a trailing ``  (note)`` so the reader sees it did not
        fail the run while still reading uniformly."""
        tag = "" if self.severity == "violation" else "  (note)"
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}{tag}"


# ---------------------------------------------------------------------------
# Shared AST helpers (mirroring the census's idioms so the two agree)
# ---------------------------------------------------------------------------


def _attr_chain(node: ast.AST) -> str:
    """Dotted attribute/name chain text, or '' if not a chain. ``a.b.c`` ->
    'a.b.c'; a call/subscript/literal -> ''. Mirrors the census helper."""
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


def _tag_target(target: str) -> str:
    """'behavioral' / 'environmental' / 'unknown' for a mock target token.
    Behavioral wins ties (the risk surface must not be under-counted), matching
    the census; an unknown token is treated as behavioral-leaning ONLY by the
    caller's choice — here we return 'unknown' and let the caller default it."""
    low = target.lower()
    if any(tok in low for tok in _BEHAVIORAL_TARGET_HINTS):
        return "behavioral"
    if any(tok in low for tok in _ENVIRONMENTAL_TARGET_HINTS):
        return "environmental"
    return "unknown"


def _is_test_file(path: Path) -> bool:
    name = path.name
    return name.startswith(_TEST_FILE_PREFIX) or name.endswith(_TEST_FILE_SUFFIX)


def _excluded(rel: str) -> bool:
    parts = Path(rel).parts
    if any(p in EXCLUDE_DIR_PARTS for p in parts):
        return True
    return any(sub in rel for sub in EXCLUDE_PATH_SUBSTRINGS)


def _iter_test_functions(
    tree: ast.Module,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every ``test_*`` def — module-level or a method of a ``Test*``/other
    class (pytest collects both). Nested defs inside a test are NOT tests."""
    out: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith(_TEST_FN_PREFIX):
                out.append(node)
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith(
                    _TEST_FN_PREFIX
                ):
                    out.append(sub)
    return out


def _function_names_used(fn: ast.AST) -> set[str]:
    """The leaf-name set used anywhere in a function — bare names + the dotted
    head of an attribute chain. Used for in-scope freeze/seed/mock detection."""
    names: set[str] = set()
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Name):
            names.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            chain = _attr_chain(sub)
            if chain:
                names.add(chain.split(".")[0])
    return names


# ---------------------------------------------------------------------------
# RULE 1 — structure-insensitivity (Beck: structure-insensitive)
# ---------------------------------------------------------------------------


class _StructureVisitor(ast.NodeVisitor):
    """Walk ONE test function body. Decide whether its ONLY meaningful
    assertions are call-shape, and split the call-shape signal into SHAPE
    (``assert_called_with`` / ``.call_args`` — structure coupling, the violation)
    vs COUNT (``assert_called`` / ``.call_count`` — the retry-count steelman, NOT
    a violation on its own). Records the mock target names the shape assertions
    name, so the caller can tag behavioral vs environmental."""

    def __init__(self) -> None:
        self.has_behavior_assert = False
        self.has_shape_assert = False  # assert_called_with / .call_args (structure)
        self.has_count_assert = False  # assert_called / .call_count (retry-count)
        self.assert_count = 0
        #: object names that a SHAPE or COUNT assertion was made against (the
        #: mocked collaborator), e.g. {"provider", "logger"}.
        self.shape_targets: set[str] = set()
        self.count_targets: set[str] = set()

    # do not descend into nested defs / closures
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute):
            tail = func.attr
            base = _attr_chain(func.value)
            obj = base.split(".")[0] if base else ""
            if tail in _SHAPE_ASSERT_METHODS:
                self.has_shape_assert = True
                if obj:
                    self.shape_targets.add(obj)
            elif tail in _COUNT_ASSERT_METHODS:
                self.has_count_assert = True
                if obj:
                    self.count_targets.add(obj)
            elif _is_assert_helper(tail):
                # _assert_conserved(...) / log.assert_phase_completed(8) — a
                # behavior check delegated to a raising helper (census MAJOR
                # heuristic). Excludes the mock assert_* family (matched above).
                self.has_behavior_assert = True
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self.assert_count += 1
        kind, obj = self._classify_assert_test(node.test)
        if kind == "shape":
            self.has_shape_assert = True
            if obj:
                self.shape_targets.add(obj)
        elif kind == "count":
            self.has_count_assert = True
            if obj:
                self.count_targets.add(obj)
        elif kind == "behavior":
            self.has_behavior_assert = True
        # kind == "trivial" (assert True) — ignored, not meaningful
        self.generic_visit(node)

    def _classify_assert_test(self, test: ast.AST) -> tuple[str, str]:
        """Classify the expression an ``assert`` checks. Returns
        (kind, object_name) where kind is shape|count|behavior|trivial."""
        # A call-shape attribute read anywhere in the asserted expression.
        shape_obj = self._shape_attr_object(test)
        if shape_obj is not None:
            return "shape", shape_obj
        count_obj = self._count_attr_object(test)
        if count_obj is not None:
            return "count", count_obj
        if isinstance(test, ast.Constant) and bool(test.value):
            return "trivial", ""
        return "behavior", ""

    @staticmethod
    def _shape_attr_object(node: ast.AST) -> str | None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute) and sub.attr in _SHAPE_ATTRS:
                base = _attr_chain(sub.value)
                return base.split(".")[0] if base else ""
        return None

    @staticmethod
    def _count_attr_object(node: ast.AST) -> str | None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute) and sub.attr in _COUNT_ATTRS:
                base = _attr_chain(sub.value)
                return base.split(".")[0] if base else ""
        return None


def _is_assert_helper(name: str) -> bool:
    if name in _SHAPE_ASSERT_METHODS or name in _COUNT_ASSERT_METHODS:
        return False
    return any(name.startswith(p) for p in _ASSERT_HELPER_PREFIXES)


def _pytest_raises_present(fn: ast.AST) -> bool:
    """True if the body uses ``pytest.raises``/``pytest.warns`` — a behavior
    assertion on a raised exception/warning. Mirrors the census helper."""
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Call):
            chain = _attr_chain(sub.func)
            if chain.endswith("pytest.raises") or chain.endswith("pytest.warns"):
                return True
            if chain in ("raises", "warns"):
                return True
    return False


def _structure_violations(rel: str, tree: ast.Module) -> list[Violation]:
    out: list[Violation] = []
    for fn in _iter_test_functions(tree):
        v = _StructureVisitor()
        for stmt in fn.body:
            v.visit(stmt)
        # pytest.raises/warns anywhere in the body is a behavior assertion.
        if _pytest_raises_present(fn):
            v.has_behavior_assert = True

        # A test with ANY behavior assertion is mixed-or-behavior → NOT flagged.
        if v.has_behavior_assert:
            continue
        # No call-shape signal at all → it is "none"/smoke, not this rule's job.
        if not (v.has_shape_assert or v.has_count_assert):
            continue

        # RETRY-COUNT STEELMAN (rigor #2): the ONLY structure signal is a COUNT
        # (``assert_called_once`` / ``.call_count == N``) with NO shape/arg
        # assertion. For a retry wrapper / threshold counter the count IS the
        # behavior under test (test_note_taker_counter_resets_after_fire asserts
        # ``stub.call_count == 1`` to verify the threshold fires once then
        # resets — that is the unit's contract, not incidental structure). DO
        # NOT flag; this is exactly the census's lone "structure" hit, which is
        # a false positive for THIS rule's stricter definition.
        if v.has_count_assert and not v.has_shape_assert:
            continue

        # A SHAPE/ARGUMENT assertion (assert_called_with / .call_args) with no
        # behavior assertion IS structure-coupling. Tag by collaborator: a
        # behavioral collaborator (provider/dispatch/db) is the violation; a
        # nuisance (logger/time.sleep) is downgraded to a note.
        targets = sorted(v.shape_targets) or ["<mock>"]
        named = ", ".join(targets)
        tag = _classify_targets(v.shape_targets)
        if tag == "environmental":
            out.append(
                Violation(
                    rel,
                    fn.lineno,
                    "structure",
                    f"test asserts only call-shape on {named} (out-of-scope "
                    f"nuisance — logger / time.sleep class); acceptable isolation, "
                    f"but consider asserting the unit's output too "
                    f"(Beck: structure-insensitive)",
                    severity="note",
                )
            )
        else:
            out.append(
                Violation(
                    rel,
                    fn.lineno,
                    "structure",
                    f"test asserts only call-shape on {named}; breaks on "
                    f"behavior-preserving refactor (Beck: structure-insensitive)",
                )
            )
    return out


def _classify_targets(targets: set[str]) -> str:
    """'behavioral' if any target reads behavioral, else 'environmental' if all
    known targets are environmental, else 'behavioral' (an unknown collaborator
    is treated as behavioral — the risk surface must not be under-counted, per
    the census; a clearly-environmental nuisance is the only downgrade)."""
    if not targets:
        return "behavioral"
    tags = {_tag_target(t) for t in targets}
    if "behavioral" in tags or "unknown" in tags:
        return "behavioral"
    return "environmental"


# ---------------------------------------------------------------------------
# RULE 2 — isolation (Beck: isolated)
# ---------------------------------------------------------------------------


def _fixture_scope(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """The scope of a ``@pytest.fixture(scope=...)`` decorator, or None if the
    function is not a fixture. A bare ``@pytest.fixture`` (no scope kw) is
    function-scoped — returns ``"function"``."""
    for dec in fn.decorator_list:
        chain = _attr_chain(dec) or _attr_chain(getattr(dec, "func", dec))
        if not chain.endswith("fixture"):
            continue
        if isinstance(dec, ast.Call):
            for kw in dec.keywords:
                if kw.arg == "scope" and isinstance(kw.value, ast.Constant):
                    return str(kw.value.value)
        return "function"
    return None


def _frozen_dataclass_names(tree: ast.Module) -> set[str]:
    """Class names in the module decorated ``@dataclass(frozen=True)`` — an
    instance of one is IMMUTABLE, so a fixture returning it is not an isolation
    hazard (the lone real-tree module-scoped fixture returns a frozen
    ``DispatchConfig`` — correctly spared)."""
    frozen: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and _attr_chain(dec.func).endswith("dataclass")
                and any(
                    kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value
                    for kw in dec.keywords
                )
            ):
                frozen.add(node.name)
    return frozen


#: Builtins/constructors that produce a MUTABLE object when a fixture
#: yields/returns them. A frozen ``tuple``/``frozenset`` is immutable → spared.
_MUTABLE_BUILTINS: frozenset[str] = frozenset(
    {"list", "dict", "set", "bytearray", "defaultdict", "OrderedDict", "Counter", "deque"}
)


def _isolation_violations(rel: str, tree: ast.Module) -> list[Violation]:
    out: list[Violation] = []
    frozen_names = _frozen_dataclass_names(tree)
    module_classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}

    def _returned_mutable(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
        returned: list[ast.AST] = []
        for sub in ast.walk(fn):
            if isinstance(sub, (ast.Return, ast.Yield)) and sub.value is not None:
                returned.append(sub.value)
        for val in returned:
            if isinstance(
                val, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
            ):
                return {
                    "List": "list",
                    "Dict": "dict",
                    "Set": "set",
                    "ListComp": "list",
                    "DictComp": "dict",
                    "SetComp": "set",
                }[type(val).__name__]
            if isinstance(val, ast.Call):
                callee = val.func
                name = (
                    callee.id
                    if isinstance(callee, ast.Name)
                    else (callee.attr if isinstance(callee, ast.Attribute) else "")
                )
                if name in _MUTABLE_BUILTINS:
                    return name
                if (
                    name
                    and name[0].isupper()
                    and name not in frozen_names
                    and name in module_classes
                ):
                    return name
        return None

    # --- module/session-scoped mutable fixtures ---------------------------
    fixtures: dict[str, tuple[int, str, str]] = {}  # name -> (line, scope, type)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = _fixture_scope(node)
            if scope in _SHARED_SCOPES:
                mtype = _returned_mutable(node)
                if mtype is not None:
                    fixtures[node.name] = (node.lineno, scope, mtype)

    # count consumers (>= 2) — a test that names the fixture as a parameter.
    if fixtures:
        consumers: dict[str, int] = {name: 0 for name in fixtures}
        for fn in _iter_test_functions(tree):
            params = {a.arg for a in fn.args.args}
            for name in fixtures:
                if name in params:
                    consumers[name] += 1
        for name, (line, scope, mtype) in fixtures.items():
            n = consumers[name]
            if n >= 2:
                out.append(
                    Violation(
                        rel,
                        line,
                        "isolation",
                        f"{scope}-scoped fixture {name} yields mutable {mtype} "
                        f"shared by {n} tests; a mutation leaks across tests, "
                        f"making order matter (Beck: isolated)",
                    )
                )

    # --- module-global mutation inside a test -----------------------------
    module_level_names = _module_level_assigned_names(tree)
    for fn in _iter_test_functions(tree):
        out.extend(_global_mutation_violations(rel, fn, module_level_names))

    return out


def _module_level_assigned_names(tree: ast.Module) -> set[str]:
    """Names bound at module scope (a target of a top-level ``X = ...``). A
    test that reassigns or mutates one of these leaks across tests."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


#: Mutating-method names on a container (a call to one of these on a
#: module-level name mutates shared module state).
_MUTATING_METHODS: frozenset[str] = frozenset(
    {"append", "extend", "update", "add", "insert", "pop", "clear", "setdefault"}
)


def _global_mutation_violations(
    rel: str, fn: ast.FunctionDef | ast.AsyncFunctionDef, module_names: set[str]
) -> list[Violation]:
    out: list[Violation] = []
    reported_lines: set[int] = set()

    def _emit(line: int, msg: str) -> None:
        if line in reported_lines:
            return
        reported_lines.add(line)
        out.append(Violation(rel, line, "isolation", msg))

    # names declared ``global`` in the function — a reassignment of one leaks.
    declared_global: set[str] = set()
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Global):
            declared_global.update(sub.names)

    for sub in ast.walk(fn):
        # ``global X; X = ...`` (reassign a global) and ``X[k] = ...`` on a
        # module-level name (mutate a shared module-level container).
        if isinstance(sub, ast.Assign):
            for tgt in sub.targets:
                if isinstance(tgt, ast.Name) and tgt.id in declared_global:
                    _emit(
                        sub.lineno,
                        f"test reassigns module global {tgt.id} (declared "
                        f"`global`); the mutation persists into the next test "
                        f"(Beck: isolated)",
                    )
                elif (
                    isinstance(tgt, ast.Subscript)
                    and isinstance(tgt.value, ast.Name)
                    and tgt.value.id in module_names
                ):
                    _emit(
                        sub.lineno,
                        f"test mutates module-level {tgt.value.id}[...]; the "
                        f"change leaks into the next test (Beck: isolated)",
                    )
        # ``X.append(...)`` / ``X.update(...)`` on a module-level mutable name.
        elif (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and isinstance(sub.func.value, ast.Name)
            and sub.func.value.id in module_names
            and sub.func.attr in _MUTATING_METHODS
        ):
            _emit(
                sub.lineno,
                f"test mutates module-level {sub.func.value.id}.{sub.func.attr}"
                f"(...); the change leaks into the next test (Beck: isolated)",
            )
    return out


# ---------------------------------------------------------------------------
# RULE 3 — determinism (Beck: deterministic)
# ---------------------------------------------------------------------------


def _module_has_mark(
    tree: ast.Module, fn: ast.FunctionDef | ast.AsyncFunctionDef, mark: str
) -> bool:
    """True if the function carries ``@pytest.mark.<mark>`` OR the module sets
    ``pytestmark`` containing it (module-wide marks apply to every test)."""
    for dec in fn.decorator_list:
        chain = _attr_chain(dec) or _attr_chain(getattr(dec, "func", dec))
        if chain.endswith(f"mark.{mark}"):
            return True
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "pytestmark":
                    for sub in ast.walk(node.value):
                        if isinstance(sub, ast.Attribute) and sub.attr == mark:
                            return True
    return False


def _has_seed_call(fn: ast.AST) -> bool:
    """``random.seed(...)`` / ``np.random.seed(...)`` / ``seed(...)`` present in
    the body — RNG is then deterministic."""
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Call):
            chain = _attr_chain(sub.func)
            tail = chain.split(".")[-1] if chain else ""
            if tail == "seed":
                return True
    return False


def _clock_frozen_in_scope(fn: ast.AST) -> bool:
    """A frozen/monkeypatched clock in scope — freezegun ``freeze_time`` (used as
    a decorator OR a ``with``), OR a monkeypatch/patch whose target names a clock
    token (``datetime`` / ``time`` / ``now`` / ``utcnow`` / ``monotonic``)."""
    names = _function_names_used(fn)
    if any(tok in names for tok in _FREEZE_TOKENS):
        return True
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Call):
            chain = _attr_chain(sub.func)
            tail = chain.split(".")[-1] if chain else ""
            root = chain.split(".")[0] if chain else ""
            is_patch = (
                tail == "patch"
                or chain in ("patch", "mock.patch")
                or (root == "monkeypatch" and tail in ("setattr", "setitem"))
            )
            if is_patch:
                target_text = _first_arg_text(sub)
                low = target_text.lower()
                if any(
                    tok in low
                    for tok in ("datetime", "time", "now", "utcnow", "monotonic", "clock")
                ):
                    return True
    return False


def _first_arg_text(call: ast.Call) -> str:
    """Best-effort text of a patch/monkeypatch target: a string-literal first
    arg, or the dotted chain of the first (and second, for monkeypatch.setattr)
    argument(s)."""
    parts: list[str] = []
    for a in call.args[:2]:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            parts.append(a.value)
        else:
            chain = _attr_chain(a)
            if chain:
                parts.append(chain)
    return " ".join(parts)


def _network_mocked_in_scope(fn: ast.AST) -> bool:
    """A mock/patch of a network surface in scope — a ``patch(...)`` /
    ``monkeypatch`` whose target names a network token, OR an ``httpx``
    ``MockTransport`` / a ``*Transport`` / ``respx`` / ``responses`` /
    ``Fake*``/``Stub*`` HTTP double in the body."""
    names = _function_names_used(fn)
    if "respx" in names or "responses" in names:
        return True
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Call):
            chain = _attr_chain(sub.func)
            tail = chain.split(".")[-1] if chain else ""
            root = chain.split(".")[0] if chain else ""
            # an httpx.MockTransport / a Fake/Stub/Mock transport double
            if tail in ("MockTransport",) or (
                tail.endswith("Transport")
                and (tail.startswith(("Mock", "Fake", "Stub")) or "Mock" in tail)
            ):
                return True
            is_patch = (
                tail == "patch"
                or chain in ("patch", "mock.patch")
                or (root == "monkeypatch" and tail in ("setattr", "setitem"))
            )
            if is_patch:
                low = _first_arg_text(sub).lower()
                if any(
                    tok in low
                    for tok in (
                        "httpx",
                        "requests",
                        "socket",
                        "urllib",
                        "transport",
                        "client",
                        "session",
                        "get",
                        "post",
                        "fetch",
                    )
                ):
                    return True
    return False


def _determinism_violations(rel: str, tree: ast.Module) -> list[Violation]:
    out: list[Violation] = []
    for fn in _iter_test_functions(tree):
        out.extend(_determinism_for_fn(rel, tree, fn))
    return out


def _determinism_for_fn(
    rel: str, tree: ast.Module, fn: ast.FunctionDef | ast.AsyncFunctionDef
) -> list[Violation]:
    out: list[Violation] = []

    frozen = _clock_frozen_in_scope(fn)
    seeded = _has_seed_call(fn)
    net_mocked = _network_mocked_in_scope(fn)
    is_integration = _module_has_mark(tree, fn, "integration")

    reported: set[tuple[str, int]] = set()

    # --- TIME: an INLINE clock call inside an assert expression ------------
    # WHERE THE LINE IS (rigor #2 boundary, documented): the smell is a wall
    # clock read used as a LIVE comparison operand INSIDE the assert
    # (``assert claims.issued_at <= int(time.time())`` — flaky at a boundary).
    # It is NOT the DEPENDENCY-INJECTION idiom ``now = datetime.now(...);
    # score_gap(entry, now=now); assert ... == 0.0`` where a single captured
    # reference time is INJECTED into the unit and the asserted quantity is a
    # delta that cancels the wall-clock value out — that is the CORRECT way to
    # test time-dependent code and must not flag (test_continuous_daemon's
    # score_gap tests). Statically separating "live operand" from "injected
    # reference captured once" is unreliable, so the rule flags ONLY a clock
    # call that lexically sits inside the assert's own test expression; a clock
    # bound to a name and reused/injected is spared. (SPR-04's dynamic
    # frozen-vs-live diff catches an injected-clock test that IS in fact flaky.)
    if not frozen:
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Call) and _nondeterministic_call_kind(sub) == "clock":
                if not _node_flows_into_assert(sub, fn):
                    continue
                key = ("time", sub.lineno)
                if key in reported:
                    continue
                reported.add(key)
                tail = _attr_chain(sub.func).split(".")[-1]
                out.append(
                    Violation(
                        rel,
                        sub.lineno,
                        "determinism",
                        f"unfrozen wall-clock {tail}() read inline in an "
                        f"assertion; the test is time-of-day-dependent — freeze "
                        f"the clock (freezegun / monkeypatch) or inject a fixed "
                        f"reference time (Beck: deterministic)",
                    )
                )

    # --- RNG: an INLINE random read inside an assert expression ------------
    # Same boundary: ``assert uuid.uuid4().hex[:10] == ...`` (asserting a random
    # value) is the smell; the pervasive ``doc_id = f"d-{uuid.uuid4().hex}"``
    # UNIQUE-KEY idiom (a fresh key, never asserted) is NOT.
    if not seeded:
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Call) and _nondeterministic_call_kind(sub) == "rng":
                if not _node_flows_into_assert(sub, fn):
                    continue
                key = ("rng", sub.lineno)
                if key in reported:
                    continue
                reported.add(key)
                tail = _attr_chain(sub.func)
                out.append(
                    Violation(
                        rel,
                        sub.lineno,
                        "determinism",
                        f"unseeded random value ({tail}) read inline in an "
                        f"assertion; seed the RNG or assert a property, not the "
                        f"value (Beck: deterministic)",
                    )
                )

    # --- NETWORK: a real network call not mocked and not @integration ------
    if not net_mocked and not is_integration:
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Call) and _is_network_call(sub):
                key = ("net", sub.lineno)
                if key in reported:
                    continue
                reported.add(key)
                tail = _attr_chain(sub.func)
                out.append(
                    Violation(
                        rel,
                        sub.lineno,
                        "determinism",
                        f"real network call {tail}(...) not behind a mock; the "
                        f"test depends on a live service — mock it, or mark it "
                        f"@pytest.mark.integration (declared in pyproject.toml; "
                        f"0 tests use it) so it is honestly labeled rather than "
                        f"silently nondeterministic (Beck: deterministic)",
                    )
                )
    return out


def _nondeterministic_call_kind(call: ast.Call) -> str | None:
    """'clock' / 'rng' / None for a call.

    Clock — ONLY a stdlib wall-clock read: ``time.time()`` / ``time.time_ns()`` /
    ``time.monotonic()`` and ``datetime.now(...)`` / ``datetime.utcnow()`` /
    ``datetime.datetime.now()`` / ``datetime.datetime.utcnow()``. The receiver
    chain MUST be rooted at the conventional stdlib module name (``time`` /
    ``datetime``), or contain ``datetime`` as a segment for the ``now``/``utcnow``
    forms. CRITICAL NARROWING (rigor #3 — the dominant real-tree false positive):
    an injected FAKE-clock method — ``clock.now()`` / ``_FakeClock().now()`` /
    ``self.now()`` — is NOT a wall clock and is NOT matched. The throttle/rate-
    governor/arxiv suites all inject a ``_FakeClock`` whose ``.now()`` is
    deterministic precisely so the test is reproducible; flagging those was
    crying wolf on the correct shape. ``monotonic`` is matched only as
    ``time.monotonic`` for the same reason.

    RNG — ``random.*`` / ``uuid.uuid4()`` / ``uuid.uuid1()`` / ``secrets.*``."""
    chain = _attr_chain(call.func)
    if not chain:
        return None
    parts = chain.split(".")
    tail = parts[-1]
    root = parts[0]
    # clock — require a real stdlib clock receiver, never an arbitrary `.now()`.
    if tail in ("time", "time_ns", "monotonic", "perf_counter") and root == "time":
        return "clock"
    if tail in ("now", "utcnow") and ("datetime" in parts):
        # datetime.now() / datetime.utcnow() / datetime.datetime.now(...)
        return "clock"
    # rng
    if root == "random":
        return "rng"
    if root == "secrets":
        return "rng"
    if tail in ("uuid4", "uuid1") or chain.endswith("uuid.uuid4") or chain.endswith("uuid.uuid1"):
        return "rng"
    return None


def _is_network_call(call: ast.Call) -> bool:
    chain = _attr_chain(call.func)
    if not chain:
        return False
    parts = chain.split(".")
    root = parts[0]
    tail = parts[-1]
    if root in _NET_CALLS and tail in _NET_CALLS[root]:
        return True
    # urllib.request.urlopen
    return chain.endswith("request.urlopen") or chain.endswith("urllib.request.urlopen")


def _node_flows_into_assert(target: ast.AST, fn: ast.AST) -> bool:
    """True if ``target`` (a Call node) lexically sits inside an ``assert``
    statement's test expression. The narrowing that keeps a poll-deadline
    ``while time.time() < deadline`` and an un-asserted timestamp from flagging:
    only a clock/RNG value that is itself asserted-upon is the smell."""
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Assert):
            for inner in ast.walk(sub.test):
                if inner is target:
                    return True
    return False


# ---------------------------------------------------------------------------
# Tree walk + CLI (the same exit-code contract as the other AST lints)
# ---------------------------------------------------------------------------

_RULES = ("structure", "isolation", "determinism")
_RULE_FNS = {
    "structure": _structure_violations,
    "isolation": _isolation_violations,
    "determinism": _determinism_violations,
}


def find_violations(
    paths: list[Path], rules: tuple[str, ...] = _RULES, root: Path = _REPO
) -> list[Violation]:
    """Walk every ``test_*.py`` / ``*_test.py`` under ``paths`` and return the
    sorted violation list for the selected rules. Reads files as text and parses
    with ``ast``; never imports or executes a test module."""
    out: list[Violation] = []
    seen: set[Path] = set()
    files: list[Path] = []
    for p in paths:
        if p.is_file() and p.suffix == ".py":
            files.append(p)
        elif p.is_dir():
            files.extend(p.rglob("*.py"))
    for py in sorted(set(files)):
        if py in seen:
            continue
        seen.add(py)
        try:
            rel = py.relative_to(root).as_posix()
        except ValueError:
            rel = py.as_posix()
        if _excluded(rel):
            continue
        if not _is_test_file(py):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for rule in rules:
            out.extend(_RULE_FNS[rule](rel, tree))
    out.sort(key=lambda v: (v.path, v.line, v.rule, v.severity))
    return out


def _parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="python -m tools.lint.test_desiderata_check",
        description=(
            "Static AST lint over tests/ for three Beck-desiderata violations: "
            "structure-coupled assertions, shared mutable fixtures, time/RNG/"
            "network nondeterminism. Reports a worklist; rewrites nothing."
        ),
    )
    ap.add_argument(
        "--paths",
        nargs="+",
        default=["tests/"],
        help="paths (dirs or files) to lint, relative to the repo root (default: tests/).",
    )
    ap.add_argument(
        "--rule",
        choices=[*_RULES, "all"],
        default="all",
        help="which rule(s) to run (default: all).",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    rules = _RULES if args.rule == "all" else (args.rule,)
    resolved: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        resolved.append(p if p.is_absolute() else (_REPO / p))
    violations = find_violations(resolved, rules, _REPO)

    hard = [v for v in violations if v.severity == "violation"]
    notes = [v for v in violations if v.severity == "note"]
    for v in violations:
        print(v.render())

    if hard:
        by_rule = {r: sum(1 for v in hard if v.rule == r) for r in _RULES}
        print(
            f"\nTest-desiderata violations: {len(hard)} "
            f"([structure] {by_rule['structure']} / [isolation] "
            f"{by_rule['isolation']} / [determinism] {by_rule['determinism']}) "
            f"+ {len(notes)} note(s). Each cites the Beck desideratum it breaks. "
            f"This is a worklist — it reports, it does not rewrite a test. SPR-06 "
            f"wires it informational-first on CI; SPR-04's dynamic re-runs confirm "
            f"the determinism + isolation findings."
        )
        return 1
    print(f"OK: no test-desiderata violations ({len(notes)} downgraded note(s) printed above).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
