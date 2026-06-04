"""§9.0 gating of ``structured_blocks`` on the full-text serve path (Reader SPR-03).

SPR-02 added a ``documents.structured_blocks`` column (the serialized SPR-01
typed-block ``Document`` the one ``<Reader>`` renders). SPR-03 wires it through
the serve gate so a SERVABLE book's structured blocks reach the client — but
ONLY a servable book's. The load-bearing assertion: ``structured_blocks`` is
gated IDENTICALLY to ``full_text``. It rides the SAME serve gate, so:

  * a SERVABLE book serves BOTH full_text AND structured_blocks;
  * a GATED book serves NEITHER (snippet only, both None);
  * a TAKEN-DOWN book serves NEITHER (both None, no body at all).

There is no second gate to drift out of sync — the structured blocks come out
of the SAME ``serve_full_text`` SELECT/branching as the raw body, populated on
exactly the branches that emit ``full_text`` and left None on every branch that
withholds it. If a refactor ever served structured blocks where ``full_text``
is withheld, that is the §9.0 (Hachette / Bartz) leak in a new column, and these
tests turn red.

The endpoint-level test pins the JSON projection: ``FullTextResponse`` carries
``structured_blocks`` for a servable book and None for a gated one — the gate's
verdict reaches the wire intact.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.books import ingest as bingest  # noqa: E402
from substrate.books import takedown  # noqa: E402
from substrate.books.serve import serve_full_text  # noqa: E402
from substrate.books.serve_guard import serve_full_text_guarded  # noqa: E402
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS  # noqa: E402
from substrate.graph.ops import insert_document  # noqa: E402
from substrate.graph.schema import init_database  # noqa: E402

# A serialized SPR-01 typed-block Document — the exact shape SPR-02 persists and
# the one <Reader> deserializes. Only its presence/absence is asserted here.
_BLOCKS_JSON = json.dumps(
    {
        "id": "doc-x",
        "title": "A Servable Book",
        "schema_version": 1,
        "blocks": [
            {"type": "heading", "level": 1, "spans": [{"type": "text", "text": "Chapter 1"}]},
            {"type": "paragraph", "spans": [{"type": "text", "text": "The opening of the book."}]},
        ],
    }
)
_BODY = "## Page 1\n\nThe opening of the book.\n\n## Page 2\n\nThe second page.\n" * 4


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-serve-sb-")
    db_path = os.path.join(tmp, "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    con = connect_write(db_path, purpose="serve-sb-test")
    init_database(con)
    con.close()
    return db_path


def _insert(db, document_id, *, content_class, structured_blocks):
    """Insert a documents row carrying ``structured_blocks`` (the column SPR-02
    writes). ``content_class`` decides the serve verdict (servable vs gated)."""
    con = connect_write(db, purpose="setup")
    try:
        insert_document(
            con, document_id=document_id, source_tier=2,
            document_type="book", title="A Servable Book", author="Auth",
            raw_text=_BODY, content_class=content_class,
            structured_blocks=structured_blocks,
        )
    finally:
        con.close()


# ── servable → structured_blocks ARE served (alongside full_text) ───


def test_servable_book_serves_structured_blocks_with_full_text(db):
    """A servable book's structured blocks reach the caller — and they are
    populated on EXACTLY the branch that emits full_text (both present)."""
    _insert(db, "doc-x", content_class="public_domain", structured_blocks=_BLOCKS_JSON)
    con = connect_read(db)
    try:
        r = serve_full_text(con, "doc-x")
    finally:
        con.close()
    assert r.servable is True
    assert r.full_text is not None
    # The §9.0 invariant: structured_blocks is present iff a full body is served.
    assert r.structured_blocks == _BLOCKS_JSON
    parsed = json.loads(r.structured_blocks)
    assert isinstance(parsed["blocks"], list) and parsed["blocks"]


def test_servable_book_with_null_structured_blocks_serves_none(db):
    """A legacy / un-backfilled servable book (NULL column) serves full_text but
    structured_blocks=None — the frontend then falls back to the raw_text
    flattener. Additive, never blank."""
    _insert(db, "doc-legacy", content_class="public_domain", structured_blocks=None)
    con = connect_read(db)
    try:
        r = serve_full_text(con, "doc-legacy")
    finally:
        con.close()
    assert r.servable is True and r.full_text is not None
    assert r.structured_blocks is None


# ── gated → structured_blocks are WITHHELD (same as full_text) ──────


def test_gated_book_withholds_structured_blocks(db):
    """A gated book serves a bounded snippet but NO full body — and NO structured
    blocks. The §9.0 leak this guards: serving structured blocks where full_text
    is withheld. Both must be None for a gated book even though the COLUMN is
    populated (the gate, not the column, decides what leaves storage)."""
    _insert(
        db, "doc-gated",
        content_class=GATED_DEFAULT_CONTENT_CLASS, structured_blocks=_BLOCKS_JSON,
    )
    con = connect_read(db)
    try:
        r = serve_full_text(con, "doc-gated")
    finally:
        con.close()
    assert r.servable is False
    assert r.full_text is None
    assert r.snippet is not None  # bounded snippet (fair-use regime)
    # Structured blocks are withheld in lockstep with full_text, even though the
    # documents.structured_blocks column is populated — the gate withholds.
    assert r.structured_blocks is None


# ── taken-down → structured_blocks are WITHHELD (no body at all) ────


def test_taken_down_book_withholds_structured_blocks(db):
    """A taken-down book serves no body, no snippet — and no structured blocks.
    Removal is absolute; the structured column is withheld with everything else.
    Uses the real register→takedown path."""
    _insert(db, "doc-td", content_class="public_domain", structured_blocks=_BLOCKS_JSON)
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(con, document_id="doc-td", content_class="public_domain")
    finally:
        con.close()
    # It serves first (servable, blocks present) — proving the takedown is what
    # withholds them, not a pre-existing absence.
    con = connect_read(db)
    try:
        before = serve_full_text(con, "doc-td")
    finally:
        con.close()
    assert before.servable is True and before.structured_blocks == _BLOCKS_JSON

    con = connect_write(db, purpose="takedown")
    try:
        assert takedown.take_down(con, "doc-td", reason="rights-holder demand") is True
    finally:
        con.close()

    con = connect_read(db)
    try:
        after = serve_full_text(con, "doc-td")
    finally:
        con.close()
    assert after.servable is False and after.reason == "taken_down"
    assert after.full_text is None and after.snippet is None
    assert after.structured_blocks is None


# ── the guard preserves the gate's structured_blocks verdict ────────


def test_guarded_serve_preserves_structured_blocks_verdict(db):
    """serve_full_text_guarded (the API-side gate) preserves the structured_blocks
    decision the bare gate made — it only ENRICHES with rights context, never
    re-decides what body leaves storage. So a servable book keeps its blocks and a
    gated book keeps None through the guard."""
    _insert(db, "doc-srv", content_class="public_domain", structured_blocks=_BLOCKS_JSON)
    _insert(
        db, "doc-gtd",
        content_class=GATED_DEFAULT_CONTENT_CLASS, structured_blocks=_BLOCKS_JSON,
    )
    con = connect_read(db)
    try:
        g_srv = serve_full_text_guarded(con, "doc-srv")
        g_gtd = serve_full_text_guarded(con, "doc-gtd")
        bare_srv = serve_full_text(con, "doc-srv")
        bare_gtd = serve_full_text(con, "doc-gtd")
    finally:
        con.close()
    # The guard's structured_blocks matches the bare gate's on both verdicts.
    assert g_srv.structured_blocks == bare_srv.structured_blocks == _BLOCKS_JSON
    assert g_gtd.structured_blocks is bare_gtd.structured_blocks is None


# ── endpoint projection: the verdict reaches the wire intact ────────


def test_full_text_endpoint_projects_structured_blocks(db):
    """GET /books/{id}/full-text returns structured_blocks for a servable book
    and None for a gated one — the gate's §9.0 verdict reaches the JSON wire
    intact (gated identically to full_text)."""
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    _insert(db, "doc-srv", content_class="public_domain", structured_blocks=_BLOCKS_JSON)
    _insert(
        db, "doc-gtd",
        content_class=GATED_DEFAULT_CONTENT_CLASS, structured_blocks=_BLOCKS_JSON,
    )
    client = TestClient(
        create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    )

    srv = client.get("/books/doc-srv/full-text")
    assert srv.status_code == 200
    srv_body = srv.json()
    assert srv_body["servable"] is True
    assert srv_body["full_text"] is not None
    assert srv_body["structured_blocks"] == _BLOCKS_JSON  # served for a servable book

    gtd = client.get("/books/doc-gtd/full-text")
    assert gtd.status_code == 200
    gtd_body = gtd.json()
    assert gtd_body["servable"] is False
    assert gtd_body["full_text"] is None
    # Gated identically to full_text — withheld on the wire.
    assert gtd_body["structured_blocks"] is None
