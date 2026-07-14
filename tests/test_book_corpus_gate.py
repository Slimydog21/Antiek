"""Read SPR-01 — servable-corpus legal gate tests.

The keystone sprint of the Read workflow. These tests are the mechanical
gates the spec demands: deny-by-default servability, data-layer
enforcement of full-text serving (bypassing the UI), takedown that purges
cached full text, and the rigor #3 rights edge cases. They sit alongside
``test_retrieval_time_gate.py`` — that file tests the chunk-search G1
gate; this one tests the *full-text serve* gate that reuses the same
``content_class`` column with stricter, deny-by-default semantics.

The single most important assertion in this file: a non-servable book's
full text cannot be pulled out at the DATA layer, with the UI entirely
out of the picture (``test_data_layer_enforcement_bypasses_ui``).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from runtime.db_lock import connect_read, connect_write
from services.html_projection.reader_store import (
    atomic_write_reader_snapshot,
    reader_snapshot_path_for,
)
from substrate.books import ingest as bingest
from substrate.books import serve, takedown
from substrate.books.model import TocItem, get_book_asset, upsert_book_asset
from substrate.books.servability import (
    ServabilityStatus,
    is_servable_full_text,
    servability_of,
)
from substrate.constants import (
    BOOK_DEFAULT_SERVABILITY,
    SERVABLE_CONTENT_CLASSES,
    SOURCE_DECLARED_OPEN_CONTENT_CLASS,
    SYSTEM_INVESTIGATION_ID,
    TAKEDOWN_CONTENT_CLASS,
)
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database, list_tables

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) * (i + 1) for i, c in enumerate(text)) or 1
        return [
            float(h % 7) / 7.0,
            float((h >> 3) % 11) / 11.0,
            float((h >> 5) % 13) / 13.0,
            float((h >> 7) % 17) / 17.0,
        ]


@pytest.fixture
def db(monkeypatch):
    """Isolated graph DB + events dir, wired through the env vars the
    API + emit paths resolve. Returns the db_path."""
    tmp = tempfile.mkdtemp(prefix="antiek-book-gate-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    con = connect_write(db_path, purpose="book-gate-test")
    init_database(con)
    con.close()
    return db_path


def _insert_book(
    db_path: str,
    document_id: str,
    *,
    raw_text: str = "FULL BODY TEXT. " * 80,
    with_chunk: bool = True,
    title: str = "A Book",
    author: str = "An Author",
) -> None:
    """Insert a bare book document (+ optional chunk) with NULL
    content_class — the realistic pre-registration state."""
    con = connect_write(db_path, purpose="insert")
    insert_document(
        con,
        document_id=document_id,
        source_tier=2,
        document_type="book",
        title=title,
        author=author,
        raw_text=raw_text,
    )
    if with_chunk:
        insert_chunk(
            con,
            document_id=document_id,
            chunk_index=0,
            text="chunk body text about quantum",
            token_count=5,
            embedding=StubEmbedding().encode("chunk body text about quantum"),
        )
    con.close()


# ---------------------------------------------------------------------------
# M2 — servability projection + deny-by-default
# ---------------------------------------------------------------------------


def test_servability_projection_is_deny_by_default():
    """Unknown / NULL / restricted content all resolve to gated — the
    deny-by-default branch that catches 'aggregated from online'."""
    assert servability_of(None) is ServabilityStatus.GATED_METADATA_ONLY
    assert servability_of("restricted_pending_opt_in") is ServabilityStatus.GATED_METADATA_ONLY
    assert servability_of("some_unrecognised_value") is ServabilityStatus.GATED_METADATA_ONLY
    assert not is_servable_full_text(servability_of(None))


def test_servability_projection_servable_classes():
    assert servability_of("public_domain") is ServabilityStatus.PUBLIC_DOMAIN
    assert servability_of("user_owned") is ServabilityStatus.PLATFORM_AUTHORED
    assert servability_of("user_public_contribution") is ServabilityStatus.PLATFORM_AUTHORED
    assert servability_of("opt_in_licensed") is ServabilityStatus.PUBLISHER_OPTED_IN
    # 2026-05-29 remap: source_declared_open (CC-BY/CC-BY-SA) is its own servable
    # status, distinct from PUBLISHER_OPTED_IN.
    assert servability_of("source_declared_open") is ServabilityStatus.SOURCE_DECLARED_OPEN
    for cc in ("public_domain", "user_owned", "opt_in_licensed", "source_declared_open"):
        assert is_servable_full_text(servability_of(cc))


def test_takedown_overrides_license_in_projection():
    """A taken-down public-domain book projects to TAKEN_DOWN — the
    override wins over the (preserved) license."""
    assert servability_of("public_domain", taken_down=True) is ServabilityStatus.TAKEN_DOWN
    assert not is_servable_full_text(servability_of("public_domain", taken_down=True))


def test_projection_allowlist_matches_constant():
    """The set of content classes the projection calls servable MUST
    equal SERVABLE_CONTENT_CLASSES (the SQL allowlist). The import-time
    assert guards it; this is the regression test that keeps it visible."""
    projected = {
        cc
        for cc in (
            "public_domain",
            "user_owned",
            "user_public_contribution",
            "opt_in_licensed",
            "source_declared_open",
            "restricted_pending_opt_in",
        )
        if is_servable_full_text(servability_of(cc))
    }
    assert projected == set(SERVABLE_CONTENT_CLASSES)


def test_default_servability_constant_is_gated():
    assert ServabilityStatus.GATED_METADATA_ONLY.value == BOOK_DEFAULT_SERVABILITY


# ---------------------------------------------------------------------------
# M1 — book model + M7 single-writer
# ---------------------------------------------------------------------------


def test_book_asset_table_exists(db):
    con = connect_read(db)
    try:
        assert "book_assets" in list_tables(con)
    finally:
        con.close()


def test_book_model_stores_toc_and_reloads(db):
    _insert_book(db, "doc-book-toc")
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(
            con,
            document_id="doc-book-toc",
            toc=[TocItem("Chapter 1", 0, 0), TocItem("1.1 Intro", 2, 1)],
            page_count=42,
            provenance="test",
        )
    finally:
        con.close()
    con = connect_read(db)
    try:
        asset = get_book_asset(con, "doc-book-toc")
    finally:
        con.close()
    assert asset is not None
    assert asset.page_count == 42
    assert asset.pagination_scheme == "pdf_page"
    assert [t.title for t in asset.toc] == ["Chapter 1", "1.1 Intro"]
    assert asset.toc[1].level == 1


def test_book_writes_require_locked_connection(db):
    """M7: book_assets writes reject a raw (non-locked) connection."""
    raw = connect_read(db)  # read-only, not a LockedConnection
    try:
        with pytest.raises(TypeError, match="LockedConnection"):
            upsert_book_asset(raw, document_id="doc-x", page_count=1)
    finally:
        raw.close()


# ---------------------------------------------------------------------------
# M3 — data-layer enforcement on full-text serve
# ---------------------------------------------------------------------------


def test_gated_book_full_text_denied_at_data_layer(db):
    """A book with no license defaults to gated; full text is denied."""
    _insert_book(db, "doc-gated")
    con = connect_write(db, purpose="register")
    try:
        asset = bingest.register_book(con, document_id="doc-gated", provenance="online")
    finally:
        con.close()
    assert asset.servability is ServabilityStatus.GATED_METADATA_ONLY
    assert asset.servable_full_text is False

    con = connect_read(db)
    try:
        r = serve.serve_full_text(con, "doc-gated")
    finally:
        con.close()
    assert r.servable is False
    assert r.full_text is None
    assert r.snippet is not None  # bounded Authors-Guild-v-Google snippet
    assert r.reason == "gated_metadata_only"


def test_data_layer_enforcement_bypasses_ui(db):
    """THE keystone test. With the UI entirely out of the picture — a
    raw read connection calling the serve function directly — full text
    of a non-servable book is still blocked. The gate is in the data
    layer, not the UI."""
    _insert_book(db, "doc-restricted", raw_text="SECRET COPYRIGHTED BODY " * 50)
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(
            con,
            document_id="doc-restricted",
            content_class="restricted_pending_opt_in",
            provenance="aggregated, unknown rights",
        )
    finally:
        con.close()
    # Bypass every surface: open the DB read-only and ask the serve
    # function for full text directly.
    con = connect_read(db)
    try:
        r = serve.serve_full_text(con, "doc-restricted")
        # And the rawest possible bypass: even a hand-written SELECT only
        # yields the body because we DIDN'T gate the raw table — the gate
        # is the serve function. Confirm the function refused.
        raw_body = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?",
            ["doc-restricted"],
        ).fetchone()[0]
    finally:
        con.close()
    assert r.full_text is None, "data-layer gate leaked full text of a gated book"
    # A gated book may return a bounded snippet (Authors Guild v. Google),
    # but never the whole body: the snippet is length-capped + truncated.
    assert r.snippet is not None and r.snippet.endswith("…")
    assert len(r.snippet) < len(raw_body), "snippet is not bounded below full body"
    # The body is still in raw_text (gating withholds serving; it doesn't
    # delete) — but the serve function never returned it.
    assert raw_body is not None


def test_servable_book_serves_full_text(db):
    _insert_book(db, "doc-public", raw_text="PUBLIC DOMAIN BODY " * 60)
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(
            con,
            document_id="doc-public",
            content_class="public_domain",
            license_basis="published 1850, out of copyright",
        )
    finally:
        con.close()
    con = connect_read(db)
    try:
        r = serve.serve_full_text(con, "doc-public")
    finally:
        con.close()
    assert r.servable is True
    assert r.full_text is not None and "PUBLIC DOMAIN BODY" in r.full_text
    assert r.snippet is None


def test_serve_unknown_document_is_not_found(db):
    con = connect_read(db)
    try:
        r = serve.serve_full_text(con, "doc-does-not-exist")
    finally:
        con.close()
    assert r.found is False
    assert r.full_text is None


# ---------------------------------------------------------------------------
# M4 — takedown
# ---------------------------------------------------------------------------


def test_takedown_purges_cached_full_text_and_blocks_serve(db):
    """Serve a servable book, then take it down; the cached full text is
    purged (raw_text nulled) and serving is blocked — not even a
    snippet."""
    _insert_book(db, "doc-td", raw_text="SERVABLE BODY " * 40)
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(con, document_id="doc-td", content_class="public_domain")
    finally:
        con.close()
    snapshot_path = reader_snapshot_path_for("doc-td")
    atomic_write_reader_snapshot(
        snapshot_path,
        "<!doctype html><article>LEAKABLE SERVABLE BODY</article>",
    )
    # Confirm it served first.
    con = connect_read(db)
    try:
        assert serve.serve_full_text(con, "doc-td").servable is True
    finally:
        con.close()
    # Take it down.
    con = connect_write(db, purpose="takedown")
    try:
        performed = takedown.take_down(con, "doc-td", reason="rights-holder demand")
    finally:
        con.close()
    assert performed is True
    con = connect_read(db)
    try:
        r = serve.serve_full_text(con, "doc-td")
        raw = con.execute(
            "SELECT content_class, raw_text, metadata FROM documents WHERE document_id=?",
            ["doc-td"],
        ).fetchone()
    finally:
        con.close()
    assert r.servable is False
    assert r.reason == "taken_down"
    assert r.full_text is None
    assert r.snippet is None, "taken-down book must not even return a snippet"
    # Cached full text purged + retrieval restricted via the existing gate.
    assert raw[0] == TAKEDOWN_CONTENT_CLASS
    assert raw[1] is None, "raw_text (the cached served full text) was not purged"
    receipt = Path(snapshot_path).read_text(encoding="utf-8")
    assert "LEAKABLE SERVABLE BODY" not in receipt
    assert "<strong>viewability</strong> non-viewable" in receipt
    assert "<strong>servability</strong> taken_down" in receipt
    metadata = json.loads(raw[2])
    assert metadata["reader_projection_state"] == "ready"
    assert metadata["reader_projection_reason"] == "taken_down"


def test_takedown_excludes_book_from_chunk_search_gate(db):
    """The keystone reuse: takedown moves content_class to the existing
    restricted gate, so the chunk-search G1 gate (search.py) ALSO excludes
    the book — no new gating mechanism, removal from EVERY retrieval
    path."""
    from substrate.graph.search import search

    # Unique title so we can identify this book in chunk-search results
    # (results expose document_title, and chunk_id is content-addressed).
    title = "Quantum Takedown Probe Title"
    _insert_book(db, "doc-td2", raw_text="quantum body " * 40, title=title)
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(con, document_id="doc-td2", content_class="public_domain")
    finally:
        con.close()
    embed = StubEmbedding()

    def _hits(con) -> bool:
        res = search(con, "quantum", model=embed, top_k=10)
        return any(r["document_title"] == title for r in res["results"])

    # Before takedown: the chunk is retrievable on the attribution path.
    con = connect_read(db)
    try:
        assert _hits(con) is True
    finally:
        con.close()
    # Take down, then the same attribution-path search must exclude it.
    con = connect_write(db, purpose="takedown")
    try:
        takedown.take_down(con, "doc-td2", reason="dmca")
    finally:
        con.close()
    con = connect_read(db)
    try:
        assert _hits(con) is False, (
            "taken-down book still retrievable via chunk-search gate; "
            "takedown must remove from every retrieval path"
        )
    finally:
        con.close()


def test_takedown_is_idempotent(db):
    _insert_book(db, "doc-td3")
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(con, document_id="doc-td3", content_class="public_domain")
    finally:
        con.close()
    con = connect_write(db, purpose="takedown")
    try:
        first = takedown.take_down(con, "doc-td3", reason="x")
        second = takedown.take_down(con, "doc-td3", reason="x again")
    finally:
        con.close()
    assert first is True
    assert second is False  # already down; no second purge / event


def test_takedown_emits_audit_events(db):
    """The action is audited: book.taken_down + book.servability_changed
    land in the trajectory, reconstructable later."""
    from substrate.event_log import trajectory

    _insert_book(db, "doc-td4", raw_text="body " * 40)
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(con, document_id="doc-td4", content_class="public_domain")
    finally:
        con.close()
    con = connect_write(db, purpose="takedown")
    try:
        takedown.take_down(con, "doc-td4", reason="audited demand")
    finally:
        con.close()
    events = trajectory(SYSTEM_INVESTIGATION_ID)
    td_events = [
        e
        for e in events
        if e.get("action_type") == "book.taken_down" and e.get("document_id") == "doc-td4"
    ]
    assert len(td_events) == 1
    payload = td_events[0]["payload"]
    assert payload["reason"] == "audited demand"
    assert payload["purged_full_text"] is True
    assert payload["previous_content_class"] == "public_domain"
    assert any(
        e.get("action_type") == "book.servability_changed" and e.get("document_id") == "doc-td4"
        for e in events
    )


def test_reinstate_restores_license_but_not_body(db):
    _insert_book(db, "doc-td5", raw_text="body " * 40)
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(con, document_id="doc-td5", content_class="public_domain")
    finally:
        con.close()
    con = connect_write(db, purpose="td")
    try:
        takedown.take_down(con, "doc-td5", reason="x")
    finally:
        con.close()
    con = connect_write(db, purpose="reinstate")
    try:
        reinstated = takedown.reinstate(con, "doc-td5")
    finally:
        con.close()
    assert reinstated is True
    con = connect_read(db)
    try:
        asset = get_book_asset(con, "doc-td5")
        raw = con.execute(
            "SELECT raw_text FROM documents WHERE document_id=?", ["doc-td5"]
        ).fetchone()[0]
    finally:
        con.close()
    assert asset.content_class == "public_domain"  # license restored
    assert asset.taken_down is False
    assert raw is None, "raw_text stays purged after reinstate — re-ingest required"


def test_takedown_unregistered_book_raises(db):
    _insert_book(db, "doc-noasset", with_chunk=False)  # document but no book_assets
    con = connect_write(db, purpose="td")
    try:
        with pytest.raises(takedown.BookNotRegistered):
            takedown.take_down(con, "doc-noasset", reason="x")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# M5 — ingest provenance + aggregate-defaults-gated + ip_holder
# ---------------------------------------------------------------------------


def test_aggregated_unknown_rights_defaults_gated(db):
    """A book aggregated 'from online' with unknown rights (no
    content_class passed) lands gated_metadata_only."""
    _insert_book(db, "doc-agg")
    con = connect_write(db, purpose="register")
    try:
        asset = bingest.register_book(
            con,
            document_id="doc-agg",
            provenance="scraped from a public website",
        )
    finally:
        con.close()
    assert asset.servability is ServabilityStatus.GATED_METADATA_ONLY
    assert asset.provenance == "scraped from a public website"
    assert asset.content_class == TAKEDOWN_CONTENT_CLASS  # the gated/restricted state


def test_ingest_sets_ip_holder_from_rights_holder_name(db):
    """A named rights holder gets a found-or-created pre-onboarded escrow
    account; the document carries its ip_holder_id."""
    from substrate import ip_holders

    _insert_book(db, "doc-ip")
    con = connect_write(db, purpose="register")
    try:
        asset = bingest.register_book(
            con,
            document_id="doc-ip",
            content_class="opt_in_licensed",
            rights_holder_name="MIT Press",
        )
        holder = ip_holders.get(con, asset.ip_holder_id)
    finally:
        con.close()
    assert asset.ip_holder_id is not None
    assert holder is not None
    assert holder.display_name == "MIT Press"
    assert holder.status == "pre_onboarded"


def test_ingest_ip_holder_is_idempotent_on_name(db):
    """Re-ingesting another book from the same publisher reuses the
    escrow account rather than fanning out duplicates."""
    from substrate import ip_holders

    _insert_book(db, "doc-ip-a")
    _insert_book(db, "doc-ip-b")
    con = connect_write(db, purpose="register")
    try:
        a = bingest.register_book(
            con,
            document_id="doc-ip-a",
            content_class="opt_in_licensed",
            rights_holder_name="Cambridge University Press",
        )
        b = bingest.register_book(
            con,
            document_id="doc-ip-b",
            content_class="opt_in_licensed",
            rights_holder_name="Cambridge University Press",
        )
        holders = [
            h for h in ip_holders.list_all(con) if h.display_name == "Cambridge University Press"
        ]
    finally:
        con.close()
    assert a.ip_holder_id == b.ip_holder_id
    assert len(holders) == 1


def test_register_rejects_unknown_content_class(db):
    _insert_book(db, "doc-bad")
    con = connect_write(db, purpose="register")
    try:
        # The rights core now delegates to substrate.rights.register, whose
        # validation message is source-agnostic ("unrecognised content_class").
        with pytest.raises(ValueError, match="unrecognised content_class"):
            bingest.register_book(con, document_id="doc-bad", content_class="totally_made_up")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# M6 — servable-corpus query API
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def _register(db, document_id, content_class=None, **kw):
    _insert_book(db, document_id)
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(con, document_id=document_id, content_class=content_class, **kw)
    finally:
        con.close()


def test_api_lists_only_servable_by_default(db, client):
    _register(db, "doc-srv-1", content_class="public_domain")
    _register(db, "doc-srv-2", content_class="opt_in_licensed", rights_holder_name="MIT Press")
    _register(db, "doc-gated-1")  # gated default

    res = client.get("/books")
    assert res.status_code == 200
    body = res.json()
    ids = {b["document_id"] for b in body["books"]}
    assert ids == {"doc-srv-1", "doc-srv-2"}
    assert all(b["servable_full_text"] for b in body["books"])


def test_api_lists_gated_flagged(db, client):
    _register(db, "doc-srv-3", content_class="public_domain")
    _register(db, "doc-gated-2")
    res = client.get("/books", params={"status": "gated"})
    body = res.json()
    ids = {b["document_id"] for b in body["books"]}
    assert ids == {"doc-gated-2"}
    assert all(not b["servable_full_text"] for b in body["books"])
    assert all(b["servability"] == "gated_metadata_only" for b in body["books"])


def test_api_book_detail_carries_toc_never_full_text(db, client):
    _insert_book(db, "doc-detail", raw_text="BODY " * 50)
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(
            con,
            document_id="doc-detail",
            content_class="public_domain",
            toc=[TocItem("Ch 1", 0, 0)],
            page_count=12,
        )
    finally:
        con.close()
    res = client.get("/books/doc-detail")
    assert res.status_code == 200
    body = res.json()
    assert body["toc"][0]["title"] == "Ch 1"
    assert body["page_count"] == 12
    assert "full_text" not in body  # detail never inlines the body


def test_api_full_text_endpoint_enforces_gate(db, client):
    _insert_book(db, "doc-api-gated", raw_text="GATED BODY " * 50)
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(con, document_id="doc-api-gated")  # gated
    finally:
        con.close()
    res = client.get("/books/doc-api-gated/full-text")
    assert res.status_code == 200
    body = res.json()
    assert body["servable"] is False
    assert body["full_text"] is None
    assert body["chunks"] == []
    assert body["snippet"] is not None


def test_api_full_text_serves_servable(db, client):
    _insert_book(db, "doc-api-srv", raw_text="OPEN BODY " * 50)
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(con, document_id="doc-api-srv", content_class="public_domain")
    finally:
        con.close()
    res = client.get("/books/doc-api-srv/full-text")
    body = res.json()
    assert body["servable"] is True
    assert "OPEN BODY" in body["full_text"]
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["chunk_id"]
    assert body["chunks"][0]["page_index"] is None


def test_api_full_text_manifest_is_ordered_and_page_owned(db, client):
    _insert_book(db, "doc-api-manifest", raw_text="## Page 1\nFirst.\n## Page 2\nSecond.", with_chunk=False)
    con = connect_write(db, purpose="reader-manifest")
    try:
        bingest.register_book(con, document_id="doc-api-manifest", content_class="public_domain")
        second = insert_chunk(
            con,
            document_id="doc-api-manifest",
            chunk_index=1,
            text="## Page 2\nSecond.",
            section_path="Page 2",
            token_count=3,
        )
        first = insert_chunk(
            con,
            document_id="doc-api-manifest",
            chunk_index=0,
            text="## Page 1\nFirst.",
            section_path="Page 1",
            token_count=3,
        )
    finally:
        con.close()

    body = client.get("/books/doc-api-manifest/full-text").json()
    assert [chunk["chunk_id"] for chunk in body["chunks"]] == [first, second]
    assert [chunk["chunk_index"] for chunk in body["chunks"]] == [0, 1]
    assert [chunk["page_index"] for chunk in body["chunks"]] == [0, 1]


def test_api_full_text_unknown_404(db, client):
    assert client.get("/books/doc-nope/full-text").status_code == 404


def test_api_chunk_anchor_resolves_only_for_servable_owning_book(db, client):
    _insert_book(db, "doc-anchor")
    con = connect_write(db, purpose="anchor-seed")
    try:
        bingest.register_book(
            con,
            document_id="doc-anchor",
            content_class="public_domain",
            license_basis="public domain",
        )
        chunk_id = con.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = 'doc-anchor'"
        ).fetchone()[0]
        con.execute(
            "UPDATE chunks SET section_path = 'Page 3' WHERE chunk_id = ?",
            [chunk_id],
        )
    finally:
        con.close()

    body = client.get(f"/books/doc-anchor/chunk-anchors/{chunk_id}").json()
    assert body == {
        "document_id": "doc-anchor",
        "chunk_id": chunk_id,
        "page_index": 2,
        "page_resolved": True,
        "reason": "page_resolved",
    }


def test_api_chunk_anchor_is_honest_when_page_unresolved(db, client):
    _insert_book(db, "doc-anchor-chapter")
    con = connect_write(db, purpose="anchor-unresolved")
    try:
        bingest.register_book(
            con,
            document_id="doc-anchor-chapter",
            content_class="public_domain",
            license_basis="public domain",
        )
        chunk_id = con.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = 'doc-anchor-chapter'"
        ).fetchone()[0]
        con.execute(
            "UPDATE chunks SET section_path = 'Chapter Four' WHERE chunk_id = ?",
            [chunk_id],
        )
    finally:
        con.close()

    body = client.get(f"/books/doc-anchor-chapter/chunk-anchors/{chunk_id}").json()
    assert body["page_index"] is None
    assert body["page_resolved"] is False
    assert body["reason"] == "page_not_resolved"


def test_api_chunk_anchor_rejects_wrong_document_and_gated_body(db, client):
    _insert_book(db, "doc-anchor-a")
    _insert_book(db, "doc-anchor-b", with_chunk=False)
    con = connect_write(db, purpose="anchor-boundary")
    try:
        bingest.register_book(
            con, document_id="doc-anchor-a", content_class="public_domain",
        )
        bingest.register_book(
            con,
            document_id="doc-anchor-b",
            content_class="restricted_pending_opt_in",
        )
        chunk_a = con.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = 'doc-anchor-a'"
        ).fetchone()[0]
        chunk_b = insert_chunk(
            con,
            document_id="doc-anchor-b",
            chunk_index=0,
            text="distinct gated chunk body",
            token_count=4,
            embedding=StubEmbedding().encode("distinct gated chunk body"),
        )
    finally:
        con.close()

    assert client.get(
        f"/books/doc-anchor-a/chunk-anchors/{chunk_b}"
    ).status_code == 404
    gated = client.get(f"/books/doc-anchor-b/chunk-anchors/{chunk_b}")
    assert gated.status_code == 403
    assert "chunk body text" not in gated.text
    assert chunk_a != chunk_b


def _insert_arxiv_t1(db_path, document_id, *, arxiv_id, license_uri):
    """Insert a servable arXiv doc (CC-BY / T1) the way the OAI persist path
    stamps it — content_class ``source_declared_open`` (servable) plus a
    metadata blob carrying ``license_uri`` + ``arxiv_id``. A deliberately LYING
    stored ``rights_tier='T3'`` proves the response tier is re-derived from the
    license URI, not echoed from the stored value."""
    con = connect_write(db_path, purpose="insert-arxiv")
    try:
        insert_document(
            con,
            document_id=document_id,
            source_tier=3,
            document_type="academic_paper",
            title="An arXiv Paper",
            author="A. Author",
            raw_text="OPEN ARXIV BODY. " * 60,
            content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS,
            metadata={
                "source": "arxiv_oai_pmh",
                "license_uri": license_uri,
                "arxiv_id": arxiv_id,
                "rights_tier": "T3",  # a LIE; response must re-derive to T1
            },
        )
    finally:
        con.close()


def test_api_full_text_response_carries_rights_context_for_t1_arxiv(db, client):
    """ROUTE-SEAM ENFORCEMENT (Read SPR-05): the full-text JSON response must
    carry the four rights-context fields the data-driven reader renders off —
    ``tier``, ``ad_eligible``, ``canonical_url``, ``license`` — with the values
    the guard resolved for a servable T1 (CC-BY) arXiv doc.

    This is the test the critic's send-back demanded: it FAILS if ANY of the four
    field-mappings (``tier=``, ``ad_eligible=``, ``canonical_url=``, ``license=``)
    is deleted from the ``get_book_full_text`` handler, because the pydantic model
    then defaults that field (``None`` / ``False``) and the assertion below sees
    the wrong value. The four assertions are individually load-bearing — no one
    of them can be removed without losing coverage of one mapping."""
    _insert_arxiv_t1(
        db,
        "doc-api-arxiv-t1",
        arxiv_id="2405.00005",
        license_uri="http://creativecommons.org/licenses/by/4.0/",
    )
    res = client.get("/books/doc-api-arxiv-t1/full-text")
    assert res.status_code == 200
    body = res.json()
    # Serve decision: a servable T1 body is emitted.
    assert body["servable"] is True
    assert "OPEN ARXIV BODY" in body["full_text"]
    # The four rights-context fields, each guarding one handler mapping.
    assert body["tier"] == "T1"  # re-derived from the license, not the stored T3 lie
    assert body["ad_eligible"] is True  # ads_allowed(T1)
    assert body["canonical_url"] == "https://arxiv.org/abs/2405.00005"
    assert body["license"] == "http://creativecommons.org/licenses/by/4.0/"


# ---------------------------------------------------------------------------
# Rigor #3 — the rights edge cases the spec names explicitly
# ---------------------------------------------------------------------------


def test_public_domain_text_with_copyrighted_translation_is_gated_when_uncertain(db):
    """A public-domain work can carry a copyrighted modern translation.
    When provenance is uncertain, the operator does NOT pass a servable
    content_class — so it lands gated. Intellectual honesty (rigor #1):
    a hopeful classifier must not mark uncertain content servable."""
    _insert_book(db, "doc-translation", title="The Odyssey (Fagles trans.)")
    con = connect_write(db, purpose="register")
    try:
        asset = bingest.register_book(
            con,
            document_id="doc-translation",
            provenance="public-domain work, but this edition is a 1996 translation",
            license_basis="underlying work PD; THIS translation may be in copyright — gated",
        )
    finally:
        con.close()
    assert asset.servability is ServabilityStatus.GATED_METADATA_ONLY


def test_takedown_mid_read_blocks_subsequent_serve(db):
    """Takedown mid-read: a reader who fetched full text once gets nothing
    on the next fetch. The serve function is the gate, evaluated per
    request — there's no cached grant."""
    _insert_book(db, "doc-midread", raw_text="MID READ BODY " * 40)
    con = connect_write(db, purpose="register")
    try:
        bingest.register_book(con, document_id="doc-midread", content_class="public_domain")
    finally:
        con.close()
    con = connect_read(db)
    try:
        first = serve.serve_full_text(con, "doc-midread")
    finally:
        con.close()
    assert first.servable is True
    con = connect_write(db, purpose="td")
    try:
        takedown.take_down(con, "doc-midread", reason="demand arrived mid-read")
    finally:
        con.close()
    con = connect_read(db)
    try:
        second = serve.serve_full_text(con, "doc-midread")
    finally:
        con.close()
    assert second.servable is False
    assert second.full_text is None


def test_partial_opt_in_book_each_resolves_independently(db):
    """Two books from the same publisher: one opted-in, one still gated.
    Servability is per-book — a publisher opt-in doesn't blanket-serve
    everything attributed to them until each book is licensed."""
    _insert_book(db, "doc-pub-in")
    _insert_book(db, "doc-pub-pending")
    con = connect_write(db, purpose="register")
    try:
        a = bingest.register_book(
            con,
            document_id="doc-pub-in",
            content_class="opt_in_licensed",
            rights_holder_name="Princeton University Press",
        )
        b = bingest.register_book(
            con,
            document_id="doc-pub-pending",
            rights_holder_name="Princeton University Press",  # gated default
        )
    finally:
        con.close()
    assert a.servable_full_text is True
    assert b.servable_full_text is False
    assert a.ip_holder_id == b.ip_holder_id  # same publisher, different servability
