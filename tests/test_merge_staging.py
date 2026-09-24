"""Tests for the SPR-01 staging → merge write path.

The keystone contract, proven mechanically (not by reasoning):

- M2  staging mode performs ZERO live writes during ingest, and embeds in
      staging (non-null vectors land in the staging chunks table).
- M3  the merge reproduces the staged net-new per-table counts into a temp
      live DB; merge is dependency-ordered (no orphans).
- M4  chunk/node vectors are COPIED element-identically, never recomputed
      (no embedding-model call in the merge module).
- M5  re-merge inserts 0 rows (idempotent on the content-stable id); a forced
      mid-merge exception rolls back to pre-merge counts (atomic); after the
      interruption a clean re-run yields the same final counts (resumable);
      and idempotency keys on document_id, not a mutable title.
- M6  the live DB is readable throughout a staging ingest (no ingest-
      attributable blocked reads), and the connect_write-held merge window is
      bounded to seconds, recorded distinct from the ingest duration.

Strategy: build populated staging DBs through the REAL ingest path
(`acquisition.books.ingest_servable_book`) using the project's stub-reader +
stub-embedder pattern, so the test exercises exactly what production writes.
The merge then runs against temp live DBs. No network, no real PDFs, no real
embedding model.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

import duckdb
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# ---------------------------------------------------------------------------
# Stubs mirroring tests/test_acquisition_books.py so the ingest path is real
# but PDF-extraction + embedding are deterministic and offline.
# ---------------------------------------------------------------------------
from acquisition.books import ingest_servable_book  # noqa: E402
from runtime import db_lock  # noqa: E402
from runtime.db_lock import connect_read, connect_write  # noqa: E402
from runtime.staging_db import prepare_staging_db, resolve_ingest_target  # noqa: E402
from substrate.graph.migrate_v9_insight_question import (  # noqa: E402
    _already_has_insight_question,
)
from substrate.graph.schema import init_database, init_database_at_path  # noqa: E402
from tools.merge_staging import SchemaDivergence, merge_staging  # noqa: E402


class _StubPage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _StubReader:
    """Drop-in for pypdf.PdfReader, matching the contract the real reader
    uses: ``.pages`` (objects with ``extract_text``) and ``.metadata`` (an
    object with ``.get``). The body is fixed long text that clears the
    word-count gate; the document_id varies with the source bytes, which is
    what the merge keys on."""

    def __init__(self, _source=None, page_texts=None, meta=None):
        self._pages = [_StubPage(t) for t in (page_texts or [_LONG_PAGE, _LONG_PAGE])]
        self._meta = SimpleNamespace(get=lambda key, _m=(meta or {}): _m.get(key))

    @property
    def pages(self):
        return list(self._pages)

    @property
    def metadata(self):
        return self._meta


class _StubEmbedder:
    """Deterministic 16-dim embedding keyed on text, so a chunk's vector is a
    known function of its content — lets us assert byte/element identity after
    a merge without a real model."""

    dimension = 16
    provider_name = "stub"
    model_name = "stub-dim-16"

    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        # second non-zero element so the vector is not a trivial one-hot —
        # exercises multi-element copy fidelity.
        v[(h + 3) % 16] = 0.5
        return v


_LONG_PAGE = (
    "Long enough body to clear the MIN_INGEST_WORD_COUNT gate. "
    "Repeated text repeated text repeated text repeated text. " * 20
)


@pytest.fixture
def env(monkeypatch):
    """A tmp workspace + redirected event-log dir (events are JSONL files, not
    DB rows — redirect them so the test never writes into ~/.antiek)."""
    tmpdir = tempfile.mkdtemp(prefix="antiek-merge-test-")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    # Belt-and-suspenders: never let an unset db_path resolve to prod.
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "never-used.duckdb"))
    monkeypatch.setattr("acquisition.books.reader.PdfReader", _StubReader)
    yield {"tmpdir": tmpdir, "events_dir": events_dir}


def _stage_books(staging_path: str, books: list[dict]) -> list[str]:
    """Ingest the given books into the staging DB via the real path. Each
    book dict: {bytes, content_class?, rights_holder_name?}. Returns the
    document_ids."""
    prepare_staging_db(staging_path)
    doc_ids = []
    for b in books:
        res = ingest_servable_book(
            b["bytes"],
            investigation_id="inv-merge-test",
            content_class=b.get("content_class"),
            rights_holder_name=b.get("rights_holder_name"),
            db_path=staging_path,
            embedder=_StubEmbedder(),
        )
        doc_ids.append(res.document_id)
    return doc_ids


def _counts(db_path: str, tables=("documents", "chunks", "nodes", "book_assets", "ip_holders")):
    con = duckdb.connect(db_path, read_only=True)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    finally:
        con.close()


# A pre-V9 ``nodes`` table: the NARROW node_type CHECK (no insight/question),
# so ``init_database`` -> ``migrate_v9_insight_question`` actually rebuilds the
# table. This reproduces the prod live DB's provenance — built before a
# rebuilding migration ran — as opposed to a one-shot ``init_database_at_path``
# fresh DB whose tables were never rebuilt.
_LEGACY_PRE_V9_SQL = """
CREATE TABLE nodes (
    node_id          TEXT PRIMARY KEY,
    canonical_label  TEXT NOT NULL,
    node_type        TEXT NOT NULL CHECK (node_type IN (
        'entity','organization','person','property',
        'metric','mechanism','claim','method','constraint'
    )),
    embedding        FLOAT[],
    graph_scope      TEXT NOT NULL CHECK (graph_scope IN ('depth','cross_domain','constraint')),
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    degree_cached    INTEGER NOT NULL DEFAULT 0,
    metadata         TEXT
);
CREATE TABLE edges (
    edge_id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL REFERENCES nodes(node_id),
    target_node_id TEXT NOT NULL REFERENCES nodes(node_id),
    relation TEXT NOT NULL,
    chunk_id TEXT,
    source_document_id TEXT,
    source_tier INTEGER NOT NULL CHECK (source_tier BETWEEN 1 AND 5),
    extraction_confidence FLOAT NOT NULL CHECK (extraction_confidence >= 0 AND extraction_confidence <= 1),
    extracted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_from TIMESTAMP NOT NULL DEFAULT '1970-01-01',
    valid_until TIMESTAMP,
    superseded_by TEXT REFERENCES edges(edge_id),
    graph_scope TEXT NOT NULL CHECK (graph_scope IN ('depth','cross_domain','constraint')),
    investigation_id TEXT,
    metadata TEXT
);
"""


def _init_live_via_migration_path(live_path: str) -> None:
    """Build a live DB the way prod actually came to exist: a legacy schema
    (narrow node_type CHECK) that a later ``init_database`` upgrades by
    REBUILDING the nodes table via ``migrate_v9_insight_question``. This is the
    distinction the M2 acceptance criterion turns on — a one-shot
    ``init_database_at_path`` never rebuilds a table, so it can't surface a
    migration-induced column reorder; this path can."""
    con = connect_write(live_path, purpose="test-legacy-bootstrap")
    try:
        con.execute(_LEGACY_PRE_V9_SQL)
        assert not _already_has_insight_question(con), "legacy fixture is not legacy"
    finally:
        con.close()
    con = connect_write(live_path, purpose="test-init-over-legacy")
    try:
        init_database(con)  # invokes migrate_v9 → rebuilds nodes/edges
        assert _already_has_insight_question(con), "migration did not run"
    finally:
        con.close()


def _ordered_cols(db_path: str, table: str) -> list[str]:
    con = duckdb.connect(db_path, read_only=True)
    try:
        return [
            r[0]
            for r in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='main' AND table_name=? ORDER BY ordinal_position",
                [table],
            ).fetchall()
        ]
    finally:
        con.close()


# ---------------------------------------------------------------------------
# M2 — staging mode does zero live writes; embeds in staging
# ---------------------------------------------------------------------------


def test_staging_ingest_zero_live_writes(env):
    """A staging-mode ingest leaves the LIVE DB row counts unchanged for
    documents/book_assets/chunks/nodes (zero live writes during ingest)."""
    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)
    before = _counts(live)

    # The orchestrator routes the ingest's write target through this helper;
    # exercise it directly so the test pins the routing, not just the connectors.
    target = resolve_ingest_target(db_path=None, staging_db=staging)
    assert os.path.abspath(target) == os.path.abspath(staging)

    _stage_books(staging, [{"bytes": b"book-A", "content_class": "public_domain"}])

    after = _counts(live)
    assert after == before, "staging ingest must not touch the live DB"
    # but staging holds the rows
    staging_counts = _counts(staging)
    assert staging_counts["documents"] == 1
    assert staging_counts["chunks"] >= 1


def test_staging_chunks_have_nonnull_vectors(env):
    """The slow work (embedding) happens in staging: chunk vectors are
    present (non-null) in the staging chunks table."""
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    _stage_books(staging, [{"bytes": b"book-vec", "content_class": "public_domain"}])
    con = duckdb.connect(staging, read_only=True)
    try:
        total, embedded = con.execute(
            "SELECT COUNT(*), COUNT(embedding) FROM chunks"
        ).fetchone()
    finally:
        con.close()
    assert total >= 1
    assert embedded == total, "every staged chunk must carry a precomputed vector"


# ---------------------------------------------------------------------------
# M3 — counts match, dependency order, no orphans
# ---------------------------------------------------------------------------


def test_counts_match_after_merge(env):
    """Merging staging into a temp live DB reproduces staging's per-table row
    counts for net-new ids."""
    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)
    _stage_books(
        staging,
        [
            {"bytes": b"book-1", "content_class": "public_domain"},
            {"bytes": b"book-2", "rights_holder_name": "MIT Press"},
        ],
    )
    staging_counts = _counts(staging)

    result = merge_staging(live_db=live, staging_db=staging)

    live_counts = _counts(live)
    for table in ("documents", "chunks", "nodes", "book_assets", "ip_holders"):
        assert live_counts[table] == staging_counts[table], (
            f"{table}: live {live_counts[table]} != staging {staging_counts[table]}"
        )
    # the per-table insert summary equals the staged totals (fresh live)
    inserted = {t.table: t.inserted for t in result.tables}
    assert inserted["documents"] == staging_counts["documents"]
    assert inserted["chunks"] == staging_counts["chunks"]


def test_merge_releases_parked_staging_writer(env, monkeypatch):
    """Pre-existing defect: the continuous ingest stages rows and then calls
    merge_staging in the SAME process. With the warm-writer keepalive on
    (default 20 s; pytest disables it, so re-enable it here) the parked
    staging writer still holds the file and DuckDB refused the ATTACH with
    ``BinderException: Unique file handle conflict``. The merge must release
    that parked writer before attaching."""
    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)
    monkeypatch.setattr(db_lock, "_write_keepalive_s", lambda: 20.0)

    try:
        _stage_books(
            staging, [{"bytes": b"book-parked", "content_class": "public_domain"}]
        )
        # The control: the staging writer really is parked before the merge.
        assert db_lock._warm_key(staging) in db_lock._warm_slots

        result = merge_staging(live_db=live, staging_db=staging)

        assert result.total_inserted > 0
        assert db_lock._warm_key(staging) not in db_lock._warm_slots
        # The live writer parks on exit too; release it before reading.
        assert db_lock.flush_warm_writers(live) == 1
        assert _counts(live)["documents"] == 1
    finally:
        db_lock.flush_warm_writers(staging)
        db_lock.flush_warm_writers(live)


def test_merge_window_excludes_the_staging_close(env, monkeypatch):
    """Closing the parked staging writer happens under the write gate but
    before the live flock; the reported keystone window must not include it."""
    import tools.merge_staging as ms

    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)
    real_flush = db_lock.flush_warm_writers

    def slow_flush(path: str, **kw: object) -> int:
        time.sleep(0.6)  # a slow checkpoint-on-close
        return real_flush(path, **kw)

    monkeypatch.setattr(ms, "flush_warm_writers", slow_flush)
    try:
        _stage_books(
            staging, [{"bytes": b"book-slow-close", "content_class": "public_domain"}]
        )
        result = merge_staging(live_db=live, staging_db=staging)
        assert result.total_inserted > 0
        assert result.window_s < 0.5, result.window_s
    finally:
        db_lock.flush_warm_writers(staging)
        db_lock.flush_warm_writers(live)


def test_merge_fails_closed_when_the_staging_close_outlasts_its_bound(env, monkeypatch):
    """If the staging writer's expiry close cannot be waited out, the merge
    raises before the live DB is opened — never an ATTACH on an open handle."""
    import tools.merge_staging as ms

    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)

    def stuck_flush(path: str, **kw: object) -> int:
        raise db_lock.WarmWriterCloseTimeout("simulated: still closing")

    monkeypatch.setattr(ms, "flush_warm_writers", stuck_flush)
    try:
        _stage_books(
            staging, [{"bytes": b"book-stuck", "content_class": "public_domain"}]
        )
        with pytest.raises(db_lock.WarmWriterCloseTimeout):
            merge_staging(live_db=live, staging_db=staging)
        assert not db_lock._PROCESS_WRITE_GATE.locked()
        assert _counts(live)["documents"] == 0
    finally:
        db_lock.flush_warm_writers(staging)
        db_lock.flush_warm_writers(live)


def test_flush_warm_writers_without_slot(tmp_path):
    assert db_lock.flush_warm_writers(str(tmp_path / "absent.duckdb")) == 0


def test_merge_leaves_no_orphans(env):
    """After a merge every chunk + book_asset references a present document
    (dependency-ordered copy resolves FKs)."""
    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)
    _stage_books(staging, [{"bytes": b"book-orphan", "content_class": "public_domain"}])
    merge_staging(live_db=live, staging_db=staging)

    con = duckdb.connect(live, read_only=True)
    try:
        orphan_chunks = con.execute(
            "SELECT COUNT(*) FROM chunks c "
            "WHERE NOT EXISTS (SELECT 1 FROM documents d WHERE d.document_id=c.document_id)"
        ).fetchone()[0]
        orphan_assets = con.execute(
            "SELECT COUNT(*) FROM book_assets b "
            "WHERE NOT EXISTS (SELECT 1 FROM documents d WHERE d.document_id=b.document_id)"
        ).fetchone()[0]
    finally:
        con.close()
    assert orphan_chunks == 0
    assert orphan_assets == 0


def test_merge_preserves_content_class_not_redecided(env):
    """The merge copies whatever content_class the staged document carries —
    it does not re-derive servability (that is SPR-02)."""
    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)
    [doc_id] = _stage_books(
        staging, [{"bytes": b"book-cc", "content_class": "source_declared_open"}]
    )
    merge_staging(live_db=live, staging_db=staging)
    con = duckdb.connect(live, read_only=True)
    try:
        cc = con.execute(
            "SELECT content_class FROM documents WHERE document_id=?", [doc_id]
        ).fetchone()[0]
    finally:
        con.close()
    assert cc == "source_declared_open"


# ---------------------------------------------------------------------------
# M2/M3 — column-order safety across the migration path (sharpen defect #1)
#
# The merge copies with an EXPLICIT named column list (never ``s.*``).
# Order may diverge; live-only nullable columns are null-filled. These tests:
#   - migration-path live still merges correctly;
#   - order divergence still succeeds with correct column placement;
#   - live-only columns null-fill;
#   - missing required staging PK still aborts before insert.
# ---------------------------------------------------------------------------


def test_merge_into_migration_path_live_db(env):
    """A live DB built via the table-REBUILDING migration path (legacy schema
    → init_database → migrate_v9 rebuilds nodes) merges correctly: per-table
    counts match staging, content_class is preserved, and chunk vectors are
    element-identical. Guards the M2 criterion that a live-schema change can't
    silently diverge — exercised against a rebuilt table, not a fresh init."""
    live = os.path.join(env["tmpdir"], "live_migrated.duckdb")
    staging = os.path.join(env["tmpdir"], "staging_migrated.duckdb")
    _init_live_via_migration_path(live)
    # sanity: the live nodes table really went through the rebuild and its
    # columns still match a freshly-bootstrapped staging file's nodes columns.
    prepare_staging_db(staging)
    assert _ordered_cols(live, "nodes") == _ordered_cols(staging, "nodes")

    _stage_books(
        staging,
        [
            {"bytes": b"mig-book-1", "content_class": "source_declared_open"},
            {"bytes": b"mig-book-2", "rights_holder_name": "MIT Press"},
        ],
    )
    staging_counts = _counts(staging)

    staged = duckdb.connect(staging, read_only=True)
    try:
        staged_vecs = dict(staged.execute("SELECT chunk_id, embedding FROM chunks").fetchall())
    finally:
        staged.close()

    merge_staging(live_db=live, staging_db=staging)

    live_counts = _counts(live)
    for table in ("documents", "chunks", "nodes", "book_assets", "ip_holders"):
        assert live_counts[table] == staging_counts[table], (
            f"{table}: live {live_counts[table]} != staging {staging_counts[table]}"
        )
    livecon = duckdb.connect(live, read_only=True)
    try:
        # content_class landed in the content_class column (not shuffled).
        cc = livecon.execute(
            "SELECT content_class FROM documents "
            "WHERE document_id=(SELECT document_id FROM documents "
            "                   WHERE content_class='source_declared_open' LIMIT 1)"
        ).fetchone()
        assert cc is not None and cc[0] == "source_declared_open"
        live_vecs = dict(livecon.execute("SELECT chunk_id, embedding FROM chunks").fetchall())
    finally:
        livecon.close()
    for cid, vec in staged_vecs.items():
        assert live_vecs[cid] == vec, f"vector for {cid} changed across migration-path merge"


def test_merge_succeeds_despite_column_order_divergence(env):
    """Column ORDER may diverge between staging and live — named projection
    still lands values in the correct columns (Mini prod failure mode)."""
    live = os.path.join(env["tmpdir"], "live_reordered.duckdb")
    staging = os.path.join(env["tmpdir"], "staging_reordered.duckdb")
    init_database_at_path(live)
    _stage_books(staging, [{"bytes": b"reorder-book", "content_class": "public_domain"}])

    # Transpose page_count / toc_json on LIVE only (same names, different order).
    with connect_write(live, purpose="test-force-reorder") as con:
        con.execute("DROP TABLE book_assets")
        con.execute(
            "CREATE TABLE book_assets ("
            "  document_id TEXT PRIMARY KEY REFERENCES documents(document_id),"
            "  page_count INTEGER,"
            "  toc_json TEXT,"
            "  pagination_scheme TEXT, cover_uri TEXT, provenance TEXT,"
            "  license_basis TEXT,"
            "  taken_down BOOLEAN NOT NULL DEFAULT FALSE,"
            "  taken_down_at TIMESTAMP, takedown_reason TEXT,"
            "  pre_takedown_content_class TEXT,"
            "  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,"
            "  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
    assert _ordered_cols(live, "book_assets")[:3] == ["document_id", "page_count", "toc_json"]
    assert _ordered_cols(staging, "book_assets")[:3] != ["document_id", "page_count", "toc_json"]

    result = merge_staging(live_db=live, staging_db=staging)
    assert sum(t.inserted for t in result.tables) >= 1
    livecon = duckdb.connect(live, read_only=True)
    try:
        row = livecon.execute(
            "SELECT content_class FROM documents LIMIT 1"
        ).fetchone()
        assert row is not None and row[0] == "public_domain"
    finally:
        livecon.close()


def test_merge_null_fills_live_only_columns(env):
    """Live-only nullable columns (e.g. chunks.owner_user_id) do not block merge."""
    live = os.path.join(env["tmpdir"], "live_extra_col.duckdb")
    staging = os.path.join(env["tmpdir"], "staging_extra_col.duckdb")
    init_database_at_path(live)
    with connect_write(live, purpose="test-add-live-only-col") as con:
        con.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS owner_user_id TEXT")
        con.execute(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS structured_blocks TEXT"
        )
    _stage_books(staging, [{"bytes": b"extra-col-book", "content_class": "public_domain"}])
    assert "owner_user_id" in _ordered_cols(live, "chunks")
    assert "owner_user_id" not in _ordered_cols(staging, "chunks")

    result = merge_staging(live_db=live, staging_db=staging)
    assert any(t.table == "chunks" and t.inserted >= 1 for t in result.tables)
    livecon = duckdb.connect(live, read_only=True)
    try:
        nulls = livecon.execute(
            "SELECT count(*) FROM chunks WHERE owner_user_id IS NULL"
        ).fetchone()[0]
        assert nulls >= 1
    finally:
        livecon.close()


def test_schema_divergence_aborts_when_staging_missing_pk(env, monkeypatch):
    """Missing required PK on staging still aborts before any insert."""
    live = os.path.join(env["tmpdir"], "live_missing_pk.duckdb")
    staging = os.path.join(env["tmpdir"], "staging_missing_pk.duckdb")
    init_database_at_path(live)
    _stage_books(staging, [{"bytes": b"pk-book", "content_class": "public_domain"}])

    import tools.merge_staging as ms

    real = ms._ordered_columns

    def _hide_chunk_pk(con, table: str, *, catalog: str):
        cols = real(con, table, catalog=catalog)
        if catalog == "staging" and table == "chunks":
            return [c for c in cols if c != "chunk_id"]
        return cols

    monkeypatch.setattr(ms, "_ordered_columns", _hide_chunk_pk)
    before = _counts(live)
    with pytest.raises(SchemaDivergence, match="chunks"):
        merge_staging(live_db=live, staging_db=staging)
    assert _counts(live) == before



# ---------------------------------------------------------------------------
# M4 — vectors copied element-identical, never recomputed
# ---------------------------------------------------------------------------


def test_vectors_copied_element_identical(env):
    """Live chunk vectors are element-identical to the staged vectors."""
    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)
    _stage_books(staging, [{"bytes": b"book-vec-id", "content_class": "public_domain"}])

    staged = duckdb.connect(staging, read_only=True)
    try:
        staged_vecs = dict(
            staged.execute("SELECT chunk_id, embedding FROM chunks").fetchall()
        )
    finally:
        staged.close()

    merge_staging(live_db=live, staging_db=staging)

    livecon = duckdb.connect(live, read_only=True)
    try:
        live_vecs = dict(
            livecon.execute("SELECT chunk_id, embedding FROM chunks").fetchall()
        )
    finally:
        livecon.close()

    assert set(live_vecs) == set(staged_vecs)
    for cid, vec in staged_vecs.items():
        assert live_vecs[cid] == vec, f"vector for {cid} changed across merge"
    # and at least one vector is non-trivial (proves we copied real data)
    assert any(v is not None and any(x != 0 for x in v) for v in live_vecs.values())


def test_no_embedding_call_in_merge_module():
    """Grep-assert: the merge module imports/calls no embedding model — vectors
    are copied as data, never recomputed at merge."""
    path = os.path.join(_REPO, "tools", "merge_staging.py")
    with open(path, encoding="utf-8") as f:
        src = f.read().lower()
    for needle in ("sentence_transformers", "default_embedding_provider", ".encode(", "model.encode"):
        assert needle not in src, f"merge module unexpectedly references {needle!r}"


# ---------------------------------------------------------------------------
# M5 — idempotency, atomic rollback, resumability, id-keyed (not title)
# ---------------------------------------------------------------------------


def test_remerge_is_idempotent_zero_inserts(env):
    """A second merge of the same staging file inserts 0 rows on every table."""
    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)
    _stage_books(
        staging,
        [
            {"bytes": b"book-idem-1", "content_class": "public_domain"},
            {"bytes": b"book-idem-2", "rights_holder_name": "Cambridge University Press"},
        ],
    )
    merge_staging(live_db=live, staging_db=staging)
    counts_after_first = _counts(live)

    second = merge_staging(live_db=live, staging_db=staging)
    for t in second.tables:
        assert t.inserted == 0, f"re-merge inserted {t.inserted} into {t.table}"
    assert _counts(live) == counts_after_first


def test_atomic_rollback_on_mid_merge_failure(env):
    """A forced exception inside the merge transaction leaves the live DB at
    its pre-merge counts — atomic rollback, no orphan rows."""
    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)
    _stage_books(staging, [{"bytes": b"book-rollback", "content_class": "public_domain"}])
    before = _counts(live)

    with pytest.raises(RuntimeError, match="injected mid-merge failure"):
        merge_staging(live_db=live, staging_db=staging, fail_after_attach=True)

    assert _counts(live) == before, "failed merge must roll back to pre-merge counts"


def test_resumable_after_interruption(env):
    """After a simulated interruption (rolled-back merge), a clean re-run
    completes and yields the same final counts as an uninterrupted merge."""
    live_a = os.path.join(env["tmpdir"], "live_a.duckdb")
    live_b = os.path.join(env["tmpdir"], "live_b.duckdb")
    staging = os.path.join(env["tmpdir"], "staging_resume.duckdb")
    init_database_at_path(live_a)
    init_database_at_path(live_b)
    _stage_books(
        staging,
        [
            {"bytes": b"book-resume-1", "content_class": "public_domain"},
            {"bytes": b"book-resume-2", "rights_holder_name": "Princeton University Press"},
        ],
    )

    # live_a: interrupted, then a clean re-run.
    with pytest.raises(RuntimeError):
        merge_staging(live_db=live_a, staging_db=staging, fail_after_attach=True)
    merge_staging(live_db=live_a, staging_db=staging)

    # live_b: a single uninterrupted merge.
    merge_staging(live_db=live_b, staging_db=staging)

    assert _counts(live_a) == _counts(live_b)


def test_idempotency_keys_on_document_id_not_title(env):
    """Two staging rows with the SAME document_id but different titles collapse
    to ONE live row — the key is the content-stable id, not the title."""
    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)
    init_database_at_path(staging)

    # Hand-stage two documents sharing a document_id but with different titles,
    # to prove the anti-join keys on document_id, not (title, author).
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_document

    with connect_write(staging, purpose="test-stage-dups") as con:
        insert_document(
            con, document_id="doc-shared-id", source_tier=2, document_type="book",
            title="Title One", content_class="public_domain", on_conflict="ignore",
        )
        # second row, same id, different title — on_conflict=ignore keeps one in
        # staging; the merge must likewise produce exactly one live row.
        insert_document(
            con, document_id="doc-shared-id", source_tier=2, document_type="book",
            title="Title Two — different", content_class="public_domain",
            on_conflict="ignore",
        )

    merge_staging(live_db=live, staging_db=staging)
    con = duckdb.connect(live, read_only=True)
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id='doc-shared-id'"
        ).fetchone()[0]
    finally:
        con.close()
    assert n == 1


def test_ip_holder_remap_no_duplicate_escrow_accounts(env):
    """Re-ingesting the same publisher across two staging batches must not fan
    out into duplicate live ip_holders, and merged documents must reference the
    LIVE holder id (not a dangling staging id)."""
    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging1 = os.path.join(env["tmpdir"], "staging1.duckdb")
    staging2 = os.path.join(env["tmpdir"], "staging2.duckdb")
    init_database_at_path(live)
    _stage_books(staging1, [{"bytes": b"pub-book-1", "rights_holder_name": "MIT Press"}])
    _stage_books(staging2, [{"bytes": b"pub-book-2", "rights_holder_name": "MIT Press"}])

    merge_staging(live_db=live, staging_db=staging1)
    merge_staging(live_db=live, staging_db=staging2)

    con = duckdb.connect(live, read_only=True)
    try:
        n_holders = con.execute(
            "SELECT COUNT(*) FROM ip_holders WHERE display_name='MIT Press'"
        ).fetchone()[0]
        live_holder_id = con.execute(
            "SELECT ip_holder_id FROM ip_holders WHERE display_name='MIT Press'"
        ).fetchone()[0]
        # every document for this publisher points at the one live holder id
        bad = con.execute(
            "SELECT COUNT(*) FROM documents d "
            "WHERE d.ip_holder_id IS NOT NULL "
            "  AND d.ip_holder_id NOT IN (SELECT ip_holder_id FROM ip_holders)"
        ).fetchone()[0]
        n_docs_for_pub = con.execute(
            "SELECT COUNT(*) FROM documents WHERE ip_holder_id=?", [live_holder_id]
        ).fetchone()[0]
    finally:
        con.close()
    assert n_holders == 1, "duplicate escrow account created for the same publisher"
    assert bad == 0, "a document references a holder id absent from ip_holders"
    assert n_docs_for_pub == 2


def test_ip_holder_remap_leaves_holder_column_writable(env, monkeypatch):
    """The remap drops a legacy ``idx_documents_ip_holder`` and must not put it
    back. With that index present, DuckDB refuses to UPDATE ``ip_holder_id`` on
    any document that chunks reference, so a re-created index turned every
    later holder write (the persist-path resolver, the backfill) into a
    ConstraintException while the warm schema probe reported the file current.
    """
    import tools.merge_staging as merge_module

    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging1 = os.path.join(env["tmpdir"], "staging1.duckdb")
    staging2 = os.path.join(env["tmpdir"], "staging2.duckdb")
    init_database_at_path(live)
    _stage_books(staging1, [{"bytes": b"pub-book-3", "rights_holder_name": "MIT Press"}])
    _stage_books(staging2, [{"bytes": b"pub-book-4", "rights_holder_name": "MIT Press"}])
    merge_staging(live_db=live, staging_db=staging1)

    con = duckdb.connect(live)
    try:
        # A live file from before the index was retired.
        con.execute("CREATE INDEX idx_documents_ip_holder ON documents(ip_holder_id)")
    finally:
        con.close()

    remaps: list[dict[str, str]] = []
    real_remap = merge_module._remap_document_ip_holders

    def recording_remap(con, remap):
        remaps.append(dict(remap))
        return real_remap(con, remap)

    monkeypatch.setattr(merge_module, "_remap_document_ip_holders", recording_remap)
    # The same publisher again: its staging holder id remaps onto the live one.
    merge_staging(live_db=live, staging_db=staging2)
    assert remaps and remaps[0], "premise: the second merge must exercise the remap"

    con = duckdb.connect(live)
    try:
        indexes = {
            row[0]
            for row in con.execute(
                "SELECT index_name FROM duckdb_indexes() WHERE table_name = 'documents'"
            ).fetchall()
        }
        chunked = con.execute(
            "SELECT d.document_id FROM documents d "
            "JOIN chunks c ON c.document_id = d.document_id LIMIT 1"
        ).fetchone()
        assert chunked is not None, "premise: a merged book has chunks referencing it"
        con.execute(
            "UPDATE documents SET ip_holder_id = ip_holder_id WHERE document_id = ?",
            [chunked[0]],
        )
    finally:
        con.close()
    assert "idx_documents_ip_holder" not in indexes


# ---------------------------------------------------------------------------
# M3/M5 — merge is a single connect_write transaction
# ---------------------------------------------------------------------------


def test_merge_is_single_connect_write(env, monkeypatch):
    """The merge opens the live writer exactly once. Spy on connect_write and
    assert one call for the whole merge (not one-per-table)."""
    import tools.merge_staging as merge_mod

    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)
    _stage_books(
        staging,
        [
            {"bytes": b"book-tx-1", "content_class": "public_domain"},
            {"bytes": b"book-tx-2", "rights_holder_name": "MIT Press"},
        ],
    )

    calls = {"n": 0}
    real = merge_mod.connect_write

    def _spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(merge_mod, "connect_write", _spy)
    merge_staging(live_db=live, staging_db=staging)
    assert calls["n"] == 1, f"merge opened the live writer {calls['n']} times, want 1"


# ---------------------------------------------------------------------------
# M6 — live readable during staging ingest + bounded merge window
# ---------------------------------------------------------------------------


def test_live_readable_during_ingest(env):
    """A live read-loop succeeds continuously while a staging ingest writes —
    zero failed/blocked reads attributable to the ingest."""
    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)
    # seed one live row so the read loop has something to read
    _stage_books(staging, [{"bytes": b"seed-into-live", "content_class": "public_domain"}])
    merge_staging(live_db=live, staging_db=staging)

    staging2 = os.path.join(env["tmpdir"], "staging2.duckdb")

    read_results = {"ok": 0, "fail": 0}
    stop = threading.Event()

    def _reader():
        while not stop.is_set():
            try:
                con = connect_read(live)
                try:
                    con.execute("SELECT COUNT(*) FROM documents").fetchone()
                finally:
                    con.close()
                read_results["ok"] += 1
            except Exception:
                read_results["fail"] += 1
            time.sleep(0.005)

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    try:
        # the ingest writes to a SEPARATE staging file → the live reader is
        # never contended by it.
        _stage_books(
            staging2,
            [{"bytes": f"during-ingest-{i}".encode(), "content_class": "public_domain"}
             for i in range(4)],
        )
    finally:
        stop.set()
        t.join(timeout=5)

    assert read_results["ok"] > 0, "live reader never ran"
    assert read_results["fail"] == 0, (
        f"{read_results['fail']} live reads were blocked during a staging ingest"
    )


def test_merge_window_is_bounded(env):
    """Regression guard on a small batch: the connect_write-held merge window
    is seconds-scale, distinct from the (here, instantaneous) ingest. A
    generous ceiling catches an accidental per-row-write regression that would
    balloon the window. The PRODUCTION-scale figure is asserted+recorded by
    ``test_merge_window_at_production_scale`` below."""
    live = os.path.join(env["tmpdir"], "live.duckdb")
    staging = os.path.join(env["tmpdir"], "staging.duckdb")
    init_database_at_path(live)
    _stage_books(
        staging,
        [{"bytes": f"window-book-{i}".encode(), "content_class": "public_domain"}
         for i in range(6)],
    )
    result = merge_staging(live_db=live, staging_db=staging)
    assert result.total_inserted > 0
    # Bound: this representative batch must merge well under 10s. A regression
    # to per-row writes / per-table connect_write reopen would blow past this.
    assert result.window_s < 10.0, f"merge window {result.window_s:.3f}s exceeds bound"


def test_merge_window_at_production_scale():
    """The keystone number, at the scale the keystone actually runs (sharpen
    defect #2). The first prod ingest landed 31 docs / 5,017 chunks; merge that
    real shape and assert the connect_write-held window is seconds-scale — not
    a toy-batch figure presented as production. Re-runnable via
    ``tools.measure_merge_window``; the recorded number + slope are in the
    handoff. A regression to per-row writes / per-table lock reopen would blow
    far past the bound at 5k chunks even if a 6-book batch stayed under it."""
    from tools.measure_merge_window import PROD_CHUNKS, PROD_DOCS, measure_one

    window_s = measure_one(n_docs=PROD_DOCS, n_chunks=PROD_CHUNKS, dim=16)
    # Generous seconds-scale ceiling. Measured ~0.07-0.13s across embedding
    # dims 16-768 on dev hardware (see handoff); this bound is ~25x the
    # 768-dim figure so it stays honest about the keystone claim while
    # absorbing slower box / cold-cache variance, and still trips loudly on a
    # per-row-write regression (which would be tens of seconds at 5k chunks).
    assert window_s < 3.0, (
        f"production-scale (5017-chunk) merge window {window_s:.3f}s is not "
        "seconds-scale — the keystone claim has regressed"
    )
