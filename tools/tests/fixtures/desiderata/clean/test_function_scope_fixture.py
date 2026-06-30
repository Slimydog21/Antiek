"""Guard fixture: function-scoped fixture — correctly isolated per test.

Must NOT flag: the default pytest scope creates a fresh list for each test.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def isolated_list():
    return []


def test_one_appends(isolated_list):
    isolated_list.append(1)
    assert isolated_list == [1]


def test_two_starts_empty(isolated_list):
    assert isolated_list == []