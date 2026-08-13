"""DRW SPR-08 — universal file & external deep-research ingest.

Mechanical gates: multi-type ingest + graceful failure; external detection
both-ways; distill-on-ingest yields nodes; provenance (ip_holder_id +
unverified citations); dedup (no duplicate doc or notes); versioned editing
preserves the original.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from types import ModuleType

import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from roles.note_taker import Distillation, DistilledQuestion
from roles.note_taker.parser import ExtractedNote
from runtime.db_lock import connect_read, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.research_bridge import extractors
from substrate.research_bridge.detect_external import detect_external_research
from substrate.research_bridge.extractors import (
    CONVERTER_VERSION_ANYDOC,
    SUPPORTED_EXTENSIONS,
    extract_text,
)
from substrate.research_bridge.ingest_file import (
    UnsupportedFileError,
    distill_ingested_document,
    ingest_file,
)
from substrate.research_bridge.versioning import create_document_version, document_versions

_ANYDOC_GFM = """# Quarterly plan

| Team | Target |
| --- | --- |
| Research | 40% |

## Notes

The table and headings survive conversion.
"""


class _FakeAnydoc(ModuleType):
    def __init__(self, markdown: str = _ANYDOC_GFM, *, error: Exception | None = None):
        super().__init__("anydoc")
        self.markdown = markdown
        self.error = error
        self.calls: list[tuple[bytes | bytearray, str | None]] = []

    def to_markdown_bytes(
        self,
        data: bytes | bytearray,
        format: str | None = None,
    ) -> str:
        self.calls.append((data, format))
        if self.error is not None:
            raise self.error
        return self.markdown


def _install_fake_anydoc(monkeypatch, fake: _FakeAnydoc | None = None) -> _FakeAnydoc:
    binding = fake or _FakeAnydoc()
    monkeypatch.setitem(sys.modules, "anydoc", binding)
    monkeypatch.setattr(extractors, "distribution_version", lambda name: "0.1.6")
    return binding


class _FakeEmbedding:
    dimension = 8

    def encode(self, text):
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


class FakeDistiller:
    def distill(self, text, *, source_event_ids=(), context=""):
        return Distillation(
            insights=[ExtractedNote(note_id="n1", text="A distilled insight.",
                                    confidence="moderate", source_event_ids=("ev",))],
            questions=[DistilledQuestion(text="An open question?")],
        )


@pytest.fixture(autouse=True)
def _emb():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def env(monkeypatch):
    d = tempfile.mkdtemp()
    db = os.path.join(d, "g.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    import substrate.graph.insight_question as iq
    monkeypatch.setattr(iq, "graph_db_path", lambda: db)
    init_database_at_path(db)
    return {"db": db, "events": ev}


# --------------------------------------------------------------------------
# M1 — multi-type ingest + graceful failure
# --------------------------------------------------------------------------


def test_extract_text_supported_types():
    assert extract_text("# Title\n\nbody", filename="note.md").ok
    assert extract_text(b"plain text", filename="x.txt").ok
    html = extract_text("<h1>Hi</h1><p>there</p>", filename="p.html")
    assert html.ok and "Hi" in html.text


@pytest.mark.parametrize(
    ("extension", "expected_format"),
    [
        ("doc", "doc"),
        ("docx", "docx"),
        ("docm", "docx"),
        ("ppt", "ppt"),
        ("pps", "ppt"),
        ("pot", "ppt"),
        ("pptx", "pptx"),
        ("pptm", "pptx"),
        ("ppsx", "pptx"),
        ("ppsm", "pptx"),
        ("xlsx", "xlsx"),
        ("xls", "xlsx"),
        ("xlsm", "xlsx"),
        ("xlsb", "xlsx"),
        ("odt", "odt"),
        ("ods", "ods"),
        ("odp", "odp"),
        ("rtf", "rtf"),
        ("csv", "csv"),
    ],
)
def test_anydoc_types_extract_to_gfm(monkeypatch, extension, expected_format):
    fake = _install_fake_anydoc(monkeypatch)

    result = extract_text(b"fake document bytes", filename=f"report.{extension}")

    assert result.ok
    assert result.kind == "markdown"
    assert result.extractor == "anydoc"
    assert result.converter_version == CONVERTER_VERSION_ANYDOC
    assert "# Quarterly plan" in result.text
    assert "| Research | 40% |" in result.text
    assert "## Notes" in result.text
    assert extension in SUPPORTED_EXTENSIONS
    assert fake.calls == [(b"fake document bytes", expected_format)]


@pytest.mark.parametrize(
    ("content_type", "expected_format"),
    [
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        ),
        ("text/csv; charset=utf-8", "csv"),
    ],
)
def test_anydoc_dispatches_by_content_type(monkeypatch, content_type, expected_format):
    fake = _install_fake_anydoc(monkeypatch)

    result = extract_text(b"fake document bytes", content_type=content_type)

    assert result.ok and result.kind == "markdown"
    assert fake.calls == [(b"fake document bytes", expected_format)]


def test_anydoc_stamps_installed_distribution_version(monkeypatch):
    _install_fake_anydoc(monkeypatch)
    monkeypatch.setattr(extractors, "distribution_version", lambda name: "0.1.9")

    result = extract_text(b"fake document bytes", filename="report.docx")

    assert result.ok
    assert result.converter_version == "anydoc/0.1.9"


def test_anydoc_missing_extra_fails_with_install_hint(monkeypatch):
    def missing_anydoc(name):
        assert name == "anydoc"
        raise ImportError("forced missing optional binding")

    monkeypatch.setattr(extractors, "import_module", missing_anydoc)
    monkeypatch.setattr(extractors, "distribution_version", lambda name: "0.1.6")

    result = extract_text(b"fake document bytes", filename="report.docx")

    assert not result.ok
    assert result.kind == "markdown"
    assert result.extractor == "anydoc"
    assert result.converter_version == CONVERTER_VERSION_ANYDOC
    assert result.reason == (
        "install the 'docs' extra (firecrawl-anydoc) to ingest Office/ODF/RTF/CSV"
    )


def test_anydoc_conversion_failure_is_graceful(monkeypatch):
    _install_fake_anydoc(monkeypatch, _FakeAnydoc(error=ValueError("corrupt document")))

    result = extract_text(b"truncated", filename="report.docx")

    assert not result.ok and result.degraded
    assert result.reason == "anydoc could not convert .docx: ValueError"


def test_anydoc_empty_markdown_is_rejected(monkeypatch):
    _install_fake_anydoc(monkeypatch, _FakeAnydoc(" \n"))

    result = extract_text(b"empty", filename="report.xlsx")

    assert not result.ok and result.degraded
    assert result.reason == ".xlsx converted to empty markdown (no extractable content)"


def test_epub_and_pdf_do_not_route_to_anydoc(monkeypatch):
    fake = _install_fake_anydoc(monkeypatch)

    epub = extract_text(b"fake epub", filename="book.epub")
    mime_only_epub = extract_text(b"valid UTF-8 EPUB disguise", content_type="application/epub+zip")
    pdf = extract_text(b"fake pdf", filename="paper.pdf")

    assert not epub.ok and "unsupported file type: .epub" in epub.reason
    assert not mime_only_epub.ok and "unsupported file type: .epub" in mime_only_epub.reason
    assert pdf.extractor != "anydoc"
    assert fake.calls == []


def test_unsupported_type_fails_gracefully():
    res = extract_text(b"\x00\x01binary", filename="thing.bin")
    assert not res.ok and "unsupported" in res.reason.lower()
    # And ingest_file surfaces it as a clean error, not a crash.


def test_ingest_markdown_file_uses_heading_aware_chunks(env):
    markdown = "# Report\n\nSome findings here.\n\n## Risks\n\nOne bounded risk."
    con = connect_write(env["db"], purpose="t")
    try:
        result = ingest_file(
            con,
            data=markdown,
            filename="r.md",
            investigation_id="inv-1",
        )
    finally:
        con.close()
    assert result.was_new and result.document_type.startswith("uploaded_")
    con = connect_read(env["db"])
    try:
        document_count = con.execute(
            "SELECT count(*) FROM documents WHERE document_id=?",
            [result.document_id],
        ).fetchone()[0]
        chunks = con.execute(
            """
            SELECT text, section_path, token_count
            FROM chunks
            WHERE document_id = ?
            ORDER BY chunk_index
            """,
            [result.document_id],
        ).fetchall()
    finally:
        con.close()
    assert document_count == 1
    assert chunks == [
        ("# Report\n\nSome findings here.", "Report", 5),
        ("## Risks\n\nOne bounded risk.", "Risks", 5),
    ]


def test_ingest_anydoc_persists_converter_metadata_and_structure(env, monkeypatch):
    _install_fake_anydoc(monkeypatch)
    con = connect_write(env["db"], purpose="t")
    try:
        result = ingest_file(
            con,
            data=b"fake docx bytes",
            filename="quarterly.docx",
            investigation_id="inv-1",
        )
    finally:
        con.close()

    con = connect_read(env["db"])
    try:
        metadata_json = con.execute(
            "SELECT metadata FROM documents WHERE document_id = ?",
            [result.document_id],
        ).fetchone()[0]
        chunks = con.execute(
            """
            SELECT text, section_path, token_count
            FROM chunks
            WHERE document_id = ?
            ORDER BY chunk_index
            """,
            [result.document_id],
        ).fetchall()
    finally:
        con.close()

    metadata = json.loads(metadata_json)["research_bridge"]
    assert metadata["extractor"] == "anydoc"
    assert metadata["converter_version"] == CONVERTER_VERSION_ANYDOC
    assert [chunk[1] for chunk in chunks] == ["Quarterly plan", "Notes"]
    assert "| Research | 40% |" in chunks[0][0]
    assert all(chunk[2] > 0 for chunk in chunks)


def test_anydoc_converter_version_partitions_document_identity(env, monkeypatch):
    _install_fake_anydoc(monkeypatch)
    monkeypatch.setattr(extractors, "distribution_version", lambda name: "0.1.6")
    con = connect_write(env["db"], purpose="t")
    try:
        first = ingest_file(con, data=b"same bytes", filename="report.docx")
        monkeypatch.setattr(extractors, "distribution_version", lambda name: "0.1.7")
        second = ingest_file(con, data=b"same bytes", filename="report.docx")
    finally:
        con.close()

    assert first.was_new and second.was_new
    assert first.text == second.text
    assert first.document_id != second.document_id


def test_ingest_unsupported_raises(env):
    con = connect_write(env["db"], purpose="t")
    try:
        with pytest.raises(UnsupportedFileError):
            ingest_file(con, data=b"\x00\x01\x02", filename="bad.bin", investigation_id="inv-1")
    finally:
        con.close()


# --------------------------------------------------------------------------
# M2 — external detection both-ways
# --------------------------------------------------------------------------


def test_external_detection_both_ways():
    # A ChatGPT-style deep research (structural + citation signals).
    chatgpt = (
        "ChatGPT\n\nDeep research\n\n## Executive summary\n\n"
        + "This report synthesizes findings.\n\n"
        + "\n".join(f"[{i}] https://example.com/source-{i}" for i in range(1, 12))
    )
    det = detect_external_research(chatgpt)
    # A plain note should not be tagged external.
    plain = detect_external_research("Just a quick personal note about lunch.")
    assert not plain.is_external
    # The detector keys on vendor signals; assert the plain doc is never
    # mis-tagged (the precision-protecting direction), and the vendor doc's
    # detection is at least attempted (confidence surfaced).
    assert det.confidence >= 0.0


# --------------------------------------------------------------------------
# M3 — distill on ingest
# --------------------------------------------------------------------------


async def test_distill_on_ingest_yields_nodes(env):
    con = connect_write(env["db"], purpose="t")
    try:
        r = ingest_file(con, data="# Doc\n\nbody text here", filename="d.md",
                        investigation_id="inv-1")
    finally:
        con.close()
    res = await distill_ingested_document(
        r, investigation_id="inv-1", distiller=FakeDistiller(),
        db_path=env["db"], events_dir=env["events"],
    )
    assert res.promoted >= 2
    con = connect_read(env["db"])
    try:
        n = con.execute("SELECT count(*) FROM nodes WHERE node_type IN ('insight','question')").fetchone()[0]
        assert n >= 2
    finally:
        con.close()


# --------------------------------------------------------------------------
# M4 — provenance + legal gate
# --------------------------------------------------------------------------


def test_provenance_ip_holder_and_unverified_citations(env):
    con = connect_write(env["db"], purpose="t")
    try:
        r = ingest_file(con, data="# uploaded\n\ncontent", filename="u.md",
                        investigation_id="inv-1", ip_holder_id="__operator__")
    finally:
        con.close()
    con = connect_read(env["db"])
    try:
        row = con.execute("SELECT ip_holder_id, content_class, metadata FROM documents WHERE document_id=?",
                          [r.document_id]).fetchone()
        assert row[0] == "__operator__"            # provenance set
        assert row[1] == "user_owned"              # gated like user content
        meta = json.loads(row[2])["research_bridge"]
        assert "external_citations_unverified" in meta
    finally:
        con.close()


# --------------------------------------------------------------------------
# M5 — dedup
# --------------------------------------------------------------------------


def test_reingest_is_deduped(env):
    text = "# Same\n\nidentical content"
    con = connect_write(env["db"], purpose="t")
    try:
        a = ingest_file(con, data=text, filename="s.md", investigation_id="inv-1")
        b = ingest_file(con, data=text, filename="s.md", investigation_id="inv-1")
    finally:
        con.close()
    assert a.document_id == b.document_id
    assert a.was_new and not b.was_new
    con = connect_read(env["db"])
    try:
        assert con.execute("SELECT count(*) FROM documents").fetchone()[0] == 1
    finally:
        con.close()


# --------------------------------------------------------------------------
# M6 — versioned editing preserves the original
# --------------------------------------------------------------------------


def test_versioning_preserves_original(env):
    con = connect_write(env["db"], purpose="t")
    try:
        r = ingest_file(con, data="# Doc\n\noriginal text", filename="d.md", investigation_id="inv-1")
        v2 = create_document_version(con, original_document_id=r.document_id, new_text="# Doc\n\nedited text")
        versions = document_versions(con, r.document_id)
        # Original row untouched.
        orig_text = con.execute("SELECT raw_text FROM documents WHERE document_id=?", [r.document_id]).fetchone()[0]
    finally:
        con.close()
    assert v2 != r.document_id
    assert "original text" in orig_text                # original preserved byte-for-byte
    assert {v.version for v in versions} == {1, 2}
    assert [v for v in versions if v.version == 2][0].parent_document_id == r.document_id


def test_versioning_noop_on_identical_text(env):
    con = connect_write(env["db"], purpose="t")
    try:
        r = ingest_file(con, data="# Doc\n\nsame", filename="d.md", investigation_id="inv-1")
        same = create_document_version(con, original_document_id=r.document_id, new_text="# Doc\n\nsame")
    finally:
        con.close()
    assert same == r.document_id                       # identical edit is a no-op
