"""SPR-AHT-04 — ingest reader snapshot."""

from __future__ import annotations

from acquisition.snapshot.reader_html import build_reader_snapshot, sanitize_html_fragment


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