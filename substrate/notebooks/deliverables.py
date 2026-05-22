"""Public API for substrate/notebooks deliverables (2026-05-22).

Adapter layer over the existing ``deliverables`` table (defined in
``substrate/graph/schema.py``) that adds the publication semantics the
master spec's reward chain requires:

  - publication_uri + published_at columns (via this module's migration)
  - deliverable_citations join table (new, this module owns)
  - "is published" = ``published_at IS NOT NULL`` rather than a new
    status enum value (DuckDB doesn't ALTER CHECK constraints)

Three responsibilities:

1. **Migration loader** — additive ALTER TABLE + new join table.
2. **Write API** — ``mark_published`` / ``cite_notebook``.
3. **Read API** — ``find_published_deliverables_citing_notebook``: the
   join reward_deep uses.

This module deliberately doesn't expose a ``create_deliverable``
wrapper because the existing graph schema already requires
``deliverable_kind`` + the CHECK constraint on it. Sprint 19's
deliverable-creation surface will use the existing ``insert_deliverable``
in substrate/graph/ops.py and then call this module's ``mark_published``
+ ``cite_notebook`` to land the publication semantics.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import duckdb

_HERE = os.path.dirname(os.path.abspath(__file__))
_MIGRATIONS_DIR = os.path.join(_HERE, "migrations")
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ── Records ──


@dataclass
class DeliverableRecord:
    """A deliverable row plus the publication overlay this module adds."""

    deliverable_id: str
    title: str
    deliverable_kind: str
    owner_user_id: str
    status: str  # graph CHECK: 'draft' | 'in_review' | 'final'
    published_at: Optional[datetime]
    publication_uri: Optional[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_published(self) -> bool:
        """Published = published_at IS NOT NULL. The graph schema's
        ``status`` is independent (a deliverable can be 'final' but
        unpublished, or 'draft' but published if the operator releases
        it early)."""
        return self.published_at is not None


# ── Schema ──


def init_deliverables_schema_at_path(db_path: str) -> None:
    """Apply this module's deliverables extensions (ALTER COLUMNs +
    deliverable_citations table) to ``db_path``. Idempotent.

    Wired into ``substrate.graph.ensure_initialized`` so every caller
    gets the publication overlay automatically.
    """
    path = os.path.join(_MIGRATIONS_DIR, "0001_deliverables.sql")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, encoding="utf-8") as f:
        sql_text = f.read()
    with duckdb.connect(db_path) as con:
        for stmt in _split_statements(sql_text):
            try:
                con.execute(stmt)
            except (duckdb.CatalogException, duckdb.ParserException) as exc:
                msg = str(exc).lower()
                if "already exists" in msg or "duplicate" in msg:
                    continue
                raise


def _split_statements(sql_text: str):
    cleaned_lines = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        idx = line.find("--")
        if idx >= 0:
            line = line[:idx]
        if line.strip():
            cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines).strip()
    for raw in cleaned.split(";"):
        stmt = raw.strip()
        if stmt:
            yield stmt


# ── Write API ──


def mark_published(
    deliverable_id: str,
    *,
    publication_uri: str,
    db_path: Optional[str] = None,
) -> DeliverableRecord:
    """Stamp ``published_at = now`` + ``publication_uri = uri`` on an
    existing deliverable.

    Does NOT touch the graph-schema ``status`` (that's the operator's
    workflow state — draft / in_review / final). Publication is
    orthogonal: a 'final' deliverable can be unpublished (operator
    decided to shelve it) and a 'draft' can be published (early
    release).
    """
    from substrate.graph import default_db_path
    path = db_path or default_db_path()
    now = datetime.now(timezone.utc)
    with duckdb.connect(path) as con:
        con.execute(
            "UPDATE deliverables SET publication_uri=?, published_at=?, "
            "updated_at=? WHERE deliverable_id=?",
            [publication_uri, now, now, deliverable_id],
        )
    loaded = load_deliverable(deliverable_id, db_path=path)
    if loaded is None:
        raise KeyError(f"mark_published: deliverable {deliverable_id} not found")
    return loaded


def mark_unpublished(
    deliverable_id: str,
    *,
    db_path: Optional[str] = None,
) -> DeliverableRecord:
    """Clear publication. Reward_deep stops counting; the row stays."""
    from substrate.graph import default_db_path
    path = db_path or default_db_path()
    now = datetime.now(timezone.utc)
    with duckdb.connect(path) as con:
        con.execute(
            "UPDATE deliverables SET publication_uri=NULL, published_at=NULL, "
            "updated_at=? WHERE deliverable_id=?",
            [now, deliverable_id],
        )
    loaded = load_deliverable(deliverable_id, db_path=path)
    if loaded is None:
        raise KeyError(f"mark_unpublished: deliverable {deliverable_id} not found")
    return loaded


def cite_notebook(
    *,
    deliverable_id: str,
    notebook_id: str,
    block_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    """Record a citation. Idempotent on the composite primary key."""
    from substrate.graph import default_db_path
    path = db_path or default_db_path()
    with duckdb.connect(path) as con:
        try:
            con.execute(
                "INSERT INTO deliverable_citations "
                "(deliverable_id, notebook_id, block_id) VALUES (?, ?, ?)",
                [deliverable_id, notebook_id, block_id],
            )
        except (duckdb.ConstraintException, duckdb.IntegrityError):
            pass  # already cited


# ── Read API ──


def load_deliverable(
    deliverable_id: str,
    *,
    db_path: Optional[str] = None,
) -> Optional[DeliverableRecord]:
    from substrate.graph import default_db_path
    path = db_path or default_db_path()
    with duckdb.connect(path) as con:
        row = con.execute(
            "SELECT deliverable_id, title, deliverable_kind, owner_user_id, "
            "status, published_at, publication_uri, metadata "
            "FROM deliverables WHERE deliverable_id = ?",
            [deliverable_id],
        ).fetchone()
    if row is None:
        return None
    md = row[7]
    if isinstance(md, str) and md:
        try:
            md = json.loads(md)
        except json.JSONDecodeError:
            md = {}
    return DeliverableRecord(
        deliverable_id=row[0],
        title=row[1],
        deliverable_kind=row[2],
        owner_user_id=row[3],
        status=row[4],
        published_at=row[5],
        publication_uri=row[6],
        metadata=md if isinstance(md, dict) else {},
    )


def find_published_deliverables_citing_notebook(
    notebook_id: str,
    *,
    db_path: Optional[str] = None,
) -> list[DeliverableRecord]:
    """The reward_deep join. Returns every published (published_at IS
    NOT NULL) deliverable citing the given notebook.

    Unpublished + retracted deliverables are excluded — reward_deep
    only counts the publication threshold."""
    from substrate.graph import default_db_path
    path = db_path or default_db_path()
    with duckdb.connect(path) as con:
        rows = con.execute(
            "SELECT d.deliverable_id, d.title, d.deliverable_kind, "
            "d.owner_user_id, d.status, d.published_at, "
            "d.publication_uri, d.metadata "
            "FROM deliverables d "
            "JOIN deliverable_citations dc USING (deliverable_id) "
            "WHERE dc.notebook_id = ? AND d.published_at IS NOT NULL",
            [notebook_id],
        ).fetchall()
    out: list[DeliverableRecord] = []
    for row in rows:
        md = row[7]
        if isinstance(md, str) and md:
            try:
                md = json.loads(md)
            except json.JSONDecodeError:
                md = {}
        out.append(DeliverableRecord(
            deliverable_id=row[0],
            title=row[1],
            deliverable_kind=row[2],
            owner_user_id=row[3],
            status=row[4],
            published_at=row[5],
            publication_uri=row[6],
            metadata=md if isinstance(md, dict) else {},
        ))
    return out


__all__ = [
    "DeliverableRecord",
    "cite_notebook",
    "find_published_deliverables_citing_notebook",
    "init_deliverables_schema_at_path",
    "load_deliverable",
    "mark_published",
    "mark_unpublished",
]
