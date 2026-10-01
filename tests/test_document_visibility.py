"""Safe metadata admission matches its SQL representation."""

from __future__ import annotations

import duckdb
import pytest

from substrate.rights.document_visibility import (
    document_discoverability_sql,
    document_discoverable,
)


@pytest.mark.parametrize("owner", [None, "A", "B", " A ", "__operator__"])
def test_scalar_sql_agreement(owner):
    rows = [
        ("public", "public_domain", "A", False),
        ("privateA", "user_authored_private", "A", False),
        ("privateB", "personal_reading", "B", False),
        ("legacy", None, "A", False),
        ("old", "user_owned", "B", False),
        ("unknown", "typo", "A", False),
        ("taken", "public_domain", "A", True),
        ("licensed", "restricted_pending_opt_in", "A", False),
        ("research", "research_only", "A", False),
    ]
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE documents (document_id TEXT, content_class TEXT, owner_user_id TEXT)")
    con.execute("CREATE TABLE book_assets (document_id TEXT, taken_down BOOLEAN)")
    con.executemany("INSERT INTO documents VALUES (?, ?, ?)", [(r[0], r[1], r[2]) for r in rows])
    con.executemany("INSERT INTO book_assets VALUES (?, ?)", [(r[0], True) for r in rows if r[3]])
    sql, params = document_discoverability_sql(owner_user_id=owner, document_alias="d")
    found = {r[0] for r in con.execute(f"SELECT d.document_id FROM documents d WHERE {sql}", params).fetchall()}
    expected = {r[0] for r in rows if document_discoverable(
        content_class=r[1], stored_owner_user_id=r[2], taken_down=r[3], owner_user_id=owner
    )}
    assert found == expected
    con.close()


def test_invalid_static_alias():
    for alias in ("d.bad", "td", "TD", "pa04_doc"):
        with pytest.raises(ValueError):
            document_discoverability_sql(owner_user_id=None, document_alias=alias)
