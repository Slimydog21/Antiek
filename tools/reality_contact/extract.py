"""Static (AST, never-execute) extraction of mock/patch targets from a test file.

Given a ``test_*.py`` file, return every mock/patch target as a ``MockTarget``
carrying its resolved dotted path (or ``unresolved``), the FORM it took, and a
cited ``file:line``. The extractor NEVER imports or runs the test — it parses
with the stdlib ``ast`` module, exactly like ``tools/lint/rate_governor_check.py``
and ``tools/lint/serve_invariants_check.py``.

Forms covered (the ones actually in the Antiek test tree, surveyed by grep):

  1. ``@patch("dotted.path")``               decorator
  2. ``with patch("dotted.path"): ...``      context manager
  3. ``patch.object(Module, "attr")``        object-target patch
  4. ``monkeypatch.setattr("dotted.path", v)``           string target
  5. ``monkeypatch.setattr(obj, "attr", v)``             object + attr target
  6. ``mocker.patch("dotted.path")`` / ``mocker.patch.object(...)``  pytest-mock
  7. ``MagicMock()/AsyncMock()/Mock()`` assigned into a name that SHADOWS a
     core symbol — i.e. ``X = MagicMock()`` where ``X`` is an import alias the
     extractor can resolve to a dotted path (a stand-in OVER the real symbol).

Resolution. String targets resolve directly. Symbol targets (``patch.object(M,
"a")``, ``monkeypatch.setattr(M, "a", v)``) resolve via the test's own
import aliases — both module-level AND function-local imports are tracked, so
``from tools import run_corpus_ingest as orch`` inside a test body binds
``orch -> tools.run_corpus_ingest`` (which is correctly NOT a core module — the
exact false-positive a naive substring match on ``orch`` would make).

A target the extractor cannot statically resolve to a dotted path (a target
built at runtime, a name with no traceable import) is recorded as
``unresolved`` WITH its location — NEVER dropped. The classifier turns an
``unresolved`` that could land on a core path into ``indeterminate`` (never
``reality``), which is the honesty bar.

KNOWN, ACCEPTED LIMITATIONS (logged, honesty bar):
  * Aliases bound by something other than an ``import`` (a plain assignment
    ``m = some_module``, a conftest fixture, a DI-injected object) are NOT
    resolved — the symbol-target becomes ``unresolved``.
  * Re-export indirection (an alias pointing at a package ``__init__`` that
    re-exports a core symbol) is resolved to the alias's literal dotted path,
    not chased through re-exports.
  * Dynamically-built string targets (``patch(prefix + ".thing")``) are
    ``unresolved``.
These are the safe direction: an unresolvable target becomes ``unresolved`` →
``indeterminate``, never a false ``reality``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

# The mock CONSTRUCTORS that, when assigned into a name shadowing an import
# alias, stand a stub OVER the real symbol (form 7).
_MOCK_CTORS: frozenset[str] = frozenset({"MagicMock", "AsyncMock", "Mock", "NonCallableMock"})

# The patch-call attribute names (``patch`` / ``patch.object`` / a mocker's
# ``.patch`` / ``.patch.object``). The receiver disambiguates the form.
_PATCH_NAMES: frozenset[str] = frozenset({"patch"})


@dataclass(frozen=True)
class MockTarget:
    """One extracted mock/patch target.

    target     the resolved dotted path (e.g. ``substrate.dispatch.router.dispatch``)
               or ``None`` when unresolved.
    resolved   True iff ``target`` is a statically-resolved dotted path.
    form       which extraction form produced this (decorator / with /
               patch.object / monkeypatch-str / monkeypatch-obj / mocker /
               mock-ctor-shadow).
    lineno     1-based line of the mock call/assignment.
    raw        a short human string describing what was seen (for the ledger
               evidence + audit).
    """

    target: str | None
    resolved: bool
    form: str
    lineno: int
    raw: str


# --------------------------------------------------------------------------- #
# Import-alias resolution
# --------------------------------------------------------------------------- #
@dataclass
class _AliasTable:
    """Maps a NAME visible in a scope to the dotted path it refers to.

    name_to_path[n] = dotted path that bare name ``n`` resolves to. Built from:
      * ``import a.b.c``            -> {"a": "a"}            (bare name is top pkg)
      * ``import a.b.c as x``       -> {"x": "a.b.c"}
      * ``from a.b import c``       -> {"c": "a.b.c"}
      * ``from a.b import c as y``  -> {"y": "a.b.c"}
    """

    name_to_path: dict[str, str] = field(default_factory=dict)

    def merged_with(self, other: _AliasTable) -> _AliasTable:
        """A child scope's table layered over (shadowing) this one."""
        m = dict(self.name_to_path)
        m.update(other.name_to_path)
        return _AliasTable(m)

    def resolve_name(self, name: str) -> str | None:
        return self.name_to_path.get(name)


def _aliases_from_imports(stmts: list[ast.stmt]) -> _AliasTable:
    """Collect import aliases from a flat list of statements (one scope level)."""
    table = _AliasTable()
    for st in stmts:
        if isinstance(st, ast.Import):
            for alias in st.names:
                if alias.asname:
                    table.name_to_path[alias.asname] = alias.name
                else:
                    # ``import a.b.c`` binds the TOP name ``a`` -> ``a``.
                    top = alias.name.split(".")[0]
                    table.name_to_path[top] = top
        elif isinstance(st, ast.ImportFrom):
            if st.module is None or st.level:  # relative import — out of scope
                continue
            for alias in st.names:
                bound = alias.asname or alias.name
                table.name_to_path[bound] = f"{st.module}.{alias.name}"
    return table


def _resolve_dotted_from_node(node: ast.AST, aliases: _AliasTable) -> str | None:
    """Resolve an expression node to a dotted path using import aliases.

    Handles ``Name`` (``orch`` -> its alias) and ``Attribute`` chains
    (``mod.sub.fn`` -> ``<alias of mod>.sub.fn``). Returns None for anything
    not statically resolvable (a call result, a subscript, an unknown name)."""
    parts: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if not isinstance(cur, ast.Name):
        return None
    base = aliases.resolve_name(cur.id)
    if base is None:
        return None
    parts.append(base)
    parts.reverse()
    return ".".join(parts)


def _string_constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


# --------------------------------------------------------------------------- #
# Per-call extraction helpers
# --------------------------------------------------------------------------- #
def _call_name_chain(func: ast.AST) -> list[str]:
    """The attribute chain of a call's func, outermost-attr-last.

    ``patch`` -> ["patch"]; ``patch.object`` -> ["patch", "object"];
    ``mocker.patch`` -> ["mocker", "patch"]; ``mocker.patch.object`` ->
    ["mocker", "patch", "object"]; ``monkeypatch.setattr`` -> ["monkeypatch",
    "setattr"]."""
    chain: list[str] = []
    cur = func
    while isinstance(cur, ast.Attribute):
        chain.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        chain.append(cur.id)
    chain.reverse()
    return chain


def _patch_string_or_objattr(
    call: ast.Call, aliases: _AliasTable
) -> tuple[str | None, bool, str]:
    """Resolve a ``patch(...)`` / ``patch.object(...)`` / ``mocker.patch(...)``
    call's TARGET. Returns (dotted_path_or_None, resolved, raw)."""
    chain = _call_name_chain(call.func)
    is_object = chain and chain[-1] == "object"
    if is_object:
        # patch.object(Module, "attr"[, ...]) — resolve Module via aliases, then
        # append the attr string.
        if len(call.args) >= 2:
            mod = _resolve_dotted_from_node(call.args[0], aliases)
            attr = _string_constant(call.args[1])
            if mod is not None and attr is not None:
                return f"{mod}.{attr}", True, f"patch.object({_short(call.args[0])}, {attr!r})"
        return None, False, "patch.object(<unresolved>)"
    # patch("dotted.path") / mocker.patch("dotted.path")
    if call.args:
        s = _string_constant(call.args[0])
        if s is not None:
            return s, True, f"patch({s!r})"
    return None, False, "patch(<unresolved-target>)"


def _monkeypatch_setattr(
    call: ast.Call, aliases: _AliasTable
) -> tuple[str | None, bool, str]:
    """Resolve a ``monkeypatch.setattr(...)`` call's target.

    Two signatures:
      setattr("dotted.path", value[, raising=...])       -> string target
      setattr(obj, "attr", value[, raising=...])         -> obj.attr target
    """
    if not call.args:
        return None, False, "monkeypatch.setattr(<no-args>)"
    first = call.args[0]
    s = _string_constant(first)
    if s is not None:
        # String-target form. (A leading string + a string attr would be the
        # rare setattr("mod", "attr") — but pytest's string form is the FULL
        # dotted path in arg0; arg1 is the value. So arg0 string is the target.)
        return s, True, f"monkeypatch.setattr({s!r})"
    # Object-target form: setattr(obj, "attr", value).
    if len(call.args) >= 2:
        attr = _string_constant(call.args[1])
        mod = _resolve_dotted_from_node(first, aliases)
        if attr is not None and mod is not None:
            return f"{mod}.{attr}", True, f"monkeypatch.setattr({_short(first)}, {attr!r})"
        if attr is not None:
            # obj resolved to nothing (a local var / fixture / DI object) — we
            # can't pin a dotted path. Record unresolved with what we know.
            return None, False, f"monkeypatch.setattr(<unresolved-obj>, {attr!r})"
    return None, False, "monkeypatch.setattr(<unresolved>)"


def _short(node: ast.AST) -> str:
    """A short readable rendering of an arg node for raw/audit strings."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        chain = _call_name_chain(node)
        return ".".join(chain)
    return node.__class__.__name__


def _is_mock_ctor_call(node: ast.AST) -> str | None:
    """If ``node`` is a ``MagicMock()/AsyncMock()/Mock()`` call, return the ctor
    name; else None. Recognizes both ``MagicMock(...)`` (Name) and
    ``mock.MagicMock(...)`` (Attribute)."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name) and func.id in _MOCK_CTORS:
        return func.id
    if isinstance(func, ast.Attribute) and func.attr in _MOCK_CTORS:
        return func.attr
    return None


# --------------------------------------------------------------------------- #
# Scope walk
# --------------------------------------------------------------------------- #
class _Extractor(ast.NodeVisitor):
    """Walks a parsed test module, carrying a per-scope alias table.

    Module-level imports seed the base table. Each function body adds its own
    function-local imports (layered ON TOP, so a local alias shadows a module
    one — and a local ``from tools import run_corpus_ingest as orch`` is seen).
    Class bodies pass the table through unchanged."""

    def __init__(self, module_aliases: _AliasTable) -> None:
        self._alias_stack: list[_AliasTable] = [module_aliases]
        self.targets: list[MockTarget] = []

    @property
    def _aliases(self) -> _AliasTable:
        return self._alias_stack[-1]

    def _enter_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        local = _aliases_from_imports([s for s in node.body if isinstance(s, ast.stmt)])
        self._alias_stack.append(self._aliases.merged_with(local))
        for child in node.body:
            self.visit(child)
        self._alias_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._handle_decorators(node)
        self._enter_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._handle_decorators(node)
        self._enter_function(node)

    def _handle_decorators(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for dec in node.decorator_list:
            call = dec if isinstance(dec, ast.Call) else None
            func = call.func if call is not None else dec
            chain = _call_name_chain(func)
            # @patch(...) / @patch.object(...) / @mock.patch(...) decorators.
            if chain and chain[-1] in _PATCH_NAMES or (
                len(chain) >= 2 and chain[-1] == "object" and chain[-2] in _PATCH_NAMES
            ):
                if call is None:
                    # @patch with no call (rare; nothing to resolve)
                    continue
                target, resolved, raw = _patch_string_or_objattr(call, self._aliases)
                self.targets.append(
                    MockTarget(target, resolved, "decorator", dec.lineno, raw)
                )

    def visit_With(self, node: ast.With) -> None:  # noqa: N802
        self._handle_with(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:  # noqa: N802
        self._handle_with(node)

    def _handle_with(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            expr = item.context_expr
            if isinstance(expr, ast.Call):
                chain = _call_name_chain(expr.func)
                if (chain and chain[-1] in _PATCH_NAMES) or (
                    len(chain) >= 2 and chain[-1] == "object" and chain[-2] in _PATCH_NAMES
                ):
                    target, resolved, raw = _patch_string_or_objattr(expr, self._aliases)
                    self.targets.append(
                        MockTarget(target, resolved, "with", expr.lineno, raw)
                    )
        for child in node.body:
            self.visit(child)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        chain = _call_name_chain(node.func)
        # monkeypatch.setattr(...) — a setattr in monkeypatch's signature shape.
        # We deliberately do NOT gate on the receiver variable name: the pytest
        # fixture can be bound to any parameter (``def t(mp): mp.setattr(...)``),
        # and an aliased receiver is just as much a monkeypatch as the
        # conventionally-named one. Silently dropping it would mislabel a real
        # core-mock as `reality` — the single failure this instrument exists to
        # prevent. So a ``*.setattr(...)`` that RESOLVES to a dotted path is
        # always extracted (the classifier decides whether that path is core); a
        # NON-resolving setattr is recorded as `unresolved` only when the
        # receiver is monkeypatch-shaped, so the ledger is not flooded with every
        # unrelated object's ``.setattr``.
        if len(chain) >= 2 and chain[-1] == "setattr":
            target, resolved, raw = _monkeypatch_setattr(node, self._aliases)
            if resolved or "monkeypatch" in chain[0]:
                self.targets.append(
                    MockTarget(target, resolved, "monkeypatch", node.lineno, raw)
                )
        # mocker.patch(...) / mocker.patch.object(...) — pytest-mock fixture.
        elif "mocker" in chain[0:1] and "patch" in chain:
            target, resolved, raw = _patch_string_or_objattr(node, self._aliases)
            self.targets.append(
                MockTarget(target, resolved, "mocker", node.lineno, raw)
            )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        # Form 7: ``X = MagicMock()`` where ``X`` resolves (via import alias) to
        # a dotted path — a stub stood OVER a real imported symbol. A MagicMock
        # bound to a name that is NOT an import alias is just test input DATA and
        # is correctly ignored (the near-miss negative).
        ctor = _is_mock_ctor_call(node.value)
        if ctor is not None:
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    dotted = self._aliases.resolve_name(tgt.id)
                    if dotted is not None:
                        self.targets.append(
                            MockTarget(
                                dotted,
                                True,
                                "mock-ctor-shadow",
                                node.lineno,
                                f"{tgt.id} = {ctor}()  (shadows import {dotted})",
                            )
                        )
                    # else: local data var named X — NOT a patch over a core
                    # symbol. Intentionally not emitted (false-positive guard).
        self.generic_visit(node)


def extract_targets(source: str) -> list[MockTarget]:
    """Parse ``source`` (a test file's text) and return every mock/patch target.

    Pure-static: parses with ``ast``, never executes. Raises ``SyntaxError`` if
    the source does not parse — the caller (ledger) records that as a
    ``parse-error`` rather than letting it abort the run."""
    tree = ast.parse(source)
    module_aliases = _aliases_from_imports([s for s in tree.body if isinstance(s, ast.stmt)])
    ext = _Extractor(module_aliases)
    # Visit module-level statements (imports already collected; visiting them
    # again is harmless). Functions/classes drive the scope stack.
    for stmt in tree.body:
        ext.visit(stmt)
    # Deterministic order: by line then by resolved target string.
    return sorted(ext.targets, key=lambda t: (t.lineno, t.target or "", t.form))


def extract_file(path: Path) -> list[MockTarget]:
    """Extract from a file path (convenience wrapper)."""
    return extract_targets(path.read_text(encoding="utf-8"))
