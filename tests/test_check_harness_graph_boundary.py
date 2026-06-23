"""Harness CLI must not import graph funnel."""

from __future__ import annotations

from scripts.check_harness_graph_boundary import main


def test_harness_boundary_clean() -> None:
    assert main([]) == 0