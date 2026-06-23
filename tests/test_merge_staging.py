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

import duckdb
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# ---------------------------------------------------------------------------
# Stubs mirroring tests/test_acquisition_books.py so the ingest path is real
# but PDF-extraction + embedding are deterministic and offline.
# ---------------------------------------------------------------------------
from types import SimpleNamespace

from acquisition.books import ingest_servable_book  # noqa: E402
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
# The merge copies with an EXPLICIT column list guarded by a pre-merge
# names+order check, never a positional ``s.*``. These two tests are the
# defensible record that a future migration which rebuilds/reorders a live
# table cannot silently corrupt a merge:
#   - the first builds live via the REBUILDING migration path (not a fresh
#     init) and asserts the merge still lands data in the right columns;
#   - the second forces a column-order divergence and asserts the merge aborts
#     BEFORE any insert rather than shuffling data.
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


def test_schema_divergence_aborts_merge_before_any_insert(env):
    """If a merged table's column ORDER diverges between staging and live, the
    merge must raise SchemaDivergence and write nothing — a positional copy
    would shuffle data into the wrong columns. The guard fires before BEGIN, so
    live counts are untouched."""
    live = os.path.join(env["tmpdir"], "live_diverged.duckdb")
    staging = os.path.join(env["tmpdir"], "staging_diverged.duckdb")
    init_database_at_path(live)
    _stage_books(staging, [{"bytes": b"diverge-book", "content_class": "public_domain"}])

    # Force a divergence on book_assets: swap two adjacent columns' order on
    # LIVE only (same names+types, different ordinal positions) — exactly the
    # shape a future table-rebuilding migration could introduce. Recreate the
    # table with toc_json/page_count transposed.
    with connect_write(live, purpose="test-force-divergence") as con:
        con.execute("DROP TABLE book_assets")
        con.execute(
            "CREATE TABLE book_assets ("
            "  document_id TEXT PRIMARY KEY REFERENCES documents(document_id),"
            "  page_count INTEGER,"               # transposed ↑ ahead of toc_json
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
    before = _counts(live)

    with pytest.raises(SchemaDivergence, match="book_assets"):
        merge_staging(live_db=live, staging_db=staging)

    # Nothing was written — the guard fired before the first insert.
    assert _counts(live) == before, "a diverged-schema merge must write nothing"


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
