"""Fixture: `with patch("core.symbol")` context-manager form → theater."""

from unittest.mock import patch

from substrate.dispatch import router  # noqa: F401


def test_with_patches_core():
    with patch("substrate.dispatch.router.dispatch") as m:
        m.return_value = object()
        assert True
