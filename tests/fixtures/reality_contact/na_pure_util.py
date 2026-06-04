"""Fixture: imports NO core subsystem → n-a.

A pure utility test. It uses a MagicMock as INPUT DATA (the near-miss negative:
a MagicMock bound to a name that is NOT an import alias must NOT be flagged as
a core shadow), and patches only a non-core, non-imported helper. Verdict: n-a.
"""

from unittest.mock import MagicMock, patch


def test_pure_util_addition():
    fake_input = MagicMock()  # input DATA, not a patch over any core symbol
    fake_input.value = 2
    assert 1 + fake_input.value == 3


@patch("some.unrelated.helper")  # not a core module; file imports no core
def test_pure_util_with_unrelated_patch(_helper):
    assert True
