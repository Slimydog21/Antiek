"""SPR-AHT-04 — ingest reader snapshot."""

from __future__ import annotations

from acquisition.snapshot.reader_html import (
    build_reader_snapshot,
    markdown_to_safe_html,
    sanitize_html_fragment,
)


def test_strips_script_tags():
    raw = "<p>ok</p><script>alert(1)</script>"
    assert "<script>" not in sanitize_html_fragment(raw)


def test_build_snapshot_includes_metadata():
    html = build_reader_snapshot(
        source_url="https://example.com/a",
        document_id="doc-1",
        ip_holder_id=None,
        main_html="<p>Body</p>",
        ingested_at="2026-06-23T00:00:00Z",
    )
    assert "doc-1" in html
    assert "Body" in html
    assert "example.com" in html


def test_markdown_to_safe_html_headings():
    body = markdown_to_safe_html("## Section\n\nPara one.")
    assert "<h2>Section</h2>" in body
    assert "Para one." in body
    assert "<script>" not in body


def test_build_snapshot_book_metadata():
    html = build_reader_snapshot(
        source_url="file:///books/foo.pdf",
        document_id="doc-book-abc",
        ip_holder_id=None,
        main_html="<p>Chapter</p>",
        ingested_at="2026-06-24T00:00:00Z",
        title="Test Book",
        author="Author",
        source_kind="book",
    )
    assert "kind</strong> book" in html
    assert "Test Book" in html
    assert "Author" in html