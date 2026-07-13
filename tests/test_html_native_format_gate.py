"""Tests for ``substrate.html_native_format_gate`` — the ask-#6 HTML-native vision
invariant as falsifiable code. Each test isolates ONE honest state so the five
verdicts (html_native / ported_to_html / unported_html_served / non_html_served /
unknown) are exercised independently plus the conservative unknown-format handling."""

from __future__ import annotations

import pytest

from substrate.html_native_format_gate import (
    HTML_FORMAT,
    KNOWN_FORMATS,
    AssetFormatDescriptor,
    HtmlNativeFormatError,
    verify_html_native_batch,
    verify_html_native_format,
)

_ASSET = "asset://antiek/9780000000001"


def _desc(
    asset_id: str = _ASSET,
    source_format: str = "html",
    serve_format: str = "html",
    port_recorded: bool | None = None,
) -> AssetFormatDescriptor:
    return AssetFormatDescriptor(
        asset_id=asset_id,
        source_format=source_format,
        serve_format=serve_format,
        port_recorded=port_recorded,
    )


def test_html_native_source_html_served_html_is_cleanest() -> None:
    report = verify_html_native_format(_desc(source_format="html", serve_format="html"))
    assert report.verdict == "html_native"
    assert report.html_native is True
    assert report.violation is None


def test_ported_to_html_with_provenance_is_clean() -> None:
    report = verify_html_native_format(
        _desc(source_format="pdf", serve_format="html", port_recorded=True)
    )
    assert report.verdict == "ported_to_html"
    assert report.html_native is True
    assert report.violation is None


def test_non_html_served_is_violation_pdf() -> None:
    report = verify_html_native_format(_desc(source_format="pdf", serve_format="pdf"))
    assert report.verdict == "non_html_served"
    assert report.html_native is False
    assert report.violation == "non_html_served"


def test_non_html_served_is_violation_epub_direct() -> None:
    # source html (already ported) but served as epub directly — still a violation
    report = verify_html_native_format(_desc(source_format="html", serve_format="epub"))
    assert report.verdict == "non_html_served"
    assert report.html_native is False
    assert report.violation == "non_html_served"


def test_unported_html_served_is_integrity_gap() -> None:
    report = verify_html_native_format(
        _desc(source_format="epub", serve_format="html", port_recorded=False)
    )
    assert report.verdict == "unported_html_served"
    assert report.html_native is False  # distinct violation, not clean
    assert report.violation == "unported_html_served"


def test_unknown_when_serve_format_unknown() -> None:
    report = verify_html_native_format(_desc(source_format="pdf", serve_format="unknown"))
    assert report.verdict == "unknown"
    assert report.html_native is None
    assert report.violation is None


def test_unknown_when_port_recorded_none_with_non_html_source() -> None:
    report = verify_html_native_format(
        _desc(source_format="pdf", serve_format="html", port_recorded=None)
    )
    assert report.verdict == "unknown"
    assert report.html_native is None  # cannot resolve clean vs suspect -> honest None


def test_distinct_violations_never_collapse() -> None:
    # non_html_served (wrong format) and unported_html_served (right format, no provenance)
    # are two DIFFERENT violations that both fail html_native but for different reasons.
    non_html = verify_html_native_format(_desc(source_format="pdf", serve_format="pdf"))
    unported = verify_html_native_format(
        _desc(source_format="pdf", serve_format="html", port_recorded=False)
    )
    assert non_html.html_native is False
    assert unported.html_native is False
    assert non_html.verdict != unported.verdict
    assert non_html.violation != unported.violation


def test_unrecognized_serve_format_conservatively_non_html() -> None:
    # a served format we don't recognize is NOT html -> treated as a violation (conservative)
    report = verify_html_native_format(_desc(source_format="html", serve_format="xyz"))
    assert report.verdict == "non_html_served"
    assert report.html_native is False
    assert any("not in the known vocabulary" in n for n in report.notes)


def test_unrecognized_source_format_carried_not_violation() -> None:
    # an unrecognized SOURCE format served as html with port recorded is still clean —
    # only what reaches the viewer matters; the origin format being unrecognized is not a violation
    report = verify_html_native_format(
        _desc(source_format="xyz", serve_format="html", port_recorded=True)
    )
    assert report.verdict == "ported_to_html"
    assert report.html_native is True
    assert any("source_format" in n and "known vocabulary" in n for n in report.notes)


def test_raw_binary_serve_is_violation() -> None:
    report = verify_html_native_format(
        _desc(source_format="docx", serve_format="raw_binary")
    )
    assert report.verdict == "non_html_served"
    assert report.html_native is False


def test_book_and_research_output_both_gated() -> None:
    # ask #6 covers books AND human-viewable research output — both must be html
    book = verify_html_native_format(
        _desc(asset_id="asset://antiek/book/1", source_format="epub",
              serve_format="html", port_recorded=True)
    )
    research = verify_html_native_format(
        _desc(asset_id="asset://antiek/research/2", source_format="html",
              serve_format="html")
    )
    assert book.html_native is True
    assert research.html_native is True


def test_batch_preserves_order_and_is_auditable() -> None:
    descs = [
        _desc(asset_id="a", source_format="html", serve_format="html"),
        _desc(asset_id="b", source_format="pdf", serve_format="pdf"),
        _desc(asset_id="c", source_format="epub", serve_format="html", port_recorded=True),
    ]
    reports = verify_html_native_batch(descs)
    assert [r.asset_id for r in reports] == ["a", "b", "c"]
    assert reports[0].html_native is True
    assert reports[1].html_native is False
    assert reports[2].html_native is True


def test_report_is_advisory_and_frozen() -> None:
    report = verify_html_native_format(_desc())
    assert report.authority == "advisory"
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.html_native = False  # type: ignore[misc]


def test_validation_empty_asset_id_raises() -> None:
    with pytest.raises(HtmlNativeFormatError):
        verify_html_native_format(_desc(asset_id=""))


def test_html_format_is_html() -> None:
    assert HTML_FORMAT == "html"
    assert "html" in KNOWN_FORMATS
    assert "pdf" in KNOWN_FORMATS
    assert "epub" in KNOWN_FORMATS


def test_deterministic_same_descriptor_same_report() -> None:
    d = _desc(source_format="pdf", serve_format="html", port_recorded=True)
    r1 = verify_html_native_format(d)
    r2 = verify_html_native_format(d)
    assert r1 == r2
