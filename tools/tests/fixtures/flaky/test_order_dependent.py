"""Deliberately order-dependent fixture pair — module-scoped mutable leak."""

from __future__ import annotations

import pytest

_BUCKET: list[str] = []


@pytest.fixture(scope="module")
def shared_bucket():
    return _BUCKET


def test_order_writer(shared_bucket):
    shared_bucket.append("wrote")
    assert len(shared_bucket) >= 1


def test_order_reader_expects_empty(shared_bucket):
    # Fails when test_order_writer ran first in this module-scoped bucket.
    assert len(shared_bucket) == 0