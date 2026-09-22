"""SPR-08 T1 — ``documents.ip_holder_id`` is populated on the persist path.

Before this task the resolver in ``middleware.ip_holder_resolver`` had zero
production callers, so every document landed with a NULL holder and the
per-second escrow guard failed for every window. These tests drive the three
persist paths that now call ``resolve_and_apply`` under the SAME write lock
(no second connection) and the one-shot backfill for rows that pre-date the
wiring:

  * ``substrate.graph.ops.insert_document``   — the generic upsert
  * ``acquisition.arxiv.oai_persist``          — the arXiv INSERT
  * ``acquisition.arxiv.store``                — the arXiv PDF store (an
    existing row that the harvest persisted before the resolver was wired)
  * ``tools.backfill_ip_holders``              — NULL rows, incl. FK parents

Mutation-checked (see the task commit): removing any one of the three
persist-path calls turns its test red; making the backfill skip the write
turns the apply test red.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from types import SimpleNamespace

import pytest

from acquisition.arxiv.adapter import arxiv_doc_id
from acquisition.arxiv.oai_persist import persist_oai_records
from acquisition.arxiv.pdf_fetch import FetchedPdf
from acquisition.arxiv.store import store_pdf_for_arxiv_row
from runtime.db_lock import connect_read, connect_write
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database_at_path
from substrate.ip_holders import create_pre_onboarded
from substrate.schemas.documents import ArxivOaiRecord
from tools import backfill_ip_holders

_CC_BY = "http://creativecommons.org/licenses/by/4.0/"


@pytest.fixture
def db_path(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-ipholder-ingest-")
    path = os.path.join(tmp, "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmp, "events"))
    init_database_at_path(path)
    return path


def _holder_of(db_path: str, document_id: str) -> str | None:
    con = connect_read(db_path)
    try:
        row = con.execute(
            "SELECT ip_holder_id FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None, f"{document_id!r} was not persisted"
    return row[0]


def _attributed_count(db_path: str) -> int:
    con = connect_read(db_path)
    try:
        return int(
            con.execute(
                "SELECT count(*) FROM documents WHERE ip_holder_id IS NOT NULL"
            ).fetchone()[0]
        )
    finally:
        con.close()


def _seed_holder(db_path: str, *, display_name: str, **metadata) -> str:
    with connect_write(db_path, purpose="ingest-test-seed-holder") as con:
        return create_pre_onboarded(con, display_name=display_name, metadata=metadata)


# ── substrate.graph.ops.insert_document ────────────────────────────────────


def test_insert_document_resolves_holder_by_domain(db_path):
    """The done-bar case: a document whose source_uri matches a registry
    holder's domain lands with a NON-NULL ip_holder_id, resolved on the same
    write-locked connection the insert used."""
    holder = _seed_holder(db_path, display_name="MIT Press", domains=["mitpress.mit.edu"])
    with connect_write(db_path, purpose="ingest-test") as con:
        insert_document(
            con,
            document_id="doc-mit",
            source_tier=2,
            document_type="book",
            source_uri="https://mitpress.mit.edu/books/foo",
            title="Foo",
        )
    resolved = _holder_of(db_path, "doc-mit")
    assert resolved is not None
    assert resolved == holder


def test_insert_document_leaves_null_when_registry_has_no_match(db_path):
    """Conservative by design: no match -> NULL, never a fabricated holder."""
    _seed_holder(db_path, display_name="MIT Press", domains=["mitpress.mit.edu"])
    with connect_write(db_path, purpose="ingest-test") as con:
        insert_document(
            con,
            document_id="doc-other",
            source_tier=3,
            document_type="web",
            source_uri="https://unrelated.example/x",
        )
    assert _holder_of(db_path, "doc-other") is None


def test_insert_document_explicit_holder_is_never_re_resolved(db_path):
    """A caller-supplied ip_holder_id is authoritative: even when the domain
    would resolve to a DIFFERENT holder, the explicit value stands."""
    _seed_holder(db_path, display_name="MIT Press", domains=["mitpress.mit.edu"])
    explicit = _seed_holder(db_path, display_name="Explicit Publisher")
    with connect_write(db_path, purpose="ingest-test") as con:
        insert_document(
            con,
            document_id="doc-explicit",
            source_tier=2,
            document_type="book",
            source_uri="https://mitpress.mit.edu/books/bar",
            ip_holder_id=explicit,
        )
    assert _holder_of(db_path, "doc-explicit") == explicit


def test_insert_document_resolves_isbn_from_metadata(db_path):
    """The resolver's first rung reads ``metadata.isbn``; the persist path
    hands it over from the metadata dict, so ISBN beats domain here."""
    isbn_holder = _seed_holder(
        db_path, display_name="ISBN Owner", isbns=["978-0-262-03561-3"]
    )
    _seed_holder(db_path, display_name="Domain Owner", domains=["example.com"])
    with connect_write(db_path, purpose="ingest-test") as con:
        insert_document(
            con,
            document_id="doc-isbn",
            source_tier=2,
            document_type="book",
            source_uri="https://example.com/book",
            metadata={"isbn": "9780262035613"},
        )
    assert _holder_of(db_path, "doc-isbn") == isbn_holder


# ── acquisition.arxiv.oai_persist ──────────────────────────────────────────


def test_oai_persist_resolves_holder_on_insert(db_path):
    """The arXiv INSERT path resolves against the registry too: a holder
    listing ``arxiv.org`` claims the harvested row."""
    holder = _seed_holder(db_path, display_name="arXiv", domains=["arxiv.org"])
    arxiv_id = "2402.30001"
    persist_oai_records(
        [
            ArxivOaiRecord(
                arxiv_id=arxiv_id,
                datestamp="2024-02-15",
                license_uri=_CC_BY,
                title="A Paper",
                categories=("cs.AI",),
            )
        ],
        db_path=db_path,
    )
    assert _holder_of(db_path, arxiv_doc_id(arxiv_id)) == holder


def test_oai_persist_re_harvest_resolves_a_pre_resolver_row(db_path):
    """A row harvested before any holder existed is NULL; the next harvest of
    the same id (the UPDATE branch) resolves it, without duplicating the row."""
    arxiv_id = "2402.30002"
    record = ArxivOaiRecord(
        arxiv_id=arxiv_id, datestamp="2024-02-15", license_uri=_CC_BY, title="P"
    )
    persist_oai_records([record], db_path=db_path)
    assert _holder_of(db_path, arxiv_doc_id(arxiv_id)) is None

    holder = _seed_holder(db_path, display_name="arXiv", domains=["arxiv.org"])
    result = persist_oai_records([record], db_path=db_path)
    assert result.inserted == 0 and result.updated == 1
    assert _holder_of(db_path, arxiv_doc_id(arxiv_id)) == holder


# ── acquisition.arxiv.store ────────────────────────────────────────────────


class _StubEmbedder:
    dimension = 16

    def encode(self, text: str) -> list[float]:
        v = [0.0] * 16
        v[abs(hash(text)) % 16] = 1.0
        return v


def _fake_extract(_content: bytes) -> SimpleNamespace:
    body = "A synthetic open-access paper body sentence. " * 80
    return SimpleNamespace(
        markdown=body, word_count=len(body.split()), page_count=1
    )


def test_pdf_store_resolves_holder_on_a_pre_resolver_row(db_path):
    """The PDF store path operates on a row the harvest persisted EARLIER. When
    that row pre-dates the registry entry (NULL holder), the store's own
    ``resolve_and_apply`` call — inside its single transaction — attributes it.
    Chunks are written in the same transaction, which proves the plain UPDATE
    on the unindexed ``ip_holder_id`` coexists with FK children."""
    arxiv_id = "2402.30003"
    persist_oai_records(
        [
            ArxivOaiRecord(
                arxiv_id=arxiv_id, datestamp="2024-02-15", license_uri=_CC_BY,
                title="Open Paper", categories=("cs.AI",),
            )
        ],
        db_path=db_path,
    )
    assert _holder_of(db_path, arxiv_doc_id(arxiv_id)) is None

    holder = _seed_holder(db_path, display_name="arXiv", domains=["arxiv.org"])
    content = b"%PDF-1.4 synthetic"
    fetched = FetchedPdf(
        arxiv_id=arxiv_id,
        source_url=f"https://arxiv.org/pdf/{arxiv_id}",
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
    )
    outcome = store_pdf_for_arxiv_row(
        fetched, db_path=db_path, embedder=_StubEmbedder(), extract_text=_fake_extract
    )
    assert outcome.status == "stored", outcome
    assert outcome.chunks_written > 0
    assert _holder_of(db_path, arxiv_doc_id(arxiv_id)) == holder


# ── tools.backfill_ip_holders ──────────────────────────────────────────────


def _seed_pre_resolver_rows(db_path: str) -> None:
    """Three NULL-holder rows as the pre-T1 corpus left them: two resolvable
    (one of which has chunks, i.e. is an FK parent) and one unmatched."""
    with connect_write(db_path, purpose="ingest-test-seed-docs") as con:
        insert_document(
            con, document_id="doc-a", source_tier=2, document_type="book",
            source_uri="https://www.gutenberg.org/ebooks/1",
        )
        insert_document(
            con, document_id="doc-b", source_tier=2, document_type="book",
            source_uri="https://gutenberg.org/ebooks/2",
        )
        insert_document(
            con, document_id="doc-c", source_tier=3, document_type="web",
            source_uri="https://nobody.example/x",
        )
        insert_chunk(con, document_id="doc-a", chunk_index=0, text="chunk a0")
        insert_chunk(con, document_id="doc-a", chunk_index=1, text="chunk a1")


def test_backfill_dry_run_counts_and_writes_nothing(db_path):
    _seed_pre_resolver_rows(db_path)
    assert _attributed_count(db_path) == 0
    _seed_holder(db_path, display_name="Project Gutenberg", domains=["gutenberg.org"])

    report = backfill_ip_holders.run(db_path, apply=False)
    assert report.attributed_before == 0
    assert report.examined == 3
    assert report.resolved == 2
    assert report.unresolved == 1
    assert report.attributed_after == 0
    assert _attributed_count(db_path) == 0


def test_backfill_apply_attributes_null_rows_including_fk_parents(db_path):
    """The done-bar shape: attributed count 0 before, > 0 after. ``doc-a`` has
    chunks referencing it, so this also proves the UPDATE lands on an FK
    parent (ip_holder_id is unindexed by schema design)."""
    _seed_pre_resolver_rows(db_path)
    holder = _seed_holder(
        db_path, display_name="Project Gutenberg", domains=["gutenberg.org"]
    )
    before = _attributed_count(db_path)
    assert before == 0

    report = backfill_ip_holders.run(db_path, apply=True)
    after = _attributed_count(db_path)
    assert after == 2 > before
    assert report.attributed_before == 0
    assert report.attributed_after == 2
    assert _holder_of(db_path, "doc-a") == holder
    assert _holder_of(db_path, "doc-b") == holder
    assert _holder_of(db_path, "doc-c") is None


def test_backfill_second_apply_is_idempotent_and_never_overwrites(db_path):
    _seed_pre_resolver_rows(db_path)
    first = _seed_holder(
        db_path, display_name="Project Gutenberg", domains=["gutenberg.org"]
    )
    backfill_ip_holders.run(db_path, apply=True)
    # A second holder that ALSO matches must not steal the attribution.
    _seed_holder(db_path, display_name="Gutenberg Mirror", domains=["gutenberg.org"])

    report = backfill_ip_holders.run(db_path, apply=True)
    assert report.examined == 1  # only doc-c is still NULL
    assert report.resolved == 0
    assert _holder_of(db_path, "doc-a") == first
    assert _holder_of(db_path, "doc-b") == first


def test_backfill_cli_prints_the_bar_numbers(db_path, capsys, monkeypatch):
    # The fixture made db_path the substrate default; the CLI refuses the
    # default (prod guard), so point the default elsewhere for this run.
    monkeypatch.setenv(
        "ANTIEK_DUCKDB_PATH", os.path.join(os.path.dirname(db_path), "other.duckdb")
    )
    _seed_pre_resolver_rows(db_path)
    _seed_holder(db_path, display_name="Project Gutenberg", domains=["gutenberg.org"])
    rc = backfill_ip_holders.main(["--db-path", db_path, "--apply", "--workers", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[before] : 0" in out
    assert "[after]  : 2" in out


def test_backfill_cli_refuses_more_than_one_worker(db_path):
    with pytest.raises(SystemExit) as exc:
        backfill_ip_holders.main(["--db-path", db_path, "--workers", "2"])
    assert exc.value.code == 2


def test_backfill_cli_refuses_the_prod_default_path(db_path, capsys):
    """The substrate default path is the prod store; the fixture pointed
    ANTIEK_DUCKDB_PATH at our tmp file, so passing that same path must be
    refused exactly as the real default would be."""
    rc = backfill_ip_holders.main(["--db-path", db_path])
    assert rc == 2
    assert "operator-gated" in capsys.readouterr().err
