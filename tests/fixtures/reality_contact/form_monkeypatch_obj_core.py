"""Fixture: `monkeypatch.setattr(obj, "attr", v)` object form → theater.

`search` is the import alias for substrate.graph.search; setattr(search,
"search", ...) resolves to substrate.graph.search.search — a core symbol.
"""

from substrate.graph import search


def test_monkeypatch_obj_core(monkeypatch):
    monkeypatch.setattr(search, "search", lambda *a, **k: [])
    assert True
