"""Tests for the reality-contact mutation probe (SPR-07).

The probe is only trustworthy if two properties hold, and BOTH are asserted here:

1. **Hermeticity (M1, load-bearing).** :func:`inject_fault` restores the
   original CORE symbol on exit — EVEN when the wrapped body raises. The residue
   test injects, exits via a raised exception, then asserts a known-real function
   works normally afterward. A single leaked mutation would poison every later
   test and turn every FP/FN rate into garbage.

2. **The probe itself works (known-good sanity, M3).** A clearly-`reality` test
   goes RED under the injected fault, and a synthetic-theater test (mocks the
   faulted symbol) stays GREEN. If the probe couldn't tell these apart it would
   measure nothing.

These tests are themselves `reality` by the classifier's own definition: they
import and exercise the real probe module and mock nothing on a core path. The
subprocess-based sanity tests are marked `slow`-friendly but kept tiny (one test
file each) so the suite stays fast.
"""

from __future__ import annotations

import importlib

import pytest

from tools.reality_contact import REPO_ROOT
from tools.reality_contact.mutation_probe import (
    FAULT_PLAN,
    FAULT_RAISE,
    FAULT_SENTINEL,
    MutationProbeError,
    SubsystemFault,
    _make_corrupt,
    _render_fault_plugin,
    _resolve_symbol,
    inject_fault,
    load_reality_tests_by_subsystem,
    probe_subsystem,
    render_report,
    run_synthetic_theater_control,
    symbol_is_corrupted,
)
from tools.reality_contact.mutation_probe import (
    # Aliased on import: the probe's helper is named `test_references_symbol`,
    # which pytest would otherwise try to COLLECT as a test (it takes args, not
    # fixtures). Importing it under a non-`test_` alias keeps it a plain helper.
    test_references_symbol as references_symbol,
)

# A stable, known-real CORE symbol used across the hermeticity tests.
_OPS_SYMBOL = "substrate.graph.ops.insert_document"


def _real_insert_document_works() -> bool:
    """A residue probe: import the REAL insert_document fresh and confirm it is
    the genuine callable, not a leaked corrupted stub. We check identity against
    the module attribute and that it is NOT carrying the mutation marker — we do
    NOT call it (it needs a live DB connection); the marker check is the
    leak-detector."""
    return not symbol_is_corrupted(_OPS_SYMBOL)


# --------------------------------------------------------------------------- #
# M1 — symbol resolution
# --------------------------------------------------------------------------- #
def test_every_fault_plan_symbol_resolves_to_a_callable() -> None:
    """Every per-subsystem fault target resolves and is callable — a typo here
    would silently make a whole subsystem un-probeable."""
    for fault in FAULT_PLAN:
        owner, attr = _resolve_symbol(fault.symbol)
        assert hasattr(owner, attr), f"{fault.symbol}: missing {attr}"
        assert callable(getattr(owner, attr)), f"{fault.symbol} is not callable"


def test_resolve_search_module_not_the_reexported_function() -> None:
    """`substrate.graph.search` is both a module AND a re-exported bare function
    off the `substrate.graph` package; the resolver must reach the MODULE so the
    fault lands on the real `search` function inside it."""
    owner, attr = _resolve_symbol("substrate.graph.search.search")
    mod = importlib.import_module("substrate.graph.search")
    assert owner is mod
    assert attr == "search"


def test_resolve_rejects_a_bare_module() -> None:
    """A fault must target a symbol inside a module, not a module itself."""
    with pytest.raises(MutationProbeError):
        _resolve_symbol("substrate.graph.ops")


# --------------------------------------------------------------------------- #
# M1 — the hermetic injector + the load-bearing residue test
# --------------------------------------------------------------------------- #
def test_inject_fault_corrupts_inside_restores_outside() -> None:
    """Identity/behaviour before, during, and after the context."""
    import substrate.graph.ops as ops

    original = ops.insert_document
    assert not symbol_is_corrupted(_OPS_SYMBOL)

    with inject_fault(_OPS_SYMBOL):
        assert symbol_is_corrupted(_OPS_SYMBOL)
        with pytest.raises(MutationProbeError):
            ops.insert_document()  # corrupted -> raises

    assert not symbol_is_corrupted(_OPS_SYMBOL)
    assert ops.insert_document is original  # EXACT identity restored


def test_residue_restoration_even_on_exception() -> None:
    """THE residue test (mandatory). Inject, exit via a raised exception inside
    the context, then assert a known-real function is back to normal afterward —
    no leaked mutation."""
    import substrate.graph.ops as ops

    original = ops.insert_document

    class _Boom(RuntimeError):
        pass

    with pytest.raises(_Boom), inject_fault(_OPS_SYMBOL):
        assert symbol_is_corrupted(_OPS_SYMBOL)
        raise _Boom("explode inside the mutated context")

    # The exception propagated, but the symbol MUST be restored.
    assert not symbol_is_corrupted(_OPS_SYMBOL)
    assert ops.insert_document is original
    assert _real_insert_document_works()


def test_hermetic_across_repeated_uses() -> None:
    """Repeated inject/restore cycles never accumulate a leak (the runner relies
    on this — one test's fault must never bleed into the next)."""
    import substrate.graph.ops as ops

    original = ops.insert_document
    for _ in range(5):
        with inject_fault(_OPS_SYMBOL):
            assert symbol_is_corrupted(_OPS_SYMBOL)
        assert not symbol_is_corrupted(_OPS_SYMBOL)
    assert ops.insert_document is original


def test_sentinel_mode_returns_wrong_value_then_restores() -> None:
    """The softer corruption mode: the symbol returns a wrong sentinel rather
    than raising, and is still restored on exit."""
    import substrate.graph.ops as ops

    original = ops.insert_document
    with inject_fault(_OPS_SYMBOL, mode=FAULT_SENTINEL):
        result = ops.insert_document()
        assert result != original  # a wrong value, not the real work
        assert isinstance(result, str)
    assert ops.insert_document is original


def test_unknown_mode_rejected() -> None:
    with pytest.raises(MutationProbeError), inject_fault(_OPS_SYMBOL, mode="not-a-mode"):
        pass


def test_corrupt_factory_marks_the_replacement() -> None:
    """A corrupted symbol carries the mutation marker so the residue detector can
    distinguish it from the real one."""
    raising = _make_corrupt(lambda: None, FAULT_RAISE, "x.y")
    sentinel = _make_corrupt(lambda: None, FAULT_SENTINEL, "x.y")
    assert getattr(raising, "__rc_mutation_probe_corrupted__", False)
    assert getattr(sentinel, "__rc_mutation_probe_corrupted__", False)
    with pytest.raises(MutationProbeError):
        raising()
    assert isinstance(sentinel(), str)


# --------------------------------------------------------------------------- #
# M2 — ledger reading + fairness check
# --------------------------------------------------------------------------- #
def test_load_reality_tests_by_subsystem_matches_ledger() -> None:
    """The probe reads its sample from the REAL ledger, not from memory. The six
    CORE subsystems must all be present and carry only existing test paths."""
    by_sub = load_reality_tests_by_subsystem()
    expected = {f.subsystem for f in FAULT_PLAN}
    assert expected.issubset(set(by_sub)), f"missing subsystems: {expected - set(by_sub)}"
    for paths in by_sub.values():
        for p in paths:
            assert (REPO_ROOT / p).exists(), f"ledger names a non-existent test: {p}"


def test_references_symbol_is_a_real_source_check() -> None:
    """The fairness check distinguishes a test that names the symbol from one
    that does not — this is what separates classifier-wrong from shallow-fault."""
    # test_register_source.py imports and calls insert_document.
    assert references_symbol("tests/test_register_source.py", _OPS_SYMBOL)
    # A test that does not reference it returns False (use a schema-only test).
    assert not references_symbol(
        "tests/test_register_source.py",
        "substrate.graph.search.search",
    )


def test_references_symbol_ignores_docstring_mentions() -> None:
    """THE fairness-rigor test. A test that only MENTIONS the symbol name in a
    docstring/comment (but never imports or calls it) must NOT be fairness-eligible
    — otherwise a shallow fault would be falsely scored a classifier error. These
    three router tests mention 'dispatch' only in prose; they import
    register_provider / _PROVIDER_REGISTRY, never `dispatch`."""
    dispatch = "substrate.dispatch.router.dispatch"
    for prose_only in (
        "tests/test_dispatch_synthesis_pin.py",
        "tests/test_connector_bridge.py",
        "tests/test_evidence_retriever_bridge.py",
    ):
        assert not references_symbol(prose_only, dispatch), (
            f"{prose_only} only mentions 'dispatch' in prose; the AST fairness "
            f"check must not count it as driving the symbol"
        )
    # A test that genuinely calls search() IS eligible (it really makes contact).
    assert references_symbol("tests/test_graph.py", "substrate.graph.search.search")


def test_fault_covers_package_reexport_binding() -> None:
    """THE probe-completeness test. A symbol re-exported by its parent package
    (e.g. `from substrate.graph import search`) must be faulted at the re-export
    site too, else a test importing it that way passes under a 'broken' core and is
    falsely flagged a classifier false positive. Confirm the fault lands on every
    same-identity binding site."""
    import importlib

    from tools.reality_contact.mutation_probe import _binding_sites

    sym = "substrate.graph.search.search"
    sites = _binding_sites(sym)
    site_names = {(m.__name__, a) for m, a in sites}
    # Both the defining module and the parent-package re-export must be present.
    assert ("substrate.graph.search", "search") in site_names
    assert ("substrate.graph", "search") in site_names

    pkg = importlib.import_module("substrate.graph")
    module = importlib.import_module("substrate.graph.search")
    with inject_fault(sym):
        assert symbol_is_corrupted(sym)
        assert getattr(pkg.search, "__rc_mutation_probe_corrupted__", False)
        assert getattr(module.search, "__rc_mutation_probe_corrupted__", False)
    # Restored at BOTH sites.
    assert not getattr(pkg.search, "__rc_mutation_probe_corrupted__", False)
    assert not getattr(module.search, "__rc_mutation_probe_corrupted__", False)


# --------------------------------------------------------------------------- #
# M2/M3 — known-good sanity: the probe itself works (subprocess)
# --------------------------------------------------------------------------- #
def test_known_good_reality_test_goes_red_under_fault() -> None:
    """A clearly-reality test (it calls the real insert_document) MUST go RED when
    that symbol is faulted — proving the probe detects loss of real contact."""
    fault = next(f for f in FAULT_PLAN if f.subsystem == "substrate.graph.ops")
    result = probe_subsystem(
        fault,
        reality_tests=["tests/test_register_source.py"],
        sample_n=1,
    )
    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.references_symbol is True
    assert outcome.passed_under_fault is False, (
        "a reality test that really calls insert_document must FAIL under fault"
    )
    assert outcome.verdict == "expected-red"


def test_synthetic_theater_stays_green_under_fault() -> None:
    """The FN-direction control: a synthetic theater test that mocks the faulted
    symbol stays GREEN under the fault (it never calls the real symbol). If this
    went red the probe would falsely flag a true theater test as a false
    negative."""
    fault = next(f for f in FAULT_PLAN if f.subsystem == "substrate.graph.ops")
    outcome = run_synthetic_theater_control(fault)
    assert outcome.label == "theater"
    assert outcome.passed_under_fault is True, (
        "a synthetic theater test mocking the symbol must stay GREEN under fault"
    )
    assert outcome.verdict == "expected-green"


# --------------------------------------------------------------------------- #
# M3 — report rendering is deterministic + states the fairness split
# --------------------------------------------------------------------------- #
def test_probe_subsystem_separates_fp_from_shallow() -> None:
    """Construct a tiny SubsystemResult by hand and confirm the verdict logic:
    a pass that references the symbol is `classifier-fp`; a pass that does not is
    `shallow-fault`; a red is `expected-red`. (Pure logic — no subprocess.)"""
    from tools.reality_contact.mutation_probe import SubsystemResult, TestOutcome

    fault = SubsystemFault("sub", "pkg.mod.sym", FAULT_RAISE, "why")
    r = SubsystemResult(
        subsystem="sub",
        fault=fault,
        sample_size=3,
        selection_rule="hand-built",
        total_reality=3,
    )
    r.outcomes = [
        TestOutcome("sub", "t_red.py", "reality", "pkg.mod.sym", FAULT_RAISE, True, False, 1, "expected-red"),
        TestOutcome("sub", "t_fp.py", "reality", "pkg.mod.sym", FAULT_RAISE, True, True, 0, "classifier-fp"),
        TestOutcome("sub", "t_shallow.py", "reality", "pkg.mod.sym", FAULT_RAISE, False, True, 0, "shallow-fault"),
    ]
    # Only the FP and RED reference the symbol -> fairness-eligible = 2.
    assert len(r.fairness_eligible()) == 2
    assert r.fp_rate() == pytest.approx(0.5)  # 1 fp / 2 eligible
    assert len(r.shallow()) == 1
    assert len(r.expected_red()) == 1


def test_render_report_is_deterministic_and_names_the_fault() -> None:
    """Rendering the same probe twice is byte-identical, and the report names the
    injected symbol + fault per subsystem (defensibility / reproducibility)."""
    from tools.reality_contact.mutation_probe import (
        ProbeReport,
        SubsystemResult,
        TestOutcome,
    )

    fault = FAULT_PLAN[0]
    r = SubsystemResult(
        subsystem=fault.subsystem,
        fault=fault,
        sample_size=1,
        selection_rule="rule",
        total_reality=1,
    )
    r.outcomes = [
        TestOutcome(
            fault.subsystem, "tests/t.py", "reality", fault.symbol,
            fault.mode, True, False, 1, "expected-red",
        )
    ]
    report = ProbeReport(sample_n=1, subsystem_results=[r])
    report.theater_controls = [
        TestOutcome(
            fault.subsystem, "<synthetic theater control>", "theater", fault.symbol,
            fault.mode, True, True, 0, "expected-green",
        )
    ]
    text_a = render_report(report)
    text_b = render_report(report)
    assert text_a == text_b
    assert fault.symbol in text_a
    assert "False-positive rate" in text_a
    assert "Gate recommendation" in text_a


def test_render_fault_plugin_text_is_self_contained() -> None:
    """The generated subprocess plugin references the probe's own resolver and
    installs the fault in pytest_configure (before collection)."""
    text = _render_fault_plugin("substrate.graph.ops.insert_document", FAULT_RAISE)
    assert "pytest_configure" in text
    assert "_binding_sites" in text  # patches every re-export binding, not just one
    assert "_make_corrupt" in text
    assert "substrate.graph.ops.insert_document" in text
