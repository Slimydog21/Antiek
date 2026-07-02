"""Fixture: test mutates a module-level mutable container.

The lint must flag the append: state persists into the next test.
"""

from __future__ import annotations

_MODULE_CACHE: list[int] = []


def test_pollutes_module_cache():
    _MODULE_CACHE.append(99)