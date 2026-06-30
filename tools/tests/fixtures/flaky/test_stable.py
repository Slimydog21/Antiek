"""Stable control fixture — must never be proposed for quarantine."""

from __future__ import annotations


def test_always_stable():
    assert 2 + 2 == 4