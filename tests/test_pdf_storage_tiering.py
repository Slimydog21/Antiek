"""Tests for SPR-04 M2 — tier-gated PDF storage on the EXISTING arXiv row.

The LOAD-BEARING assertions (rigor bar 3):
  - a T3-seeded row → store attempt REFUSED → raw_text still NULL +
    content_class still the gated floor (the cardinal-sin negative, asserted
    directly).
  - a T1-seeded row → store → raw_text set + content_class promoted
    (source_declared_open for CC-BY, public_domain for CC0) + body indexed
    (chunks present) → serve_full_text_guarded serves the body WITHOUT raising.
  - a T2 (CC-BY-NC) row → store attempt DEFERRED → raw_text still NULL +
    content_class still gated.

Seeding: a row is created exactly the way SPR-01 does — via
``persist_oai_records([ArxivOaiRecord(...)])`` — so the store path operates on a
real harvested row (license_uri / rights_tier in metadata, gated floor). The PDF
is a real ``text_to_pdf`` body so the real ``read_pdf`` reader extracts it; no
network, no sentence-transformers.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv.adapter import arxiv_doc_id  # noqa: E402
from acquisition.arxiv.oai_persist import persist_oai_records  # noqa: E402
from acquisition.arxiv.pdf_fetch import FetchedPdf  # noqa: E402
from acquisition.arxiv.store import store_pdf_for_arxiv_row  # noqa: E402
from acquisition.books.public_domain import text_to_pdf  # noqa: E402
from runtime.db_lock import connect_read  # noqa: E402
from substrate.books.serve_guard import serve_full_text_guarded  # noqa: E402
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS  # noqa: E402
from substrate.rights import RightsTier, T3BodyServeError  # noqa: E402
from substrate.schemas.documents import ArxivOaiRecord  # noqa: E402

_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_CC0 = "http://creativecommons.org/publicdomain/zero/1.0/"
_CC_BY_NC = "http://creativecommons.org/licenses/by-nc/4.0/"
_ARXIV_DEFAULT = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"

# A real PDF with comfortably > MIN_BODY_WORD_COUNT (100) words, so the real
# read_pdf extractor clears the husk floor.
_PDF_TEXT = "This is a synthetic open-access academic paper body. " * 60
_PDF_BYTES = text_to_pdf(_PDF_TEXT, title="Open Paper")


class _StubEmbedder:
    """Deterministic fake EmbeddingModel — no sentence-transformers in CI."""

    dimension = 16

    def encode(self, text: str) -> list[float]:
        v = [0.0] * 16
        v[abs(hash(text)) % 16] = 1.0
        return v


@pytest.fixture
def temp_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-spr04-store-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield db_path


def _seed_row(db_path: str, arxiv_id: str, license_uri: str | None) -> str:
    """Seed exactly as SPR-01 does (the gated-floor metadata row)."""
    rec = ArxivOaiRecord(
        arxiv_id=arxiv_id,
        datestamp="2024-02-15",
        license_uri=license_uri,
        title=f"Paper {arxiv_id}",
        categories=("cs.AI",),
    )
    persist_oai_records([rec], db_path=db_path)
    return arxiv_doc_id(arxiv_id)


def _fetched(arxiv_id: str) -> FetchedPdf:
    import hashlib

    return FetchedPdf(
        arxiv_id=arxiv_id,
        source_url=f"https://arxiv.org/pdf/{arxiv_id}",
        content=_PDF_BYTES,
        sha256=hashlib.sha256(_PDF_BYTES).hexdigest(),
        byte_size=len(_PDF_BYTES),
    )


def _read_doc(db_path: str, document_id: str):
    with connect_read(db_path) as con:
        return con.execute(
            "SELECT content_class, raw_text, metadata FROM documents "
            "WHERE document_id = ?",
            [document_id],
        ).fetchone()


# ---------------------------------------------------------------------------
# T1 — stored, promoted, indexed, serves clean
# ---------------------------------------------------------------------------


def test_t1_cc_by_stored_promoted_indexed_and_serves(temp_db):
    doc_id = _seed_row(temp_db, "2402.10001", _CC_BY)

    # Pre-state: gated floor, no body.
    cc, raw, _ = _read_doc(temp_db, doc_id)
    assert cc == GATED_DEFAULT_CONTENT_CLASS
    assert raw is None

    outcome = store_pdf_for_arxiv_row(
        _fetched("2402.10001"), db_path=temp_db, embedder=_StubEmbedder()
    )
    assert outcome.status == "stored"
    assert outcome.tier is RightsTier.T1_REDISTRIBUTABLE
    assert outcome.content_class == "source_declared_open"  # CC-BY remap
    assert outcome.chunks_written > 0
    assert outcome.sha256 == _fetched("2402.10001").sha256

    # Post-state: body present, class promoted, provenance recorded.
    cc, raw, meta = _read_doc(temp_db, doc_id)
    assert cc == "source_declared_open"
    assert raw is not None and len(raw) > 0
    import json

    md = json.loads(meta)
    # Rights anchors untouched; provenance block added.
    assert md["license_uri"] == _CC_BY
    assert md["rights_tier"] == RightsTier.T1_REDISTRIBUTABLE.value
    prov = md["pdf_acquisition"]
    assert prov["source_url"] == "https://arxiv.org/pdf/2402.10001"
    assert prov["sha256"] == outcome.sha256
    assert prov["byte_size"] == len(_PDF_BYTES)
    assert "fetched_at" in prov

    # Chunks landed for search.
    with connect_read(temp_db) as con:
        n = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?", [doc_id]
        ).fetchone()[0]
    assert n > 0

    # INTEGRATION: the SPR-02 serve guard emits the body WITHOUT raising (T1).
    with connect_read(temp_db) as con:
        result = serve_full_text_guarded(con, doc_id)
    assert result.servable is True
    assert result.full_text is not None
    assert result.full_text == raw


def test_t1_cc0_promotes_to_public_domain(temp_db):
    doc_id = _seed_row(temp_db, "2402.10002", _CC0)
    outcome = store_pdf_for_arxiv_row(
        _fetched("2402.10002"), db_path=temp_db, embedder=_StubEmbedder()
    )
    assert outcome.status == "stored"
    assert outcome.content_class == "public_domain"
    cc, raw, _ = _read_doc(temp_db, doc_id)
    assert cc == "public_domain"
    assert raw is not None


def test_t1_index_failure_rolls_back_body_class_envelope_and_provenance(temp_db):
    doc_id = _seed_row(temp_db, "2402.10003", _CC_BY)
    before = _read_doc(temp_db, doc_id)

    class _ExplodingEmbedder:
        dimension = 16

        def encode(self, _text: str) -> list[float]:
            raise RuntimeError("embedding failed after promotion began")

    with pytest.raises(RuntimeError, match="embedding failed"):
        store_pdf_for_arxiv_row(
            _fetched("2402.10003"),
            db_path=temp_db,
            embedder=_ExplodingEmbedder(),
        )

    assert _read_doc(temp_db, doc_id) == before
    with connect_read(temp_db) as con:
        assert con.execute(
            "SELECT count(*) FROM chunks WHERE document_id=?", [doc_id]
        ).fetchone() == (0,)


# ---------------------------------------------------------------------------
# T3 — REFUSED, never stored (the load-bearing negative)
# ---------------------------------------------------------------------------


def test_t3_default_terms_refused_never_stored(temp_db):
    doc_id = _seed_row(temp_db, "2402.20001", _ARXIV_DEFAULT)

    outcome = store_pdf_for_arxiv_row(
        _fetched("2402.20001"), db_path=temp_db, embedder=_StubEmbedder()
    )
    assert outcome.status == "refused"
    assert outcome.tier is RightsTier.T3_DEFAULT_UNKNOWN

    # The cardinal-sin negative: NO body, class STILL the gated floor.
    cc, raw, _ = _read_doc(temp_db, doc_id)
    assert raw is None
    assert cc == GATED_DEFAULT_CONTENT_CLASS

    # And the guard is never even exercised for it — it would deny.
    with connect_read(temp_db) as con:
        result = serve_full_text_guarded(con, doc_id)
    assert result.servable is False
    assert result.full_text is None


def test_t3_missing_license_refused_never_stored(temp_db):
    """Deny-by-default: an absent license resolves to T3 → refused."""
    doc_id = _seed_row(temp_db, "2402.20002", None)
    outcome = store_pdf_for_arxiv_row(
        _fetched("2402.20002"), db_path=temp_db, embedder=_StubEmbedder()
    )
    assert outcome.status == "refused"
    cc, raw, _ = _read_doc(temp_db, doc_id)
    assert raw is None
    assert cc == GATED_DEFAULT_CONTENT_CLASS


# ---------------------------------------------------------------------------
# T2 — DEFERRED (counsel gate), not stored
# ---------------------------------------------------------------------------


def test_t2_cc_by_nc_deferred_not_stored(temp_db):
    doc_id = _seed_row(temp_db, "2402.30001", _CC_BY_NC)

    outcome = store_pdf_for_arxiv_row(
        _fetched("2402.30001"), db_path=temp_db, embedder=_StubEmbedder()
    )
    assert outcome.status == "deferred"
    assert outcome.tier is RightsTier.T2_NON_COMMERCIAL

    # Not stored, not promoted.
    cc, raw, _ = _read_doc(temp_db, doc_id)
    assert raw is None
    assert cc == GATED_DEFAULT_CONTENT_CLASS


# ---------------------------------------------------------------------------
# Husk + missing-row + idempotency edges
# ---------------------------------------------------------------------------


def test_t1_low_word_husk_skipped_not_stored(temp_db):
    """A T1 paper whose extraction yields < MIN_BODY_WORD_COUNT words is a husk
    (scanned PDF / extraction failure) → skipped, NOT stored as a servable body."""
    doc_id = _seed_row(temp_db, "2402.40001", _CC_BY)

    class _HuskReader:
        markdown = "tiny"
        word_count = 3
        page_count = 1

    outcome = store_pdf_for_arxiv_row(
        _fetched("2402.40001"),
        db_path=temp_db,
        embedder=_StubEmbedder(),
        extract_text=lambda b: _HuskReader(),
    )
    assert outcome.status == "skipped_low_words"
    cc, raw, _ = _read_doc(temp_db, doc_id)
    assert raw is None
    assert cc == GATED_DEFAULT_CONTENT_CLASS


def test_t1_corrupt_pdf_extraction_failure_skipped_not_stored(temp_db):
    """A T1 paper whose body passes the %PDF precheck but RAISES during parse
    (a corrupt / encrypted / truncated PDF) → skipped gracefully, NOT stored and
    NOT crashing the run. Mirrors the husk path: metadata-only, never promoted."""
    doc_id = _seed_row(temp_db, "2402.40002", _CC_BY)

    def _boom(_b):
        raise ValueError("corrupt PDF: xref broken")

    # The call must NOT raise — the extraction failure is handled gracefully.
    outcome = store_pdf_for_arxiv_row(
        _fetched("2402.40002"),
        db_path=temp_db,
        embedder=_StubEmbedder(),
        extract_text=_boom,
    )
    assert outcome.status == "skipped_extraction_failure"
    assert outcome.tier is RightsTier.T1_REDISTRIBUTABLE

    # The cardinal-sin negative: NO body, class STILL the gated floor.
    cc, raw, _ = _read_doc(temp_db, doc_id)
    assert raw is None
    assert cc == GATED_DEFAULT_CONTENT_CLASS

    # The body was never indexed — no chunks for the doc.
    with connect_read(temp_db) as con:
        n = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?", [doc_id]
        ).fetchone()[0]
    assert n == 0


def test_missing_row_is_an_error(temp_db):
    """SPR-01 must have harvested the paper first; storing against a row that
    does not exist is an error, not a silent new-row creation."""
    # Ensure the DB exists but has no row for this id.
    _seed_row(temp_db, "2402.50000", _CC_BY)
    with pytest.raises(ValueError):
        store_pdf_for_arxiv_row(
            _fetched("2402.99999"), db_path=temp_db, embedder=_StubEmbedder()
        )


def test_re_store_is_idempotent(temp_db):
    """Re-fetching + re-storing the same T1 paper is a no-op on the row state
    (same promoted class, same body, same chunk ids — content-addressed)."""
    doc_id = _seed_row(temp_db, "2402.60001", _CC_BY)
    o1 = store_pdf_for_arxiv_row(
        _fetched("2402.60001"), db_path=temp_db, embedder=_StubEmbedder()
    )
    cc1, raw1, _ = _read_doc(temp_db, doc_id)
    with connect_read(temp_db) as con:
        n1 = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?", [doc_id]
        ).fetchone()[0]

    o2 = store_pdf_for_arxiv_row(
        _fetched("2402.60001"), db_path=temp_db, embedder=_StubEmbedder()
    )
    cc2, raw2, _ = _read_doc(temp_db, doc_id)
    with connect_read(temp_db) as con:
        n2 = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?", [doc_id]
        ).fetchone()[0]

    assert o1.status == o2.status == "stored"
    assert cc1 == cc2 == "source_declared_open"
    assert raw1 == raw2
    assert n1 == n2  # content-addressed chunk ids → no duplicates on re-store


# ---------------------------------------------------------------------------
# The drift backstop: a T3 row can never be served even if something tried to
# promote it. (We assert resolve_tier + the guard agree the body-servable
# ceiling is {T1}.)
# ---------------------------------------------------------------------------


def test_guard_would_raise_on_a_t3_body_drift(temp_db):
    """If a T3 row's body+class were ever (wrongly) promoted to servable, the
    SPR-02 guard catches the drift and raises. We simulate the drift directly to
    prove the backstop the store path relies on actually fires."""
    doc_id = _seed_row(temp_db, "2402.70001", _ARXIV_DEFAULT)
    # Force the drift: write a body + promote the class out-of-band.
    from runtime.db_lock import connect_write

    with connect_write(temp_db, purpose="test/drift") as con:
        # Deliberately bypass the sanctioned writer to construct persisted
        # corruption; the sanctioned writer now rejects this promotion early.
        con.execute(
            "UPDATE documents SET raw_text=?, content_class=? WHERE document_id=?",
            ["a wrongly-stored body " * 50, "source_declared_open", doc_id],
        )

    with connect_read(temp_db) as con, pytest.raises(T3BodyServeError):
        serve_full_text_guarded(con, doc_id)
