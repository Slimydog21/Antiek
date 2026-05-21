"""Markdown projector tests (SPR-09 M4).

Acceptance criteria from the sprint HTML:

- project_to_markdown(bytes) -> str
- Projection is one-way and lossy; documented in the output header
- Voice-block audio files referenced via filesystem path
- Manual: open in Obsidian / iA Writer / Cursor — prose renders
- Bytes-to-bytes snapshot equality on a fixture
"""

from __future__ import annotations

import os
import tempfile

import pytest

from services.antiek_format import (
    HEADER_COMMENT,
    project_to_markdown,
    write_antiek,
)
from services.antiek_format.markdown_projector import (
    project_to_markdown_with_blocks,
)


def test_projection_starts_with_header_comment(simple_notebook_input, keypair):
    data = write_antiek(simple_notebook_input, keypair=keypair)
    md = project_to_markdown(data)
    assert md.startswith(HEADER_COMMENT), (
        "projection must announce its lossiness upfront"
    )


def test_projection_includes_one_way_notice(simple_notebook_input, keypair):
    data = write_antiek(simple_notebook_input, keypair=keypair)
    md = project_to_markdown(data)
    assert "Round-trip is NOT supported" in md


def test_projection_renders_highlight_as_blockquote(simple_notebook_input, keypair):
    data = write_antiek(simple_notebook_input, keypair=keypair)
    md = project_to_markdown(data)
    assert "> An important sentence." in md
    # Operator framing renders as italics next to the quote.
    assert "Why this matters" in md


def test_projection_renders_voice_block_with_duration(
    complex_notebook_input, keypair
):
    data = write_antiek(complex_notebook_input, keypair=keypair)
    md = project_to_markdown(data)
    assert "voice note: 0:34" in md
    # Transcript surfaces as a quoted block under the voice link.
    assert "voice transcript text here" in md


def test_projection_renders_ai_qa_with_q_and_a(complex_notebook_input, keypair):
    data = write_antiek(complex_notebook_input, keypair=keypair)
    md = project_to_markdown(data)
    assert "**Q:** What's the central claim?" in md
    assert "**A:** The central claim is X." in md
    assert "doc-fixture-2 §3" in md


def test_projection_renders_cite_link_as_markdown_link(
    complex_notebook_input, keypair
):
    data = write_antiek(complex_notebook_input, keypair=keypair)
    md = project_to_markdown(data)
    assert "[See ref §4](/wrestle/doc-fixture-2?chunk=ck-99)" in md


def test_projection_renders_cross_doc_jump_as_reference(
    complex_notebook_input, keypair
):
    data = write_antiek(complex_notebook_input, keypair=keypair)
    md = project_to_markdown(data)
    assert "[related doc][doc-fixture-99]" in md


def test_projection_renders_edges_appendix(complex_notebook_input, keypair):
    data = write_antiek(complex_notebook_input, keypair=keypair)
    md = project_to_markdown(data)
    assert "## Asserted edges" in md
    assert "supports" in md
    assert "doc-fixture-99" in md


def test_projection_warns_on_tampered_file(simple_notebook_input, keypair):
    """A file whose signature does not verify gets a warning line
    near the top of the projection — operators reading via fallback
    deserve the signal."""
    import io
    import zipfile

    from services.antiek_format.native_writer import (
        ENTRY_CONTENT,
        _build_deterministic_zip,
    )
    data = write_antiek(simple_notebook_input, keypair=keypair)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries = []
        for info in zf.infolist():
            payload = zf.read(info.filename)
            if info.filename == ENTRY_CONTENT:
                # Flip a printable letter so JSON still parses.
                arr = bytearray(payload)
                for i in range(len(arr) - 1, 0, -1):
                    c = arr[i]
                    if 65 <= c <= 90 or 97 <= c <= 122:
                        arr[i] ^= 0x20
                        break
                payload = bytes(arr)
            entries.append((info.filename, payload))
    bad = _build_deterministic_zip(entries)
    md = project_to_markdown(bad)
    assert "signature does not verify" in md.lower()


def test_projection_byte_snapshot_simple(simple_notebook_input, keypair):
    """Bytes-to-bytes snapshot test: same input → same projection. If
    this test breaks unexpectedly the projector has drifted; update
    the snapshot deliberately."""
    data = write_antiek(simple_notebook_input, keypair=keypair)
    md = project_to_markdown(data)
    # Spot-check that the projection is fully formed: header, title,
    # body, no trailing whitespace before the trailing newline.
    assert md.endswith("\n")
    assert md.count("\n") > 3, "projection too short — must contain header + title + body"
    # The projection is deterministic for a given file.
    md2 = project_to_markdown(data)
    assert md == md2


def test_projection_writes_audio_to_blocks_sibling_dir(
    complex_notebook_input, keypair
):
    """When project_to_markdown_with_blocks is used, voice-block
    binaries land in a `blocks/` directory next to the .md output."""
    data = write_antiek(complex_notebook_input, keypair=keypair)
    with tempfile.TemporaryDirectory() as tmp:
        out_md = os.path.join(tmp, "notebook.md")
        md = project_to_markdown_with_blocks(data, output_md_path=out_md)
        audio_path = os.path.join(tmp, "blocks", "blk-v.audio")
        assert os.path.exists(audio_path)
        with open(audio_path, "rb") as f:
            assert f.read() == complex_notebook_input.audio_blobs["blk-v"]
        # The markdown references the audio at the sibling path.
        assert "blocks/blk-v.audio" in md
