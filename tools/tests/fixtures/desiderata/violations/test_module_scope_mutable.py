"""Fixture: module-scoped mutable fixture shared by multiple tests.

The lint must flag the fixture definition: mutations leak across consumers.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def shared_bucket():
    return {}


def test_a_fills_bucket(shared_bucket):
    shared_bucket["a"] = 1


def test_b_reads_bucket(shared_bucket):
    assert "a" in shared_bucket