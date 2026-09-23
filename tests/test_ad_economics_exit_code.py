"""The harness's exit code must follow its own verdict.

``overall`` — conservation, per-window conservation, non-negativity, every
escrow trace, the gate staying closed, disbursement staying blocked, and a
byte-identical replay — was computed as a LOCAL inside ``render_report`` and
reached only the printed ``OVERALL:`` line. ``main`` returned
``0 if idempotent else 1``.

So a run whose ledger did not conserve printed ``OVERALL: DISCREPANCY`` and
still exited 0. Idempotency is a real check, but it is one of seven, and it is
the one that holds while every other invariant is broken: re-accruing the same
batches twice changes nothing whether or not the money conserved. Any cron,
wrapper or CI step gating on ``$?`` was blind to a broken money story.

These tests pin the predicate to the exit code from both directions, against a
report built by hand so the failure modes can be produced without a database.
"""
from __future__ import annotations

import dataclasses

import pytest

from tools import verify_ad_economics as ve


def _healthy() -> ve.VerificationReport:
    """A report satisfying every clause, built from the real dataclasses."""
    rec = ve.Reconciliation(
        reconciles=True, per_window_reconciles=True, all_non_negative=True,
        **{f.name: getattr(_zero_rec(), f.name)
           for f in dataclasses.fields(ve.Reconciliation)
           if f.name not in {"reconciles", "per_window_reconciles", "all_non_negative"}},
    )
    return dataclasses.replace(_skeleton(), reconciliation=rec)


def _zero_rec() -> ve.Reconciliation:
    kwargs = {}
    for f in dataclasses.fields(ve.Reconciliation):
        if f.type in ("bool", bool) or f.name.startswith(("reconciles", "per_window", "all_non")):
            kwargs[f.name] = True
        else:
            kwargs[f.name] = _neutral(f)
    return ve.Reconciliation(**kwargs)


def _neutral(f):
    t = str(f.type)
    if "int" in t:
        return 0
    if "Decimal" in t:
        from decimal import Decimal
        return Decimal("0")
    if "tuple" in t or "list" in t:
        return ()
    if "bool" in t:
        return True
    return None


def _skeleton() -> ve.VerificationReport:
    safety = ve.SafetyValve(
        **{f.name: (False if f.name == "gate_allowed" else True if "bool" in str(f.type)
                    else _neutral(f))
           for f in dataclasses.fields(ve.SafetyValve)}
    )
    ab = ve.AlgorithmComparison(
        **{f.name: _neutral(f) for f in dataclasses.fields(ve.AlgorithmComparison)}
    )
    return ve.VerificationReport(
        corpus=(), results=[], reconciliation=_zero_rec(), traces=[],
        safety=safety, ab=ab, holders=(),
    )


def test_a_healthy_report_verifies():
    assert ve.report_verifies(_healthy()) is True


@pytest.mark.parametrize(
    "field",
    ["reconciles", "per_window_reconciles", "all_non_negative"],
    ids=["conservation", "per_window", "non_negative"],
)
def test_each_reconciliation_clause_alone_fails_the_predicate(field):
    """One broken clause is enough. This is what the old exit code ignored."""
    report = _healthy()
    broken = dataclasses.replace(report.reconciliation, **{field: False})
    assert ve.report_verifies(dataclasses.replace(report, reconciliation=broken)) is False


def test_an_open_gate_fails_the_predicate():
    report = _healthy()
    safety = dataclasses.replace(report.safety, gate_allowed=True)
    assert ve.report_verifies(dataclasses.replace(report, safety=safety)) is False


def test_unblocked_disbursement_fails_the_predicate():
    report = _healthy()
    safety = dataclasses.replace(report.safety, disbursement_blocked=False)
    assert ve.report_verifies(dataclasses.replace(report, safety=safety)) is False


def test_the_report_text_and_the_predicate_cannot_disagree():
    """Structural: the printed verdict must be derived from the same predicate.

    Two hand-rolled copies of a seven-clause boolean is exactly how the exit
    code drifted from the report in the first place, so this fails on a
    re-inlined copy even when the behaviour still happens to agree.
    """
    import inspect

    src = inspect.getsource(ve.render_report)
    assert "report_verifies(report)" in src, "render_report re-inlined the predicate"
    assert "rec.per_window_reconciles and rec.all_non_negative" not in src, (
        "render_report hand-rolls the clauses again"
    )


def test_main_gates_its_exit_code_on_the_predicate():
    """The defect itself: main must read `overall`, not idempotency alone."""
    import inspect

    src = inspect.getsource(ve.main)
    assert "report_verifies(report)" in src, (
        "main ignores the report verdict — the exact defect this file pins"
    )
    assert "return 0 if idempotent else 1" not in src, (
        "main still returns on idempotency alone"
    )
