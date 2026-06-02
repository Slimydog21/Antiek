"""Tests for the public-domain acquisition connector (SPR-01).

Strategy: NO live HTTP. A ``FakeSourceClient`` records canned Gutendex /
archive.org JSON responses + canned PDF bytes, exposing the same
``get_json`` / ``get_bytes`` surface as the real ``SourceClient``. Real
PDF bytes are minted with reportlab so the FULL ingest path runs offline —
read → chunk → embed → graph write → §9.0 servability registration — and
we assert on actual DuckDB row counts and the resolved servability.

Coverage:

Rights logic (M2):
  1. Gutenberg copyright=false → public_domain candidate w/ specific basis
  2. Gutenberg copyright=true → no candidate (skipped)
  3. Gutenberg copyright=null (unknown) → no candidate (skipped)
  4. Gutenberg PD work with no PDF format → skipped
  5. archive.org explicit "public domain" rights → candidate
  6. archive.org ambiguous rights → no candidate (skipped)

Ingest + servability (M2/M3):
  7. explicit-PD work → ingested content_class=public_domain, servable,
     non-empty license_basis, non-empty body text
  8. ambiguous/unknown-rights work → NOT ingested servable (skip outcome)
  9. corrupt/truncated PDF → that item skipped, raises nothing to caller
  10. download failure (SourceError) → that item skipped, batch continues

Idempotency (M3):
  11. same work ingested twice → one documents row, not two (row count)

Throttle/retry (M1):
  12. SourceClient retries a 429 then succeeds; throttle serializes requests

CLI / curated (M4):
  13. dry-run lists candidates, writes nothing
  14. curated id list resolves to a candidate batch via the fake client
"""

from __future__ import annotations

import io
import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.books.public_domain import (
    PublicDomainWork,
    SourceClient,
    SourceError,
    archive_candidate,
    gutenberg_candidates,
    ingest_work,
    strip_gutenberg_boilerplate,
    text_to_pdf,
)

# ---------------------------------------------------------------------------
# Real-PDF fixture (reportlab) — offline, exercises the full read path
# ---------------------------------------------------------------------------


def _make_pdf(title: str, body: str, *, pages: int = 3) -> bytes:
    """Mint a small but real multi-page PDF with extractable text + a title,
    so read_pdf/pypdf produces non-empty markdown above the word gate."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle(title)
    for page in range(pages):
        text = c.beginText(72, 720)
        text.textLine(title)
        for i in range(40):  # enough words to clear MIN_INGEST_WORD_COUNT
            text.textLine(f"Page {page + 1} line {i}: {body}")
        c.drawText(text)
        c.showPage()
    c.save()
    return buf.getvalue()


_PD_PDF = _make_pdf(
    "On Liberty",
    "the only freedom which deserves the name is that of pursuing our own good",
)

# A Gutenberg-style plain-text file: license header, START/END markers, body.
_GUTENBERG_BODY = (
    "The only freedom which deserves the name is that of pursuing our own "
    "good in our own way, so long as we do not attempt to deprive others of "
    "theirs or impede their efforts to obtain it. " * 30
)
_GUTENBERG_TXT = (
    "﻿The Project Gutenberg eBook of On Liberty\r\n\r\n"
    "This eBook is for the use of anyone anywhere in the United States and\r\n"
    "most other parts of the world at no cost and with almost no restrictions\r\n"
    "whatsoever.\r\n\r\n"
    "*** START OF THE PROJECT GUTENBERG EBOOK ON LIBERTY ***\r\n\r\n"
    + _GUTENBERG_BODY
    + "\r\n\r\n*** END OF THE PROJECT GUTENBERG EBOOK ON LIBERTY ***\r\n"
    "Some trailing license boilerplate that must be trimmed.\r\n"
).encode("utf-8")


# ---------------------------------------------------------------------------
# Fake source client — no network
# ---------------------------------------------------------------------------


class FakeSourceClient:
    """Records canned JSON-by-URL and bytes-by-URL. Same surface the real
    ``SourceClient`` exposes (``get_json`` / ``get_bytes``)."""

    def __init__(self, *, json_by_url=None, bytes_by_url=None):
        self._json = json_by_url or {}
        self._bytes = bytes_by_url or {}
        self.json_calls: list[str] = []
        self.bytes_calls: list[str] = []

    def get_json(self, url: str, *, params: dict | None = None) -> dict:
        self.json_calls.append(url)
        if url not in self._json:
            raise SourceError(f"no canned json for {url}")
        return self._json[url]

    def get_bytes(self, url: str) -> bytes:
        self.bytes_calls.append(url)
        if url not in self._bytes:
            raise SourceError(f"download failed (no canned bytes) for {url}")
        return self._bytes[url]


def _gutendex_page(books: list[dict], *, next_url=None) -> dict:
    return {"count": len(books), "next": next_url, "previous": None, "results": books}


def _gutenberg_book(
    book_id: int, *, copyright_flag, with_text=True, with_pdf=False, title="On Liberty"
):
    """Mirror real Gutendex shape (verified 2026-05-28): plain-text is the
    norm, PDF is essentially never offered. ``with_pdf`` exists only to
    exercise the direct-PDF branch; ``with_text=False, with_pdf=False`` is
    the no-ingestible-format case."""
    formats = {
        "text/html": f"https://www.gutenberg.org/ebooks/{book_id}.html.images",
        "application/epub+zip": f"https://www.gutenberg.org/ebooks/{book_id}.epub3.images",
    }
    if with_text:
        formats["text/plain; charset=utf-8"] = (
            f"https://www.gutenberg.org/ebooks/{book_id}.txt.utf-8"
        )
    if with_pdf:
        formats["application/pdf"] = f"https://www.gutenberg.org/files/{book_id}/{book_id}-pdf.pdf"
    return {
        "id": book_id,
        "title": title,
        "authors": [{"name": "Mill, John Stuart", "birth_year": 1806, "death_year": 1873}],
        "subjects": ["Liberty", "Political science"],
        "copyright": copyright_flag,
        "formats": formats,
    }


_GUTENDEX_URL = "https://gutendex.com/books"


# ---------------------------------------------------------------------------
# Temp substrate
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_substrate(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-pd-test-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmpdir}


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


# ---------------------------------------------------------------------------
# 1-6: rights logic
# ---------------------------------------------------------------------------


def test_gutenberg_copyright_false_is_public_domain():
    client = FakeSourceClient(
        json_by_url={_GUTENDEX_URL: _gutendex_page([_gutenberg_book(7370, copyright_flag=False)])}
    )
    works = gutenberg_candidates(client, ids=[7370], limit=5)
    assert len(works) == 1
    w = works[0]
    assert w.source == "project_gutenberg"
    assert w.pd_basis is not None
    assert "Project Gutenberg" in w.pd_basis
    assert "public domain" in w.pd_basis.lower()
    # real Gutenberg serves plain text, not PDF — we ingest via text→PDF
    assert w.download_format == "text"
    assert w.download_url.endswith(".txt.utf-8")


def test_gutenberg_prefers_pdf_when_offered():
    client = FakeSourceClient(
        json_by_url={
            _GUTENDEX_URL: _gutendex_page(
                [_gutenberg_book(7370, copyright_flag=False, with_pdf=True)]
            )
        }
    )
    (w,) = gutenberg_candidates(client, ids=[7370], limit=5)
    assert w.download_format == "pdf"
    assert w.download_url.endswith(".pdf")


def test_gutenberg_copyright_true_skipped():
    client = FakeSourceClient(
        json_by_url={_GUTENDEX_URL: _gutendex_page([_gutenberg_book(1, copyright_flag=True)])}
    )
    assert gutenberg_candidates(client, ids=[1], limit=5) == []


def test_gutenberg_copyright_unknown_skipped():
    client = FakeSourceClient(
        json_by_url={_GUTENDEX_URL: _gutendex_page([_gutenberg_book(2, copyright_flag=None)])}
    )
    assert gutenberg_candidates(client, ids=[2], limit=5) == []


def test_gutenberg_no_ingestible_format_skipped():
    client = FakeSourceClient(
        json_by_url={
            _GUTENDEX_URL: _gutendex_page(
                [_gutenberg_book(3, copyright_flag=False, with_text=False, with_pdf=False)]
            )
        }
    )
    assert gutenberg_candidates(client, ids=[3], limit=5) == []


def test_archive_explicit_public_domain_candidate():
    ident = "onlibertytext"
    client = FakeSourceClient(
        json_by_url={
            f"https://archive.org/metadata/{ident}": {
                "metadata": {
                    "title": "On Liberty",
                    "creator": "John Stuart Mill",
                    "rights": "Public Domain",
                },
                "files": [{"name": "onliberty.pdf"}, {"name": "meta.xml"}],
            }
        }
    )
    w = archive_candidate(client, ident)
    assert w is not None
    assert w.source == "archive_org"
    assert "public domain" in w.pd_basis.lower()
    assert w.download_url.endswith(".pdf")


def test_archive_ambiguous_rights_skipped():
    ident = "ambiguous"
    client = FakeSourceClient(
        json_by_url={
            f"https://archive.org/metadata/{ident}": {
                "metadata": {"title": "Maybe", "rights": "All rights reserved"},
                "files": [{"name": "x.pdf"}],
            }
        }
    )
    assert archive_candidate(client, ident) is None


def test_archive_negated_public_domain_skipped():
    """Deny-by-default: a rights string that contains "public domain" but
    explicitly NEGATES it must not be classed public_domain just because the
    PD token substring-matches (verified BLOCKER: "NOT in the public domain"
    was accepted)."""
    from acquisition.books.public_domain import _archive_pd_basis

    # The full archive path skips negated rights.
    ident = "negated"
    client = FakeSourceClient(
        json_by_url={
            f"https://archive.org/metadata/{ident}": {
                "metadata": {
                    "title": "Still Copyrighted",
                    "rights": "This work is NOT in the public domain",
                },
                "files": [{"name": "x.pdf"}],
            }
        }
    )
    assert archive_candidate(client, ident) is None

    # And the basis mapper itself returns None for the negated phrase while a
    # clean PD / CC0 statement still yields a basis.
    assert (
        _archive_pd_basis(
            {"rights": "This work is NOT in the public domain"}, "neg"
        )
        is None
    )
    assert _archive_pd_basis({"rights": "Public Domain"}, "clean") is not None
    assert (
        _archive_pd_basis(
            {"licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/"},
            "cc0",
        )
        is not None
    )


def test_archive_copyright_claim_with_pd_token_skipped():
    """An affirmative copyright claim (©/copyright + year) denies PD even when
    "public domain" also appears — a copyrighted work must never be classed
    public_domain on a co-present PD substring. A false-positive PD is the
    higher-cost error here (§9 provenance/legal gate)."""
    from acquisition.books.public_domain import _archive_pd_basis

    # © + year alongside a PD-token phrase: deny.
    assert (
        _archive_pd_basis(
            {"rights": "© 2021 Penguin. Public domain text reproduced."}, "c1"
        )
        is None
    )
    # "Copyright <year>" alongside "public domain edition": deny.
    assert (
        _archive_pd_basis(
            {"rights": "Copyright 2020 Acme. public domain edition"}, "c2"
        )
        is None
    )
    # "(c) <year>" form: deny.
    assert _archive_pd_basis({"rights": "(c) 2019 Author. public domain"}, "c3") is None
    # Critical false-negative guard: the legitimate "No known copyright
    # restrictions" PD statement (no year) must STILL yield a basis — the
    # year-anchored copyright-claim regex must not clobber it.
    assert (
        _archive_pd_basis({"rights": "No known copyright restrictions"}, "nkc")
        is not None
    )


# ---------------------------------------------------------------------------
# 7-10: ingest + servability + failure isolation
# ---------------------------------------------------------------------------


def test_explicit_pd_work_ingested_servable(temp_substrate):
    import duckdb

    book = _gutenberg_book(7370, copyright_flag=False)
    txt_url = book["formats"]["text/plain; charset=utf-8"]
    client = FakeSourceClient(
        json_by_url={_GUTENDEX_URL: _gutendex_page([book])},
        bytes_by_url={txt_url: _GUTENBERG_TXT},
    )
    (work,) = gutenberg_candidates(client, ids=[7370], limit=1)
    assert work.download_format == "text"
    outcome = ingest_work(
        work, client, db_path=temp_substrate["db_path"], embedder=_StubEmbedder()
    )
    assert outcome.ingested is True
    assert outcome.servability == "public_domain"
    assert outcome.servable_full_text is True
    assert outcome.word_count > 0

    con = duckdb.connect(temp_substrate["db_path"])
    try:
        content_class, license_basis = con.execute(
            "SELECT d.content_class, b.license_basis "
            "FROM documents d JOIN book_assets b ON d.document_id = b.document_id "
            "WHERE d.document_id = ?",
            [outcome.document_id],
        ).fetchone()
        (raw_text,) = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?",
            [outcome.document_id],
        ).fetchone()
    finally:
        con.close()
    assert content_class == "public_domain"
    assert license_basis and "Project Gutenberg" in license_basis
    assert raw_text and len(raw_text) > 0
    assert "deserves the name" in raw_text  # real body extracted readably
    assert "trailing license boilerplate" not in raw_text  # END marker trimmed


def test_ambiguous_work_not_ingested_servable(temp_substrate):
    """A work with no explicit PD basis must NOT be ingested servable —
    asserted explicitly (rigor #1)."""
    work = PublicDomainWork(
        source="archive_org",
        source_id="unknown-rights",
        title="Unknown Rights Work",
        author=None,
        source_uri="https://archive.org/details/unknown-rights",
        download_url="https://archive.org/download/unknown-rights/x.pdf",
        download_format="pdf",
        pd_basis=None,
    )
    client = FakeSourceClient(bytes_by_url={work.download_url: _PD_PDF})
    outcome = ingest_work(
        work, client, db_path=temp_substrate["db_path"], embedder=_StubEmbedder()
    )
    assert outcome.ingested is False
    assert outcome.document_id is None
    assert outcome.skipped_reason == "no_explicit_public_domain_basis"
    assert client.bytes_calls == []  # never even downloaded


def test_corrupt_pdf_skips_item_not_batch(temp_substrate):
    book = _gutenberg_book(99, copyright_flag=False, with_pdf=True, title="Corrupt")
    pdf_url = book["formats"]["application/pdf"]
    client = FakeSourceClient(
        json_by_url={_GUTENDEX_URL: _gutendex_page([book])},
        bytes_by_url={pdf_url: b"%PDF-1.4 truncated garbage not a real pdf"},
    )
    (work,) = gutenberg_candidates(client, ids=[99], limit=1)
    assert work.download_format == "pdf"
    outcome = ingest_work(
        work, client, db_path=temp_substrate["db_path"], embedder=_StubEmbedder()
    )
    assert outcome.ingested is False
    assert outcome.skipped_reason is not None


def test_download_failure_skips_item(temp_substrate):
    work = PublicDomainWork(
        source="project_gutenberg",
        source_id="500",
        title="Vanished",
        author=None,
        source_uri="https://www.gutenberg.org/ebooks/500",
        download_url="https://www.gutenberg.org/files/500/500-pdf.pdf",
        download_format="pdf",
        pd_basis="Project Gutenberg; US public domain",
    )
    client = FakeSourceClient()  # no canned bytes → get_bytes raises SourceError
    outcome = ingest_work(
        work, client, db_path=temp_substrate["db_path"], embedder=_StubEmbedder()
    )
    assert outcome.ingested is False
    assert outcome.skipped_reason.startswith("download_failed")


# ---------------------------------------------------------------------------
# 11: idempotency by row count
# ---------------------------------------------------------------------------


def test_ingest_idempotent_by_row_count(temp_substrate):
    import duckdb

    book = _gutenberg_book(7370, copyright_flag=False)
    txt_url = book["formats"]["text/plain; charset=utf-8"]
    client = FakeSourceClient(
        json_by_url={_GUTENDEX_URL: _gutendex_page([book])},
        bytes_by_url={txt_url: _GUTENBERG_TXT},
    )
    (work,) = gutenberg_candidates(client, ids=[7370], limit=1)

    o1 = ingest_work(work, client, db_path=temp_substrate["db_path"], embedder=_StubEmbedder())

    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (docs_after_first,) = con.execute("SELECT COUNT(*) FROM documents").fetchone()
    finally:
        con.close()

    o2 = ingest_work(work, client, db_path=temp_substrate["db_path"], embedder=_StubEmbedder())

    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (docs_after_second,) = con.execute("SELECT COUNT(*) FROM documents").fetchone()
        (asset_count,) = con.execute(
            "SELECT COUNT(*) FROM book_assets WHERE document_id = ?", [o1.document_id]
        ).fetchone()
    finally:
        con.close()

    assert o1.document_id == o2.document_id
    assert docs_after_first == docs_after_second  # second run added zero documents
    assert asset_count == 1


# ---------------------------------------------------------------------------
# 12: throttle + retry (real SourceClient, fake transport)
# ---------------------------------------------------------------------------


def test_source_client_retries_429_then_succeeds(monkeypatch):

    class _Resp:
        def __init__(self, status, payload=None):
            self.status_code = status
            self._payload = payload or {}
            self.content = b"ok"

        def json(self):
            return self._payload

    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(429)
        return _Resp(200, {"results": []})

    sleeps: list[float] = []
    monkeypatch.setattr("acquisition.books.public_domain.time.sleep", lambda s: sleeps.append(s))

    client = SourceClient(min_interval_s=0.0, max_retries=3)
    monkeypatch.setattr(client._session, "get", fake_get)

    out = client.get_json("https://gutendex.com/books")
    assert out == {"results": []}
    assert calls["n"] == 2  # one 429 retry then success
    assert any(s > 0 for s in sleeps)  # backed off


def test_source_client_exhausts_retries_raises(monkeypatch):
    class _Resp:
        status_code = 503
        content = b""

        def json(self):
            return {}

    monkeypatch.setattr("acquisition.books.public_domain.time.sleep", lambda s: None)
    client = SourceClient(min_interval_s=0.0, max_retries=2)
    monkeypatch.setattr(client._session, "get", lambda *a, **k: _Resp())
    with pytest.raises(SourceError):
        client.get_json("https://gutendex.com/books")


# ---------------------------------------------------------------------------
# 13-14: CLI dry-run + curated
# ---------------------------------------------------------------------------


def test_cli_dry_run_writes_nothing(temp_substrate, monkeypatch, capsys):
    import tools.ingest_public_domain as cli

    book = _gutenberg_book(7370, copyright_flag=False)
    fake = FakeSourceClient(json_by_url={_GUTENDEX_URL: _gutendex_page([book])})
    monkeypatch.setattr(cli, "SourceClient", lambda **kw: fake)

    rc = cli.main(["--ids", "7370", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "On Liberty" in out
    assert fake.bytes_calls == []  # nothing downloaded


def test_cli_curated_resolves_batch(temp_substrate, monkeypatch):
    import tools.ingest_public_domain as cli

    # canned page returns one PD book regardless of which curated ids are asked
    book = _gutenberg_book(1497, copyright_flag=False, title="The Republic")
    fake = FakeSourceClient(json_by_url={_GUTENDEX_URL: _gutendex_page([book])})

    works = cli.discover(
        fake, subject=None, search=None, ids=None, curated=True, limit=5
    )
    assert len(works) == 1
    assert works[0].title == "The Republic"
    assert works[0].pd_basis is not None


# ---------------------------------------------------------------------------
# 15-17: text→PDF bridge + boilerplate strip (Gutenberg's real format path)
# ---------------------------------------------------------------------------


def test_strip_gutenberg_boilerplate_trims_markers():
    out = strip_gutenberg_boilerplate(_GUTENBERG_TXT.decode("utf-8"))
    assert "deserves the name" in out
    assert "This eBook is for the use" not in out  # header trimmed
    assert "trailing license boilerplate" not in out  # footer trimmed


def test_strip_gutenberg_boilerplate_no_markers_unchanged():
    text = "A work with no Gutenberg markers at all."
    assert strip_gutenberg_boilerplate(text) == text


def test_text_to_pdf_roundtrips_through_reader():
    from acquisition.books.reader import read_pdf

    body = "The quick brown fox jumps over the lazy dog. " * 40
    pdf = text_to_pdf(body, title="Round Trip")
    assert pdf[:4] == b"%PDF"
    r = read_pdf(pdf)
    assert "quick brown fox" in r.markdown
    assert r.word_count > 100


def test_text_to_pdf_is_byte_deterministic():
    """Idempotency depends on this: the same text must render to the same
    bytes so the adapter's content-hash doc id is stable across runs."""
    body = "deterministic body text " * 50
    assert text_to_pdf(body, title="T") == text_to_pdf(body, title="T")


def test_text_to_pdf_preserves_unicode_and_is_deterministic():
    """Regression lock for the Unicode BLOCKERs in the text→PDF bridge.

    Round 1's bug: the bridge coerced every line to Latin-1 with "replace",
    turning œ ligatures, smart quotes, em-dashes, accents, and Greek into "?"
    — silently corrupting the philosophy corpus (e.g. "Ph?nicians",
    "Renan?s ?Marc-Aurèle").

    Round 2's bug (the deeper one): the fix registered a Unicode TTF but
    sourced it from matplotlib's install dir, which is NOT an Antiek
    dependency. On a clean install matplotlib is absent → fallback to
    reportlab's Vera, which has NO Greek glyphs. Greek then renders as
    ``.notdef`` and extracts back as NUL ("\\x00") rather than "?", so the
    corpus loses its Greek silently while a "?"-only check still passes.

    The fix vendors DejaVuSans into ``acquisition/books/fonts/`` and resolves
    it relative to the module, so this test exercises the vendored path with
    NO dependence on matplotlib being installed. It locks the properties the
    fix must hold simultaneously:
      (a) the glyphs round-trip through text_to_pdf → read_pdf with ZERO "?"
          substitution,
      (b) the round-trip contains NO NUL char — the gate that catches the
          ``.notdef``→NUL silent-corruption mode the Vera fallback caused, and
      (c) two renders of the same text are byte-identical (idempotency)."""
    from acquisition.books.reader import read_pdf

    glyphs = ["œ", "‘", "’", "“", "”", "—", "è", "Φυσικά"]
    sample = (
        "Phoenicians œuvre ‘smart’ “quotes” "
        "em—dash accented è Greek Φυσικά"
    )

    pdf = text_to_pdf(sample, title="UnicodeRegression")
    assert pdf[:4] == b"%PDF"

    r = read_pdf(pdf)
    extracted = r.markdown
    # (a) No glyph was dropped to a "?" replacement char.
    assert extracted.count("?") == 0
    # (b) No glyph was dropped to a .notdef → NUL — the silent-corruption mode
    #     the non-Greek Vera fallback produced. This is the assertion that
    #     would have caught the matplotlib-dependence regression.
    assert "\x00" not in extracted
    for g in glyphs:
        assert g in extracted, f"glyph {g!r} did not survive the round-trip"

    # (c) byte-determinism: idempotency depends on identical bytes.
    assert text_to_pdf(sample, title="UnicodeRegression") == pdf
