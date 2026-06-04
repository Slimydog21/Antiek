"""Fixture: a NO-ASSERT SMOKE test file.

``test_smoke_runs`` constructs and calls the unit but asserts nothing — it
only proves the code path does not raise. ``test_trivial_true`` asserts a
constant. The census must label both ``none`` (no meaningful assertion). A
green ``none`` test predicts nothing about correctness.

Parsed, not executed (see test_pure_behavior.py header).
"""

from __future__ import annotations


def build() -> dict:
    return {"ok": True}


def test_smoke_runs():
    build()


def test_trivial_true():
    build()
    assert True
