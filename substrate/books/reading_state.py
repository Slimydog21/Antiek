"""The reading-state bus (reading-global SPR-01) — schema + store.

Position is EARNED persistence: page turns are not events and the position
is underivable from artifacts, so one row per (owner, document) holds the
operator's reading progress — REFS AND NUMBERS ONLY (the spec's refs-only
rule: no book text, no selection text, no annotation content — those have
their lawful stores in units 1-2, or are unlawful to store at all).

Additive idempotent DDL under the write lock, CHECK constraints mirroring
the API-layer validation (the unit-1 highlights convention,
substrate/books/highlights/schema.py):

  reading_state (
    owner_user_id VARCHAR,
    document_id  VARCHAR,
    page_index   INTEGER CHECK (>= 0),        -- the page-index locator
    anchor_ref   VARCHAR,                     -- optional unit-1 anchor id
    prefs_json   VARCHAR CHECK (= '{}'),      -- the EMPTY v1 allowlist
    revision     INTEGER CHECK (>= 0),        -- optimistic concurrency
    updated_at   TIMESTAMPTZ,
    PRIMARY KEY (owner_user_id, document_id)
  )

The prefs CHECK is the anti-smuggling backstop: the v1 allowlist is EMPTY
(the reader exposes no display prefs today), so the only storable value is
the canonical empty object. The API refuses non-empty prefs with a 422
BEFORE the store runs; the CHECK is the second layer for any writer that
skips the API. The field exists so the FIRST real pref lands as data, not
as a schema migration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from runtime.db_lock import LockedConnection


class SqlExecutor(Protocol):
    """The one call every connection in this package needs (the highlights
    convention): write side (LockedConnection) and read side
    (connect_read's DuckDBPyConnection) both satisfy it structurally."""

    def execute(self, sql: str, parameters: Any = None) -> Any: ...


DDL = """
CREATE TABLE IF NOT EXISTS reading_state (
  owner_user_id VARCHAR NOT NULL,
  document_id VARCHAR NOT NULL,
  page_index INTEGER NOT NULL CHECK (page_index >= 0),
  anchor_ref VARCHAR,
  prefs_json VARCHAR NOT NULL CHECK (prefs_json = '{}'),
  revision INTEGER NOT NULL CHECK (revision >= 0),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (owner_user_id, document_id)
);
"""

#: The v1 prefs allowlist — EMPTY by design (the reader has no display
#: prefs). The first real pref joins this set WITH its own evidence; until
#: then any non-empty prefs map is a 422 at the API and a CHECK violation
#: at the DB. Keys, not values: the allowlist names the lawful pref keys.
PREFS_V1_ALLOWLIST: frozenset[str] = frozenset()

#: The canonical serialization of the empty prefs map (the CHECK's value).
EMPTY_PREFS_JSON = "{}"


def init_reading_state_schema(con: LockedConnection) -> None:
    """Create the additive reading-state schema on an existing writer
    connection (idempotent — CREATE TABLE IF NOT EXISTS throughout)."""
    con.execute(DDL)


def reading_state_table_exists(con: object) -> bool:
    """Whether the table is present (read paths must not run DDL — a CREATE
    on a read connection fails, and a GET acquires no write lock for this)."""
    row = con.execute(  # type: ignore[attr-defined]
        "SELECT 1 FROM duckdb_tables() WHERE table_name = 'reading_state' LIMIT 1"
    ).fetchone()
    return row is not None


def serialize_prefs(prefs: dict[str, Any]) -> str:
    """The canonical prefs serialization — the value the CHECK constrains.
    Keys outside the v1 allowlist are the CALLER's 422, never silently
    dropped here; this function is honest about what it was given."""
    return json.dumps(prefs, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ReadingStateRow:
    """One owner's reading position on one document."""

    owner_user_id: str
    document_id: str
    page_index: int
    anchor_ref: str | None
    prefs_json: str
    revision: int
    updated_at: str


def _to_row(r: Any) -> ReadingStateRow:
    return ReadingStateRow(
        owner_user_id=str(r[0]),
        document_id=str(r[1]),
        page_index=int(r[2]),
        anchor_ref=None if r[3] is None else str(r[3]),
        prefs_json=str(r[4]),
        revision=int(r[5]),
        updated_at=str(r[6]),
    )


class ReadingStateStore:
    """Read and write reading positions, one row per (owner, document)."""

    def get(
        self, con: SqlExecutor, *, owner_user_id: str, document_id: str
    ) -> ReadingStateRow | None:
        """The owner's row, or None (no position recorded — a first read).
        Read-safe: no row can exist before the table does."""
        if not reading_state_table_exists(con):
            return None
        row = con.execute(
            "SELECT owner_user_id, document_id, page_index, anchor_ref, "
            "prefs_json, revision, updated_at FROM reading_state "
            "WHERE owner_user_id = ? AND document_id = ? LIMIT 1",
            [owner_user_id, document_id],
        ).fetchone()
        return None if row is None else _to_row(row)

    def put(
        self,
        con: LockedConnection,
        *,
        owner_user_id: str,
        document_id: str,
        page_index: int,
        anchor_ref: str | None,
        prefs_json: str,
        expected_revision: int,
    ) -> ReadingStateRow | None:
        """INSERT or UPDATE with optimistic concurrency. Returns the new row,
        or None when expected_revision is STALE (the API maps None → 409 —
        never a silent clobber). A create expects revision 0; an update
        expects the row's current revision and increments it."""
        init_reading_state_schema(con)
        existing = self.get(
            con, owner_user_id=owner_user_id, document_id=document_id
        )
        if existing is None:
            if expected_revision != 0:
                return None
            con.execute(
                "INSERT INTO reading_state (owner_user_id, document_id, "
                "page_index, anchor_ref, prefs_json, revision) "
                "VALUES (?, ?, ?, ?, ?, 1)",
                [owner_user_id, document_id, page_index, anchor_ref, prefs_json],
            )
        else:
            if expected_revision != existing.revision:
                return None
            con.execute(
                "UPDATE reading_state SET page_index = ?, anchor_ref = ?, "
                "prefs_json = ?, revision = revision + 1, "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE owner_user_id = ? AND document_id = ?",
                [page_index, anchor_ref, prefs_json, owner_user_id, document_id],
            )
        row = self.get(con, owner_user_id=owner_user_id, document_id=document_id)
        assert row is not None  # the write above just landed, same connection
        return row
