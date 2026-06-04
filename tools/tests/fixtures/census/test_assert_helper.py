"""Fixture: a test whose entire check is a custom ASSERT-HELPER call.

``test_pool_is_conserved`` delegates its whole behavior check to
``_assert_conserved(shares)`` — a helper that RAISES on failure (it computes a
real value and asserts a property of it). ``test_phase_completed`` delegates to
``log.assert_phase_completed(8)`` — an assert-helper reached through an
attribute chain (its TAIL is ``assert_phase_completed``). Neither test has a
bare ``assert`` statement; the helper call IS the behavior assertion.

The census must classify BOTH ``behavior`` (not ``none``).

This is the MAJOR regression fixture: round-1 ``_classify_assert`` only saw bare
``ast.Assert`` statements and ``pytest.raises``, so an assert-helper-only test
had no behavior signal and was flagged ``none`` — wrongly pushing real files
like test_corpus_body_quality_gate.py and test_attribution_golden.py into the
5-lowest-predictiveness list that feeds SPR-02. On the old code these tests are
``none``; on the fix they are ``behavior``.

``test_only_mock_shape_helper`` is the FAIRNESS guard: a call to the
``unittest.mock`` ``assert_called_once`` family is CALL-SHAPE structure, NOT a
behavior helper — it must stay ``structure``, proving the heuristic excludes the
mock-assert family rather than swallowing it.

Parsed, not executed (see test_pure_behavior.py header).
"""

from __future__ import annotations

from unittest.mock import MagicMock


def _assert_conserved(shares) -> None:
    total = sum(shares.values())
    assert abs(total - 1.0) < 1e-9, total


def compute_shares() -> dict[str, float]:
    return {"a": 0.5, "b": 0.5}


class _PhaseLog:
    def assert_phase_completed(self, phase: int) -> None:
        if phase < 0:
            raise AssertionError("not completed")


def test_pool_is_conserved():
    shares = compute_shares()
    _assert_conserved(shares)


def test_phase_completed():
    log = _PhaseLog()
    log.assert_phase_completed(8)  # no raise == completed


def test_only_mock_shape_helper():
    client = MagicMock()
    client.send("x")
    # A unittest.mock call-shape assertion is STRUCTURE, not a behavior helper.
    client.send.assert_called_once_with("x")
