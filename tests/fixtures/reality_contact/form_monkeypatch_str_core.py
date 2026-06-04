"""Fixture: `monkeypatch.setattr("dotted.core.path", v)` string form → theater."""

from substrate.graph import ops  # noqa: F401


def test_monkeypatch_str_core(monkeypatch):
    monkeypatch.setattr("substrate.graph.ops.insert_document", lambda *a, **k: "doc-x")
    assert True
