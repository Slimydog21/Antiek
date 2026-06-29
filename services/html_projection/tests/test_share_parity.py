"""SPR-06 M4: routing map + emission parity tests.

Tests the single routing-map decision point and verifies that ``emit``
produces correct, deterministic, gate-clean artifacts for every format.
"""

from __future__ import annotations

import pytest

from services.antiek_format.native_reader import read_antiek
from services.antiek_format.signature import ensure_keypair
from services.antiek_format.single_file import verify_single_file_html
from services.html_projection.gate import assert_script_free
from services.html_projection.routing_map import (
    EXPORT_FORMATS,
    SURFACE_FORMATS,
    ExportItem,
    emit,
    formats_for,
)


# ── Fixtures ──


@pytest.fixture
def keypair(tmp_path):
    """A real Ed25519 keypair via ensure_keypair on a temp DuckDB."""
    return ensure_keypair("test-user", db_path=str(tmp_path / "k.duckdb"))


@pytest.fixture
def item():
    """A minimal but valid ExportItem."""
    return ExportItem(
        content_tiptap={
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello world"}],
                }
            ],
        },
        title="Test Document",
        document_id="doc-1",
        user_id="user-1",
        notebook_id="nb-1",
        parent_document_id=None,
        content_class="notebook",
    )


# ── Routing map: single decision point ──


def test_surface_formats_is_single_decision_point():
    """SURFACE_FORMATS is the ONLY place format-choice lives.

    ``formats_for`` returns exactly the table's entry for every
    declared surface.
    """
    for surface, expected in SURFACE_FORMATS.items():
        assert formats_for(surface) == expected


def test_formats_for_unknown_surface_returns_html_default():
    """Unknown surface defaults to ("html",)."""
    assert formats_for("unknown_surface") == ("html",)
    assert formats_for("") == ("html",)


def test_export_formats_is_closed_set():
    """EXPORT_FORMATS is the canonical closed set of three formats."""
    assert EXPORT_FORMATS == ("html", "antiek", "antiek_html")


# ── emit("html") ──


def test_emit_html_is_gate_clean(item):
    """HTML output passes the zero-script gate."""
    html = emit(item, "html")
    assert isinstance(html, str)
    assert_script_free(html)


def test_emit_html_contains_title(item):
    """HTML output contains the document title."""
    html = emit(item, "html")
    assert "Test Document" in html


# ── emit("antiek") ──


def test_emit_antiek_valid_container(item, keypair):
    """Antiek output is a valid container: reads back, signature valid."""
    data = emit(item, "antiek", keypair=keypair)
    assert isinstance(data, bytes)
    result = read_antiek(data)
    assert result.signature_valid is True


def test_emit_antiek_contains_projection(item, keypair):
    """Antiek container carries the ENTRY_PROJECTION (projection.html)."""
    data = emit(item, "antiek", keypair=keypair)
    result = read_antiek(data)
    assert result.projection_html is not None


def test_emit_antiek_requires_keypair(item):
    """Antiek format raises ValueError without keypair."""
    with pytest.raises(ValueError, match="requires a keypair"):
        emit(item, "antiek")


# ── emit("antiek_html") ──


def test_emit_antiek_html_verifies(item, keypair):
    """Single-file .antiek.html passes verify_single_file_html."""
    html = emit(item, "antiek_html", keypair=keypair)
    assert isinstance(html, str)
    assert verify_single_file_html(html) is True


def test_emit_antiek_html_requires_keypair(item):
    """Antiek_html format raises ValueError without keypair."""
    with pytest.raises(ValueError, match="requires a keypair"):
        emit(item, "antiek_html")


# ── Byte-compare parity ──


@pytest.mark.parametrize("fmt", EXPORT_FORMATS)
def test_byte_parity(item, keypair, fmt):
    """Identical input -> byte-identical output for every format.

    This is the parity the spec demands: two routes calling ``emit``
    with the same input get identical artifacts because emission is
    deterministic.
    """
    if fmt == "html":
        a = emit(item, fmt)
        b = emit(item, fmt)
    else:
        a = emit(item, fmt, keypair=keypair)
        b = emit(item, fmt, keypair=keypair)
    assert a == b


# ── Unknown format ──


def test_emit_unknown_format_raises(item):
    """Unknown format raises ValueError."""
    with pytest.raises(ValueError, match="unknown format"):
        emit(item, "pdf")


def test_emit_unknown_format_raises_even_with_keypair(item, keypair):
    """Unknown format raises ValueError even when keypair is provided."""
    with pytest.raises(ValueError, match="unknown format"):
        emit(item, "pdf", keypair=keypair)
