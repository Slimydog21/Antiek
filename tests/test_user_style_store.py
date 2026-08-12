"""Direct store-level tests for the style-wheel fork store + provenance column.

These complement ``tests/test_style_api.py`` (HTTP-acceptance) by exercising
``substrate/styles/store.py`` directly: the ``parent`` provenance column, its
idempotent migration on legacy tables, and the read-time fallback that keeps a
GET from 500-ing on a pre-provenance DB that has not yet been migrated by a
write.
"""

from __future__ import annotations

import duckdb

from services.html_projection.styles import ProjectionStyle
from substrate.styles.store import UserStyleStore


def _style(name: str, *, parent: str | None = None, label: str | None = None) -> ProjectionStyle:
    return ProjectionStyle(
        name=name,
        label=label or name.replace("-", " ").title(),
        description="",
        theme_css="",
        source_fidelity=False,
        builtin=False,
        parent=parent,
    )


def _legacy_table(db_path: str) -> None:
    """Create a user_styles table WITHOUT the parent column, mimicking a DB
    created before the provenance migration, and seed one fork row."""
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            "CREATE TABLE user_styles ("
            "user_id VARCHAR NOT NULL, name VARCHAR NOT NULL, "
            "label VARCHAR NOT NULL, description VARCHAR NOT NULL DEFAULT '', "
            "theme_css VARCHAR NOT NULL DEFAULT '', "
            "source_fidelity BOOLEAN NOT NULL DEFAULT FALSE, "
            "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "PRIMARY KEY (user_id, name))"
        )
        con.execute(
            "INSERT INTO user_styles (user_id, name, label) "
            "VALUES ('u', 'legacy-fork', 'Legacy fork')"
        )
    finally:
        con.close()


def test_save_and_recover_parent(tmp_path):
    db_path = str(tmp_path / "t.duckdb")
    store = UserStyleStore(db_path)
    store.save("u", _style("warm", parent="academic-paper"))
    forks = store.list_for_user("u")
    assert len(forks) == 1
    assert forks[0].name == "warm"
    assert forks[0].parent == "academic-paper"


def test_save_without_parent_recovers_none(tmp_path):
    db_path = str(tmp_path / "t.duckdb")
    store = UserStyleStore(db_path)
    store.save("u", _style("from-scratch", parent=None))
    forks = store.list_for_user("u")
    assert forks[0].parent is None


def test_legacy_table_list_returns_none_parent(tmp_path):
    """A pre-provenance table (no parent column) read BEFORE any write since
    upgrade must not 500: the read-time fallback returns provenance=None for
    every legacy fork."""
    db_path = tmp_path / "t.duckdb"
    _legacy_table(db_path)
    store = UserStyleStore(str(db_path))
    forks = store.list_for_user("u")
    assert len(forks) == 1
    assert forks[0].name == "legacy-fork"
    assert forks[0].parent is None  # honest "origin untracked" for legacy rows


def test_write_migrates_legacy_table_and_backfills_null(tmp_path):
    """The first write after upgrade adds the parent column; pre-existing
    legacy rows keep NULL (no invented provenance), and the column now exists
    for future rows."""
    db_path = tmp_path / "t.duckdb"
    _legacy_table(db_path)
    store = UserStyleStore(str(db_path))
    store.save("u", _style("new-fork", parent="blog"))

    con = duckdb.connect(str(db_path))
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info('user_styles')").fetchall()]
        assert "parent" in cols  # migration ran
        rows = con.execute(
            "SELECT name, parent FROM user_styles WHERE user_id = 'u' ORDER BY name"
        ).fetchall()
    finally:
        con.close()
    by_name = dict(rows)
    assert by_name["legacy-fork"] is None  # backfill is NULL, not invented
    assert by_name["new-fork"] == "blog"


def test_replace_fork_updates_parent_in_place(tmp_path):
    db_path = str(tmp_path / "t.duckdb")
    store = UserStyleStore(db_path)
    store.save("u", _style("warm", parent="academic-paper"))
    store.save("u", _style("warm", parent="book", label="Warm v2"))
    forks = store.list_for_user("u")
    assert len(forks) == 1
    assert forks[0].parent == "book"
    assert forks[0].label == "Warm v2"


def test_parent_persists_across_store_instances(tmp_path):
    """Provenance is durable data, not in-memory state: a fresh store instance
    recovers the same parent from the DB."""
    db_path = str(tmp_path / "t.duckdb")
    UserStyleStore(db_path).save("u", _style("durable", parent="slate"))
    forks = UserStyleStore(db_path).list_for_user("u")
    assert forks[0].parent == "slate"


def test_delete_removes_fork(tmp_path):
    db_path = str(tmp_path / "t.duckdb")
    store = UserStyleStore(db_path)
    store.save("u", _style("temporary", parent="antiek"))
    assert store.delete("u", "temporary") is True
    assert store.list_for_user("u") == []
    assert store.delete("u", "temporary") is False  # idempotent


def test_list_for_user_isolated(tmp_path):
    db_path = str(tmp_path / "t.duckdb")
    store = UserStyleStore(db_path)
    store.save("alice", _style("alice-style", parent="blog"))
    store.save("bob", _style("bob-style", parent="slate"))
    assert {f.name for f in store.list_for_user("alice")} == {"alice-style"}
    assert {f.name for f in store.list_for_user("bob")} == {"bob-style"}
