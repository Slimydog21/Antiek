"""fake_gate_detector.py — deterministic mutation-LITE fake-gate detector.

Antiek × Beck Test-Integrity, SPR-02. Kent Beck: *"if you change the behavior
of the code and a test doesn't break, then the test isn't doing anything."*
That sentence is the spec. ``ci.yml`` already carries a special case — the
**invariant-registry meta-check** that reds when a ``guarded`` declaration's
guard is "missing, skipped, xfailed, xpassed, stubbed, or vacuous (the §14.4
fake-green disease)". This tool GENERALIZES that one meta-check from a single
registry to a bounded, named set of load-bearing lines across the product.

THE TECHNIQUE (mutation-lite, NOT full mutation testing)
========================================================
Full mutation testing (mutmut / cosmic-ray) reruns the whole suite per mutant —
unaffordable on ~5,088 tests under the repo's 40-minute CI ceiling (see
``mutants/README.md`` for the not-mutmut decision). Instead we flip a *named
handful* of load-bearing lines listed in committed ``mutants/*.toml`` files. For
each mutant:

  1. resolve the anchor (a function/method qualname + a statement matcher) via
     ``ast`` — NOT a bare line number, which drifts under refactors;
  2. apply ONE mutation op (``noop`` / ``early_return`` / ``invert_guard`` /
     ``swap_compare``) to the working-tree source;
  3. run ONLY that mutant's ``test_selector`` against the EXISTING (mocked)
     suite — no live model, no real-provider dependency;
  4. ALWAYS restore the original bytes (``try/finally``, survives exceptions AND
     ``KeyboardInterrupt``), and assert the sha256 matches afterward.

Outcome per mutant:
  * ``killed``      — ≥1 targeting test FAILED. The gate is real (good).
  * ``survived``    — all targeting tests PASSED on broken code. FAKE GATE — the
                      finding.
  * ``no-tests``    — the selector matched ZERO tests. Also a finding: an
                      unguarded load-bearing line.
  * ``anchor-stale``— the anchor no longer resolves (a refactor moved/removed the
                      line). NOT a false pass — reported so the mutant is fixed.
  * ``timed-out``   — the test run exceeded the per-mutant timeout. NOT survived,
                      NOT killed; the file is restored.
  * ``clean-run-timeout`` — the mutated run produced node errors, but the CLEAN
                      re-run that would prove them mutation-caused (vs pre-existing)
                      TIMED OUT. We cannot adjudicate, so we do NOT credit the node
                      errors as a kill (that would MASK a fake gate); the mutant is
                      SURFACED as a finding for human review. A real test-BODY
                      failure under mutation is still ``killed`` regardless.

SAFETY (rigor #3 — the #1 constraint)
======================================
This tool writes to REAL product source files (temporarily). A crashed run that
strands a mutated ``db_lock.py`` is a catastrophe far worse than any fake gate.
The restore is bulletproof BY CONSTRUCTION:
  * sha256 of the target is captured BEFORE any mutation;
  * the original bytes are restored in a ``finally`` that catches BaseException
    (so it survives ``KeyboardInterrupt`` / ``SystemExit``);
  * the post-restore sha256 is asserted to equal the pre-mutation sha256 — a
    mismatch raises ``RestoreIntegrityError`` LOUDLY (we do not silently proceed
    over a corrupted tree);
  * a pre-flight ``git status --porcelain`` guard REFUSES to run if any mutant
    target has uncommitted changes (so a crash can't strand a half-mutated file
    over real edits).

DETERMINISM
===========
Same mutant set + same tree → same outcomes. Mutants run in committed order
(sorted by ``id``); no randomness anywhere. ``fake_gates.json`` is emitted with
``sort_keys=True`` and omits any wall-clock field from its hashed core (a
two-run diff is empty).

BASELINE / GRANDFATHERING (M4)
==============================
On a suite the autopsy calls diseased, the first run WILL find survivors. Per
``docs/decisions/ci-informational-gates.md`` you cannot fail CI on a backlog. We
MIRROR EXACTLY the capture/enforce/stale contract of
``tools/lints/cli_with_baseline.py`` + ``tools/lints/baseline.py`` (a sorted,
schema-versioned JSON of ``ViolationKey``-shaped entries):
  * ``--capture``  writes the current findings (survivors + no-tests) to
    ``mutants/survivors_baseline.json``; the operator commits it.
  * ``--enforce``  reds (exit 1) ONLY on a finding NOT in the baseline — a NEW
    fake gate. Grandfathered findings exit 0.
  * ``--stale``    reports baselined findings now ``killed`` (someone wrote a
    real test) so the baseline can shrink — it only ever moves DOWN.

CLI
===
    python -m tools.fake_gate_detector --measure            # report, exit 0
    python -m tools.fake_gate_detector --measure --only ID  # one mutant
    python -m tools.fake_gate_detector --capture            # write baseline
    python -m tools.fake_gate_detector --enforce            # exit 1 on NEW
    python -m tools.fake_gate_detector --enforce --stale    # + stale report

Output mirrors the existing AST lints' ``path:line`` contract (cf.
``tools/lint/serve_invariants_check.py``) so the operator reads a fake gate the
same way as the rest of the CI floor.

STDLIB ONLY beyond the repo's own pytest. Uses ``ast`` for the anchor resolver,
``hashlib`` for the restore proof, ``tomllib`` for the mutant set, ``subprocess``
for the pre-flight git guard + the pytest run.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "Mutant",
    "MutantResult",
    "Outcome",
    "AnchorError",
    "RestoreIntegrityError",
    "DirtyTreeError",
    "load_mutants",
    "resolve_anchor",
    "apply_op",
    "run_mutant",
    "run_all",
    "main",
]

# ---------------------------------------------------------------------------
# Constants — documented; the bounded-set + cost decisions live in
# mutants/README.md. These are the operating parameters.
# ---------------------------------------------------------------------------

#: Per-mutant pytest timeout (seconds). Justified vs the repo's 40-min full-suite
#: CI ceiling for ~5,088 tests: a single-module selector is a tiny fraction (the
#: heaviest seed selector runs in <3s; 300s is ~100x headroom for a contended
#: runner). A mutant that *would* hang the suite is itself a finding, recorded
#: ``timed-out`` (not survived, not killed) with the file restored.
DEFAULT_TIMEOUT_S = 300

#: Baseline schema version — bumped only on an incompatible shape change. Mirrors
#: tools/lints/baseline.py SCHEMA_VERSION.
BASELINE_SCHEMA_VERSION = 1

#: Repo root = parent of tools/ (this file lives at tools/fake_gate_detector.py).
_REPO = Path(__file__).resolve().parent.parent

#: The committed mutant set + the survivor baseline live here.
_MUTANTS_DIR = _REPO / "mutants"
_BASELINE_FILE = _MUTANTS_DIR / "survivors_baseline.json"
_REPORT_JSON = _REPO / "fake_gates.json"

#: The repo's own runner (no real-model keys; the EXISTING mocked suite).
_PYTEST_BASE: tuple[str, ...] = (
    sys.executable,
    "-m",
    "pytest",
    "-q",
    "-p",
    "no:cacheprovider",
    "-p",
    "no:xdist",
)

Outcome = Literal[
    "killed", "survived", "no-tests", "anchor-stale", "timed-out",
    "clean-run-timeout",
]

#: The ACTIONABLE findings — surfaced first in the report, gated in --enforce.
#: ``clean-run-timeout`` is a possible fake gate the tool could not adjudicate
#: (the clean re-run timed out): it is SURFACED for human review, never silently
#: credited as a kill — the safe direction for a fake-gate detector (rigor #1).
FINDING_OUTCOMES: frozenset[str] = frozenset(
    {"survived", "no-tests", "clean-run-timeout"}
)

#: Valid mutation operators.
VALID_OPS: frozenset[str] = frozenset(
    {"noop", "early_return", "invert_guard", "swap_compare"}
)

#: Comparison-operator swaps for the swap_compare op. Each maps a source operator
#: token to the token it is replaced with — an inversion that changes behavior on
#: the boundary case (==/!=, </>=, etc.). Deterministic single substitution.
_COMPARE_SWAPS: dict[str, str] = {
    "==": "!=",
    "!=": "==",
    " is not ": " is ",
    " is ": " is not ",
    " not in ": " in ",
    " in ": " not in ",
    ">=": "<",
    "<=": ">",
    ">": "<=",
    "<": ">=",
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AnchorError(RuntimeError):
    """The anchor (qualname + statement matcher) did not resolve in the target.
    Surfaced as the ``anchor-stale`` outcome — NEVER a false pass."""


class RestoreIntegrityError(RuntimeError):
    """The post-restore sha256 did NOT match the pre-mutation sha256. The tree
    may be corrupted; raised LOUDLY so the operator stops and inspects rather
    than proceeding over a half-restored product source file."""


class DirtyTreeError(RuntimeError):
    """A mutant target has uncommitted changes. The pre-flight refuses to run so
    a crash cannot strand a half-mutated file over real edits."""


# ---------------------------------------------------------------------------
# Mutant schema (the committed TOML contract — see mutants/README.md)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Mutant:
    """One committed mutant. ``anchor`` is ``qualname`` + ``match`` (a statement
    substring) — an AST-resolvable locator, NOT a bare line number (which drifts
    under refactors). ``test_selector`` is a pytest ``-k`` expr or a path/node
    selector that SHOULD catch the mutation. ``rationale`` defends the line as
    load-bearing (rigor #5)."""

    id: str
    target: str  # repo-relative path
    qualname: str  # function/method qualname, e.g. "serve_full_text_guarded"
    match: str  # statement substring identifying the line within the qualname
    op: str  # one of VALID_OPS
    test_selector: tuple[str, ...]  # pytest args (path::node / -k expr)
    rationale: str
    added: str  # ISO date
    added_by: str
    # swap_compare only: which comparison token to swap (defaults to first found).
    swap: str = ""

    def __post_init__(self) -> None:
        if self.op not in VALID_OPS:
            raise ValueError(
                f"mutant {self.id!r}: op {self.op!r} is not one of "
                f"{sorted(VALID_OPS)}"
            )
        if not self.test_selector:
            raise ValueError(f"mutant {self.id!r}: test_selector is empty")
        if self.swap and self.swap not in _COMPARE_SWAPS:
            raise ValueError(
                f"mutant {self.id!r}: swap token {self.swap!r} not in "
                f"{sorted(_COMPARE_SWAPS)}"
            )


@dataclass(frozen=True)
class MutantResult:
    """The outcome of one mutant run. ``path_line`` is the resolved
    ``path:line`` of the mutated statement (the anchor resolution) — empty only
    for ``anchor-stale``. ``failed_tests`` lists the killing test node ids (for
    ``killed``); ``n_tests`` is how many tests the selector ran."""

    id: str
    outcome: Outcome
    path_line: str
    op: str
    rationale: str
    selector: tuple[str, ...]
    n_tests: int
    failed_tests: tuple[str, ...]
    detail: str

    def is_finding(self) -> bool:
        return self.outcome in FINDING_OUTCOMES


# ---------------------------------------------------------------------------
# Mutant loading (deterministic order: sorted by id)
# ---------------------------------------------------------------------------


def load_mutants(mutants_dir: Path = _MUTANTS_DIR) -> list[Mutant]:
    """Load every ``mutants/*.toml`` (skipping the baseline JSON + README), in
    deterministic id order. Each TOML may carry one ``[[mutant]]`` array or a
    single ``[mutant]`` table; both shapes are supported so a target can group
    several mutants in one file."""
    out: list[Mutant] = []
    for toml_path in sorted(mutants_dir.glob("*.toml")):
        with toml_path.open("rb") as fh:
            data = tomllib.load(fh)
        entries = _mutant_entries(data)
        for entry in entries:
            out.append(_mutant_from_entry(entry, toml_path))
    out.sort(key=lambda m: m.id)
    _assert_unique_ids(out)
    return out


def _mutant_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    if "mutant" in data and isinstance(data["mutant"], list):
        return list(data["mutant"])
    if "mutant" in data and isinstance(data["mutant"], dict):
        return [data["mutant"]]
    if "mutants" in data and isinstance(data["mutants"], list):
        return list(data["mutants"])
    raise ValueError(
        "mutant TOML must carry a [[mutant]] array or a [mutant] table"
    )


def _mutant_from_entry(entry: dict[str, Any], src: Path) -> Mutant:
    try:
        anchor = entry["anchor"]
        selector = entry["test_selector"]
        if isinstance(selector, str):
            selector = [selector]
        return Mutant(
            id=str(entry["id"]),
            target=str(entry["target"]),
            qualname=str(anchor["qualname"]),
            match=str(anchor["match"]),
            op=str(entry["op"]),
            test_selector=tuple(str(s) for s in selector),
            rationale=str(entry["rationale"]),
            added=str(entry["added"]),
            added_by=str(entry["added_by"]),
            swap=str(entry.get("swap", "")),
        )
    except KeyError as exc:
        raise ValueError(f"{src.name}: mutant missing field {exc}") from exc


def _assert_unique_ids(mutants: Sequence[Mutant]) -> None:
    seen: set[str] = set()
    for m in mutants:
        if m.id in seen:
            raise ValueError(f"duplicate mutant id {m.id!r}")
        seen.add(m.id)


# ---------------------------------------------------------------------------
# AST anchor resolver — find the target statement by qualname + matcher
# ---------------------------------------------------------------------------


def _find_qualname_node(tree: ast.Module, qualname: str) -> ast.AST | None:
    """Resolve a dotted qualname (``func`` or ``Class.method``) to its def node.
    Walks the tree; supports one level of class nesting (the suite's shape)."""
    parts = qualname.split(".")
    if len(parts) == 1:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == parts[0]:
                return node
        # A bare name may also be a module-level Assign target (a constant
        # like a frozenset) — resolve to the Assign node so a weight/constant
        # can be anchored.
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == parts[0]:
                        return node
        return None
    # Class.method
    cls_name, fn_name = parts[0], parts[1]
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == fn_name:
                    return sub
    return None


def _node_span(node: ast.AST) -> tuple[int, int]:
    """1-based inclusive (first_line, last_line) for a def/assign node, including
    its decorators (so the matcher search covers the whole construct)."""
    first = node.lineno
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.decorator_list:
        first = min(first, min(d.lineno for d in node.decorator_list))
    last = getattr(node, "end_lineno", node.lineno) or node.lineno
    return first, last


@dataclass(frozen=True)
class _Anchor:
    """A resolved anchor: the def node it lives in + the 1-based source line of
    the matched statement."""

    node: ast.AST
    line: int  # 1-based line of the matched statement


def resolve_anchor(source: str, mutant: Mutant) -> _Anchor:
    """Resolve ``mutant``'s anchor against ``source``. Returns the def node and
    the 1-based line of the single statement matching ``mutant.match`` within the
    qualname's span. Raises ``AnchorError`` (→ ``anchor-stale``) if the qualname
    is gone OR the matcher matches zero / >1 lines (an ambiguous matcher is as
    stale as a missing one — we refuse to guess which line to mutate)."""
    tree = ast.parse(source)
    node = _find_qualname_node(tree, mutant.qualname)
    if node is None:
        raise AnchorError(
            f"qualname {mutant.qualname!r} not found in {mutant.target}"
        )
    first, last = _node_span(node)
    lines = source.splitlines()
    hits = [
        ln
        for ln in range(first, last + 1)
        if mutant.match in lines[ln - 1]
    ]
    if not hits:
        raise AnchorError(
            f"match {mutant.match!r} not found in {mutant.qualname!r} "
            f"(lines {first}-{last}) of {mutant.target}"
        )
    if len(hits) > 1:
        raise AnchorError(
            f"match {mutant.match!r} is AMBIGUOUS in {mutant.qualname!r} "
            f"({len(hits)} lines: {hits}) of {mutant.target} — tighten it"
        )
    return _Anchor(node=node, line=hits[0])


# ---------------------------------------------------------------------------
# Mutation operators — produce mutated SOURCE TEXT (then verified parseable)
# ---------------------------------------------------------------------------


def _leading_ws(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def apply_op(source: str, mutant: Mutant, anchor: _Anchor) -> str:
    """Return the mutated source for ``mutant``. The result is guaranteed to PARSE
    (we ``ast.parse`` it before returning — a mutation that does not parse is a
    detector bug, not a finding, and raises so it is caught in tests, never run
    against the suite)."""
    lines = source.splitlines(keepends=True)
    idx = anchor.line - 1  # 0-based
    line = lines[idx]
    newline = "\n" if line.endswith("\n") else ""

    if mutant.op == "noop":
        indent = _leading_ws(line)
        lines[idx] = f"{indent}pass  # MUTANT[{mutant.id}]:noop{newline}"

    elif mutant.op == "early_return":
        # Insert ``return`` (None) as the FIRST statement of the function body,
        # at the matched statement's indentation. The matched line identifies the
        # function's first real statement (the mutant points at it). We replace
        # that first statement with an early return so the body never executes.
        indent = _leading_ws(line)
        lines[idx] = f"{indent}return  # MUTANT[{mutant.id}]:early_return{newline}"

    elif mutant.op == "invert_guard":
        # Flip ``if <cond>:`` to ``if not (<cond>):`` (and the symmetric
        # ``if not <cond>:`` form). Operates on the matched line's text.
        lines[idx] = _invert_guard_line(line, mutant)

    elif mutant.op == "swap_compare":
        lines[idx] = _swap_compare_line(line, mutant)

    else:  # pragma: no cover — guarded by Mutant.__post_init__
        raise ValueError(f"unknown op {mutant.op!r}")

    mutated = "".join(lines)
    try:
        ast.parse(mutated)
    except SyntaxError as exc:
        raise AnchorError(
            f"mutant {mutant.id!r} op {mutant.op!r} produced unparseable source "
            f"at {mutant.target}:{anchor.line} — {exc}. The anchor likely points "
            f"at a line whose shape the op cannot mutate; fix the mutant."
        ) from exc
    return mutated


def _invert_guard_line(line: str, mutant: Mutant) -> str:
    """Invert an ``if``/``elif``/``while`` guard on one line. ``if X:`` →
    ``if not (X):``; ``if not X:`` → ``if (X):``. Refuses (AnchorError) if the
    line is not a single-line guard ending in ``:``."""
    stripped = line.rstrip("\n")
    nl = "\n" if line.endswith("\n") else ""
    indent = _leading_ws(stripped)
    body = stripped.strip()
    for kw in ("if ", "elif ", "while "):
        if body.startswith(kw) and body.endswith(":"):
            cond = body[len(kw) : -1].strip()
            if cond.startswith("not "):
                new_cond = f"({cond[len('not '):].strip()})"
            else:
                new_cond = f"not ({cond})"
            return f"{indent}{kw}{new_cond}:  # MUTANT[{mutant.id}]:invert_guard{nl}"
    raise AnchorError(
        f"mutant {mutant.id!r} op invert_guard expects a single-line "
        f"if/elif/while guard ending ':'; got {body!r}"
    )


def _swap_compare_line(line: str, mutant: Mutant) -> str:
    """Swap ONE comparison operator on the line. If ``mutant.swap`` is set, that
    exact token is swapped (first occurrence); otherwise the first matching token
    from ``_COMPARE_SWAPS`` is used. Raises AnchorError if no swappable operator
    is present."""
    stripped = line.rstrip("\n")
    nl = "\n" if line.endswith("\n") else ""
    if mutant.swap:
        tok = mutant.swap
        if tok not in stripped:
            raise AnchorError(
                f"mutant {mutant.id!r} swap token {tok!r} not on line: {stripped!r}"
            )
        swapped = stripped.replace(tok, _COMPARE_SWAPS[tok], 1)
        return f"{swapped}  # MUTANT[{mutant.id}]:swap_compare{nl}"
    # Auto: pick the first token that appears. Order matters — try the
    # longer/spaced tokens (" is not ", ">=") before their substrings.
    for tok in ("==", "!=", " is not ", " not in ", " is ", " in ", ">=", "<=", ">", "<"):
        if tok in stripped:
            swapped = stripped.replace(tok, _COMPARE_SWAPS[tok], 1)
            return f"{swapped}  # MUTANT[{mutant.id}]:swap_compare{nl}"
    raise AnchorError(
        f"mutant {mutant.id!r} op swap_compare found no comparison operator on "
        f"line: {stripped!r}"
    )


# ---------------------------------------------------------------------------
# sha256 + the pre-flight clean-tree guard
# ---------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def assert_clean_tree(targets: Iterable[str], repo: Path = _REPO) -> None:
    """Pre-flight: REFUSE to run if any mutant target has uncommitted changes.
    A crash mid-mutation could otherwise strand a half-mutated file over real
    edits, and the byte-for-byte restore would restore the WRONG (dirty) bytes.
    Checked via ``git status --porcelain`` on the exact target paths."""
    target_list = sorted(set(targets))
    if not target_list:
        return
    proc = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--", *target_list],
        capture_output=True,
        text=True,
        check=False,
    )
    dirty = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if dirty:
        raise DirtyTreeError(
            "REFUSING to run: mutant target(s) have uncommitted changes — a "
            "crash could strand a half-mutated file over real edits, and the "
            "restore would restore the dirty bytes, not the committed ones. "
            "Commit or stash these first:\n  " + "\n  ".join(dirty)
        )


# ---------------------------------------------------------------------------
# The mutate → run → restore engine (SAFETY core)
# ---------------------------------------------------------------------------


def _run_pytest(selector: Sequence[str], repo: Path, timeout_s: int) -> tuple[int, _PytestRun, str]:
    """Run pytest with ``selector`` and parse the outcome. Returns
    ``(returncode, _PytestRun, raw_tail)``. A timeout propagates as
    ``subprocess.TimeoutExpired`` (handled by the caller)."""
    cmd = [*_PYTEST_BASE, *selector]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(repo),
        timeout=timeout_s,
        check=False,
    )
    out = proc.stdout + "\n" + proc.stderr
    parsed = _parse_pytest_output(out)
    tail = "\n".join(out.splitlines()[-14:])
    return proc.returncode, parsed, tail


@dataclass(frozen=True)
class _PytestRun:
    """Parsed pytest outcome. ``n_ran`` = tests that COLLECTED and ran
    (passed + runtime-failed) — the test-body basis for a KILL. ``n_failed_runtime``
    = tests that ran and FAILED (an assertion / runtime error in a test body).
    ``collection_errors`` = files/nodes that failed to IMPORT/COLLECT — these are
    SELECTOR or ENVIRONMENT defects (e.g. a missing optional dep), NOT a kill: a
    pre-existing collection error reds whether or not the code is mutated, so
    counting it as a kill would mask a fake gate (rigor #1).

    ``node_error_nodes`` = the raw node-level ``ERROR ...::...`` lines (a
    setup/fixture error on a COLLECTED test). The PARSE layer is deliberately
    NEUTRAL about these — it does NOT fold them into ``n_ran`` / ``n_failed_runtime``
    here, because whether a node ERROR is a KILL turns on whether it is
    MUTATION-CAUSED, and that determination needs the clean (un-mutated) tree,
    which only ``run_mutant`` has. See ``run_mutant``'s NODE-ERROR / KILL RULE."""

    n_ran: int
    n_failed_runtime: int
    collection_errors: int
    failed_nodes: tuple[str, ...]
    node_error_nodes: tuple[str, ...]


def _parse_pytest_output(out: str) -> _PytestRun:
    """Parse pytest -q output. Distinguishes runtime FAILED tests (a kill signal)
    from COLLECTION errors (a selector/environment defect that reds regardless of
    the mutation). A collection error is recognised by the
    ``N error(s) during collection`` / ``Interrupted: N error`` banners and by
    ``ERROR <path>`` summary lines that name a FILE (no ``::`` node) — those are
    import-time failures, not a test that ran.

    NODE-LEVEL ERROR — PARSE-LAYER NEUTRALITY (the tool's cardinal-risk guard,
    round-2 sharpen). A node-level ``ERROR tests/x.py::test_foo`` is a
    setup/fixture ERROR on a COLLECTED test — NOT a test-body FAILURE. A
    *mutation-caused* setup error is a legitimate kill (e.g. an ``early_return``
    that makes a write-coordinator factory return ``None`` so every fixture using
    it ERRORs), but a *pre-existing* broken fixture on a survivor's selector would
    ERROR IDENTICALLY without any mutation — counting that as a kill would be a
    FALSE kill, and a false kill MASKS a fake gate (the exact disease this tool
    fights). The parse layer cannot tell these apart from a single run, so it
    stays NEUTRAL: ``node_error_nodes`` is harvested for reporting and for the kill
    decision, but a bare node ERROR does NOT by itself add to ``n_ran`` /
    ``n_failed_runtime`` here. ``run_mutant`` resolves the kill by comparing the
    mutated run's node errors against the CLEAN tree — only NEW ones are
    mutation-caused, hence a kill."""
    import re

    passed = runtime_failed = 0
    for m in re.finditer(r"(\d+)\s+passed", out):
        passed = int(m.group(1))
    for m in re.finditer(r"(\d+)\s+failed", out):
        runtime_failed = int(m.group(1))

    # Collection errors: the explicit banners, plus a count of ``ERROR <path>``
    # summary lines whose target is a FILE (no ``::``) — those are import-time.
    collection_errors = 0
    for m in re.finditer(r"(\d+)\s+error[s]?\s+during\s+collection", out):
        collection_errors = max(collection_errors, int(m.group(1)))
    for m in re.finditer(r"Interrupted:\s+(\d+)\s+error", out):
        collection_errors = max(collection_errors, int(m.group(1)))

    # Harvest the FAILED/ERROR summary lines for reporting + to distinguish a
    # node-level ERROR (a setup/fixture error on a COLLECTED test) from a
    # file-only ERROR (an import-time COLLECTION error → it never ran).
    failed_nodes: list[str] = []
    node_error_nodes: list[str] = []
    file_only_errors = 0
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("FAILED "):
            failed_nodes.append(s.split(None, 1)[1].split(" - ", 1)[0].strip())
        elif s.startswith("ERROR "):
            node = s.split(None, 1)[1].split(" - ", 1)[0].strip()
            if "::" in node:
                node_error_nodes.append(node)  # setup/fixture error on a node
            else:
                file_only_errors += 1  # file failed to import → collection error
    collection_errors = max(collection_errors, file_only_errors)

    # n_failed_runtime / n_ran cover only test-BODY outcomes here. Node-level
    # setup ERRORs are NOT folded in at the parse layer — the kill decision for
    # them is MUTATION-CAUSATION, resolved against the clean tree in run_mutant
    # (a pre-existing broken fixture errors with or without the mutation, so
    # crediting it as a kill would falsely green a fake gate — rigor #1).
    n_failed_runtime = runtime_failed
    n_ran = passed + runtime_failed
    return _PytestRun(
        n_ran=n_ran,
        n_failed_runtime=n_failed_runtime,
        collection_errors=collection_errors,
        failed_nodes=tuple(failed_nodes),
        node_error_nodes=tuple(node_error_nodes),
    )


def _clean_tree_node_errors(
    target: Path,
    original_bytes: bytes,
    selector: Sequence[str],
    repo: Path,
    timeout_s: int,
) -> frozenset[str] | None:
    """Run ``selector`` on the CLEAN (un-mutated) tree and return the set of
    node-level ERROR node-ids it produces. Used by ``run_mutant`` to decide whether
    a node error seen under mutation is MUTATION-CAUSED (new) or PRE-EXISTING.

    This restores ``original_bytes`` to ``target`` first — the SAME bytes the
    caller's ``finally`` restores, so the post-run sha256 integrity proof is
    unaffected. Called ONLY when the mutated run produced node errors, so the
    common (no-node-error) path pays nothing and stays deterministic.

    Returns the frozenset of clean-tree node errors when the re-run COMPLETES
    (the empty set means CONFIRMED-zero: the clean tree errored on nothing). A
    timeout on the clean run returns ``None`` — a distinct UNKNOWN signal that is
    NOT the empty set. We cannot prove the mutated node errors are new (mutation-
    caused) versus pre-existing, so the SAFE direction for a fake-gate detector is
    to NOT credit them as a kill (crediting on uncertainty would MASK a fake gate,
    rigor #1). ``run_mutant`` surfaces this mutant for human review instead."""
    target.write_bytes(original_bytes)
    try:
        _rc, clean_run, _tail = _run_pytest(selector, repo, timeout_s)
    except subprocess.TimeoutExpired:
        return None
    return frozenset(clean_run.node_error_nodes)


def run_mutant(
    mutant: Mutant,
    repo: Path = _REPO,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> MutantResult:
    """Mutate → run → restore ONE mutant. The original bytes are ALWAYS restored
    in a ``finally`` that catches BaseException (KeyboardInterrupt-safe), and the
    post-restore sha256 is asserted to equal the pre-mutation sha256.

    PRECONDITION: ``assert_clean_tree`` has passed for this target (the caller —
    ``run_all`` — runs the pre-flight once for all targets before any mutation).
    """
    target = repo / mutant.target
    if not target.exists():
        return MutantResult(
            id=mutant.id, outcome="anchor-stale", path_line=f"{mutant.target}:0",
            op=mutant.op, rationale=mutant.rationale, selector=mutant.test_selector,
            n_tests=0, failed_tests=(),
            detail=f"target file {mutant.target} does not exist",
        )

    original_bytes = target.read_bytes()
    sha_before = _sha256_bytes(original_bytes)
    source = original_bytes.decode("utf-8")

    # Resolve the anchor + build the mutated source BEFORE touching disk. If
    # either fails, no write has happened — the tree is untouched.
    try:
        anchor = resolve_anchor(source, mutant)
        path_line = f"{mutant.target}:{anchor.line}"
        mutated = apply_op(source, mutant, anchor)
    except AnchorError as exc:
        return MutantResult(
            id=mutant.id, outcome="anchor-stale",
            path_line=f"{mutant.target}:0", op=mutant.op,
            rationale=mutant.rationale, selector=mutant.test_selector,
            n_tests=0, failed_tests=(), detail=str(exc),
        )

    outcome: Outcome
    run: _PytestRun | None = None
    detail = ""
    try:
        # (b) apply mutation
        target.write_bytes(mutated.encode("utf-8"))
        # (c) run ONLY this mutant's targeting tests
        try:
            rc, run, tail = _run_pytest(
                mutant.test_selector, repo, timeout_s
            )
        except subprocess.TimeoutExpired:
            outcome = "timed-out"
            detail = f"pytest exceeded {timeout_s}s"
            return MutantResult(
                id=mutant.id, outcome=outcome, path_line=path_line, op=mutant.op,
                rationale=mutant.rationale, selector=mutant.test_selector,
                n_tests=0, failed_tests=(), detail=detail,
            )

        # NODE-ERROR / KILL RULE (the tool's cardinal-risk guard, round-2 sharpen).
        # A node-level ``ERROR ...::...`` is a setup/fixture ERROR on a COLLECTED
        # test. A MUTATION-CAUSED one is a legitimate kill (e.g. an early_return
        # that makes connect_write return None, so every fixture that opens a write
        # connection ERRORs). But a PRE-EXISTING broken fixture on a survivor's
        # selector would ERROR identically WITHOUT the mutation — crediting that as
        # a kill is a FALSE kill, and a false kill MASKS a fake gate (rigor #1). So
        # a node error counts toward a kill ONLY if it is NEW under the mutation:
        # we run the selector once on the CLEAN (restored) tree and subtract the
        # node errors that already ERROR there. This clean re-run happens ONLY when
        # the mutated run produced node errors (the common path has none → zero
        # extra cost, determinism unchanged). The clean run writes ``original_bytes``
        # — the exact bytes the finally restores — so the sha256 integrity proof
        # below still holds.
        # ``clean_run_timed_out`` is the UNKNOWN case: the clean re-run could not
        # confirm whether the mutated node errors are new (mutation-caused) or
        # pre-existing. On uncertainty we do NOT credit them — see below.
        mutation_caused_node_errors: tuple[str, ...] = ()
        clean_node_error_set: frozenset[str] = frozenset()
        clean_run_timed_out = False
        if run.node_error_nodes:
            clean = _clean_tree_node_errors(
                target, original_bytes, mutant.test_selector, repo, timeout_s
            )
            if clean is None:
                # The clean re-run TIMED OUT. We CANNOT prove the under-mutation
                # node errors are mutation-caused, so we do NOT credit them
                # (crediting on uncertainty would MASK a fake gate, rigor #1).
                # The mutant is surfaced for human review (clean-run-timeout)
                # unless a real test-BODY failure killed it on its own merit.
                clean_run_timed_out = True
            else:
                clean_node_error_set = clean
                mutation_caused_node_errors = tuple(
                    n for n in run.node_error_nodes if n not in clean_node_error_set
                )

        # Effective kill ledger = test-body failures + mutation-caused node errors;
        # effective ran-count includes those node errors (they collected + executed
        # setup under the mutation).
        n_node_kills = len(mutation_caused_node_errors)
        n_killing = run.n_failed_runtime + n_node_kills
        n_ran_eff = run.n_ran + n_node_kills
        failed_eff = tuple(run.failed_nodes) + mutation_caused_node_errors

        # CLEAN-RUN-TIMEOUT (the cardinal-risk guard's UNCERTAINTY direction). The
        # mutated run produced node errors but the clean re-run TIMED OUT, so we
        # could not prove those node errors are mutation-caused. A real test-BODY
        # failure (``n_failed_runtime > 0``) is still a genuine kill on its own
        # merit — that path is unchanged. But absent a body failure we must NOT
        # credit the node errors as a kill (crediting on uncertainty would MASK a
        # fake gate, rigor #1). We SURFACE the mutant for human review instead: a
        # possible fake gate a human dismisses via the steelman, never silently
        # green. (Not reachable in the deterministic --measure run; only when a
        # clean re-run actually times out.)
        if clean_run_timed_out and run.n_failed_runtime == 0:
            outcome = "clean-run-timeout"
            detail = (
                f"mutated run produced {len(run.node_error_nodes)} node-level "
                f"setup/fixture ERROR(s), but the CLEAN re-run TIMED OUT "
                f"(>{timeout_s}s) so we CANNOT prove they are mutation-caused vs "
                f"PRE-EXISTING. Crediting them as a kill on this uncertainty would "
                f"MASK a fake gate (rigor #1), so the mutant is NOT killed — it is "
                f"surfaced for human review. Re-run un-mutated to confirm; if the "
                f"node errors are pre-existing this is a selector/fixture defect, "
                f"if they vanish it is a real kill. Tail:\n{tail}"
            )
            return MutantResult(
                id=mutant.id, outcome=outcome, path_line=path_line, op=mutant.op,
                rationale=mutant.rationale, selector=mutant.test_selector,
                n_tests=run.n_ran, failed_tests=(), detail=detail,
            )

        # A COLLECTION error reds whether or not the code is mutated (a bad selector
        # / a missing optional dep), so it is NEVER a kill — counting it as one
        # would mask a fake gate (rigor #1). When the selector ran ZERO tests AND
        # produced no mutation-caused node kill, it is a SELECTOR DEFECT surfaced as
        # ``no-tests`` (the finding: this load-bearing line has no cleanly-runnable
        # targeting test).
        if n_ran_eff == 0:
            outcome = "no-tests"
            if run.collection_errors:
                detail = (
                    f"selector collected NO runnable tests but produced "
                    f"{run.collection_errors} COLLECTION error(s) (a bad selector "
                    f"or a missing optional dep — these red regardless of the "
                    f"mutation, so they are NOT a kill). Fix the selector to a "
                    f"cleanly-collectable test, or this load-bearing line has no "
                    f"real guard. Tail:\n{tail}"
                )
            elif run.node_error_nodes:
                # Node errors appeared but NONE were new under mutation → every one
                # is a PRE-EXISTING broken fixture on the clean tree. Crediting them
                # would be a false kill, so this is a selector/fixture defect, not a
                # kill (rigor #1).
                detail = (
                    f"selector produced {len(run.node_error_nodes)} node-level "
                    f"setup/fixture ERROR(s), ALL of which ALSO ERROR on the CLEAN "
                    f"(un-mutated) tree — they are PRE-EXISTING, not mutation-caused, "
                    f"so crediting them as a kill would MASK a fake gate (rigor #1). "
                    f"Fix the selector/fixture to run cleanly un-mutated, or this "
                    f"load-bearing line has no real guard. Tail:\n{tail}"
                )
            else:
                detail = (
                    f"selector matched ZERO tests — an unguarded load-bearing "
                    f"line (pytest rc={rc}). Tail:\n{tail}"
                )
        elif n_killing > 0:
            outcome = "killed"
            node_note = (
                f"; {n_node_kills} mutation-caused node-level setup ERROR(s)"
                if n_node_kills else ""
            )
            detail = (
                f"{n_killing} test(s) RAN and FAILED on the mutation "
                f"(of {n_ran_eff} run; {run.collection_errors} collection error(s) "
                f"ignored as non-kill{node_note})"
            )
        else:
            outcome = "survived"
            detail = (
                f"all {n_ran_eff} targeting test(s) that RAN PASSED on broken "
                f"code — FAKE GATE. The selector did not catch the {mutant.op} "
                f"mutation"
                + (
                    f" ({run.collection_errors} collection error(s) ignored)."
                    if run.collection_errors else "."
                )
            )
        return MutantResult(
            id=mutant.id, outcome=outcome, path_line=path_line, op=mutant.op,
            rationale=mutant.rationale, selector=mutant.test_selector,
            n_tests=n_ran_eff, failed_tests=failed_eff, detail=detail,
        )
    finally:
        # (d) ALWAYS restore — catches normal exit, exception, AND
        # KeyboardInterrupt/SystemExit (BaseException). (e) prove the restore.
        try:
            target.write_bytes(original_bytes)
        finally:
            sha_after = _sha256_file(target)
            if sha_after != sha_before:
                raise RestoreIntegrityError(
                    f"RESTORE FAILED for {mutant.target}: sha256 before "
                    f"{sha_before} != after {sha_after}. The product source may "
                    f"be CORRUPTED — STOP and `git checkout -- {mutant.target}`."
                )


# ---------------------------------------------------------------------------
# Run-all orchestration (deterministic; pre-flight once, then committed order)
# ---------------------------------------------------------------------------


def run_all(
    mutants: Sequence[Mutant],
    repo: Path = _REPO,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    only: str | None = None,
) -> list[MutantResult]:
    """Run every mutant (or just ``only``) in committed (sorted-id) order, after
    a single pre-flight clean-tree guard over ALL distinct targets. Deterministic:
    no randomness, fixed order, fixed selectors."""
    selected = [m for m in mutants if (only is None or m.id == only)]
    if only is not None and not selected:
        raise ValueError(f"--only {only!r} matched no mutant")
    assert_clean_tree({m.target for m in selected}, repo)
    return [run_mutant(m, repo, timeout_s) for m in selected]


# ---------------------------------------------------------------------------
# Reporting — fake_gates.json (machine) + human summary; path:line contract
# ---------------------------------------------------------------------------


def results_to_payload(results: Sequence[MutantResult]) -> dict[str, Any]:
    """Deterministic machine payload for ``fake_gates.json``. No wall-clock field
    (so a two-run diff is empty); sorted by mutant id. ``findings`` lists the
    survived + no-tests outcomes first-class for CI."""
    by_outcome: dict[str, int] = {}
    for r in results:
        by_outcome[r.outcome] = by_outcome.get(r.outcome, 0) + 1
    findings = [r for r in results if r.is_finding()]
    killed = by_outcome.get("killed", 0)
    survived = by_outcome.get("survived", 0)
    denom = killed + survived
    kill_rate = round(killed / denom, 4) if denom else None
    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "summary": {
            "total": len(results),
            "killed": killed,
            "survived": survived,
            "no_tests": by_outcome.get("no-tests", 0),
            "anchor_stale": by_outcome.get("anchor-stale", 0),
            "timed_out": by_outcome.get("timed-out", 0),
            "clean_run_timeout": by_outcome.get("clean-run-timeout", 0),
            "kill_rate": kill_rate,
        },
        "findings": [
            {
                "id": r.id,
                "outcome": r.outcome,
                "path_line": r.path_line,
                "op": r.op,
                "rationale": r.rationale,
                "selector": list(r.selector),
            }
            for r in sorted(findings, key=lambda x: x.id)
        ],
        "results": [
            {
                "id": r.id,
                "outcome": r.outcome,
                "path_line": r.path_line,
                "op": r.op,
                "n_tests": r.n_tests,
                "failed_tests": list(r.failed_tests),
                "selector": list(r.selector),
                "rationale": r.rationale,
                "detail": r.detail,
            }
            for r in sorted(results, key=lambda x: x.id)
        ],
    }


def dumps_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def render_report(results: Sequence[MutantResult]) -> str:
    """Human summary. Findings (survived + no-tests) FIRST, in the path:line
    contract mirroring tools/lint/serve_invariants_check.py, with rationale + the
    failed-to-catch selector."""
    payload = results_to_payload(results)
    s = payload["summary"]
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("FAKE-GATE DETECTOR — bounded mutation-lite (read-the-findings-first)")
    lines.append("=" * 78)
    lines.append(
        f"total {s['total']}  |  killed {s['killed']}  survived {s['survived']}  "
        f"no-tests {s['no_tests']}  anchor-stale {s['anchor_stale']}  "
        f"timed-out {s['timed_out']}  clean-run-timeout {s['clean_run_timeout']}"
    )
    kr = s["kill_rate"]
    lines.append(
        f"kill-rate (killed / (killed+survived)): "
        f"{f'{kr * 100:.1f}%' if kr is not None else 'n/a (no killed+survived)'}"
    )
    lines.append("")
    findings = [r for r in results if r.is_finding()]
    if findings:
        lines.append("FINDINGS (fake gates + unguarded load-bearing lines) — fix these:")
        _finding_tags = {
            "survived": "FAKE GATE",
            "no-tests": "NO TESTS",
            "clean-run-timeout": "UNADJUDICATED (clean re-run timed out — review)",
        }
        for r in sorted(findings, key=lambda x: x.id):
            tag = _finding_tags.get(r.outcome, r.outcome.upper())
            lines.append(f"  {r.path_line}: {tag} [{r.id} op={r.op}]")
            lines.append(f"      rationale : {r.rationale}")
            lines.append(f"      selector  : {' '.join(r.selector)}  (did NOT catch it)")
        lines.append("")
    else:
        lines.append("NO FINDINGS. (On a suite the autopsy calls diseased, zero")
        lines.append("findings is SUSPECT — re-examine the seed set + kill detection.)")
        lines.append("")
    lines.append("ALL MUTANTS (committed order):")
    for r in sorted(results, key=lambda x: x.id):
        lines.append(
            f"  [{r.outcome:>12}] {r.id:<28} {r.path_line}  "
            f"(op={r.op}, n_tests={r.n_tests})"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Baseline — MIRRORS tools/lints/cli_with_baseline.py capture/enforce/stale
# ---------------------------------------------------------------------------


@dataclass(frozen=True, order=True)
class FindingKey:
    """Minimal tuple identifying "the same fake gate". Sortable for a clean,
    diff-stable baseline file. Mirrors tools/lints/baseline.ViolationKey
    (path/line/kind) — here ``kind`` is the finding outcome (survived / no-tests /
    clean-run-timeout) and the mutant ``id`` pins WHICH load-bearing line so a
    re-anchored mutant on a different line is a distinct entry."""

    id: str
    path_line: str
    kind: str  # the outcome: "survived" | "no-tests" | "clean-run-timeout"


def _finding_keys(results: Sequence[MutantResult]) -> list[FindingKey]:
    return sorted(
        FindingKey(id=r.id, path_line=r.path_line, kind=r.outcome)
        for r in results
        if r.is_finding()
    )


def _rationale_of(results: Sequence[MutantResult], key: FindingKey) -> str:
    for r in results:
        if r.id == key.id:
            return r.rationale
    return ""


def write_baseline(
    path: Path, results: Sequence[MutantResult], *, capture_date: str
) -> int:
    """Capture current findings to the baseline JSON. Mirrors
    tools/lints/baseline.write_baseline (schema_version + sorted entries). Each
    grandfathered entry records path:line, rationale, and the capture date so the
    backlog is a VISIBLE to-do, not a hidden free pass."""
    keys = _finding_keys(results)
    payload = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "lint": "fake_gate_detector",
        "captured_at": capture_date,
        "survivors": [
            {
                "id": k.id,
                "path_line": k.path_line,
                "kind": k.kind,
                "rationale": _rationale_of(results, k),
                "captured_at": capture_date,
            }
            for k in keys
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return len(keys)


def load_baseline(path: Path) -> set[FindingKey]:
    """Load grandfathered finding keys. Raises FileNotFoundError if absent (the
    caller maps that to the 'no baseline' usage error, like cli_with_baseline)."""
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise ValueError(
            f"baseline schema_version {data.get('schema_version')!r}; expected "
            f"{BASELINE_SCHEMA_VERSION}. Re-capture with --capture or migrate."
        )
    return {
        FindingKey(id=str(e["id"]), path_line=str(e["path_line"]), kind=str(e["kind"]))
        for e in data.get("survivors", [])
    }


def filter_to_new_only(
    results: Sequence[MutantResult], baseline: set[FindingKey]
) -> list[FindingKey]:
    """Current finding keys NOT in the baseline — the NEW fake gates."""
    return sorted(k for k in _finding_keys(results) if k not in baseline)


def find_stale_baseline_entries(
    results: Sequence[MutantResult], baseline: set[FindingKey]
) -> list[FindingKey]:
    """Baseline entries whose finding is GONE now (the mutant is killed / its
    anchor changed) — the operator can shrink the baseline. Mirrors
    tools/lints/baseline.find_stale_baseline_entries."""
    current = set(_finding_keys(results))
    return sorted(k for k in baseline if k not in current)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _today_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).date().isoformat()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.fake_gate_detector",
        description=(
            "Bounded mutation-lite fake-gate detector. Flips named load-bearing "
            "lines and reports whether ≥1 targeting test catches each. A survivor "
            "(or a no-tests selector) is a FAKE GATE — the finding."
        ),
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--measure", action="store_true",
                      help="run + report; exit 0 (default mode)")
    mode.add_argument("--capture", action="store_true",
                      help="run + write the survivor baseline; exit 0")
    mode.add_argument("--enforce", action="store_true",
                      help="run + exit 1 ONLY on a NEW survivor vs the baseline")
    p.add_argument("--stale", action="store_true",
                   help="(with --enforce) also report baselined survivors now killed")
    p.add_argument("--only", default=None,
                   help="run a single mutant by id")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S,
                   help=f"per-mutant pytest timeout in seconds (default {DEFAULT_TIMEOUT_S})")
    p.add_argument("--mutants-dir", default=str(_MUTANTS_DIR),
                   help="directory of mutants/*.toml (default mutants/)")
    p.add_argument("--baseline-file", default=str(_BASELINE_FILE),
                   help="survivor baseline JSON path")
    p.add_argument("--json-out", default=str(_REPORT_JSON),
                   help="where to write fake_gates.json ('-' for stdout, '' to skip)")
    p.add_argument("--repo", default=str(_REPO),
                   help="repo root (default: parent of tools/)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    mutants = load_mutants(Path(args.mutants_dir))
    results = run_all(mutants, repo=repo, timeout_s=args.timeout, only=args.only)

    # Human report → stderr is wrong for piping; print to stdout (matches the
    # census). The machine JSON goes to --json-out.
    sys.stdout.write(render_report(results))

    payload = results_to_payload(results)
    if args.json_out == "-":
        sys.stdout.write(dumps_payload(payload))
    elif args.json_out:
        Path(args.json_out).write_text(dumps_payload(payload), encoding="utf-8")

    if args.capture:
        baseline_file = Path(args.baseline_file)
        n = write_baseline(baseline_file, results, capture_date=_today_iso())
        print(f"wrote {n} survivor(s) to {baseline_file}", file=sys.stderr)
        return 0

    if args.enforce:
        baseline_file = Path(args.baseline_file)
        try:
            baseline = load_baseline(baseline_file)
        except FileNotFoundError:
            print(f"baseline not found: {baseline_file} (run --capture first)",
                  file=sys.stderr)
            return 2
        new_only = filter_to_new_only(results, baseline)
        for k in new_only:
            print(f"{k.path_line}: NEW fake-gate [{k.id}] ({k.kind})")
        rc = 1 if new_only else 0
        if args.stale:
            stale = find_stale_baseline_entries(results, baseline)
            if stale:
                print(
                    f"\n{len(stale)} stale baseline entr"
                    f"{'y' if len(stale) == 1 else 'ies'} "
                    f"(now killed — baseline can shrink):",
                    file=sys.stderr,
                )
                for k in stale:
                    print(f"  - {k.path_line} [{k.id}] {k.kind}", file=sys.stderr)
                rc = max(rc, 1)
        if new_only:
            print(
                f"\n{len(new_only)} NEW fake-gate(s) since baseline "
                f"({baseline_file.name})",
                file=sys.stderr,
            )
        return rc

    # --measure (default): the detector REPORTS; exit 0.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
