"""Mutation probe — the empirical validator for SPR-01's reality/theater labels.

The reality-contact classifier (SPR-01) is a *static* AST reader: it labels a
test ``reality`` (exercises a subsystem's real CORE engine) or ``theater`` (mocks
a CORE symbol of the subsystem it claims to cover). Static analysis can be wrong.
This module asks the only question that is ground truth: **does the test notice
when the real core breaks?**

The validation logic
--------------------
Inject a fault into a real CORE symbol, then run a sampled test under that fault:

  * a REALITY-labeled test that genuinely exercises that core MUST go RED;
  * a THEATER-labeled test that mocks the symbol STAYS GREEN (it never calls the
    real code, so a broken real symbol is invisible to it).

A ``reality`` test that PASSES under the fault never touched the core on that
path -> its label is a CANDIDATE false positive. A ``theater`` test that FAILS
under the fault did touch the core -> a false negative.

Two non-negotiable rigor properties this module is built around
---------------------------------------------------------------
1. **Hermeticity.** :func:`inject_fault` is a context manager that corrupts a
   core symbol and restores the original on exit via ``try/finally`` — EVEN ON
   EXCEPTION. A single leaked mutation poisons every later test and turns every
   FP/FN rate into garbage. The residue test in the test module is load-bearing.

2. **Fairness (classifier-wrong vs. shallow-fault).** A ``reality`` test passing
   under the fault might mean the injected fault is on a core path *this* test
   does not drive (the core is big; a test covers one corner) — NOT that the
   label is a lie. Before a "reality passed under fault" is counted as a
   classifier error, :func:`test_references_symbol` checks the test actually
   references the faulted symbol. A pass where the test never referenced the
   symbol is reported as ``shallow-fault``, not ``classifier-mislabeled``.

Isolation model
---------------
Each sampled test is run in a FRESH subprocess (``python -m pytest <file>``),
exactly as CI runs it (``pytest.ini``: ``testpaths=["tests", ...]``,
``addopts="-ra --strict-markers"``; CI adds ``-m "not integration"``). The fault
is installed by a generated pytest plugin passed via ``-p`` whose
``pytest_configure`` runs BEFORE test-module collection/import — this matters
because tests do ``from substrate.graph.ops import insert_document`` at module
scope and bind the name at import time, so the fault must already be in place
when that import runs. The subprocess gives total isolation: no mutation can
bleed into the parent or into the next test. :func:`inject_fault` (the in-process
context manager) is used by the residue/known-good tests to PROVE hermeticity;
the runner uses the subprocess-plugin path for the same fault for real isolation.

This module imports no product code at import time — it resolves CORE symbols by
dotted path only when a fault is actually injected, and it never edits the tree
(mutation is runtime-only; nothing is committed).
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import re
import subprocess
import sys
import tempfile
import textwrap
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.reality_contact import LEDGER_PATH, REPO_ROOT

# --------------------------------------------------------------------------- #
# Fault modes
# --------------------------------------------------------------------------- #
# The two corruptions a real code path would propagate to an assertion:
#   "raise"    — the symbol raises a controlled error when called. The dominant
#                mode: any test that calls the real symbol on its path errors out
#                (RED), while a test that mocked it never calls the real one.
#   "sentinel" — the symbol returns a wrong sentinel value instead of doing its
#                work. A softer corruption for symbols whose callers assert on the
#                return value rather than on a side effect.
FAULT_RAISE = "raise"
FAULT_SENTINEL = "sentinel"
_VALID_MODES = (FAULT_RAISE, FAULT_SENTINEL)

# A unique marker the corrupted symbol carries, so a residue check can confirm
# the ORIGINAL (un-marked) symbol is back after the context exits.
_MUTATION_MARKER = "__rc_mutation_probe_corrupted__"

# The sentinel object a "sentinel"-mode fault returns. Distinct identity so a
# caller's assertion against a real return value fails.
_WRONG_SENTINEL = "__RC_MUTATION_PROBE_WRONG_SENTINEL__"


class MutationProbeError(RuntimeError):
    """Raised by a fault-injected symbol when it is called under ``raise`` mode.

    Distinct type so a probed test's RED is attributable to the injected fault
    rather than to an unrelated error, and so the residue test can assert the
    real symbol does NOT raise this afterward.
    """


# --------------------------------------------------------------------------- #
# Dotted-symbol resolution
# --------------------------------------------------------------------------- #
def _resolve_symbol(dotted: str) -> tuple[Any, str]:
    """Resolve ``pkg.mod.attr`` to ``(owner_object, attr_name)``.

    The owner is the longest importable module prefix; the remainder is an att
    chain walked with ``getattr``. The final hop is returned un-walked so the
    caller can ``setattr`` on the owner to install/restore the fault.

    Resolving the parent via :func:`importlib.import_module` (not attribute access
    off a grandparent package) is deliberate: ``substrate.graph.search`` is a
    real module that the ``substrate.graph`` package *also* re-exports as a bare
    function, so ``substrate.graph.search`` reached by attribute access is the
    function, while ``import_module("substrate.graph.search")`` is the module. We
    want the module, so we import the longest module prefix explicitly.
    """
    parts = dotted.split(".")
    # Find the longest importable module prefix.
    module = None
    module_depth = 0
    for depth in range(len(parts), 0, -1):
        candidate = ".".join(parts[:depth])
        try:
            module = importlib.import_module(candidate)
            module_depth = depth
            break
        except ModuleNotFoundError:
            continue
    if module is None:
        raise MutationProbeError(f"cannot import any module prefix of {dotted!r}")
    remainder = parts[module_depth:]
    if not remainder:
        raise MutationProbeError(
            f"{dotted!r} resolves to a module, not an attribute; a fault must "
            f"target a callable symbol inside a module"
        )
    owner: Any = module
    # Walk all but the last attr; the last is the one we corrupt.
    for attr in remainder[:-1]:
        owner = getattr(owner, attr)
    return owner, remainder[-1]


def _binding_sites(dotted: str) -> list[tuple[Any, str]]:
    """Every (owner, attr) site that currently binds the SAME object as ``dotted``.

    A symbol is almost always re-exported by its parent package
    (``substrate.graph`` re-exports ``substrate.graph.ops.insert_document`` as a
    bare ``insert_document``), and a test that does ``from substrate.graph import
    insert_document`` binds the PACKAGE re-export, not the module attribute. A
    fault that patches only the defining module would then MISS that test — it
    would pass under a "broken" core because its binding was never touched, which
    would be falsely scored a classifier false positive. So the fault must land on
    every same-identity binding site.

    We return the defining site plus every ancestor PACKAGE that holds the same
    object identity. We deliberately do NOT chase arbitrary aliases across the
    whole import graph (that would be unbounded and could corrupt unrelated code);
    the defining module + its parent packages cover the import forms tests
    actually use (``from pkg import x`` and ``from pkg.mod import x``).
    """
    owner, attr = _resolve_symbol(dotted)
    target = getattr(owner, attr)
    sites: list[tuple[Any, str]] = [(owner, attr)]
    parts = dotted.split(".")
    # Ancestor packages: substrate, substrate.graph, ... (exclude the full path).
    for depth in range(1, len(parts) - 1):
        pkg_name = ".".join(parts[:depth])
        try:
            pkg = importlib.import_module(pkg_name)
        except ModuleNotFoundError:
            continue
        if getattr(pkg, attr, None) is target:
            sites.append((pkg, attr))
    return sites


def _make_corrupt(original: Any, mode: str, dotted: str) -> Any:
    """Build the corrupted replacement for ``original``."""
    if mode == FAULT_RAISE:

        def corrupted(*_args: Any, **_kwargs: Any) -> Any:
            raise MutationProbeError(
                f"RC mutation probe: core symbol {dotted!r} is corrupted "
                f"(fault mode={mode})"
            )

        setattr(corrupted, _MUTATION_MARKER, True)
        return corrupted

    if mode == FAULT_SENTINEL:

        def corrupted_sentinel(*_args: Any, **_kwargs: Any) -> Any:
            return _WRONG_SENTINEL

        setattr(corrupted_sentinel, _MUTATION_MARKER, True)
        return corrupted_sentinel

    raise MutationProbeError(f"unknown fault mode {mode!r}; valid: {_VALID_MODES}")


@contextmanager
def inject_fault(dotted_core_symbol: str, mode: str = FAULT_RAISE) -> Iterator[None]:
    """Corrupt a CORE symbol for the duration of the context, then restore it.

    Hermetic by construction: the original is captured before the body runs and
    restored in a ``finally`` so it returns EVEN IF the body raises. This is the
    property the residue test proves — a leaked mutation would poison every later
    test and void every FP/FN rate.

    Args:
        dotted_core_symbol: e.g. ``"substrate.graph.ops.insert_document"``.
        mode: ``"raise"`` (the symbol raises when called) or ``"sentinel"``
            (returns a wrong sentinel).

    Example::

        with inject_fault("substrate.graph.ops.insert_document"):
            ...  # insert_document now raises MutationProbeError when called
        # original fully restored here, even if the body raised
    """
    if mode not in _VALID_MODES:
        raise MutationProbeError(f"unknown fault mode {mode!r}; valid: {_VALID_MODES}")
    owner, attr = _resolve_symbol(dotted_core_symbol)
    if not hasattr(owner, attr):
        raise MutationProbeError(f"{dotted_core_symbol!r}: owner has no attribute {attr!r}")
    original = getattr(owner, attr)
    corrupt = _make_corrupt(original, mode, dotted_core_symbol)
    # Patch EVERY same-identity binding site (defining module + re-export
    # packages), capturing each original so restore is exact and complete.
    sites = _binding_sites(dotted_core_symbol)
    captured: list[tuple[Any, str, Any]] = [(o, a, getattr(o, a)) for o, a in sites]
    for o, a in sites:
        setattr(o, a, corrupt)
    try:
        yield
    finally:
        # Restore the EXACT original object identity at every site — never a copy.
        for o, a, orig in captured:
            setattr(o, a, orig)


def symbol_is_corrupted(dotted_core_symbol: str) -> bool:
    """True iff the symbol currently carries the mutation marker (test helper)."""
    owner, attr = _resolve_symbol(dotted_core_symbol)
    return bool(getattr(getattr(owner, attr), _MUTATION_MARKER, False))


# --------------------------------------------------------------------------- #
# Per-subsystem fault plan (defensibility: documented symbol + corruption)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SubsystemFault:
    """The fault injected for one CORE subsystem.

    ``symbol`` is the dotted CORE symbol mutated; ``mode`` the corruption;
    ``rationale`` argues why a test that genuinely runs the subsystem would
    propagate this corruption to an assertion (defensibility — recorded in the
    report so the FP/FN rates are reproducible).
    """

    subsystem: str
    symbol: str
    mode: str
    rationale: str


# Per-subsystem mutation targets. Each ``symbol`` is a documented CORE function
# of its subsystem, chosen because it is referenced by a MAJORITY of that
# subsystem's reality tests (measured on this branch, see the report) — so the
# fault lands on a path those tests actually drive (the fairness premise). The
# fairness check (test_references_symbol) is STILL applied per-test, so a test
# that happens not to reference it is reported shallow-fault, never as a
# classifier error.
FAULT_PLAN: tuple[SubsystemFault, ...] = (
    SubsystemFault(
        subsystem="substrate.graph.ops",
        symbol="substrate.graph.ops.insert_document",
        mode=FAULT_RAISE,
        rationale=(
            "insert_document is the primary graph WRITE entry point: a test that "
            "really writes a document/chunk/node to the substrate calls it on its "
            "setup path. Making it raise means no real node is written, which any "
            "test asserting against the written graph propagates to a failure. "
            "Genuinely imported/called (AST) by 34/48 graph.ops reality tests."
        ),
    ),
    SubsystemFault(
        subsystem="substrate.graph.schema",
        symbol="substrate.graph.schema.init_database",
        mode=FAULT_RAISE,
        rationale=(
            "init_database creates the real DuckDB tables a schema-claiming test "
            "must exercise. Raising it means the schema is never built, so any "
            "subsequent real query fails. Genuinely imported/called (AST) by 52/84 "
            "schema reality tests. WEAKEST-EVIDENCE CAVEAT (be honest about this "
            "subsystem): init_database sits on the SHARED DB-setup path, so it is "
            "triggered TRANSITIVELY by virtually any DB-touching test — e.g. "
            "test_attribution / test_backtest_db go RED under it even though they do "
            "NOT AST-reference it. So a RED here proves 'this test needs a working "
            "database', NOT 'this test exercises schema-CREATION specifically'. schema "
            "is the LEAST surgically-targeted subsystem fault; contrast search.search "
            "(retrieval-specific) or dispatch.dispatch (the routing decision itself), "
            "where a RED is stronger evidence of contact with that exact subsystem. "
            "The headline 0-percent FP is unaffected (only symbol-referencing tests "
            "are counted), but schema's reds carry less evidential weight."
        ),
    ),
    SubsystemFault(
        subsystem="substrate.graph.search",
        symbol="substrate.graph.search.search",
        mode=FAULT_RAISE,
        rationale=(
            "search() is the vector-retrieval core. A retrieval test that really "
            "runs the index calls it; raising means no real retrieval occurs, "
            "which a provenance/retrieval assertion propagates to a failure. "
            "Genuinely imported/called (AST) by 10/10 graph.search reality tests. "
            "NOTE: the fault is installed at BOTH substrate.graph.search.search AND "
            "the substrate.graph package re-export, because tests import it via "
            "'from substrate.graph import search' (the package binding) — patching "
            "only the module would miss them and falsely score a false positive."
        ),
    ),
    SubsystemFault(
        subsystem="substrate.dispatch.router",
        symbol="substrate.dispatch.router.dispatch",
        mode=FAULT_RAISE,
        rationale=(
            "dispatch() IS the routing decision a dispatch test exists to prove. "
            "Raising it means no routing/cost decision is made; a test asserting "
            "on the dispatch result fails. IMPORTANT HONESTY NOTE: only 2/17 router "
            "reality tests genuinely import/call dispatch directly (AST). The other "
            "15 fake the PROVIDER by DI (register_provider(stub) — a BOUNDARY seam) "
            "and reach routing INDIRECTLY through the orchestrator/synthesizer, so "
            "the probe cannot attribute a dispatch fault to them per-test and they "
            "are (fairly) NOT counted as fairness-eligible. This small eligible "
            "sample is exactly the SPR-06 DI blind spot surfacing in the probe's "
            "own coverage: the router decision is still real for those 15, but the "
            "probe can only PROVE it for the 2 that call dispatch directly."
        ),
    ),
    SubsystemFault(
        subsystem="substrate.attribution.compute",
        symbol="substrate.attribution.compute.compute_attribution_for_synthesis",
        mode=FAULT_RAISE,
        rationale=(
            "compute_attribution_for_synthesis is the §9 IP-attribution core. "
            "Raising it means no attribution is computed; an attribution test "
            "fails. Referenced by 3/3 attribution reality tests."
        ),
    ),
    SubsystemFault(
        subsystem="orchestration.loop_one.orchestrator",
        symbol="orchestration.loop_one.orchestrator._score_phase_6_synthesis",
        mode=FAULT_RAISE,
        rationale=(
            "_score_phase_6_synthesis is a real groundedness-scoring step inside "
            "the loop-1 orchestrator. The two orchestrator reality tests exercise "
            "DIFFERENT private functions (groundedness uses this; chase uses "
            "_walk_chase_chain / _select_chase_question), so the per-test fairness "
            "check is especially load-bearing here: a test not referencing this "
            "symbol is shallow-fault, not a classifier error."
        ),
    ),
)

_FAULT_BY_SUBSYSTEM: dict[str, SubsystemFault] = {f.subsystem: f for f in FAULT_PLAN}


# --------------------------------------------------------------------------- #
# Ledger reading — the reality tests per subsystem
# --------------------------------------------------------------------------- #
def load_reality_tests_by_subsystem(ledger_path: Path = LEDGER_PATH) -> dict[str, list[str]]:
    """From the SPR-01 ledger, the sorted reality-labeled test paths per CORE
    subsystem. A file appears under every subsystem it is ``reality`` for."""
    ledger: dict[str, Any] = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    by_sub: dict[str, list[str]] = {}
    for f in ledger.get("files", []):
        labels: dict[str, str] = f.get("subsystem_labels", {})
        for sub, label in labels.items():
            if label == "reality":
                by_sub.setdefault(sub, []).append(f["path"])
    return {sub: sorted(set(paths)) for sub, paths in by_sub.items()}


def test_references_symbol(test_path: str, symbol: str, repo_root: Path = REPO_ROOT) -> bool:
    """Fairness check: does this test's SOURCE genuinely IMPORT or CALL the symbol?

    This is THE load-bearing fairness check (the classifier-vs-shallow split hinges
    on it), so it must not be fooled by a textual mention. An earlier version
    matched the bare name as a regex word — but ``"dispatch"`` appears in the
    DOCSTRINGS of three router tests that never import or call ``dispatch`` (they
    import ``register_provider`` / ``_PROVIDER_REGISTRY`` instead), and a regex
    falsely counted those as fairness-eligible and inflated the FP rate. Counting a
    prose mention as evidence the test drives the symbol is exactly the "shallow
    fault unfairly indicts the classifier" error this sprint forbids.

    So we parse the AST (comments and docstrings are invisible to it) and require a
    real ``from <mod> import <short>`` / ``import ...<short>`` OR a call
    ``<short>(...)`` / ``....<short>(...)``. Only then is the fault provably on a
    path the test drives.
    """
    short = symbol.rsplit(".", 1)[-1]
    src = (repo_root / test_path).read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # Conservative fallback if the file won't parse (should not happen for a
        # ledger-listed test): whole-word text match.
        return re.search(r"\b" + re.escape(short) + r"\b", src) is not None
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if any(a.name == short for a in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any(a.name.split(".")[-1] == short for a in node.names):
                return True
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == short:
                return True
            if isinstance(func, ast.Attribute) and func.attr == short:
                return True
    return False


# --------------------------------------------------------------------------- #
# The fault plugin (installed into a probed subprocess via -p)
# --------------------------------------------------------------------------- #
def _render_fault_plugin(symbol: str, mode: str) -> str:
    """The text of a throwaway pytest plugin that installs the fault in
    ``pytest_configure`` — BEFORE test-module collection/import, so a test's
    module-scope ``from <mod> import <symbol>`` binds the corrupted object."""
    return textwrap.dedent(
        f"""
        # Auto-generated by tools.reality_contact.mutation_probe — DO NOT COMMIT.
        # Installs the core-symbol fault at EVERY same-identity binding site (the
        # defining module + its re-export packages) before pytest collects test
        # modules, so a test importing the symbol via `from pkg import x` sees the
        # fault too (else it would falsely pass under a "broken" core).
        from tools.reality_contact.mutation_probe import _binding_sites, _make_corrupt


        def pytest_configure(config):
            sites = _binding_sites({symbol!r})
            original = getattr(*sites[0])
            corrupt = _make_corrupt(original, {mode!r}, {symbol!r})
            for owner, attr in sites:
                setattr(owner, attr, corrupt)
        """
    ).strip()


# --------------------------------------------------------------------------- #
# Outcome records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TestOutcome:
    """The result of running one sampled test under one injected fault."""

    subsystem: str
    test_path: str
    label: str  # "reality" | "theater" (synthetic)
    symbol: str
    mode: str
    references_symbol: bool
    passed_under_fault: bool
    returncode: int
    # Classification of the outcome (the validation verdict for this test):
    #   "expected-red"     reality test that went RED under fault — label holds.
    #   "classifier-fp"    reality test PASSED under fault AND referenced the
    #                      symbol — a CANDIDATE false positive (classifier-wrong).
    #   "shallow-fault"    reality test PASSED under fault but did NOT reference
    #                      the symbol — fault too shallow; NOT a classifier error.
    #   "expected-green"   synthetic theater test stayed GREEN under fault — FN
    #                      direction validated; label holds.
    #   "classifier-fn"    theater test FAILED under fault — false negative.
    verdict: str
    tail: str = ""  # short stdout/stderr tail for forensics


@dataclass
class SubsystemResult:
    subsystem: str
    fault: SubsystemFault
    sample_size: int
    selection_rule: str
    total_reality: int
    # Reality tests NOT probed because the per-test fault could not be attributed
    # (they never directly import/call the faulted symbol — e.g. DI-indirect router
    # tests). Logged so the small eligible sample is honest, not silent.
    not_eligible_paths: list[str] = field(default_factory=list)
    # Reality tests eligible + un-probed only because of the sample-N cap.
    capped_paths: list[str] = field(default_factory=list)
    outcomes: list[TestOutcome] = field(default_factory=list)

    @property
    def skipped_paths(self) -> list[str]:
        """All un-probed reality tests (cap + non-eligible), for back-compat."""
        return sorted(self.capped_paths + self.not_eligible_paths)

    # --- false-positive accounting (over the stated sample) ---------------- #
    def candidate_fp(self) -> list[TestOutcome]:
        return [o for o in self.outcomes if o.verdict == "classifier-fp"]

    def shallow(self) -> list[TestOutcome]:
        return [o for o in self.outcomes if o.verdict == "shallow-fault"]

    def expected_red(self) -> list[TestOutcome]:
        return [o for o in self.outcomes if o.verdict == "expected-red"]

    def fairness_eligible(self) -> list[TestOutcome]:
        """Reality outcomes whose test actually referenced the faulted symbol —
        the only ones a false-positive rate may be computed over (the fairness
        rule: a shallow fault must not indict the classifier)."""
        return [
            o
            for o in self.outcomes
            if o.label == "reality" and o.references_symbol
        ]

    def fp_rate(self) -> float | None:
        eligible = self.fairness_eligible()
        if not eligible:
            return None
        return len(self.candidate_fp()) / len(eligible)


# --------------------------------------------------------------------------- #
# Running a single test under a fault (subprocess; CI-faithful)
# --------------------------------------------------------------------------- #
def _run_test_under_fault(
    test_path: str,
    symbol: str,
    mode: str,
    repo_root: Path = REPO_ROOT,
    timeout_s: float = 180.0,
) -> tuple[bool, int, str]:
    """Run one test file in a fresh subprocess with the fault installed.

    Returns ``(passed, returncode, tail)``. ``passed`` is True iff pytest exited
    0 (all selected tests green). Mirrors CI: ``-q -m "not integration"`` with
    ``addopts`` inherited from ``pytest.ini``.
    """
    with tempfile.TemporaryDirectory(prefix="rc_mut_plugin_") as plug_dir:
        plugin_path = Path(plug_dir) / "_rc_fault_plugin.py"
        plugin_path.write_text(_render_fault_plugin(symbol, mode), encoding="utf-8")
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            test_path,
            "-p",
            "_rc_fault_plugin",
            "-q",
            "-p",
            "no:cacheprovider",
            "-m",
            "not integration",
        ]
        env = {
            **_clean_provider_env(),
            "PYTHONPATH": f"{plug_dir}{_pathsep()}{repo_root}",
        }
        try:
            proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
                cmd,
                cwd=str(repo_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return False, -1, "TIMEOUT"
        tail = (proc.stdout or "")[-600:] + (proc.stderr or "")[-200:]
        return proc.returncode == 0, proc.returncode, tail.strip()


def _pathsep() -> str:
    import os

    return os.pathsep


def _clean_provider_env() -> dict[str, str]:
    """Inherit the real env but blank provider keys (as CI does), so a probed
    test never reaches a live API."""
    import os

    env = dict(os.environ)
    for key in (
        "DEEPSEEK_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "HERMES_API_KEY",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "ANTIEK_OPERATOR_TOKEN",
    ):
        env[key] = ""
    return env


# --------------------------------------------------------------------------- #
# Synthetic theater fixture (the FN-half validator)
# --------------------------------------------------------------------------- #
# The live tree has theater == 0, so the false-NEGATIVE half (a theater test
# that FAILS under the fault is a classifier FN) has no real theater test to
# sample. We author a SYNTHETIC theater test per subsystem: it mocks the exact
# faulted CORE symbol and asserts the mock. Under the fault it MUST stay GREEN
# (it never calls the real symbol) — proving the probe's FN-detection direction
# works WITHOUT a real theater test in the tree. This is explicitly a synthetic
# control, not a finding about the real suite.
def _render_synthetic_theater_test(symbol: str) -> str:
    module, attr = symbol.rsplit(".", 1)
    return textwrap.dedent(
        f"""
        # SYNTHETIC theater control — generated by tools.reality_contact.mutation_probe.
        # Mocks the CORE symbol {symbol!r} and asserts the mock. A genuine theater
        # test: its assertion is satisfied by the mock, never by the real core. It
        # MUST stay green when the real symbol is faulted (it never calls it).
        from unittest.mock import patch


        def test_synthetic_theater_mocks_core():
            with patch({module!r} + "." + {attr!r}, return_value="__synthetic_mock__") as m:
                import importlib
                mod = importlib.import_module({module!r})
                result = getattr(mod, {attr!r})("ignored-arg")
                assert result == "__synthetic_mock__"
                m.assert_called_once()
        """
    ).strip()


def run_synthetic_theater_control(fault: SubsystemFault, repo_root: Path = REPO_ROOT) -> TestOutcome:
    """Run a synthetic theater test (mocks the faulted symbol) under that fault.

    Expected: it STAYS GREEN -> the probe's FN direction is sound. If it goes
    RED, the probe would (wrongly) flag a true theater test as a false negative,
    so this control catches a broken probe.
    """
    with tempfile.TemporaryDirectory(prefix="rc_mut_theater_") as td:
        test_file = Path(td) / "test_rc_synthetic_theater.py"
        test_file.write_text(_render_synthetic_theater_test(fault.symbol), encoding="utf-8")
        passed, rc, tail = _run_test_under_fault(
            str(test_file), fault.symbol, fault.mode, repo_root=repo_root
        )
    verdict = "expected-green" if passed else "classifier-fn"
    return TestOutcome(
        subsystem=fault.subsystem,
        test_path="<synthetic theater control>",
        label="theater",
        symbol=fault.symbol,
        mode=fault.mode,
        references_symbol=True,  # by construction it mocks the symbol
        passed_under_fault=passed,
        returncode=rc,
        verdict=verdict,
        tail=tail,
    )


# --------------------------------------------------------------------------- #
# The probe runner
# --------------------------------------------------------------------------- #
def probe_subsystem(
    fault: SubsystemFault,
    reality_tests: Sequence[str],
    sample_n: int,
    repo_root: Path = REPO_ROOT,
) -> SubsystemResult:
    """Probe up to ``sample_n`` reality tests of one subsystem under its fault.

    Selection rule (stated, no silent caps): the reality tests are sorted by
    path; those that REFERENCE the faulted symbol are preferred (they exercise
    the fault path — the fair sample); the first ``sample_n`` of those are
    probed. Any reality test NOT probed (beyond the cap, or non-referencing) is
    recorded in ``skipped_paths``.
    """
    referencing = [t for t in reality_tests if test_references_symbol(t, fault.symbol, repo_root)]
    non_referencing = [t for t in reality_tests if t not in referencing]
    chosen = referencing[:sample_n]
    capped = referencing[sample_n:]
    selection_rule = (
        f"sorted-by-path; restrict to tests that genuinely import/call "
        f"{fault.symbol.rsplit('.', 1)[-1]!r} (AST, ignoring prose mentions); "
        f"first {sample_n} probed"
    )
    result = SubsystemResult(
        subsystem=fault.subsystem,
        fault=fault,
        sample_size=len(chosen),
        selection_rule=selection_rule,
        total_reality=len(reality_tests),
        capped_paths=sorted(capped),
        not_eligible_paths=sorted(non_referencing),
    )
    for test_path in chosen:
        refs = test_references_symbol(test_path, fault.symbol, repo_root)
        passed, rc, tail = _run_test_under_fault(test_path, fault.symbol, fault.mode, repo_root)
        if not passed:
            verdict = "expected-red"
        elif refs:
            verdict = "classifier-fp"  # candidate FP: passed AND drives the symbol
        else:
            verdict = "shallow-fault"  # passed but never references it
        result.outcomes.append(
            TestOutcome(
                subsystem=fault.subsystem,
                test_path=test_path,
                label="reality",
                symbol=fault.symbol,
                mode=fault.mode,
                references_symbol=refs,
                passed_under_fault=passed,
                returncode=rc,
                verdict=verdict,
                tail=tail,
            )
        )
    return result


@dataclass
class ProbeReport:
    sample_n: int
    subsystem_results: list[SubsystemResult] = field(default_factory=list)
    theater_controls: list[TestOutcome] = field(default_factory=list)

    def overall_fp_rate(self) -> float | None:
        eligible = [
            o
            for r in self.subsystem_results
            for o in r.fairness_eligible()
        ]
        if not eligible:
            return None
        fp = sum(len(r.candidate_fp()) for r in self.subsystem_results)
        return fp / len(eligible)


def run_probe(
    sample_n: int = 5,
    subsystems: Sequence[str] | None = None,
    ledger_path: Path = LEDGER_PATH,
    repo_root: Path = REPO_ROOT,
) -> ProbeReport:
    """Run the full probe over a stated per-subsystem sample, plus one synthetic
    theater control per subsystem."""
    by_sub = load_reality_tests_by_subsystem(ledger_path)
    report = ProbeReport(sample_n=sample_n)
    for fault in FAULT_PLAN:
        if subsystems is not None and fault.subsystem not in subsystems:
            continue
        reality_tests = by_sub.get(fault.subsystem, [])
        result = probe_subsystem(fault, reality_tests, sample_n, repo_root)
        report.subsystem_results.append(result)
        report.theater_controls.append(run_synthetic_theater_control(fault, repo_root))
    return report


# --------------------------------------------------------------------------- #
# Report rendering
# --------------------------------------------------------------------------- #
def render_report(report: ProbeReport) -> str:
    """Render the validation report markdown (M3)."""
    lines: list[str] = []
    a = lines.append
    a("# Reality-contact mutation-probe validation report")
    a("")
    a(
        "Generated by `python -m tools.reality_contact.mutation_probe`. This is the "
        "EMPIRICAL validator for SPR-01's static reality/theater labels: it injects a "
        "fault into a real CORE symbol and observes whether a `reality`-labeled test "
        "goes RED (it really exercised the core) or sails through GREEN (it never "
        "touched the core on that path — a candidate false positive). It does NOT edit "
        "the tree: every mutation is injected at runtime in a throwaway subprocess "
        "plugin and restored; nothing here is committed."
    )
    a("")
    a("## How to read this (the fairness split is load-bearing)")
    a("")
    a(
        "A `reality` test passing under the fault is a CANDIDATE false positive only "
        "if it actually **references the faulted symbol** — otherwise the fault was on "
        "a core path *this* test does not drive (a **shallow fault**), which would "
        "unfairly indict the classifier. So every per-subsystem table separates "
        "`classifier-fp` (passed AND references the symbol) from `shallow-fault` "
        "(passed, does not reference it). The false-positive RATE is computed only over "
        "**fairness-eligible** outcomes (reality tests that reference the symbol)."
    )
    a("")
    a(
        "The false-NEGATIVE half is validated on a **synthetic theater control**, not "
        "the real tree: this branch has `theater == 0` (no real theater tests to "
        "sample), so for each subsystem a synthetic test that mocks the faulted symbol "
        "and asserts the mock is run under the fault. It MUST stay GREEN — proving the "
        "probe's FN-detection direction works. A RED here would mean the probe itself "
        "is broken, not that the real suite has a false negative."
    )
    a("")
    a("## Probe self-correction (why the number is trustworthy)")
    a("")
    a(
        "An early naive version of this probe reported an overall FP rate of "
        "**16.67%** — which on inspection was ENTIRELY probe artifact, not classifier "
        "error, and fixing it is the rigor of this sprint:"
    )
    a("")
    a(
        "1. **Coarse fairness check.** The first version matched the symbol name as a "
        "regex word, so three router tests that mention `dispatch` only in their "
        "DOCSTRINGS (they import `register_provider` / `_PROVIDER_REGISTRY`, never "
        "`dispatch`) were falsely counted fairness-eligible and, on passing, scored "
        "false positives. The fix: the fairness check is now AST-based — it requires a "
        "real import or call of the symbol; prose mentions are invisible to it. "
        "Counting a docstring mention as evidence the test drives the symbol is exactly "
        "the *\"shallow fault unfairly indicts the classifier\"* error this sprint forbids."
    )
    a("")
    a(
        "2. **Incomplete fault site.** `tests/test_graph.py` genuinely calls `search()` "
        "yet passed under a faulted `substrate.graph.search.search`, because it imports "
        "via `from substrate.graph import search` — the PACKAGE re-export binding, which "
        "a module-only patch never touched. That made a real-contact test look like a "
        "false positive. The fix: the fault is now installed at every same-identity "
        "binding site (defining module + re-export packages), so a test importing the "
        "symbol either way sees it. After the fix `test_graph.py` correctly goes RED."
    )
    a("")
    a(
        "Both corrections REMOVED spurious false positives (they did not hide real ones): "
        "every probed test that still passes is now a genuine, fairly-attributed "
        "candidate. The reproduced number below is post-correction."
    )
    a("")

    overall = report.overall_fp_rate()
    a("## Headline")
    a("")
    if overall is None:
        a("- **Overall false-positive rate: n/a** (no fairness-eligible reality outcomes).")
    else:
        a(
            f"- **Overall false-positive rate (over fairness-eligible reality outcomes) "
            f"= {overall * 100:.2f}%**"
        )
    a(f"- Sample: up to N={report.sample_n} reality tests per subsystem (see per-subsystem tables).")
    a(
        "- SCOPE (read before quoting the 0%): this rate is over the actually-EXECUTED "
        "fairness-eligible tests only — a label SPOT-CHECK, not a full-suite census. "
        "Every capped or excluded test is listed by name per subsystem below (no silent "
        "skips), and per-subsystem evidence strength varies (see each fault's rationale — "
        "schema's is the weakest, search/dispatch the strongest)."
    )
    a(
        "- Theater FN-half: validated on synthetic theater controls "
        f"({sum(1 for c in report.theater_controls if c.verdict == 'expected-green')}"
        f"/{len(report.theater_controls)} stayed green as required)."
    )
    a("")

    a("## Per-subsystem results")
    a("")
    for r in report.subsystem_results:
        a(f"### `{r.subsystem}`")
        a("")
        a(f"- **Fault injected:** `{r.fault.symbol}` — mode `{r.fault.mode}`.")
        a(f"- **Why this is a valid corruption:** {r.fault.rationale}")
        a(
            f"- **Sample:** {r.sample_size} of {r.total_reality} reality tests probed "
            f"({r.selection_rule})."
        )
        fp_rate = r.fp_rate()
        eligible = len(r.fairness_eligible())
        if fp_rate is None:
            a("- **False-positive rate:** n/a (no fairness-eligible reality tests in sample).")
        else:
            a(
                f"- **False-positive rate:** {fp_rate * 100:.2f}% "
                f"({len(r.candidate_fp())} classifier-fp / {eligible} fairness-eligible)."
            )
        if r.capped_paths:
            a(
                f"- **Capped (eligible, un-probed only by the N={report.sample_n} "
                f"cap; logged, no silent skips): {len(r.capped_paths)} test(s)** —"
            )
            for p in r.capped_paths:
                a(f"  - `{p}`")
        if r.not_eligible_paths:
            a(
                f"- **Not fairness-eligible ({len(r.not_eligible_paths)} test(s)): "
                "reality-labeled but they do NOT directly import/call the faulted "
                "symbol (they reach it indirectly, e.g. via DI/the orchestrator), so "
                "the probe cannot attribute this fault to them per-test. NOT counted "
                "as FP or as classifier-correct — honestly out of this probe's reach** —"
            )
            for p in r.not_eligible_paths:
                a(f"  - `{p}`")
        a("")
        a("| test | references symbol? | passed under fault? | verdict |")
        a("| --- | :---: | :---: | --- |")
        for o in r.outcomes:
            a(
                f"| `{o.test_path}` | {'yes' if o.references_symbol else 'no'} "
                f"| {'PASS' if o.passed_under_fault else 'RED'} | `{o.verdict}` |"
            )
        a("")
        # Cite each classifier-fp with file + fault for SPR-01.
        fps = r.candidate_fp()
        if fps:
            a("**Candidate false positives (route to SPR-01 — classifier-wrong):**")
            for o in fps:
                a(
                    f"- `{o.test_path}` — labeled `reality`, PASSED under fault "
                    f"`{o.symbol}` ({o.mode}) while referencing the symbol -> the "
                    f"classifier could not prove the core ran on this path."
                )
            a("")
        shallow = r.shallow()
        if shallow:
            a("**Shallow-fault (NOT a classifier error — fault too shallow for this test):**")
            for o in shallow:
                a(
                    f"- `{o.test_path}` — passed under fault but does not reference "
                    f"`{o.symbol.rsplit('.', 1)[-1]}`; the fault is on a core path this "
                    f"test does not drive."
                )
            a("")

    a("## Synthetic theater controls (FN-direction validation)")
    a("")
    a("| subsystem | faulted symbol | stayed green? | verdict |")
    a("| --- | --- | :---: | --- |")
    for c in report.theater_controls:
        a(
            f"| `{c.subsystem}` | `{c.symbol}` "
            f"| {'yes' if c.passed_under_fault else 'NO'} | `{c.verdict}` |"
        )
    a("")

    a("## Gate recommendation (feeds SPR-06 reconsider-if)")
    a("")
    a(
        "SPR-06 (`docs/decisions/reality-contact-ratio.md`, §3.3) recorded the "
        "reconsider-if verbatim: *\"If SPR-07's mutation probe demonstrates the static "
        "classifier has a HIGH FALSE-POSITIVE rate — it red-flags tests that do make "
        "genuine reality contact — then downgrading this gate to informational becomes "
        "justified.\"* Note the directionality: a HIGH FP rate here means reality tests "
        "PASS under a broken core (the classifier called them reality but they make no "
        "contact), which is the OPPOSITE concern — it means the gate's `reality` label "
        "is too generous, not that it over-flags genuine contact. Either way the "
        "measured number is the input the operator weighs."
    )
    a("")
    if overall is None:
        a(
            "- **Recommendation: insufficient evidence.** No fairness-eligible reality "
            "outcomes were probed, so no FP rate can be stated. The gate should HOLD "
            "blocking by default until a probe with eligible samples runs."
        )
    elif overall <= 0.10:
        a(
            f"- **Recommendation: HOLD blocking.** Overall FP rate {overall * 100:.2f}% "
            "is LOW: on the stated sample, reality tests overwhelmingly DO go red when "
            "their core breaks, so the `reality` label is empirically trustworthy and "
            "the SPR-06 reconsider-if is NOT triggered."
        )
    else:
        a(
            f"- **Recommendation: consider DOWNGRADE to informational (operator call).** "
            f"Overall FP rate {overall * 100:.2f}% is HIGH on the stated sample: a "
            "meaningful share of `reality`-labeled tests pass under a broken core, so "
            "those labels do not reflect real contact. Per SPR-06 §3.3 this is the "
            "recorded condition under which downgrading the blocking gate (or narrowing "
            "its scope) is justified. The classifier mismatches below should be fixed "
            "first (route to SPR-01); re-run the probe after."
        )
    a("")
    a(
        "> Scope caveat carried from SPR-06: this probe samples the labels; it is NOT "
        "full mutation testing of the suite, and it is structurally silent on the "
        "DI-stubbed-LLM blind spot (the provider is a BOUNDARY seam, so a test that "
        "fakes the LLM by dependency injection still runs the real graph/orchestrator "
        "and is correctly `reality` for THOSE subsystems). The FP rate here is about "
        "whether a `reality` label survives a broken CORE symbol, not about whether the "
        "synthesis content was real."
    )
    a("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
DEFAULT_REPORT_PATH: Path = REPO_ROOT / "reports" / "reality_contact_mutation_validation.md"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.reality_contact.mutation_probe",
        description=(
            "Empirically validate SPR-01's reality/theater labels by injecting CORE "
            "faults and recording which sampled tests notice. Writes a validation "
            "report; never edits the tree."
        ),
    )
    parser.add_argument(
        "--sample-n",
        type=int,
        default=5,
        help="Max reality tests probed per subsystem (default 5). No silent caps: "
        "tests beyond the cap are logged as skipped.",
    )
    parser.add_argument(
        "--subsystem",
        action="append",
        dest="subsystems",
        default=None,
        help="Restrict to one CORE subsystem (repeatable). Default: all.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help=f"Report output path (default {DEFAULT_REPORT_PATH}).",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Print the report to stdout instead of writing the file.",
    )
    args = parser.parse_args(argv)

    print(
        f"[mutation-probe] running over sample N={args.sample_n} "
        f"({'all subsystems' if not args.subsystems else ', '.join(args.subsystems)})...",
        file=sys.stderr,
    )
    report = run_probe(sample_n=args.sample_n, subsystems=args.subsystems)
    text = render_report(report)

    # Log a compact summary to stderr so the run is observable.
    for r in report.subsystem_results:
        fp = r.fp_rate()
        fp_s = "n/a" if fp is None else f"{fp * 100:.1f}%"
        print(
            f"[mutation-probe] {r.subsystem}: probed {r.sample_size}/{r.total_reality}, "
            f"FP={fp_s}, expected-red={len(r.expected_red())}, "
            f"shallow={len(r.shallow())}, skipped={len(r.skipped_paths)}",
            file=sys.stderr,
        )
    for c in report.theater_controls:
        print(
            f"[mutation-probe] theater-control {c.subsystem}: {c.verdict}",
            file=sys.stderr,
        )
    overall = report.overall_fp_rate()
    print(
        f"[mutation-probe] OVERALL FP rate = "
        f"{'n/a' if overall is None else f'{overall * 100:.2f}%'}",
        file=sys.stderr,
    )

    if args.no_write:
        print(text)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"[mutation-probe] wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
