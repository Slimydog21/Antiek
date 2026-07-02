"""Fixture: a PURE BEHAVIOR test file.

No mocking machinery anywhere. The tests assert on real returned values and a
raised exception. The census must label these ``behavior`` with
``uses_mock=False``. This is the shape a predictive test should have.

NOTE: this file lives under tools/tests/fixtures/ and is NOT collected by
pytest (testpaths = tests/, compounding/...); it exists only as input the
census parses with ``ast``. It is never executed.
"""

from __future__ import annotations

import pytest


def add(a: int, b: int) -> int:
    return a + b


def divide(a: int, b: int) -> float:
    if b == 0:
        raise ZeroDivisionError("no")
    return a / b


def test_add_returns_sum():
    assert add(2, 3) == 5


def test_add_is_commutative():
    assert add(2, 3) == add(3, 2)


def test_divide_raises_on_zero():
    with pytest.raises(ZeroDivisionError):
        divide(1, 0)
