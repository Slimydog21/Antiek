"""SPR-AHT-04 — ingest reader snapshot."""

from __future__ import annotations

import pytest

from acquisition.snapshot.reader_html import (
    build_reader_snapshot,
    markdown_to_safe_html,
    sanitize_html_fragment,
    write_reader_snapshot,
)


def test_strips_script_tags():
    raw = "<p>ok</p><script>alert(1)</script>"
    assert "<script>" not in sanitize_html_fragment(raw)


def test_allowlist_removes_active_content_and_unsafe_urls():
    raw = """
    <img src="javascript:alert(1)" onerror="alert(1)">
    <a href="java&#x73;cript:alert(2)" onclick="alert(3)">click</a>
    <a href="java&#x00;script:alert(7)">control</a>
    <iframe srcdoc="<script>alert(4)</script>"></iframe>
    <svg onload="alert(5)"><circle /></svg>
    <script>alert(6)
    """
    cleaned = sanitize_html_fragment(raw).lower()
    for forbidden in (
        "onerror",
        "onclick",
        "javascript:",
        "iframe",
        "srcdoc",
        "svg",
        "script",
        "alert(",
    ):
        assert forbidden not in cleaned
    assert "click" in cleaned


def test_allowlist_preserves_safe_structure_and_hardens_links():
    cleaned = sanitize_html_fragment(
        '<article><h2>Title</h2><p class="lead">Body</p>'
        '<a href="https://example.com/paper">Paper</a></article>'
    )
    assert "<p>Body</p>" in cleaned
    assert 'class="lead"' not in cleaned
    assert 'href="https://example.com/paper"' in cleaned
    assert 'rel="noopener noreferrer"' in cleaned
    assert (
        sanitize_html_fragment(
            '<img src="https://example.com/figure.png" alt="Figure 1" width="640">'
        )
        == '<img src="https://example.com/figure.png" alt="Figure 1" width="640">'
    )


def test_url_allowlist_rejects_unicode_and_active_scheme_bypasses():
    unsafe = (
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "vbscript:msgbox(1)",
        "java\u200bscript:alert(1)",
        "java\u200cscript:alert(1)",
        "java\u2060script:alert(1)",
        "java\ufeffscript:alert(1)",
    )
    for index, value in enumerate(unsafe):
        cleaned = sanitize_html_fragment(f'<a href="{value}">unsafe-{index}</a>')
        assert "href=" not in cleaned
        assert f"unsafe-{index}" in cleaned


def test_foreign_active_content_is_removed_but_unknown_markup_is_unwrapped():
    cleaned = sanitize_html_fragment(
        "<math><mi>payload</mi></math>"
        "<template><p>hidden</p></template>"
        "<custom-semantic><p>readable</p></custom-semantic>"
        "<scr<script>ipt>alert(1)</scr</script>ipt>"
    ).lower()
    assert "payload" not in cleaned
    assert "hidden" not in cleaned
    assert "readable" in cleaned
    assert "<custom-semantic" not in cleaned
    assert "<script" not in cleaned


def test_build_snapshot_includes_metadata():
    html = build_reader_snapshot(
        source_url="https://example.com/a",
        document_id="doc-1",
        ip_holder_id=None,
        main_html="<p>Body</p>",
        ingested_at="2026-06-23T00:00:00Z",
        canonical_content_hash="sha256:abc",
        source_event_id="event-1",
    )
    assert "doc-1" in html
    assert "Body" in html
    assert "example.com" in html
    assert "sha256:abc" in html
    assert "canonical_content_hash" in html
    assert "projection_source_hash" in html
    assert "snapshot_body_hash" in html
    assert "event-1" in html
    assert "reader-html-allowlist-v1" in html


def test_snapshot_discloses_truncation():
    rendered = build_reader_snapshot(
        source_url="https://example.com/large",
        document_id="doc-large",
        ip_holder_id=None,
        main_html="<p>" + "x" * 200_100 + "</p>",
        ingested_at="2026-06-23T00:00:00Z",
    )
    assert "<strong>truncated</strong> true" in rendered


def test_image_source_does_not_accept_mailto_scheme():
    cleaned = sanitize_html_fragment(
        '<a href="mailto:reader@example.com">mail</a>'
        '<img src="mailto:reader@example.com" alt="bad source">'
    )
    assert 'href="mailto:reader@example.com"' in cleaned
    assert '<img alt="bad source">' in cleaned


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


def test_non_viewable_snapshot_requires_explicit_reason():
    with pytest.raises(ValueError, match="explicit reason"):
        build_reader_snapshot(
            source_url="https://example.com/blocked",
            document_id="doc-blocked",
            ip_holder_id=None,
            main_html="secret body",
            ingested_at="2026-07-12T00:00:00Z",
            viewable=False,
        )


def test_atomic_snapshot_failure_preserves_prior_projection(tmp_path, monkeypatch):
    path = tmp_path / "doc.html"
    write_reader_snapshot(path, "prior complete projection")

    def fail_replace(source, destination):
        raise OSError("simulated publish failure")

    monkeypatch.setattr("services.html_projection.reader_store.os.replace", fail_replace)
    with pytest.raises(OSError, match="publish failure"):
        write_reader_snapshot(path, "partial replacement")
    assert path.read_text(encoding="utf-8") == "prior complete projection"
    assert not any(item.name.startswith(".doc.html.") for item in tmp_path.iterdir())
