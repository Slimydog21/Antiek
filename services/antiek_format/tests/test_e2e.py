"""End-to-end + invariants tests (SPR-09 M7).

Acceptance criteria from the sprint HTML (verification gates):

- Round-trip identity: 5 fixture notebooks (varying complexity) write
  → read → equivalent TipTap document.
- Determinism: same notebook → write twice → byte-identical.
- Tamper: flip a byte in content.tiptap.json → signature verification
  fails.
- Major-version: write with future schema_version → reader raises
  UnsupportedVersion.
- Minor-version: write with bumped minor version → reader proceeds
  with warning.
- Markdown projection: fixture .antiek → projected .md → opens in 3
  markdown viewers without error (manual gate).
- No substrate data in file: bytes do NOT contain known substrate
  field names.

The pytest node IDs are tagged so the verification-gates table in the
sprint HTML can run them individually via -k. (e.g.
``pytest -k roundtrip``, ``pytest -k deterministic``,
``pytest -k tamper``, ``pytest -k version``,
``pytest -k no_substrate``).
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

from services.antiek_format import (
    UnsupportedVersion,
    WriterInput,
    canonical_tiptap_bytes,
    read_antiek,
    write_antiek,
)
from services.antiek_format.native_writer import (
    ENTRY_CONTENT,
    ENTRY_MANIFEST,
    _build_deterministic_zip,
    _FORBIDDEN_SUBSTRATE_FIELDS,
)


# ── Five fixtures of varying complexity ──


def _make_fixture(n: int, keypair, when: datetime) -> WriterInput:
    """Fixture factory. Each fixture is deterministic given its index;
    same notebook on every test run."""
    if n == 1:
        # Minimal: empty doc.
        return WriterInput(
            notebook_id=f"nbk-rt-{n}",
            user_id="user-test",
            document_id=f"doc-rt-{n}",
            parent_document_id=f"doc-rt-{n}",
            content_class="notebook",
            title=f"Round-trip fixture {n}",
            content_tiptap={"type": "doc", "content": []},
            blocks_index=[],
            edges=[],
            audio_blobs={},
            created_at=when,
            format_version=1,
        )
    if n == 2:
        # Single highlight card.
        return WriterInput(
            notebook_id=f"nbk-rt-{n}",
            user_id="user-test",
            document_id=f"doc-rt-{n}",
            parent_document_id=f"doc-rt-{n}",
            content_class="notebook",
            title=f"Round-trip fixture {n}",
            content_tiptap={
                "type": "doc",
                "content": [{
                    "type": "antiek_highlight_card",
                    "attrs": {"block_id": "blk-h2", "passage_text": "hello"},
                }],
            },
            blocks_index=[{
                "block_id": "blk-h2", "block_type": "highlight_card",
                "position": 1.0, "source_event_ids": ["evt-1"],
            }],
            edges=[],
            audio_blobs={},
            created_at=when,
            format_version=1,
        )
    if n == 3:
        # Prose + cite link + cross-doc jump.
        return WriterInput(
            notebook_id=f"nbk-rt-{n}",
            user_id="user-test",
            document_id=f"doc-rt-{n}",
            parent_document_id=f"doc-rt-{n}",
            content_class="notebook",
            title=f"Round-trip fixture {n}",
            content_tiptap={
                "type": "doc",
                "content": [
                    {"type": "antiek_prose", "attrs": {"block_id": "blk-p3"},
                     "content": [{"type": "text", "text": "prose"}]},
                    {"type": "antiek_cite_link",
                     "attrs": {"block_id": "blk-c3", "label": "see",
                               "target_url": "/x"}},
                    {"type": "antiek_cross_doc_jump",
                     "attrs": {"block_id": "blk-x3", "label": "elsewhere",
                               "target_document_id": "doc-rt-99"}},
                ],
            },
            blocks_index=[
                {"block_id": "blk-p3", "block_type": "prose", "position": 1.0,
                 "source_event_ids": []},
                {"block_id": "blk-c3", "block_type": "cite_link",
                 "position": 2.0, "source_event_ids": ["evt-2"]},
                {"block_id": "blk-x3", "block_type": "cross_doc_jump",
                 "position": 3.0, "source_event_ids": ["evt-3"]},
            ],
            edges=[],
            audio_blobs={},
            created_at=when,
            format_version=1,
        )
    if n == 4:
        # Voice block with audio payload + AI QA.
        return WriterInput(
            notebook_id=f"nbk-rt-{n}",
            user_id="user-test",
            document_id=f"doc-rt-{n}",
            parent_document_id=f"doc-rt-{n}",
            content_class="notebook",
            title=f"Round-trip fixture {n}",
            content_tiptap={
                "type": "doc",
                "content": [
                    {"type": "antiek_voice_block",
                     "attrs": {"block_id": "blk-v4", "duration_seconds": 12,
                               "transcript": "audio transcript"}},
                    {"type": "antiek_ai_qa",
                     "attrs": {"block_id": "blk-q4", "question": "?",
                               "answer": ".", "attribution": "src"}},
                ],
            },
            blocks_index=[
                {"block_id": "blk-v4", "block_type": "voice_block",
                 "position": 1.0, "source_event_ids": ["evt-4"]},
                {"block_id": "blk-q4", "block_type": "ai_qa", "position": 2.0,
                 "source_event_ids": ["evt-5"]},
            ],
            edges=[],
            audio_blobs={"blk-v4": b"\x00\x11\x22\x33-AUDIO-\xff" * 30},
            created_at=when,
            format_version=1,
        )
    if n == 5:
        # Everything + user-asserted edges.
        return WriterInput(
            notebook_id=f"nbk-rt-{n}",
            user_id="user-test",
            document_id=f"doc-rt-{n}",
            parent_document_id=f"doc-rt-{n}",
            content_class="notebook",
            title=f"Round-trip fixture {n}",
            content_tiptap={
                "type": "doc",
                "content": [
                    {"type": "antiek_highlight_card",
                     "attrs": {"block_id": "blk-h5",
                               "passage_text": "Unicode: 注釈 ✓"}},
                    {"type": "antiek_voice_block",
                     "attrs": {"block_id": "blk-v5", "duration_seconds": 90,
                               "transcript": "long transcript"}},
                    {"type": "antiek_ai_qa",
                     "attrs": {"block_id": "blk-q5", "question": "why?",
                               "answer": "because.", "attribution": "α"}},
                    {"type": "antiek_cite_link",
                     "attrs": {"block_id": "blk-c5", "label": "cite",
                               "target_url": "/w/doc-rt-5"}},
                    {"type": "antiek_cross_doc_jump",
                     "attrs": {"block_id": "blk-x5", "label": "neighbor",
                               "target_document_id": "doc-rt-1"}},
                    {"type": "antiek_prose",
                     "attrs": {"block_id": "blk-p5"},
                     "content": [{"type": "text", "text": "tail prose."}]},
                ],
            },
            blocks_index=[
                {"block_id": f"blk-{t[0]}5", "block_type": t,
                 "position": float(i + 1),
                 "source_event_ids": [f"evt-{i + 1}"]}
                for i, t in enumerate([
                    "highlight_card", "voice_block", "ai_qa", "cite_link",
                    "cross_doc_jump", "prose",
                ])
            ],
            edges=[
                {"edge_id": "edg-5a", "from_block_id": "blk-h5",
                 "to_content_hash": "b" * 64, "to_document_id": "doc-rt-1",
                 "kind": "supports",
                 "asserted_at": "2026-05-21T12:00:00+00:00",
                 "operator_note": None},
                {"edge_id": "edg-5b", "from_block_id": "blk-q5",
                 "to_content_hash": "c" * 64, "to_document_id": "doc-rt-3",
                 "kind": "extends",
                 "asserted_at": "2026-05-21T12:01:00+00:00",
                 "operator_note": "tied"},
            ],
            audio_blobs={"blk-v5": b"VOICE5" * 200},
            created_at=when,
            format_version=1,
        )
    raise ValueError(f"unknown fixture index {n}")


@pytest.fixture(params=[1, 2, 3, 4, 5])
def round_trip_fixture(request, keypair, fixed_created_at):
    return _make_fixture(request.param, keypair, fixed_created_at)


# ── Verification gates ──


def test_roundtrip_identity(round_trip_fixture, keypair):
    """write → read → canonical-TipTap equality. All five fixtures."""
    data = write_antiek(round_trip_fixture, keypair=keypair)
    result = read_antiek(data)
    assert result.signature_valid is True
    assert canonical_tiptap_bytes(result.content_tiptap) == canonical_tiptap_bytes(
        round_trip_fixture.content_tiptap
    ), f"round-trip identity broken for fixture {round_trip_fixture.notebook_id}"
    # Edges round-trip too.
    assert len(result.edges) == len(round_trip_fixture.edges)
    # Audio blobs survive byte-for-byte.
    for bid, blob in round_trip_fixture.audio_blobs.items():
        assert result.audio_blobs.get(bid) == blob


def test_deterministic_write(round_trip_fixture, keypair):
    """Same notebook → byte-identical .antiek bytes. All five fixtures."""
    a = write_antiek(round_trip_fixture, keypair=keypair)
    b = write_antiek(round_trip_fixture, keypair=keypair)
    assert a == b, (
        f"deterministic-write violated for {round_trip_fixture.notebook_id}: "
        f"writer produced different bytes for the same input. Inspect the "
        f"zip writer (timestamps, file order, compression mode)."
    )


def test_tamper_invalidates_signature(simple_notebook_input, keypair):
    """Flip one byte in content.tiptap.json. Signature must fail to
    verify; the reader returns the notebook with signature_valid=False."""
    data = write_antiek(simple_notebook_input, keypair=keypair)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries = []
        for info in zf.infolist():
            payload = zf.read(info.filename)
            if info.filename == ENTRY_CONTENT:
                arr = bytearray(payload)
                # Flip a printable ASCII letter near the end so the
                # JSON still parses.
                for i in range(len(arr) - 1, 0, -1):
                    c = arr[i]
                    if 65 <= c <= 90 or 97 <= c <= 122:
                        arr[i] ^= 0x20
                        break
                payload = bytes(arr)
            entries.append((info.filename, payload))
    bad = _build_deterministic_zip(entries)
    result = read_antiek(bad)
    assert result.signature_valid is False


def test_version_major_mismatch_refuses(simple_notebook_input, keypair):
    data = write_antiek(simple_notebook_input, keypair=keypair)
    bumped = _mutate_manifest(data, schema_version="99.0.0")
    with pytest.raises(UnsupportedVersion):
        read_antiek(bumped)


def test_version_minor_mismatch_warns(simple_notebook_input, keypair, caplog):
    import logging
    data = write_antiek(simple_notebook_input, keypair=keypair)
    bumped = _mutate_manifest(data, schema_version="1.99.0")
    with caplog.at_level(logging.WARNING):
        result = read_antiek(bumped)
    # Reader proceeds.
    assert result.schema_version == "1.99.0"
    assert any(
        "minor" in r.message.lower() or "minor" in str(r.args).lower()
        for r in caplog.records
    ), "expected a warning log mentioning the minor-version mismatch"


def test_no_substrate_data_in_file(complex_notebook_input, keypair):
    """Grep the produced bytes for every name in
    ``_FORBIDDEN_SUBSTRATE_FIELDS``. Master-spec invariant: none of
    them may appear. This is the load-bearing test of the sprint."""
    data = write_antiek(complex_notebook_input, keypair=keypair)
    # Decompose to inspect every component.
    payloads: list[bytes] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            payloads.append(zf.read(info.filename))
    blob = b"\n".join(payloads)
    for forbidden in _FORBIDDEN_SUBSTRATE_FIELDS:
        # We grep the field name as ASCII bytes. Substrate field names
        # are ASCII identifiers.
        assert forbidden.encode("ascii") not in blob, (
            f"substrate-derived field {forbidden!r} found inside .antiek "
            f"bytes. Master-spec invariant violated; the writer let "
            f"forbidden data through. See SPEC.md §9 + the "
            f"_FORBIDDEN_SUBSTRATE_FIELDS list."
        )


def test_no_substrate_data_when_caller_injects_it(simple_notebook_input, keypair):
    """The writer must REFUSE rather than silently strip when a caller
    tries to add a forbidden field."""
    simple_notebook_input.content_tiptap["chunks"] = [{"id": "ck-1"}]
    with pytest.raises(ValueError, match="forbidden substrate-derived field"):
        write_antiek(simple_notebook_input, keypair=keypair)


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
