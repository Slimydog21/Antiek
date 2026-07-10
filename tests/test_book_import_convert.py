"""Book-import SPR-02 — real epub → Antiek-HTML conversion engine tests.

The fixture epub is built PROGRAMMATICALLY with ``zipfile`` (an epub is a zip
of XHTML) — no network, no binary blobs in the repo. The suite proves:

- a real multi-chapter epub converts to sanitized Antiek HTML preserving
  chapter structure, headings, paragraphs, and internal anchors;
- conversion is deterministic and the output is a sanitizer fixed point;
- a hostile epub (scripts/handlers/javascript: URLs inside chapters) converts
  to provably inert output — and the raw chapters ARE dangerous (red-proof);
- malformed/hostile CONTAINERS (path traversal, zip-bomb budgets, external
  entities, DRM, non-zip, wrong mimetype, dangling spine) fail CLOSED with
  the typed error vocabulary, publishing nothing;
- publish lands the book through the EXISTING substrate seams: sanitized
  raw_text + trusted-HTML provenance, chunks via the SAME chunk_markdown the
  native books path uses (chunking parity), register_book's deny-by-default
  rights gate, and §9.0 retrieval-gate behaviour.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

import substrate.book_import.publish as publish_module
from processing.chunking.chunker import chunk_markdown
from runtime.db_lock import connect_read, connect_write
from substrate.book_import import (
    ConvertedBook,
    DrmLockedError,
    EpubLimits,
    ExternalEntityBlockedError,
    MalformedEpubError,
    MissingPublishedChunksError,
    NotAnEpubError,
    NoTextContentError,
    PublishedBookImport,
    RepublishRightsChangeError,
    StoredBodyMismatchError,
    UnsafeArchivePathError,
    ZipBombSuspectedError,
    book_publication_transaction,
    convert_epub_to_antiek_html,
    publish_converted_book,
)
from substrate.books.html_sanitizer import is_trusted_sanitized, sanitize_book_html
from substrate.books.model import get_book_asset
from substrate.books.serve import serve_full_text
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database

# ---------------------------------------------------------------------------
# Programmatic epub fixture (an epub is a zip of XHTML — built with zipfile).
# ---------------------------------------------------------------------------

_CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _chapter_xhtml(title: str, body_inner: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title}</title><style>p {{ color: red }}</style></head>
<body>
<h1 id="{title.lower().replace(" ", "-")}">{title}</h1>
{body_inner}
</body>
</html>
"""


_DEFAULT_CHAPTERS: list[tuple[str, str]] = [
    (
        "Chapter One",
        "<p>It was the best of <em>times</em>; see "
        '<a href="#note-1">the note</a>.</p>'
        '<p id="note-1">The note itself, anchored for internal linking.</p>'
        "<ul><li>a first point</li><li>a second point</li></ul>",
    ),
    (
        "Chapter Two",
        "<h2>A Section Within</h2>"
        "<p>Continuing prose with <strong>emphasis</strong> and a "
        '<a href="https://example.org/ref">reference</a>.</p>'
        "<blockquote><p>A quoted passage inside chapter two.</p></blockquote>",
    ),
    (
        "Chapter Three",
        "<p>The closing chapter's paragraph, long enough to matter.</p>"
        "<pre><code>x = 1</code></pre>",
    ),
]


def _opf(chapter_names: list[str]) -> str:
    items = "\n".join(
        f'    <item id="ch{i}" href="{name}" media-type="application/xhtml+xml"/>'
        for i, name in enumerate(chapter_names)
    )
    refs = "\n".join(f'    <itemref idref="ch{i}"/>' for i in range(len(chapter_names)))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">urn:uuid:0000-fixture</dc:identifier>
    <dc:title>The Fixture Book</dc:title>
    <dc:creator>A. Fixture Author</dc:creator>
  </metadata>
  <manifest>
{items}
  </manifest>
  <spine>
{refs}
  </spine>
</package>
"""


def _build_epub(
    chapters: list[tuple[str, str]] | None = None,
    *,
    mimetype: str | None = "application/epub+zip",
    include_container: bool = True,
    container_xml: str | None = None,
    opf_xml: str | None = None,
    drm: bool = False,
    extra_entries: dict[str, bytes] | None = None,
) -> bytes:
    chapters = _DEFAULT_CHAPTERS if chapters is None else chapters
    names = [f"ch{i + 1}.xhtml" for i in range(len(chapters))]
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if mimetype is not None:
            zf.writestr("mimetype", mimetype)
        if include_container:
            zf.writestr("META-INF/container.xml", container_xml or _CONTAINER_XML)
        if drm:
            zf.writestr("META-INF/encryption.xml", "<encryption/>")
        zf.writestr("OEBPS/content.opf", opf_xml or _opf(names))
        for name, (title, body) in zip(names, chapters, strict=True):
            zf.writestr(f"OEBPS/{name}", _chapter_xhtml(title, body))
        for name, data in (extra_entries or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


# Compact danger predicate (mirrors the SPR-01 suite's browser model).
_DANGER_MARKS = (
    "<script", "<iframe", "<svg", "<style", "onerror=", "onclick=",
    "onload=", "javascript:", "vbscript:", "expression(", "url(javascript",
)


def _looks_dangerous(text: str) -> bool:
    flat = "".join(ch for ch in text.lower() if ch not in "\t\n\r")
    return any(mark in flat for mark in _DANGER_MARKS)


# ---------------------------------------------------------------------------
# Conversion — the happy path.
# ---------------------------------------------------------------------------


def test_multichapter_epub_converts_with_structure() -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    assert converted.title == "The Fixture Book"
    assert converted.author == "A. Fixture Author"
    assert converted.chapter_count == 3
    # Chapter wrappers, in order.
    for i in (1, 2, 3):
        assert f'<section id="antiek-chapter-{i}">' in converted.html
    # Headings + paragraphs survive.
    assert '<h1 id="chapter-one">Chapter One</h1>' in converted.html
    assert "<h2>A Section Within</h2>" in converted.html
    assert "<em>times</em>" in converted.html
    # Internal anchors preserved end-to-end (link AND its target id).
    assert '<a href="#note-1">' in converted.html
    assert '<p id="note-1">' in converted.html
    # External https link preserved; chapter <style> block gone.
    assert '<a href="https://example.org/ref">' in converted.html
    assert "color: red" not in converted.html


def test_markdown_projection_is_heading_aware() -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    assert "# Chapter One" in converted.markdown
    assert "## A Section Within" in converted.markdown
    assert "- a first point" in converted.markdown
    assert "> A quoted passage inside chapter two." in converted.markdown
    assert "<" not in converted.markdown.replace("<!--", "")  # no markup leaks


def test_toc_collected_per_chapter() -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    titles = [(h.title, h.level, h.chapter_index) for h in converted.toc]
    assert ("Chapter One", 1, 0) in titles
    assert ("A Section Within", 2, 1) in titles
    assert ("Chapter Three", 1, 2) in titles
    ch1 = next(h for h in converted.toc if h.title == "Chapter One")
    assert ch1.anchor == "chapter-one"


def test_convert_from_path_matches_bytes(tmp_path: Path) -> None:
    data = _build_epub()
    epub_path = tmp_path / "fixture.epub"
    epub_path.write_bytes(data)
    from_path = convert_epub_to_antiek_html(str(epub_path))
    from_bytes = convert_epub_to_antiek_html(data)
    assert from_path == from_bytes


def test_conversion_is_deterministic() -> None:
    data = _build_epub()
    a = convert_epub_to_antiek_html(data)
    b = convert_epub_to_antiek_html(data)
    assert a.html == b.html
    assert a.markdown == b.markdown
    assert a.toc == b.toc


def test_output_is_a_sanitizer_fixed_point() -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    assert sanitize_book_html(converted.html) == converted.html


# ---------------------------------------------------------------------------
# Hostile content INSIDE chapters — the sanitize belt (red-proven).
# ---------------------------------------------------------------------------

_HOSTILE_CHAPTERS: list[tuple[str, str]] = [
    (
        "Trojan Chapter",
        "<p>readable prose</p>"
        "<script>fetch('/api/steal')</script>"
        '<img src="x" onerror="alert(1)"/>'
        '<a href="javascript:alert(1)">click</a>'
        '<p style="width:expression(alert(1))">styled</p>',
    ),
    ("Plain Chapter", "<p>innocent text after the trojan.</p>"),
]


def test_red_proof_hostile_chapters_are_dangerous_raw() -> None:
    """The raw fixture chapters WOULD be dangerous unsanitized — so a
    pass-through converter provably fails the inertness test below."""
    raw = _chapter_xhtml(*_HOSTILE_CHAPTERS[0])
    assert _looks_dangerous(raw)


def test_hostile_epub_converts_to_inert_html() -> None:
    converted = convert_epub_to_antiek_html(_build_epub(_HOSTILE_CHAPTERS))
    assert not _looks_dangerous(converted.html)
    assert "readable prose" in converted.html
    assert "innocent text after the trojan." in converted.html


def test_hostile_epub_chunks_carry_no_script() -> None:
    """Talk-to-book grounds on the chunk text — script bodies must not reach
    it even as plain text (prompt-injection surface)."""
    converted = convert_epub_to_antiek_html(_build_epub(_HOSTILE_CHAPTERS))
    for chunk in chunk_markdown(converted.markdown):
        assert "fetch('/api/steal')" not in chunk.text
        assert "alert(1)" not in chunk.text


# ---------------------------------------------------------------------------
# Hostile CONTAINERS — typed, fail-closed refusals.
# ---------------------------------------------------------------------------


def test_not_a_zip_fails_closed() -> None:
    with pytest.raises(NotAnEpubError):
        convert_epub_to_antiek_html(b"this is definitely not an epub")


def test_wrong_mimetype_fails_closed() -> None:
    with pytest.raises(NotAnEpubError):
        convert_epub_to_antiek_html(_build_epub(mimetype="text/plain"))


def test_missing_container_fails_closed() -> None:
    with pytest.raises(MalformedEpubError):
        convert_epub_to_antiek_html(_build_epub(include_container=False))


def test_dangling_spine_ref_fails_closed() -> None:
    opf = _opf(["ch1.xhtml", "ghost.xhtml"])  # ghost never written
    with pytest.raises(MalformedEpubError):
        convert_epub_to_antiek_html(
            _build_epub([_DEFAULT_CHAPTERS[0]], opf_xml=opf)
        )


def test_drm_locked_fails_closed_never_bypassed() -> None:
    with pytest.raises(DrmLockedError):
        convert_epub_to_antiek_html(_build_epub(drm=True))


@pytest.mark.parametrize("evil_name", ["../evil.xhtml", "/abs/evil.xhtml", "..\\evil.xhtml"])
def test_path_traversal_member_fails_closed(evil_name: str) -> None:
    data = _build_epub(extra_entries={evil_name: b"<p>evil</p>"})
    with pytest.raises(UnsafeArchivePathError):
        convert_epub_to_antiek_html(data)


def test_entry_count_budget_fails_closed() -> None:
    with pytest.raises(ZipBombSuspectedError):
        convert_epub_to_antiek_html(_build_epub(), limits=EpubLimits(max_entries=3))


def test_total_size_budget_fails_closed() -> None:
    with pytest.raises(ZipBombSuspectedError):
        convert_epub_to_antiek_html(
            _build_epub(), limits=EpubLimits(max_total_bytes=512)
        )


def test_compression_ratio_bomb_fails_closed() -> None:
    """A tiny compressed entry inflating enormously (the classic bomb shape)
    trips the ratio guard — proven with REAL enforcement at tightened limits,
    not a mocked check."""
    bomb = _build_epub(extra_entries={"OEBPS/padding.txt": b"\x00" * 200_000})
    with pytest.raises(ZipBombSuspectedError):
        convert_epub_to_antiek_html(
            bomb,
            limits=EpubLimits(ratio_floor_bytes=1_000, max_compression_ratio=10),
        )


def test_external_entity_in_opf_fails_closed() -> None:
    evil_opf = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE package [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>\n'
        + _opf(["ch1.xhtml"]).split("\n", 1)[1]
    )
    with pytest.raises(ExternalEntityBlockedError):
        convert_epub_to_antiek_html(
            _build_epub([_DEFAULT_CHAPTERS[0]], opf_xml=evil_opf)
        )


def test_external_entity_in_chapter_fails_closed() -> None:
    chapters = [
        (
            "XXE Chapter",
            '<!ENTITY xxe SYSTEM "file:///etc/passwd"><p>&xxe;</p>',
        )
    ]
    with pytest.raises(ExternalEntityBlockedError):
        convert_epub_to_antiek_html(_build_epub(chapters))


def test_empty_book_fails_closed() -> None:
    """All-empty chapters must refuse, never publish a hollow book."""
    with pytest.raises(NoTextContentError):
        convert_epub_to_antiek_html(_build_epub([("", ""), ("", "")]))


# ---------------------------------------------------------------------------
# Publish — into the REAL substrate (DuckDB), through the existing seams.
# ---------------------------------------------------------------------------


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) * (i + 1) for i, c in enumerate(text)) or 1
        return [
            float(h % 7) / 7.0, float((h >> 3) % 11) / 11.0,
            float((h >> 5) % 13) / 13.0, float((h >> 7) % 17) / 17.0,
        ]


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> str:
    """Isolated graph DB + events dir (same idiom as test_book_corpus_gate)."""
    tmp = tempfile.mkdtemp(prefix="antiek-book-import-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    con = connect_write(db_path, purpose="book-import-test")
    init_database(con)
    con.close()
    return db_path


def _publish(
    db_path: str,
    converted: ConvertedBook,
    *,
    content_class: str | None = None,
    rights_holder_name: str | None = None,
    license_basis: str | None = None,
    embedder: StubEmbedding | None = None,
) -> PublishedBookImport:
    con = connect_write(db_path, purpose="book-import-publish")
    try:
        return publish_converted_book(
            con,
            converted,
            content_class=content_class,
            rights_holder_name=rights_holder_name,
            license_basis=license_basis,
            embedder=embedder,
        )
    finally:
        con.close()

def test_publish_stores_sanitized_body_with_trusted_provenance(db: str) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    result = _publish(db, converted)
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT raw_text, metadata, document_type FROM documents WHERE document_id = ?",
            [result.document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    raw_text, metadata, document_type = row
    assert document_type == "book"
    assert raw_text == converted.html  # stored body IS the sanitized html
    assert is_trusted_sanitized(metadata)  # the SPR-01 contract bit, stamped


def test_publish_is_deny_by_default_gated(db: str) -> None:
    """No declared rights → the book lands GATED: full text is refused at the
    serve gate; only a bounded snippet escapes. Converting never upgrades
    rights."""
    converted = convert_epub_to_antiek_html(_build_epub())
    result = _publish(db, converted)
    assert result.servability == "gated_metadata_only"
    con = connect_read(db)
    try:
        served = serve_full_text(con, result.document_id)
    finally:
        con.close()
    assert served.servable is False
    assert served.full_text is None
    assert served.snippet  # bounded metadata-regime snippet only


def test_publish_public_domain_serves_sanitized_full_text(db: str) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    result = _publish(db, converted, content_class="public_domain")
    con = connect_read(db)
    try:
        served = serve_full_text(con, result.document_id)
    finally:
        con.close()
    assert served.servable is True
    assert served.full_text == converted.html
    assert not _looks_dangerous(served.full_text or "")


def test_publish_registers_book_asset_with_chapter_toc(db: str) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    result = _publish(db, converted)
    con = connect_read(db)
    try:
        asset = get_book_asset(con, result.document_id)
    finally:
        con.close()
    assert asset is not None
    assert asset.page_count == 3
    assert asset.pagination_scheme == "chapter"
    toc_titles = [(t.title, t.page_index) for t in asset.toc]
    assert ("Chapter One", 0) in toc_titles
    assert ("A Section Within", 1) in toc_titles
    assert ("Chapter Three", 2) in toc_titles


def test_publish_chunking_parity_with_native_seam(db: str) -> None:
    """The stored chunks must be EXACTLY what the native books path would
    produce for this text: acquisition/books/adapter.ingest_pdf feeds
    chunk_markdown(text) into insert_chunk — publish_converted_book feeds the
    SAME function the SAME way, so an imported book grounds identically to a
    natively-published one at the seam that exists on this branch."""
    converted = convert_epub_to_antiek_html(_build_epub())
    result = _publish(db, converted)
    expected = chunk_markdown(converted.markdown)  # the native path's chunker
    con = connect_read(db)
    try:
        rows = con.execute(
            "SELECT chunk_index, text, section_path, token_count FROM chunks "
            "WHERE document_id = ? ORDER BY chunk_index",
            [result.document_id],
        ).fetchall()
    finally:
        con.close()
    assert len(rows) == len(expected) > 0
    for (_idx, text, section_path, token_count), chunk in zip(rows, expected, strict=True):
        assert text == chunk.text
        assert section_path == (chunk.section or None)
        assert token_count == chunk.token_count
    # Chapter headings became section anchors — grounding carries structure.
    sections = {r[2] for r in rows}
    assert "Chapter One" in sections


def test_publish_is_idempotent_on_same_content(db: str) -> None:
    """Republish with identical args returns the existing state UNTOUCHED —
    content_class, servability, rights holder, license basis, provenance, and
    TOC are all byte-for-byte unchanged (judge r1 F7, tied to F1)."""
    converted = convert_epub_to_antiek_html(_build_epub())
    first = _publish(db, converted, content_class="public_domain")
    con = connect_read(db)
    try:
        before = get_book_asset(con, first.document_id)
    finally:
        con.close()

    # Identical explicit args → allowed, no-op.
    second = _publish(db, converted, content_class="public_domain")
    # None args (no change requested) → also allowed, no-op.
    third = _publish(db, converted)

    assert first.document_id == second.document_id == third.document_id
    assert first.was_new is True
    assert second.was_new is False and third.was_new is False
    assert second.chunk_count == 0 and third.chunk_count == 0
    assert second.content_class == "public_domain"
    assert third.servability == "public_domain"

    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [first.document_id],
        ).fetchone()
        after = get_book_asset(con, first.document_id)
    finally:
        con.close()
    assert row is not None
    assert row[0] == first.chunk_count
    assert before is not None and after is not None
    assert after.content_class == before.content_class == "public_domain"
    assert after.servability == before.servability
    assert after.ip_holder_id == before.ip_holder_id
    assert after.license_basis == before.license_basis
    assert after.provenance == before.provenance
    assert after.toc == before.toc


def test_republish_refuses_when_published_chunks_are_incomplete(db: str) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    first = _publish(db, converted, content_class="public_domain")
    assert first.chunk_count > 0

    con = connect_write(db, purpose="book-import-delete-chunks-red-proof")
    try:
        con.execute(
            "DELETE FROM chunks WHERE document_id = ? AND chunk_index = 0",
            [first.document_id],
        )
    finally:
        con.close()

    with pytest.raises(MissingPublishedChunksError, match="complete chunk set"):
        _publish(db, converted, content_class="public_domain")


def test_publish_retrieval_gate_parity(db: str) -> None:
    """§9.0 parity at retrieval: a servable imported book's chunks are
    retrievable through the SAME gated search talk-to-book grounds on; a
    gated (default) import's chunks are NOT, under the non-privileged tag."""
    from substrate.graph.search import search

    servable = convert_epub_to_antiek_html(_build_epub())
    gated_chapters = [("Hidden Chapter", "<p>entirely different withheld prose.</p>")]
    gated = convert_epub_to_antiek_html(_build_epub(gated_chapters))

    model = StubEmbedding()
    served_pub = _publish(db, servable, content_class="public_domain", embedder=model)
    gated_pub = _publish(db, gated, embedder=model)

    con = connect_read(db)
    try:
        hit = search(
            con, "Chapter One", model=model,
            document_id=served_pub.document_id,
        )
        miss = search(
            con, "withheld prose", model=model,
            document_id=gated_pub.document_id,
        )
    finally:
        con.close()
    assert hit["results"], "servable imported book must ground retrieval"
    assert miss["results"] == [], "gated imported book must NOT leak into retrieval"


def test_personal_reading_publish_avoids_parent_update_after_chunks(db: str) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    published = _publish(db, converted, content_class="personal_reading")
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [published.document_id],
        ).fetchone()
        chunks = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [published.document_id],
        ).fetchone()
    finally:
        con.close()
    assert row == ("personal_reading",)
    assert chunks is not None and chunks[0] > 0


def test_fresh_publish_rolls_back_all_rows_and_can_retry(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    events_dir = Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"])
    events_before = tuple(events_dir.iterdir())
    real_insert_chunk = publish_module.insert_chunk
    calls = 0

    def fail_second_chunk(*args: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected chunk failure")
        return real_insert_chunk(*args, **kwargs)

    monkeypatch.setattr(publish_module, "insert_chunk", fail_second_chunk)
    with pytest.raises(RuntimeError, match="injected chunk failure"):
        _publish(db, converted, content_class="personal_reading")

    con = connect_read(db)
    try:
        assert con.execute("SELECT COUNT(*) FROM documents").fetchone() == (0,)
        assert con.execute("SELECT COUNT(*) FROM book_assets").fetchone() == (0,)
        assert con.execute("SELECT COUNT(*) FROM chunks").fetchone() == (0,)
    finally:
        con.close()
    assert tuple(events_dir.iterdir()) == events_before

    monkeypatch.setattr(publish_module, "insert_chunk", real_insert_chunk)
    retried = _publish(db, converted, content_class="personal_reading")
    assert retried.was_new is True
    assert retried.content_class == "personal_reading"
    assert retried.chunk_count > 0


def test_rights_registration_failure_rolls_back_fresh_document(db: str) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    with pytest.raises(ValueError, match="unrecognised content_class"):
        _publish(db, converted, content_class="not-a-rights-class")

    con = connect_read(db)
    try:
        assert con.execute("SELECT COUNT(*) FROM documents").fetchone() == (0,)
        assert con.execute("SELECT COUNT(*) FROM book_assets").fetchone() == (0,)
        assert con.execute("SELECT COUNT(*) FROM chunks").fetchone() == (0,)
    finally:
        con.close()


def test_composed_transaction_can_atomically_rollback_publish(db: str) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    con = connect_write(db, purpose="book-import-caller-transaction-test")
    try:
        with (
            pytest.raises(RuntimeError, match="abort composed transaction"),
            book_publication_transaction(con) as transaction,
        ):
            published = publish_converted_book(
                con,
                converted,
                content_class="personal_reading",
                transaction=transaction,
            )
            assert con.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
                [published.document_id],
            ).fetchone()[0] > 0
            raise RuntimeError("abort composed transaction")
    finally:
        con.close()

    reader = connect_read(db)
    try:
        assert reader.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [published.document_id],
        ).fetchone() == (0,)
        assert reader.execute(
            "SELECT COUNT(*) FROM book_assets WHERE document_id = ?",
            [published.document_id],
        ).fetchone() == (0,)
        assert reader.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [published.document_id],
        ).fetchone() == (0,)
    finally:
        reader.close()


def test_committed_publish_emits_servability_audit_exactly_once(db: str) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    first = _publish(db, converted, content_class="personal_reading")
    event_path = Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]) / "system.jsonl"
    events = event_path.read_text().splitlines()
    assert len(events) == 1
    assert '"book.servability_changed"' in events[0]

    second = _publish(db, converted, content_class="personal_reading")
    assert second.document_id == first.document_id
    assert second.was_new is False
    assert event_path.read_text().splitlines() == events


def test_audit_sink_failure_is_repaired_by_idempotent_retry(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    real_emit = publish_module.emit_typed

    def fail_emit(*args: object, **kwargs: object) -> None:
        raise OSError("injected audit sink failure")

    monkeypatch.setattr(publish_module, "emit_typed", fail_emit)
    first = _publish(db, converted, content_class="personal_reading")
    assert first.was_new is True

    con = connect_read(db)
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM book_publication_audit_outbox "
            "WHERE emitted_at IS NULL"
        ).fetchone() == (1,)
    finally:
        con.close()

    monkeypatch.setattr(publish_module, "emit_typed", real_emit)
    second = _publish(db, converted, content_class="personal_reading")
    assert second.was_new is False
    event_path = Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]) / "system.jsonl"
    assert len(event_path.read_text().splitlines()) == 1

    con = connect_read(db)
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM book_publication_audit_outbox "
            "WHERE emitted_at IS NULL"
        ).fetchone() == (0,)
    finally:
        con.close()


def test_real_audit_write_failure_stays_pending_for_retry(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", "/dev/null")
    first = _publish(db, converted, content_class="personal_reading")
    assert first.was_new is True

    con = connect_read(db)
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM book_publication_audit_outbox "
            "WHERE emitted_at IS NULL"
        ).fetchone() == (1,)
    finally:
        con.close()

    recovered_events = tempfile.mkdtemp(prefix="antiek-book-audit-recovery-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", recovered_events)
    second = _publish(db, converted, content_class="personal_reading")
    assert second.was_new is False
    assert len((Path(recovered_events) / "system.jsonl").read_text().splitlines()) == 1


def test_expired_transaction_capability_cannot_publish(db: str) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    con = connect_write(db, purpose="book-import-expired-transaction-test")
    try:
        with book_publication_transaction(con) as transaction:
            pass
        with pytest.raises(ValueError, match="inactive"):
            publish_converted_book(con, converted, transaction=transaction)
    finally:
        con.close()

    reader = connect_read(db)
    try:
        assert reader.execute("SELECT COUNT(*) FROM documents").fetchone() == (0,)
        assert reader.execute("SELECT COUNT(*) FROM book_assets").fetchone() == (0,)
        assert reader.execute("SELECT COUNT(*) FROM chunks").fetchone() == (0,)
    finally:
        reader.close()


def test_partial_asset_recovery_preserves_exact_chunk_rows(db: str) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    published = _publish(
        db,
        converted,
        content_class="personal_reading",
        embedder=StubEmbedding(),
    )
    con = connect_write(db, purpose="book-import-partial-recovery-test")
    try:
        before = con.execute(
            "SELECT chunk_id, document_id, chunk_index, section_path, text, "
            "embedding, token_count FROM chunks WHERE document_id = ? "
            "ORDER BY chunk_index",
            [published.document_id],
        ).fetchall()
        con.execute(
            "DELETE FROM book_assets WHERE document_id = ?",
            [published.document_id],
        )
    finally:
        con.close()

    recovered = _publish(db, converted, content_class="personal_reading")
    reader = connect_read(db)
    try:
        after = reader.execute(
            "SELECT chunk_id, document_id, chunk_index, section_path, text, "
            "embedding, token_count FROM chunks WHERE document_id = ? "
            "ORDER BY chunk_index",
            [published.document_id],
        ).fetchall()
        asset = get_book_asset(reader, published.document_id)
    finally:
        reader.close()
    assert recovered.was_new is False
    assert asset is not None
    assert after == before


def test_hostile_container_publishes_nothing(db: str) -> None:
    """Fail-closed means fail-CLOSED: after a refused conversion the substrate
    has no documents row at all."""
    with pytest.raises(DrmLockedError):
        convert_epub_to_antiek_html(_build_epub(drm=True))
    con = connect_read(db)
    try:
        row = con.execute("SELECT COUNT(*) FROM documents").fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == 0


# ---------------------------------------------------------------------------
# Republish rights-stability (judge r1 F1) + id-shadow detection (F2).
# ---------------------------------------------------------------------------


def test_republish_cannot_upgrade_rights_red_proof(db: str) -> None:
    """THE F1 red-proof: import lands gated (restricted); re-publishing the
    IDENTICAL body with content_class='public_domain' must be a typed refusal
    — and the DB must prove servability did not move."""
    converted = convert_epub_to_antiek_html(_build_epub())
    first = _publish(db, converted)  # deny-by-default → restricted_pending_opt_in
    assert first.servability == "gated_metadata_only"

    with pytest.raises(RepublishRightsChangeError):
        _publish(db, converted, content_class="public_domain")

    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [first.document_id],
        ).fetchone()
        served = serve_full_text(con, first.document_id)
        asset = get_book_asset(con, first.document_id)
    finally:
        con.close()
    assert row is not None and row[0] == "restricted_pending_opt_in"
    assert served.servable is False and served.full_text is None
    assert asset is not None and asset.servability.value == "gated_metadata_only"


def test_republish_license_and_rights_holder_changes_refused(db: str) -> None:
    """The other rights-state fields are equally frozen on republish."""
    converted = convert_epub_to_antiek_html(_build_epub())
    _publish(db, converted, content_class="public_domain")
    with pytest.raises(RepublishRightsChangeError):
        _publish(
            db, converted, content_class="public_domain",
            license_basis="a new license story",
        )
    with pytest.raises(RepublishRightsChangeError):
        _publish(
            db, converted, content_class="public_domain",
            rights_holder_name="Suddenly A Publisher",
        )
    # And the refusal minted NO escrow account as a side effect.
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT COUNT(*) FROM ip_holders WHERE display_name = ?",
            ["Suddenly A Publisher"],
        ).fetchone()
    finally:
        con.close()
    assert row is not None and row[0] == 0


def test_id_shadow_is_detected_not_adopted(db: str) -> None:
    """A pre-existing document under our content-addressed id whose body is
    NOT ours is an id shadow: publish must refuse (typed), not adopt or
    overwrite it (judge r1 F2 — byte-equality is the binding defense)."""
    converted = convert_epub_to_antiek_html(_build_epub())
    body_sha = hashlib.sha256(converted.html.encode("utf-8")).hexdigest()
    shadow_id = f"doc-bookimport-{body_sha[:32]}"  # 128-bit prefix (F2)
    wcon = connect_write(db, purpose="shadow-insert")
    try:
        insert_document(
            wcon, document_id=shadow_id, source_tier=2, document_type="book",
            title="Impostor", raw_text="<p>an impostor body</p>",
        )
    finally:
        wcon.close()

    with pytest.raises(StoredBodyMismatchError):
        _publish(db, converted)

    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?", [shadow_id]
        ).fetchone()
    finally:
        con.close()
    assert row is not None and row[0] == "<p>an impostor body</p>"  # untouched


def test_document_id_uses_128_bit_prefix(db: str) -> None:
    converted = convert_epub_to_antiek_html(_build_epub())
    result = _publish(db, converted)
    body_sha = hashlib.sha256(converted.html.encode("utf-8")).hexdigest()
    assert result.document_id == f"doc-bookimport-{body_sha[:32]}"


# ---------------------------------------------------------------------------
# Container byte budget BEFORE buffering (judge r1 F3) + cumulative actual
# inflation budget (F4).
# ---------------------------------------------------------------------------


def test_container_byte_budget_fires_before_reading(tmp_path: Path) -> None:
    data = _build_epub()
    tight = EpubLimits(max_container_bytes=100)
    # Bytes source: len() checked before buffering.
    with pytest.raises(ZipBombSuspectedError):
        convert_epub_to_antiek_html(data, limits=tight)
    # Path source: stat().st_size checked before read_bytes().
    epub_path = tmp_path / "big.epub"
    epub_path.write_bytes(data)
    with pytest.raises(ZipBombSuspectedError):
        convert_epub_to_antiek_html(str(epub_path), limits=tight)


def test_container_budget_precedes_any_parsing(tmp_path: Path) -> None:
    """An oversized NON-zip file raises the budget error, not NotAnEpubError —
    proving the size check runs before the file is even opened as a zip."""
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"x" * 1_000)
    with pytest.raises(ZipBombSuspectedError):
        convert_epub_to_antiek_html(
            str(junk), limits=EpubLimits(max_container_bytes=100)
        )


def test_cumulative_actual_inflation_budget_fires() -> None:
    """The F4 accumulator, exercised at its real seam: per-entry cap generous,
    total tight — members that individually pass must cumulatively trip
    ZipBombSuspectedError on ACTUAL inflated bytes. (Unit-level because
    stdlib zipfile truncates each read at the declared header size, so a
    forged-low-header archive cannot inflate past declared totals through
    read_epub itself — the accumulator is the belt underneath that behavior.)"""
    from substrate.book_import.epub import _BudgetedReader

    data = _build_epub()
    with zipfile.ZipFile(BytesIO(data)) as zf:
        reader = _BudgetedReader(
            zf, EpubLimits(max_entry_bytes=10_000_000, max_total_bytes=600)
        )
        with pytest.raises(ZipBombSuspectedError):
            for name in (
                "OEBPS/ch1.xhtml", "OEBPS/ch2.xhtml",
                "OEBPS/ch3.xhtml", "OEBPS/content.opf",
            ):
                reader.read(name)
        # It accumulated real bytes before refusing — not a pre-emptive raise.
        assert reader.total_actual_bytes > 600
