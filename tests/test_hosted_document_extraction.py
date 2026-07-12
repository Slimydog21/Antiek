from __future__ import annotations

import io
import warnings
import zipfile
from types import SimpleNamespace

import pytest

from acquisition.documents.extract import EXTRACTOR_VERSION, extract_document_bytes


def _epub(
    *,
    chapter_names: tuple[str, ...] = ("one.xhtml", "two.xhtml"),
    media_type: str = "application/xhtml+xml",
) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>""",
        )
        manifest = "".join(
            f'<item id="c{i}" href="{name}" media-type="{media_type}"/>'
            for i, name in enumerate(chapter_names)
        )
        spine = "".join(f'<itemref idref="c{i}"/>' for i in range(len(chapter_names)))
        archive.writestr(
            "OPS/book.opf",
            f"""<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Fixture Book</dc:title><dc:creator>Fixture Author</dc:creator></metadata><manifest>{manifest}</manifest><spine>{spine}</spine></package>""",
        )
        for i, name in enumerate(chapter_names):
            words = " ".join(f"chapter{i}-word{j}" for j in range(35))
            archive.writestr(
                f"OPS/{name}",
                f"<html><body><h1>Chapter {i + 1}</h1><p>{words}</p><script>secret()</script></body></html>",
            )
    return out.getvalue()


def test_epub_extracts_spine_order_metadata_and_removes_active_content():
    result = extract_document_bytes(_epub(), source_format="epub")
    assert result.viewable is True
    assert result.title == "Fixture Book"
    assert result.author == "Fixture Author"
    assert result.text.index("Chapter 1") < result.text.index("Chapter 2")
    assert "secret" not in result.text
    assert result.word_count >= 70
    assert result.extractor_version == EXTRACTOR_VERSION
    assert result.source_byte_hash.startswith("sha256:")
    assert result.canonical_content_hash.startswith("sha256:")


def test_epub_path_traversal_is_explicitly_non_viewable():
    result = extract_document_bytes(
        _epub(chapter_names=("../../escape.xhtml",)), source_format="epub"
    )
    assert result.viewable is False
    assert result.non_viewable_reason == "epub_path_traversal"
    assert result.text == ""


def test_malformed_epub_is_explicitly_non_viewable():
    result = extract_document_bytes(b"not a zip", source_format="epub")
    assert result.viewable is False
    assert result.non_viewable_reason == "extraction_failed"


def test_epub_spine_refuses_non_html_payload():
    result = extract_document_bytes(
        _epub(media_type="application/octet-stream"), source_format="epub"
    )
    assert result.viewable is False
    assert result.non_viewable_reason == "epub_spine_not_html"


def test_epub_declared_resource_limits_are_enforced(monkeypatch):
    import acquisition.documents.extract as extractor

    raw = _epub()
    monkeypatch.setattr(extractor, "MAX_EPUB_ENTRIES", 1)
    assert extract_document_bytes(raw, source_format="epub").non_viewable_reason == (
        "epub_too_many_entries"
    )
    monkeypatch.setattr(extractor, "MAX_EPUB_ENTRIES", 2_000)
    monkeypatch.setattr(extractor, "MAX_EPUB_TOTAL_BYTES", 20)
    assert extract_document_bytes(raw, source_format="epub").non_viewable_reason == (
        "epub_uncompressed_too_large"
    )
    monkeypatch.setattr(extractor, "MAX_EPUB_TOTAL_BYTES", 20 * 1024 * 1024)
    monkeypatch.setattr(extractor, "MAX_EPUB_ITEM_BYTES", 10)
    assert extract_document_bytes(raw, source_format="epub").non_viewable_reason == (
        "epub_item_too_large"
    )
    monkeypatch.setattr(extractor, "MAX_EPUB_ITEM_BYTES", 2 * 1024 * 1024)
    monkeypatch.setattr(extractor, "MAX_EPUB_COMPRESSION_RATIO", 0.5)
    assert extract_document_bytes(raw, source_format="epub").non_viewable_reason == (
        "epub_compression_ratio_exceeded"
    )


def test_epub_duplicate_encrypted_and_empty_spine_receipts(monkeypatch):
    duplicate = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr("META-INF/container.xml", "first")
            archive.writestr("META-INF/container.xml", "second")
    assert (
        extract_document_bytes(duplicate.getvalue(), source_format="epub").non_viewable_reason
        == "epub_duplicate_entries"
    )

    class EncryptedInfo:
        filename = "encrypted.xhtml"
        flag_bits = 0x1
        file_size = 1
        compress_size = 1

    class EncryptedArchive:
        def __init__(self, source):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def infolist(self):
            return [EncryptedInfo()]

    monkeypatch.setattr("acquisition.documents.extract.zipfile.ZipFile", EncryptedArchive)
    encrypted = extract_document_bytes(b"encrypted archive", source_format="epub")
    assert encrypted.non_viewable_reason == "epub_encrypted"


def test_epub_missing_container_and_empty_spine_are_receipts():
    missing = io.BytesIO()
    with zipfile.ZipFile(missing, "w") as archive:
        archive.writestr("unrelated.txt", "body")
    assert (
        extract_document_bytes(missing.getvalue(), source_format="epub").non_viewable_reason
        == "extraction_failed"
    )
    assert (
        extract_document_bytes(_epub(chapter_names=()), source_format="epub").non_viewable_reason
        == "epub_empty_spine"
    )


def test_epub_control_xml_refuses_dtd_and_entity_declarations():
    hostile = io.BytesIO()
    with zipfile.ZipFile(hostile, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            '<!DOCTYPE container [<!ENTITY x "expanded">]><container>&x;</container>',
        )
    result = extract_document_bytes(hostile.getvalue(), source_format="epub")
    assert result.viewable is False
    assert result.non_viewable_reason == "epub_xml_dtd_forbidden"


def test_pdf_reuses_book_reader_and_carries_quality(monkeypatch):
    markdown = " ".join(f"pdfword{i}" for i in range(70))
    monkeypatch.setattr(
        "acquisition.books.reader.read_pdf",
        lambda raw: SimpleNamespace(
            markdown=markdown,
            title="PDF title",
            author="PDF author",
            page_count=4,
            pages=(SimpleNamespace(word_count=25), SimpleNamespace(word_count=45)),
            toc=(SimpleNamespace(title="Opening", page_index=0, level=0),),
        ),
    )
    result = extract_document_bytes(b"%PDF fixture", source_format="pdf")
    assert result.viewable is True
    assert result.text == markdown
    assert result.title == "PDF title"
    assert result.author == "PDF author"
    assert result.page_count == 4
    assert result.page_word_counts == (25, 45)
    assert result.toc[0].title == "Opening"
    assert result.toc[0].page_index == 0


def test_low_text_pdf_is_receipt_not_placeholder(monkeypatch):
    monkeypatch.setattr(
        "acquisition.books.reader.read_pdf",
        lambda raw: SimpleNamespace(
            markdown="scanned husk",
            title=None,
            author=None,
            page_count=10,
        ),
    )
    result = extract_document_bytes(b"%PDF scan", source_format="pdf")
    assert result.viewable is False
    assert result.non_viewable_reason == "low_word_count"
    assert result.text == ""
    assert result.canonical_content_hash.endswith(
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert result.extracted_content_hash != result.canonical_content_hash


def test_pdf_parser_failure_becomes_receipt(monkeypatch):
    def fail(raw):
        raise RuntimeError("corrupt cross-reference")

    monkeypatch.setattr("acquisition.books.reader.read_pdf", fail)
    result = extract_document_bytes(b"%PDF corrupt", source_format="pdf")
    assert result.viewable is False
    assert result.non_viewable_reason == "extraction_failed"
    assert result.text == ""


def test_html_and_text_are_bounded_content_not_markup_execution():
    html = (
        "<html><body><h1>Research</h1><p>"
        + " ".join(f"fact{i}" for i in range(60))
        + "</p><iframe>hidden</iframe><script>alert(1)</script></body></html>"
    ).encode()
    extracted = extract_document_bytes(html, source_format="html")
    assert extracted.viewable is True
    assert "Research" in extracted.text
    assert "alert" not in extracted.text
    assert "hidden" not in extracted.text

    malformed = extract_document_bytes(
        (
            "<p>before</p><script></style>ACTIVE"
            + " ".join(f"hidden{i}" for i in range(60))
            + "</script><p>"
            + " ".join(f"safe{i}" for i in range(60))
            + "</p>"
        ).encode(),
        source_format="html",
    )
    assert malformed.viewable is True
    assert "ACTIVE" not in malformed.text
    assert "safe59" in malformed.text


def test_unsupported_format_is_non_viewable_without_invented_body():
    result = extract_document_bytes(b"binary data", source_format="mobi")
    assert result.viewable is False
    assert result.non_viewable_reason == "unsupported_format"
    assert result.text == ""


@pytest.mark.parametrize("raw", [b"%PDF " + b"word " * 80, _epub()])
def test_binary_document_magic_cannot_be_laundered_through_text_format(raw):
    result = extract_document_bytes(raw, source_format="text")
    assert result.viewable is False
    assert result.non_viewable_reason == "source_format_mismatch"
    assert result.text == ""
