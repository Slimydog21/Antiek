"""Changing a chunk reader requires renewing its explicit audience review."""
import ast
import json

from tools.lint import chunk_reader_census as readers


def test_reviewed_reader_inventory_matches_source():
    assert readers.check() == []


def test_discovery_covers_projection_and_dynamic_table_variants():
    visitor = readers._Readers("production.py")
    visitor.visit(ast.parse('''
def read():
    one = "SELECT c.text FROM chunks c"
    two = "SELECT * FROM chunks"
    three = f"SELECT {projection} FROM chunks c JOIN documents d USING(document_id)"
    four = "SELECT value FROM nodes JOIN chunks c ON c.chunk_id = id"
    tables = ("chunks",)
    export = f"EXPORT DATABASE '{destination}'"
'''))
    assert len(visitor.rows) == 6


def test_new_or_changed_reader_fails_review(monkeypatch, tmp_path):
    visitor = readers._Readers("production.py")
    visitor.visit(ast.parse('def read():\n    return "SELECT text FROM chunks"'))
    row = visitor.rows[0]
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"sql_readers": [dict(row, audience="owner", disposition="guarded", evidence="probe")]}))
    monkeypatch.setattr(readers, "INVENTORY", inventory)
    monkeypatch.setattr(readers, "census", lambda: [row])
    assert readers.check() == []
    changed = dict(row, function_sha256="changed")
    monkeypatch.setattr(readers, "census", lambda: [changed])
    assert any("Unreviewed" in error for error in readers.check())
    monkeypatch.setattr(readers, "census", lambda: [row, dict(row, path="new_reader.py")])
    assert any("new_reader.py" in error for error in readers.check())
