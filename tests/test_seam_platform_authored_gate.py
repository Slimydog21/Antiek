"""Collision #4 guard — ``platform_authored``-from-Speak gating
(antiek-unified SPR-03, seam #4).

Read assumes ``platform_authored = clean and auto-servable``. A Speak biography
assembled from third-party interview claims is *not* automatically clean. So
``platform_authored`` carries a ``provenance_class ∈ {operator_authored,
speak_derived}`` (SPR-01 ``ServableEntryContract``), and a ``speak_derived``
document is served full text only after Speak's publish gate passes —
translated for Read by ``substrate/seams/servability_gate.py`` so Read consults
a boolean, never Speak's internals.

Named invariant a maintainer greps: "speak_derived docs hit the publish gate"
= this test file. The deny-by-default behavior:

* a non-gate-passing ``speak_derived`` doc is NOT served full text;
* a gate-passing ``speak_derived`` doc IS served;
* ``operator_authored`` stays auto-servable (no Write-output regression);
* Read is not coupled to Speak — the adapter takes a boolean / a
  ``ConsentContract``, not Speak's models.

Rigor #3: the negative (a speak_derived doc served without the gate) FAILS.
"""

from __future__ import annotations

from substrate.contracts.interviewer import ConsentContract
from substrate.contracts.servable import ServableEntryContract
from substrate.seams import servability_gate


def _speak_derived(document_id: str = "doc-bio-1") -> ServableEntryContract:
    return ServableEntryContract(
        document_id=document_id,
        content_class="platform_authored",
        provenance_class="speak_derived",
    )


def _operator_authored(document_id: str = "doc-op-1") -> ServableEntryContract:
    return ServableEntryContract(
        document_id=document_id,
        content_class="platform_authored",
        provenance_class="operator_authored",
    )


def test_speak_derived_not_served_without_publish_gate():
    """The load-bearing negative: a speak_derived doc whose gate has NOT passed
    is not served full text."""
    entry = _speak_derived()
    assert servability_gate.serves_full_text(entry, publish_gate_passed=False) is False
    # And the stamped entry agrees.
    gated = servability_gate.gate_speak_derived_entry(entry, publish_gate_passed=False)
    assert gated.serves_full_text is False
    assert gated.speak_publish_gate_passed is False


def test_speak_derived_served_after_publish_gate():
    entry = _speak_derived()
    assert servability_gate.serves_full_text(entry, publish_gate_passed=True) is True
    gated = servability_gate.gate_speak_derived_entry(entry, publish_gate_passed=True)
    assert gated.serves_full_text is True
    assert gated.speak_publish_gate_passed is True


def test_operator_authored_auto_servable_no_regression():
    """Write output (operator_authored) stays auto-servable regardless of the
    Speak gate — the gate does not apply to it."""
    entry = _operator_authored()
    assert servability_gate.serves_full_text(entry, publish_gate_passed=False) is True
    # Stamping a non-speak_derived entry is a no-op (returns it unchanged).
    same = servability_gate.gate_speak_derived_entry(entry, publish_gate_passed=False)
    assert same is entry
    assert same.serves_full_text is True


def test_read_consults_a_boolean_not_speak_internals():
    """Decoupling: the producing (Speak) side computes the gate from a
    ``ConsentContract`` and hands Read a boolean. Read never imports Speak
    models — the adapter's serving function takes only the contract + the
    boolean."""
    publishable = ConsentContract(
        interview_id="iv-1",
        scopes=("record", "attribute", "publish"),
        verified_before_publish=True,
        right_of_publicity_cleared=True,
    )
    not_publishable = ConsentContract(interview_id="iv-2", scopes=("record",))

    gate_ok = servability_gate.speak_publish_gate_passed(publishable)
    gate_blocked = servability_gate.speak_publish_gate_passed(not_publishable)
    assert gate_ok is True
    assert gate_blocked is False

    entry = _speak_derived()
    # Read's serving decision is a pure function of (entry, boolean).
    assert servability_gate.serves_full_text(entry, publish_gate_passed=gate_ok) is True
    assert servability_gate.serves_full_text(entry, publish_gate_passed=gate_blocked) is False


def test_takedown_overrides_even_with_gate_passed():
    """Deny-by-default deepest: a taken-down speak_derived doc is never served,
    even if the publish gate passed (takedown is terminal)."""
    entry = ServableEntryContract(
        document_id="doc-bio-2",
        content_class="platform_authored",
        provenance_class="speak_derived",
        taken_down=True,
    )
    assert servability_gate.serves_full_text(entry, publish_gate_passed=True) is False


def test_negative_a_served_ungated_speak_derived_doc_is_the_bug(monkeypatch):
    """Rigor #3 — the guard would catch a regression. Simulate a broken adapter
    that ignores the gate and 'serves' a speak_derived doc; assert our real
    adapter does NOT behave that way (the broken behavior is the bug)."""
    entry = _speak_derived()
    broken_serves = True  # a hypothetical adapter that forgot the gate
    real_serves = servability_gate.serves_full_text(entry, publish_gate_passed=False)
    assert real_serves != broken_serves, (
        "a speak_derived doc must NOT serve without the publish gate — if this "
        "fails, the seam-#4 gate has regressed"
    )
