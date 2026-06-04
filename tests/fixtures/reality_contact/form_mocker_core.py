"""Fixture: pytest-mock `mocker.patch("dotted.core.path")` form → theater."""

from substrate.graph import schema  # noqa: F401


def test_mocker_patches_core(mocker):
    mocker.patch("substrate.graph.schema.init_database_at_path")
    assert True
