"""SPR-06 M4: the routing map's single decision point + emission parity.

Proves the three things this module exists to guarantee:

1. ``SURFACE_FORMATS`` is the SINGLE decision point — ``formats_for`` returns the
   table's entry verbatim; an unknown surface falls back to ``("html",)``.
2. ``emit`` correctly reuses the existing writers: ``html`` is gate-clean and
   carries the title; ``antiek`` is a valid signed container with the SPR-04
   self-render shell present; ``antiek_html`` verifies.
3. PARITY — ``emit(item, fmt)`` is byte-identical across calls for every format,
   because emission is deterministic (two routes calling ``emit`` with the same
   input get identical artifacts).
"""

from __future__ import annotations

import io
import os
import sys
import zipfile

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Genuine late imports — need the sys.path bootstrap above.
from services.antiek_format.native_reader import read_antiek  # noqa: E402
from services.antiek_format.native_writer import ENTRY_PROJECTION  # noqa: E402
from services.antiek_format.signature import ensure_keypair  # noqa: E402
from services.antiek_format.single_file import verify_single_file_html  # noqa: E402
from services.html_projection.gate import assert_script_free  # noqa: E402
from services.html_projection.routing_map import (  # noqa: E402
    EXPORT_FORMATS,
    SURFACE_FORMATS,
    ExportItem,
    emit,
    formats_for,
)


@pytest.fixture
def keypair(tmp_path):
    """A real Ed25519 keypair in a per-test DuckDB — the signed formats need it."""
    db_path = str(tmp_path / "share-parity.duckdb")
    return ensure_keypair("user-share", db_path=db_path)


def _item() -> ExportItem:
    """A minimal canonical ExportItem: one prose paragraph + provenance."""
    return ExportItem(
        content_tiptap={
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Share parity prose."}],
                }
            ],
        },
        title="Share Parity Notebook",
        document_id="doc-share-1",
        user_id="user-share",
        notebook_id="nbk-share-1",
        parent_document_id=None,
        content_class="notebook",
    )


# ── The single decision point ──


def test_formats_for_returns_the_table_entry_verbatim():
    for surface, fmts in SURFACE_FORMATS.items():
        assert formats_for(surface) == fmts
        assert formats_for(surface) == SURFACE_FORMATS[surface]


def test_unknown_surface_defaults_to_html():
    assert formats_for("no-such-surface") == ("html",)
    assert formats_for("") == ("html",)


def test_table_seeds_match_the_spec():
    assert EXPORT_FORMATS == ("html", "antiek", "antiek_html")
    assert SURFACE_FORMATS["notebook_share"] == ("html", "antiek", "antiek_html")
    assert SURFACE_FORMATS["synthesis_share"] == ("html", "antiek", "antiek_html")
    assert SURFACE_FORMATS["theme_share"] == ("html", "antiek")


# ── emit reuses the existing writers correctly ──


def test_emit_html_is_gate_clean_and_carries_title():
    html = emit(_item(), "html")
    assert isinstance(html, str)
    assert_script_free(html)
    assert "Share Parity Notebook" in html


def test_emit_antiek_is_a_valid_signed_container(keypair):
    blob = emit(_item(), "antiek", keypair=keypair)
    assert isinstance(blob, bytes)
    result = read_antiek(blob)
    assert result.signature_valid is True
    # The SPR-04 self-render shell rides inside the container.
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = set(zf.namelist())
    assert ENTRY_PROJECTION in names


def test_emit_antiek_html_verifies(keypair):
    html = emit(_item(), "antiek_html", keypair=keypair)
    assert isinstance(html, str)
    assert verify_single_file_html(html) is True


# ── Parity: identical input -> byte-identical output ──


@pytest.mark.parametrize("fmt", EXPORT_FORMATS)
def test_emit_is_byte_identical_across_calls(fmt, keypair):
    item = _item()
    first = emit(item, fmt, keypair=keypair)
    second = emit(item, fmt, keypair=keypair)
    assert first == second


# ── Signed formats require a keypair ──


def test_emit_antiek_without_keypair_raises():
    with pytest.raises(ValueError):
        emit(_item(), "antiek")
    with pytest.raises(ValueError):
        emit(_item(), "antiek", keypair=None)


def test_emit_antiek_html_without_keypair_raises():
    with pytest.raises(ValueError):
        emit(_item(), "antiek_html")


def test_emit_unknown_format_raises(keypair):
    with pytest.raises(ValueError):
        emit(_item(), "docx", keypair=keypair)
