"""Always-failing fixture — quarantine must not hide consistent regressions."""

from __future__ import annotations


def test_always_fails():
    raise AssertionError("consistent regression")