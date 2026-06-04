"""CI-floor guard for the reality-contact ratchet (SPR-05).

Belt-and-suspenders for ``.github/workflows/reality_contact.yml``: this asserts
the SPR-04 ratchet passes on the LIVE tree under the existing ``pytest tests/``
gate and locally, so a reality-contact regression is caught even if the new
workflow is misconfigured or disabled.

It calls the real ``run_check()`` with no arguments, which regenerates the
ledger from the live tree in-memory (via ``build_ledger()``) and compares it to
the committed ``baseline.json`` — the exact same code path the CI step runs.
Nothing is mocked. By the classifier's own definition this file is therefore a
``reality`` test: it exercises the real ratchet against the real boundary
config, so the gate's own guard passes the gate's own bar.

If this goes red, the message is the same the ratchet prints: a new un-exempted
core-mock appeared (naming file:line:symbol) or a subsystem's theater count grew
past its recorded floor. The fix is to make the offending test contact reality,
or to record a reasoned exemption (``ratchet --accept --reason ...``, SPR-04) —
NOT to weaken this assertion.
"""

from __future__ import annotations

from tools.reality_contact.ratchet import EXIT_OK, run_check


def test_reality_contact_ratchet_holds_on_current_tree() -> None:
    """The live tree must not regress below the committed reality-contact floor.

    ``run_check()`` returns ``EXIT_OK`` (0) when the live tree is at or above the
    frozen baseline, and ``EXIT_REGRESSION`` (1) when a new un-exempted core-mock
    or a theater-count regression appears. We assert exit-0 so a regression turns
    this floor test red in addition to the workflow.
    """
    assert run_check() == EXIT_OK
