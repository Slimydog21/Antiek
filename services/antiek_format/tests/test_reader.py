"""Reader tests (SPR-09 M3).

Acceptance criteria from the sprint HTML:

- read_antiek(bytes) -> Notebook
- Validates manifest; rejects malformed with clear error
- Verifies signature; if invalid, returns notebook but flags signature_valid=False
- Voice-block binaries extracted to substrate-managed storage
- Major-version mismatch → UnsupportedVersion; minor → warning
- Test: write → read → assert TipTap document equality (canonicalised)
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from services.antiek_format import (
    MalformedAntiek,
    ManifestValidationError,
    UnsupportedVersion,
    canonical_tiptap_bytes,
    read_antiek,
    write_antiek,
)
from services.antiek_format.native_writer import (
    ENTRY_CONTENT,
    ENTRY_MANIFEST,
    _build_deterministic_zip,
)


def test_round_trip_simple(simple_notebook_input, keypair):
    data = write_antiek(simple_notebook_input, keypair=keypair)
    result = read_antiek(data)
    assert result.signature_valid is True
    assert result.user_id == simple_notebook_input.user_id
    assert result.content_class == "notebook"
    # TipTap-canonical equality — the headline round-trip identity test.
    assert canonical_tiptap_bytes(result.content_tiptap) == canonical_tiptap_bytes(
        simple_notebook_input.content_tiptap
    )


def test_round_trip_complex_with_audio(complex_notebook_input, keypair):
    data = write_antiek(complex_notebook_input, keypair=keypair)
    result = read_antiek(data)
    assert result.signature_valid is True
    assert canonical_tiptap_bytes(result.content_tiptap) == canonical_tiptap_bytes(
        complex_notebook_input.content_tiptap
    )
    assert "blk-v" in result.audio_blobs
    assert result.audio_blobs["blk-v"] == complex_notebook_input.audio_blobs["blk-v"]
    assert len(result.edges) == 1
    assert result.edges[0]["edge_id"] == "edg-fixture-1"


def test_read_rejects_non_zip():
    with pytest.raises(MalformedAntiek, match="not a zip"):
        read_antiek(b"this is not a zip file")


def test_read_rejects_missing_manifest(simple_notebook_input, keypair):
    data = write_antiek(simple_notebook_input, keypair=keypair)
    # Strip the manifest entry by rebuilding the zip without it.
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries = [
            (info.filename, zf.read(info.filename))
            for info in zf.infolist()
            if info.filename != ENTRY_MANIFEST
        ]
    bad = _build_deterministic_zip(entries)
    with pytest.raises(MalformedAntiek, match="manifest"):
        read_antiek(bad)


def test_read_rejects_manifest_missing_required_keys(
    simple_notebook_input, keypair
):
    data = write_antiek(simple_notebook_input, keypair=keypair)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries = []
        for info in zf.infolist():
            payload = zf.read(info.filename)
            if info.filename == ENTRY_MANIFEST:
                m = json.loads(payload.decode("utf-8"))
                del m["creator_pubkey"]
                payload = (json.dumps(m, sort_keys=True) + "\n").encode("utf-8")
            entries.append((info.filename, payload))
    bad = _build_deterministic_zip(entries)
    with pytest.raises(ManifestValidationError):
        read_antiek(bad)


def test_read_signature_invalid_returns_notebook_with_flag(
    simple_notebook_input, keypair
):
    """Tamper test: flipping a byte in the content invalidates the
    signature but the reader still returns the notebook."""
    data = write_antiek(simple_notebook_input, keypair=keypair)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries = []
        for info in zf.infolist():
            payload = zf.read(info.filename)
            if info.filename == ENTRY_CONTENT:
                # Flip one byte safely. We pick a position past the
                # opening '{' so JSON parse still succeeds.
                arr = bytearray(payload)
                # Find a printable ASCII letter and flip its case bit.
                for i in range(len(arr) - 1, 0, -1):
                    c = arr[i]
                    if 65 <= c <= 90 or 97 <= c <= 122:
                        arr[i] ^= 0x20
                        break
                payload = bytes(arr)
            entries.append((info.filename, payload))
    tampered = _build_deterministic_zip(entries)
    result = read_antiek(tampered)
    assert result.signature_valid is False
    # Content still parsed, the notebook is still readable.
    assert result.content_tiptap is not None


def test_read_major_version_mismatch_raises(simple_notebook_input, keypair):
    data = write_antiek(simple_notebook_input, keypair=keypair)
    bumped = _mutate_manifest(data, schema_version="99.0.0")
    with pytest.raises(UnsupportedVersion):
        read_antiek(bumped)


def test_read_minor_version_higher_warns(simple_notebook_input, keypair, caplog):
    data = write_antiek(simple_notebook_input, keypair=keypair)
    bumped = _mutate_manifest(data, schema_version="1.99.0")
    import logging
    with caplog.at_level(logging.WARNING):
        result = read_antiek(bumped)
    # Reader proceeds despite the warning. Signature won't verify
    # because we mutated the manifest, but that's a different assertion;
    # the version policy itself didn't raise.
    assert result.schema_version == "1.99.0"
    assert any("minor" in record.message.lower() for record in caplog.records), (
        "expected a warning log mentioning the minor-version mismatch"
    )


def test_read_audio_tamper_invalidates_signature(complex_notebook_input, keypair):
    """An audio blob whose bytes don't match the manifest's
    audio_sha256 flags signature_valid=False even though the signature
    over manifest+content+edges itself verifies. The integrity hash
    inside the signed manifest catches the tamper."""
    data = write_antiek(complex_notebook_input, keypair=keypair)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries = []
        for info in zf.infolist():
            payload = zf.read(info.filename)
            if info.filename == "blocks/blk-v.audio":
                payload = payload[:-1] + bytes([payload[-1] ^ 0xFF])
            entries.append((info.filename, payload))
    tampered = _build_deterministic_zip(entries)
    result = read_antiek(tampered)
    assert result.signature_valid is False


def test_canonical_tiptap_bytes_drops_null_attrs():
    """TipTap treats `attrs: null` the same as `attrs: absent`. Our
    canonicaliser must reflect that for round-trip identity."""
    a = {"type": "doc", "content": [
        {"type": "antiek_prose", "attrs": {"block_id": "b1", "foo": None}}
    ]}
    b = {"type": "doc", "content": [
        {"type": "antiek_prose", "attrs": {"block_id": "b1"}}
    ]}
    assert canonical_tiptap_bytes(a) == canonical_tiptap_bytes(b)


def test_canonical_tiptap_bytes_sorts_marks():
    """Mark ordering is unspecified by TipTap — our canonicaliser
    stabilises it so two docs with the same marks in different orders
    are equal."""
    a = {"type": "doc", "content": [
        {"type": "text", "text": "x",
         "marks": [{"type": "bold"}, {"type": "italic"}]}
    ]}
    b = {"type": "doc", "content": [
        {"type": "text", "text": "x",
         "marks": [{"type": "italic"}, {"type": "bold"}]}
    ]}
    assert canonical_tiptap_bytes(a) == canonical_tiptap_bytes(b)


def test_canonical_tiptap_bytes_drops_empty_content():
    """Nodes with no children may serialise with or without an empty
    `content: []` array. We treat the two as equivalent."""
    a = {"type": "doc", "content": [
        {"type": "antiek_prose", "attrs": {"block_id": "b1"}, "content": []}
    ]}
    b = {"type": "doc", "content": [
        {"type": "antiek_prose", "attrs": {"block_id": "b1"}}
    ]}
    assert canonical_tiptap_bytes(a) == canonical_tiptap_bytes(b)


# ── Helpers ──


def _mutate_manifest(data: bytes, **changes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries = []
        for info in zf.infolist():
            payload = zf.read(info.filename)
            if info.filename == ENTRY_MANIFEST:
                m = json.loads(payload.decode("utf-8"))
                m.update(changes)
                payload = (
                    json.dumps(m, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")) + "\n"
                ).encode("utf-8")
            entries.append((info.filename, payload))
    return _build_deterministic_zip(entries)
