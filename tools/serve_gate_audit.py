"""Static ungated-serve detector — make the §9.0 node-label serve gate a class,
not an instance (antiek-serve-governance SPR-02 · M3).

Context (assume zero project knowledge)
=======================================
Master-spec §9.0: a node's ``canonical_label`` can be derived from an owner-only
document (``content_class in {personal_reading, restricted_pending_opt_in}``),
so serving that label to a **non-owner** is a data-governance violation. The
graph serve surfaces (``substrate/graph/search.py``) close this the *same* way
everywhere: any SQL that SELECTs ``nodes.canonical_label`` for a non-privileged
caller composes the canonical gate fragment from
``substrate.graph.retrieval_gate.non_privileged_node_provenance_clause`` (the
provenance join + exclusion set + fail-closed-on-unresolved contract). SPR-01
gated ``search_nodes_by_label`` (#202); #292 gated ``_fetch_edges_and_nodes``.

Those were two *instances*. This module is a standing **tripwire** against
re-opening the class: a static check that fails if a function in the audited
graph-serve modules emits a ``canonical_label`` (the owner-derivable field) from
a SELECT **without** the gate fragment interpolated into that same query. The
next ungated serve helper of the common shape reds a check before it ships,
instead of leaking silently. It is a tripwire, **not** a proof of total
mediation — see "Honest limits".

What it is — and honestly is not
================================
This is a **static, AST-level** guard over an explicit, curated list of
graph-serve source modules (:data:`SERVE_MODULES`). For each top-level function
(and nested function) it asks two questions off the *source*, no DB:

  (a) does the function contain a SQL string that SELECTs / ILIKEs
      ``canonical_label`` (the owner-derivable serve field)?  and
  (b) for that *same* query, is the gate fragment interpolated into it — i.e. an
      f-string that interpolates the value of ``non_privileged_node_provenance_clause``
      (or is the function on the audited :data:`GATE_ALLOWLIST`)?

Gating is judged **per emission, not per function**: a plain (non-f-string)
labelled SELECT literal can never carry the runtime gate fragment, so it is
always flagged; an f-string is gated only if the fragment is interpolated into
*it*. This closes the ``gates query A, forgets ungated query B in the same
function`` bypass that a looser "function mentions the gate somewhere" check
would miss. On the current tree every emitter interpolates the fragment into its
own labelled SELECT, so the check returns zero findings; a newly-added ungated
``SELECT ... canonical_label`` reds it.

Honest limits (named, not hidden — see the SPR-02 rigor block):
  (i)  **Curated module scope.** The enforced set is :data:`SERVE_MODULES`. Any
       other ``substrate/graph`` module that serves the field is reported in the
       report's ``coverage_frontier`` (informational, self-disclosing) but NOT
       vetted — because whether it serves a *non-privileged* consumer (a leak)
       or is owner/research-only (legitimately ungated) is a §9.0 privilege
       adjudication, not a code-shape fact. As of this writing the frontier
       includes ``substrate/graph/traverse.py`` (path labels served via the
       research connector) — filed for privilege adjudication, deliberately not
       silently gated.
  (ii) **Literal-SQL only.** SQL built by cross-call string concatenation, a
       column selected via ``SELECT *``, or a table/column name interpolated
       from a variable can carry the label without a matchable literal, and is
       not caught. This is a tripwire against the common honest mistake (write a
       labelled SELECT, forget the gate), not a proof of total mediation.
  (iii)**Gate-by-name.** The gate must be the canonical
       :data:`GATE_CALL`; a gate applied through an un-named/re-exported helper
       would read as ungated (a false positive — the safe direction).
The complementary *data-plane* proof that no owner-only row actually renders on
the serve projection lives in ``substrate/corpus_audit.py``; the two are
deliberately different planes (code-shape here, live-rows there).
"""

from __future__ import annotations

import argparse
import ast
import os
from dataclasses import dataclass, field

# ── Configuration (the curated, audited surface) ─────────────────────────────

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

#: Graph-serve source modules whose label-emitting SQL must be gated. Repo-root
#: relative. Adding a new graph serve module here extends the guard to it.
SERVE_MODULES: tuple[str, ...] = (
    "substrate/graph/search.py",
    "substrate/graph/retrieval_substrate.py",
)

#: The single canonical gate a labelled serve SELECT must route through.
GATE_CALL = "non_privileged_node_provenance_clause"

#: The owner-derivable serve field whose emission triggers the gate requirement.
GUARDED_FIELD = "canonical_label"

#: Functions exempt from the gate requirement WITH a recorded reason. An entry
#: is an audited decision, not a silencer: each must name why serving the field
#: from this function is not a non-privileged §9.0 surface. Keyed by
#: ``"<module-relpath>::<qualname>"``. Empty on the current tree — every graph
#: emitter gates itself inline, so nothing needs an exemption.
GATE_ALLOWLIST: dict[str, str] = {}


# ── Findings ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ServeGateFinding:
    """One ungated ``canonical_label`` serve emitter."""

    module: str          # repo-relative source path
    qualname: str        # dotted function qualname within the module
    lineno: int          # 1-based line of the def
    reason: str          # human-readable why-flagged

    @property
    def key(self) -> str:
        return f"{self.module}::{self.qualname}"

    def render(self) -> str:
        return (
            f"{self.module}:{self.lineno} {self.qualname}: emits "
            f"{GUARDED_FIELD!r} from SQL without calling {GATE_CALL}()"
        )


@dataclass
class AuditReport:
    findings: list[ServeGateFinding] = field(default_factory=list)
    modules_scanned: list[str] = field(default_factory=list)
    #: Modules named in SERVE_MODULES that were not found on disk (honesty: a
    #: renamed/moved serve module must not silently drop out of coverage).
    modules_missing: list[str] = field(default_factory=list)
    #: The COVERAGE FRONTIER (honesty, not enforcement): other ``substrate/graph``
    #: modules that emit ``canonical_label`` from a SELECT but are NOT in
    #: SERVE_MODULES, so the enforcing check does not vet them. Surfaced so the
    #: completeness limit is self-disclosing — a reviewer sees the un-audited
    #: label-serve surface (e.g. traverse.py path labels) in the guard's own
    #: output rather than having to trust a docstring. Informational: it does
    #: NOT red the build, because whether such a module serves a *non-privileged*
    #: consumer (a leak) or is owner/research-only (legitimately ungated) is a
    #: §9.0 privilege adjudication, not a code-shape fact this static check can
    #: make. See the module docstring "Honest limits".
    coverage_frontier: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        # Enforcement is findings + missing-module only. The frontier is
        # informational by design (see the field doc) and does not fail ok.
        return not self.findings and not self.modules_missing

    def render(self) -> str:
        lines = ["serve-gate audit (§9.0 static ungated-serve detector)", "=" * 52]
        lines.append(f"modules scanned: {len(self.modules_scanned)}")
        for m in self.modules_missing:
            lines.append(f"  ::error:: serve module missing (coverage gap): {m}")
        if not self.findings:
            lines.append("findings: 0 — every labelled serve SELECT is gated.")
        else:
            lines.append(f"findings: {len(self.findings)} ungated serve path(s):")
            lines += [f"  ::error:: {f.render()}" for f in self.findings]
        if self.coverage_frontier:
            lines.append(
                f"coverage frontier ({len(self.coverage_frontier)} un-audited "
                f"label-serve module(s) — informational, need privilege adjudication):"
            )
            lines += [f"  ::notice:: {m}" for m in self.coverage_frontier]
        return "\n".join(lines)


# ── The static check ─────────────────────────────────────────────────────────

def _sql_selects_guarded_field(sql: str) -> bool:
    """Heuristic: this SQL string emits the guarded label field on a read path.

    True when the literal has the shape of a SELECT that reads the field —
    ``canonical_label`` present together with both ``SELECT`` and ``FROM``.
    Requiring ``FROM`` (not just any read verb) keeps prose that merely mentions
    the column — a docstring like "ILIKE search over ``canonical_label``" — from
    reading as a query, while still matching every real labelled SELECT (they
    all have a FROM clause). An INSERT/UPDATE that writes the column is not a
    serve emission and is correctly excluded.
    """
    low = sql.lower()
    if GUARDED_FIELD not in low:
        return False
    return "select" in low and "from" in low


def _gate_call_name(node: ast.AST) -> str | None:
    """The called-function name of a Call node (``.attr`` or ``.id``), else None."""
    if not isinstance(node, ast.Call):
        return None
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return None


def _gate_fragment_names(func: ast.AST) -> set[str]:
    """Names bound to the SQL *fragment* returned by the gate.

    The gate returns ``(sql_fragment, params)``; the caller writes
    ``gate_sql, gate_params = non_privileged_node_provenance_clause(...)`` and
    interpolates ``{gate_sql}`` into the SELECT. We collect the fragment name
    (the first tuple target, or a bare single target) so we can check it is
    interpolated into the *same* labelled SELECT — proving the gate is APPLIED
    to that query, not merely mentioned somewhere in the function.
    """
    names: set[str] = set()
    for sub in ast.walk(func):
        if isinstance(sub, ast.Assign) and _gate_call_name(sub.value) == GATE_CALL:
            for tgt in sub.targets:
                if isinstance(tgt, ast.Tuple) and tgt.elts:
                    first = tgt.elts[0]
                    if isinstance(first, ast.Name):
                        names.add(first.id)
                elif isinstance(tgt, ast.Name):
                    names.add(tgt.id)
    return names


def _joinedstr_text_and_interpolated(node: ast.JoinedStr) -> tuple[str, set[str], bool]:
    """(concatenated literal text, interpolated Names, has-direct-gate-call)."""
    text_parts: list[str] = []
    names: set[str] = set()
    direct_gate = False
    for val in node.values:
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            text_parts.append(val.value)
        elif isinstance(val, ast.FormattedValue):
            for sub in ast.walk(val):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
                if _gate_call_name(sub) == GATE_CALL:
                    direct_gate = True
    return "".join(text_parts), names, direct_gate


def _emission_is_gated(
    is_fstring: bool, interpolated: set[str], direct_gate: bool, gate_names: set[str],
) -> bool:
    """A labelled SELECT is gated iff the runtime gate fragment is interpolated
    INTO IT. A plain (non-f-string) literal can never carry the fragment, so it
    is never gated — this closes the ``gates query A, forgets query B`` bypass
    that a mere function-level ``mentions the gate`` check would miss (FN3)."""
    if not is_fstring:
        return False
    return direct_gate or bool(interpolated & gate_names)


def _bare_expr_string_ids(node: ast.AST) -> set[int]:
    """ids of string expressions that stand alone as a statement — docstrings and
    dead string literals. A SQL string is always an *argument* to ``.execute``,
    never a bare statement, so these can never be a real serve emission."""
    ids: set[int] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Expr) and isinstance(sub.value, (ast.Constant, ast.JoinedStr)):
            ids.add(id(sub.value))
    return ids


def _ungated_emissions(func: ast.AST) -> bool:
    """True if this function contains a labelled serve SELECT the gate is not
    applied to. Evaluated per-emission (not per-function-mention)."""
    gate_names = _gate_fragment_names(func)
    skip_ids = _bare_expr_string_ids(func)
    # Constants that are literal parts of a JoinedStr must not be double-counted
    # as standalone plain strings.
    joined_child_ids: set[int] = set()
    joined: list[ast.JoinedStr] = []
    for sub in ast.walk(func):
        if isinstance(sub, ast.JoinedStr) and id(sub) not in skip_ids:
            joined.append(sub)
            for v in sub.values:
                if isinstance(v, ast.Constant):
                    joined_child_ids.add(id(v))

    for node in joined:
        text, interpolated, direct_gate = _joinedstr_text_and_interpolated(node)
        if _sql_selects_guarded_field(text) and not _emission_is_gated(
            True, interpolated, direct_gate, gate_names,
        ):
            return True

    for sub in ast.walk(func):
        if (
            isinstance(sub, ast.Constant)
            and isinstance(sub.value, str)
            and id(sub) not in joined_child_ids
            and id(sub) not in skip_ids
            and _sql_selects_guarded_field(sub.value)
        ):
            return True  # a plain labelled SELECT literal cannot be gated
    return False


class _FunctionAuditor(ast.NodeVisitor):
    """Walk one module; flag functions with an ungated labelled serve SELECT."""

    def __init__(self, module_relpath: str) -> None:
        self.module = module_relpath
        self.findings: list[ServeGateFinding] = []
        self._scope: list[str] = []

    def _visit_function(self, node: ast.AST) -> None:
        self._scope.append(node.name)  # type: ignore[attr-defined]
        qualname = ".".join(self._scope)
        if _ungated_emissions(node):
            key = f"{self.module}::{qualname}"
            if key not in GATE_ALLOWLIST:
                self.findings.append(
                    ServeGateFinding(
                        module=self.module,
                        qualname=qualname,
                        lineno=node.lineno,  # type: ignore[attr-defined]
                        reason="labelled serve SELECT not routed through the gate",
                    )
                )
        self.generic_visit(node)
        self._scope.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function


def audit_source(source: str, module_relpath: str) -> list[ServeGateFinding]:
    """Audit one module's *source text*. Exposed so a test can feed a synthetic
    ungated helper (the negative control) without touching a real file."""
    auditor = _FunctionAuditor(module_relpath)
    auditor.visit(ast.parse(source))
    return auditor.findings


def _module_emits_guarded_field(source: str) -> bool:
    """Does this module contain ANY labelled serve SELECT (gated or not)? Used
    to compute the coverage frontier — the set of graph modules that serve the
    field but are not in the enforced SERVE_MODULES list."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    skip_ids = _bare_expr_string_ids(tree)
    for sub in ast.walk(tree):
        if id(sub) in skip_ids:
            continue
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if _sql_selects_guarded_field(sub.value):
                return True
        elif isinstance(sub, ast.JoinedStr):
            text, _, _ = _joinedstr_text_and_interpolated(sub)
            if _sql_selects_guarded_field(text):
                return True
    return False


def _coverage_frontier(root: str, audited: tuple[str, ...]) -> list[str]:
    """Other ``substrate/graph/*.py`` modules that emit the guarded field but are
    not audited — the self-disclosing completeness limit (informational)."""
    graph_dir = os.path.join(root, "substrate", "graph")
    audited_set = set(audited)
    frontier: list[str] = []
    if not os.path.isdir(graph_dir):
        return frontier
    for name in sorted(os.listdir(graph_dir)):
        if not name.endswith(".py"):
            continue
        rel = os.path.join("substrate", "graph", name)
        if rel in audited_set:
            continue
        with open(os.path.join(graph_dir, name), encoding="utf-8") as fh:
            if _module_emits_guarded_field(fh.read()):
                frontier.append(rel)
    return frontier


def audit(repo_root: str | None = None,
          modules: tuple[str, ...] = SERVE_MODULES) -> AuditReport:
    """Audit the configured serve modules on disk + compute the coverage frontier."""
    root = repo_root or _REPO
    report = AuditReport()
    for rel in modules:
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            report.modules_missing.append(rel)
            continue
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        report.modules_scanned.append(rel)
        report.findings.extend(audit_source(source, rel))
    report.coverage_frontier = _coverage_frontier(root, modules)
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--root", default=None, help="Repo root (default: this repo).")
    args = p.parse_args(argv)
    report = audit(args.root)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
