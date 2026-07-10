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

Those were two *instances*. This module makes the **class** un-reintroducible:
a standing static check that fails if a function in the graph-serve modules
emits a ``canonical_label`` (the owner-derivable field) from SQL **without**
routing through the gate. The next ungated serve helper reds a check before it
ships, instead of leaking silently.

What it is — and honestly is not
================================
This is a **static, AST-level** guard over an explicit, curated list of
graph-serve source modules (:data:`SERVE_MODULES`). For each top-level function
(and nested function) it asks two questions off the *source*, no DB:

  (a) does the function body contain a SQL string literal that SELECTs /
      ILIKEs ``canonical_label`` (the owner-derivable serve field)?  and
  (b) does that same function call ``non_privileged_node_provenance_clause``
      (the one canonical gate) — or is it on the audited :data:`GATE_ALLOWLIST`
      of functions gated by another audited means?

A function that answers (a)-yes and (b)-no is a **finding**: an ungated serve
path. On the current tree every emitter gates itself, so the check returns zero
findings; a newly-added ungated ``SELECT ... canonical_label`` reds it.

Honest limits (named, not hidden — see the SPR-02 rigor block): this is a
static check over a *curated module list* and *literal SQL strings*. It cannot
see (i) a serve path in a module not on :data:`SERVE_MODULES`, (ii) SQL built by
dynamic string concatenation across calls, or (iii) a gate applied by an
un-named helper. It is therefore a **tripwire against the common, honest
mistake** (add a raw labelled SELECT, forget the gate), NOT a proof of total
mediation. The complementary *data-plane* proof that no owner-only row actually
renders on the serve projection lives in ``substrate/corpus_audit.py``; the two
are deliberately different planes (code-shape here, live-rows there).
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

    @property
    def ok(self) -> bool:
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
        return "\n".join(lines)


# ── The static check ─────────────────────────────────────────────────────────

def _sql_selects_guarded_field(sql: str) -> bool:
    """Heuristic: this SQL string emits the guarded label field on a read path.

    True when the literal mentions ``canonical_label`` together with a read verb
    (``SELECT`` or ``ILIKE``). Deliberately conservative-to-flag: an INSERT/
    UPDATE writing the column is not a *serve* emission, so we require a read
    verb rather than the bare column name.
    """
    low = sql.lower()
    if GUARDED_FIELD not in low:
        return False
    return "select" in low or "ilike" in low


class _FunctionAuditor(ast.NodeVisitor):
    """Walk one module; flag functions that emit the guarded field ungated."""

    def __init__(self, module_relpath: str) -> None:
        self.module = module_relpath
        self.findings: list[ServeGateFinding] = []
        self._scope: list[str] = []

    def _emits_guarded_field(self, node: ast.AST) -> bool:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                if _sql_selects_guarded_field(sub.value):
                    return True
            elif isinstance(sub, ast.JoinedStr):  # f-string SQL
                for val in sub.values:
                    if (
                        isinstance(val, ast.Constant)
                        and isinstance(val.value, str)
                        and _sql_selects_guarded_field(val.value)
                    ):
                        return True
        return False

    def _calls_gate(self, node: ast.AST) -> bool:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                fn = sub.func
                name = (
                    fn.attr if isinstance(fn, ast.Attribute)
                    else fn.id if isinstance(fn, ast.Name)
                    else None
                )
                if name == GATE_CALL:
                    return True
        return False

    def _visit_function(self, node: ast.AST) -> None:
        self._scope.append(node.name)  # type: ignore[attr-defined]
        qualname = ".".join(self._scope)
        if self._emits_guarded_field(node) and not self._calls_gate(node):
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


def audit(repo_root: str | None = None,
          modules: tuple[str, ...] = SERVE_MODULES) -> AuditReport:
    """Audit the configured serve modules on disk."""
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
