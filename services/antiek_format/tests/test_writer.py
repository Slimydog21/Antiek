"""Writer tests (SPR-09 M2).

Acceptance criteria from the sprint HTML:

- write_antiek(notebook) -> bytes
- Zip created deterministically (sorted file order, fixed timestamps)
- Voice-block binaries: copy from existing storage; not re-encoded
- Substrate-derived data is NEVER written
- Test: write a notebook → unzip → confirm structure matches SPEC.md
"""

from __future__ import annotations

import io
import zipfile

import pytest

from services.antiek_format import WriterInput, write_antiek
from services.antiek_format.native_writer import (
    BLOCKS_PREFIX,
    ENTRY_CONTENT,
    ENTRY_EDGES,
    ENTRY_MANIFEST,
    ENTRY_SIGNATURE,
)


def test_write_simple_notebook_produces_zip(simple_notebook_input, keypair):
    data = write_antiek(simple_notebook_input, keypair=keypair)
    assert isinstance(data, bytes)
    assert data[:2] == b"PK", "output must start with the zip magic"

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert ENTRY_MANIFEST in names
        assert ENTRY_CONTENT in names
        assert ENTRY_SIGNATURE in names
        # No edges → no edges.jsonl entry.
        assert ENTRY_EDGES not in names
        # No audio → no blocks/ entries.
        assert not any(n.startswith(BLOCKS_PREFIX) for n in names)


def test_write_complex_notebook_includes_edges_and_audio(
    complex_notebook_input, keypair
):
    data = write_antiek(complex_notebook_input, keypair=keypair)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert ENTRY_EDGES in names, "edges.jsonl missing when edges supplied"
        assert f"{BLOCKS_PREFIX}blk-v.audio" in names, "voice-block audio missing"
        # Audio bytes are passed through unchanged.
        with zf.open(f"{BLOCKS_PREFIX}blk-v.audio") as f:
            assert f.read() == complex_notebook_input.audio_blobs["blk-v"]


def test_writer_is_deterministic(complex_notebook_input, keypair):
    """The headline M2 acceptance criterion. Two writes of the same
    notebook MUST produce byte-identical bytes. If this fails the zip
    writer is non-deterministic — fix the zip writer, do not relax
    this test."""
    a = write_antiek(complex_notebook_input, keypair=keypair)
    b = write_antiek(complex_notebook_input, keypair=keypair)
    assert a == b, (
        "writer is non-deterministic: same notebook produced different bytes. "
        "Check zip timestamps, file order, and compression mode."
    )


def test_writer_rejects_forbidden_substrate_fields_in_content(
    simple_notebook_input, keypair
):
    """Master-spec invariant: chunks / embeddings / substrate-derived
    edges MUST NOT enter the file."""
    inp = simple_notebook_input
    # Sneak in a forbidden field. The writer must refuse.
    inp.content_tiptap["embeddings"] = [0.1, 0.2, 0.3]
    with pytest.raises(ValueError, match="forbidden substrate-derived field"):
        write_antiek(inp, keypair=keypair)


def test_writer_rejects_forbidden_substrate_fields_in_blocks_index(
    simple_notebook_input, keypair
):
    inp = simple_notebook_input
    inp.blocks_index[0]["chunk_embedding"] = [0.5, 0.6]
    with pytest.raises(ValueError, match="forbidden substrate-derived field"):
        write_antiek(inp, keypair=keypair)


def test_writer_rejects_unknown_content_class(simple_notebook_input, keypair):
    inp = simple_notebook_input
    inp.content_class = "treatise"  # not in CONTENT_CLASSES
    with pytest.raises(ValueError, match="unknown content_class"):
        write_antiek(inp, keypair=keypair)


def test_writer_rejects_audio_blob_for_unknown_block(
    simple_notebook_input, keypair
):
    inp = simple_notebook_input
    inp.audio_blobs["blk-ghost"] = b"phantom audio"
    with pytest.raises(ValueError, match="not in blocks_index"):
        write_antiek(inp, keypair=keypair)


def test_writer_emits_canonical_manifest_keys(complex_notebook_input, keypair):
    """The manifest carries the seven REQUIRED fields the schema asks
    for, plus blocks_index when blocks exist."""
    import json
    data = write_antiek(complex_notebook_input, keypair=keypair)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        manifest = json.loads(zf.read(ENTRY_MANIFEST).decode("utf-8"))
    for req in [
        "schema_version", "content_class", "document_id", "parent_document_id",
        "created_at", "creator_user_id", "creator_pubkey",
    ]:
        assert req in manifest, f"manifest missing required key {req!r}"
    assert manifest["schema_version"] == "1.0.0"
    assert manifest["content_class"] == "notebook"
    assert manifest["blocks_index"], "blocks_index empty on complex fixture"
    # blocks_index entries inside the manifest have audio_path +
    # audio_sha256 stamped by the writer.
    voice_entry = next(
        b for b in manifest["blocks_index"] if b["block_id"] == "blk-v"
    )
    assert voice_entry["audio_path"] == "blocks/blk-v.audio"
    assert voice_entry["audio_sha256"], "audio_sha256 not stamped"
    assert len(voice_entry["audio_sha256"]) == 64


def test_writer_zip_uses_fixed_timestamps(complex_notebook_input, keypair):
    data = write_antiek(complex_notebook_input, keypair=keypair)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0), (
                f"non-fixed timestamp on {info.filename}: {info.date_time}"
            )


def test_writer_zip_uses_zip_stored(complex_notebook_input, keypair):
    data = write_antiek(complex_notebook_input, keypair=keypair)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            assert info.compress_type == zipfile.ZIP_STORED, (
                f"entry {info.filename} is not ZIP_STORED — compression "
                "introduces non-determinism."
            )


def test_writer_entry_order_is_canonical(complex_notebook_input, keypair):
    """manifest first, content second, edges, then blocks/* in sorted
    order, signature last."""
    data = write_antiek(complex_notebook_input, keypair=keypair)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
    assert names[0] == ENTRY_MANIFEST
    assert names[1] == ENTRY_CONTENT
    assert names[-1] == ENTRY_SIGNATURE
    assert ENTRY_EDGES in names
    edges_idx = names.index(ENTRY_EDGES)
    sig_idx = names.index(ENTRY_SIGNATURE)
    assert edges_idx < sig_idx
    # blocks/* sit between edges and signature.
    block_indices = [i for i, n in enumerate(names) if n.startswith(BLOCKS_PREFIX)]
    if block_indices:
        assert all(edges_idx < i < sig_idx for i in block_indices)
