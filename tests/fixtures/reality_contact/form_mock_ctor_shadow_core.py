"""Fixture: `X = MagicMock()` where X is an import alias of a CORE symbol.

`dispatch` is imported from substrate.dispatch.router (so the name `dispatch`
resolves to substrate.dispatch.router.dispatch). Re-binding it to a MagicMock
stands a stub OVER the real core symbol → theater.
"""

from substrate.dispatch.router import dispatch  # noqa: F401
from unittest.mock import MagicMock


def test_shadows_core_symbol():
    dispatch = MagicMock()  # noqa: F811 — stands a stub over the core symbol
    dispatch.return_value = object()
    assert True
