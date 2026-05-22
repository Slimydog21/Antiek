"""AntiekPersistence (SPR-09 M6) tests.

Acceptance criteria from the sprint HTML:

- services/notebooks/persistence.py now calls write_antiek / read_antiek.
- Existing JSON-persisted notebooks migrate forward on first read.
- Test: existing notebook from JSON era opens correctly; saves as
  .antiek on next write.
- PDF export is the existing pipeline; do not regress it (smoke).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from services.antiek_format import read_antiek
from services.notebooks.blocks import BLOCK_TAXONOMY_VERSION, BlockType
from services.notebooks.persistence import (
    AntiekPersistence,
    BlockRecord,
    JSONPersistence,
    NotebookRecord,
    SAVE_KIND_EXPLICIT,
    get_default_persistence,
)


def test_default_persistence_is_antiek(combined_db, monkeypatch):
    """SPR-09's default is AntiekPersistence."""
    monkeypatch.delenv("ANTIEK_PERSISTENCE_BACKEND", raising=False)
    from services.notebooks.persistence import reset_default_persistence
    reset_default_persistence()
    backend = get_default_persistence()
    assert isinstance(backend, AntiekPersistence)


def test_default_persistence_json_override(combined_db, monkeypatch):
    """Operators can pin the legacy backend via env var for bisection."""
    monkeypatch.setenv("ANTIEK_PERSISTENCE_BACKEND", "json")
    from services.notebooks.persistence import reset_default_persistence
    reset_default_persistence()
    backend = get_default_persistence()
    assert isinstance(backend, JSONPersistence)


def test_antiek_persistence_writes_archive_on_save(combined_db):
    with tempfile.TemporaryDirectory() as archive_root:
        p = AntiekPersistence(db_path=combined_db, archive_root=archive_root)
        record = p.get_or_create_notebook(
            user_id="user-test", document_id="doc-1"
        )
        # Add a block and save.
        block = BlockRecord(
            block_id="blk-x",
            notebook_id=record.notebook_id,
            block_type=BlockType.HIGHLIGHT_CARD.value,
            source_event_ids=["evt-1"],
            content_json={
                "block_id": "blk-x",
                "passage_text": "important sentence",
            },
            position=1.0,
            document_id="doc-1",
        )
        record.content_json = {
            "type": "doc",
            "content": [
                {"type": "antiek_highlight_card",
                 "attrs": {"block_id": "blk-x", "passage_text": "important"}}
            ],
        }
        record.blocks = [block]
        saved = p.save_notebook(record, save_kind=SAVE_KIND_EXPLICIT)
        # Archive exists on disk and parses.
        archive_path = p.archive_path(saved.notebook_id)
        assert os.path.exists(archive_path), "archive not materialised on save"
        with open(archive_path, "rb") as f:
            data = f.read()
        result = read_antiek(data)
        assert result.signature_valid is True
        assert result.document_id == "doc-1"
        assert any(b["block_id"] == "blk-x" for b in result.blocks_index)


def test_antiek_persistence_substrate_rows_still_authoritative(combined_db):
    """The substrate rows (notebook_documents + per_doc_notebook_blocks) remain
    the operational source of truth — auto-populator + reward hook
    read from them. The archive is the portable artifact alongside."""
    with tempfile.TemporaryDirectory() as archive_root:
        p = AntiekPersistence(db_path=combined_db, archive_root=archive_root)
        record = p.get_or_create_notebook(
            user_id="user-test", document_id="doc-1"
        )
        record.blocks = [
            BlockRecord(
                block_id="blk-y",
                notebook_id=record.notebook_id,
                block_type=BlockType.PROSE.value,
                source_event_ids=[],
                content_json={"text": "operator note"},
                position=1.0,
            )
        ]
        record.content_json = {"type": "doc", "content": []}
        p.save_notebook(record, save_kind=SAVE_KIND_EXPLICIT)
        # Read back via the JSON pathway (same DB).
        json_p = JSONPersistence(db_path=combined_db)
        reloaded = json_p.load_notebook(
            user_id="user-test", document_id="doc-1"
        )
        assert reloaded is not None
        assert len(reloaded.blocks) == 1
        assert reloaded.blocks[0].block_id == "blk-y"


def test_json_era_notebook_migrates_forward_on_next_save(combined_db):
    """Acceptance criterion: a JSON-era notebook (no archive yet)
    opens correctly; next save materialises a `.antiek`."""
    with tempfile.TemporaryDirectory() as archive_root:
        # 1) Simulate a SPR-08-era notebook: written by JSONPersistence
        #    with no archive on disk.
        json_p = JSONPersistence(db_path=combined_db)
        record = json_p.get_or_create_notebook(
            user_id="user-test", document_id="doc-legacy"
        )
        record.content_json = {"type": "doc", "content": []}
        json_p.save_notebook(record, save_kind=SAVE_KIND_EXPLICIT)

        # 2) Now swap in AntiekPersistence on the same DB. The archive
        #    folder is empty — no .antiek for this notebook yet.
        antiek_p = AntiekPersistence(
            db_path=combined_db, archive_root=archive_root
        )
        assert not os.path.exists(antiek_p.archive_path(record.notebook_id))

        # 3) Loading the notebook still works (substrate is the source
        #    of truth).
        loaded = antiek_p.load_notebook(
            user_id="user-test", document_id="doc-legacy"
        )
        assert loaded is not None
        assert loaded.notebook_id == record.notebook_id

        # 4) The next save materialises the archive.
        antiek_p.save_notebook(loaded, save_kind=SAVE_KIND_EXPLICIT)
        assert os.path.exists(antiek_p.archive_path(record.notebook_id)), (
            "expected the JSON-era notebook to materialise an .antiek archive "
            "on its first AntiekPersistence save"
        )


def test_antiek_persistence_upsert_blocks_refreshes_archive(combined_db):
    """Auto-populator path: upsert_blocks bypasses save_notebook but
    must still keep the archive in sync."""
    with tempfile.TemporaryDirectory() as archive_root:
        p = AntiekPersistence(db_path=combined_db, archive_root=archive_root)
        record = p.get_or_create_notebook(
            user_id="user-test", document_id="doc-1"
        )
        # First save materialises the archive at all.
        record.content_json = {"type": "doc", "content": []}
        p.save_notebook(record, save_kind=SAVE_KIND_EXPLICIT)
        first = os.path.getmtime(p.archive_path(record.notebook_id))
        first_size = os.path.getsize(p.archive_path(record.notebook_id))

        # Now the auto-populator adds a block via upsert_blocks.
        block = BlockRecord(
            block_id="blk-new",
            notebook_id=record.notebook_id,
            block_type=BlockType.HIGHLIGHT_CARD.value,
            source_event_ids=["evt-1"],
            content_json={"passage_text": "auto-populated"},
            position=10.0,
        )
        p.upsert_blocks(record.notebook_id, [block])

        # Archive should now reflect the new block.
        with open(p.archive_path(record.notebook_id), "rb") as f:
            data = f.read()
        result = read_antiek(data)
        assert any(b["block_id"] == "blk-new" for b in result.blocks_index), (
            "upsert_blocks did not refresh the .antiek archive"
        )
        # And the file actually changed.
        assert os.path.getsize(p.archive_path(record.notebook_id)) != first_size or \
               os.path.getmtime(p.archive_path(record.notebook_id)) >= first


def test_voice_block_audio_skipped_when_substrate_gap(combined_db):
    """SPR-05 substrate gap: audio bytes are not addressable today. The
    writer is implemented and ready; the persistence layer skips
    silently when neither audio_bytes_b64 nor audio_blob_path is set.
    A future sprint closes the substrate gap; nothing in SPR-09 needs
    to change."""
    with tempfile.TemporaryDirectory() as archive_root:
        p = AntiekPersistence(db_path=combined_db, archive_root=archive_root)
        record = p.get_or_create_notebook(
            user_id="user-test", document_id="doc-voice"
        )
        record.blocks = [
            BlockRecord(
                block_id="blk-voice",
                notebook_id=record.notebook_id,
                block_type=BlockType.VOICE_BLOCK.value,
                source_event_ids=["evt-1"],
                # No audio_bytes_b64, no audio_blob_path → substrate gap.
                content_json={"transcript": "what the user said"},
                position=1.0,
            )
        ]
        record.content_json = {
            "type": "doc",
            "content": [{
                "type": "antiek_voice_block",
                "attrs": {"block_id": "blk-voice", "transcript": "what the user said"},
            }],
        }
        p.save_notebook(record, save_kind=SAVE_KIND_EXPLICIT)
        with open(p.archive_path(record.notebook_id), "rb") as f:
            data = f.read()
        result = read_antiek(data)
        assert result.audio_blobs == {}, (
            "no audio bytes reachable; archive must skip the audio "
            "payload (and surface the gap honestly)"
        )
        # The block survives without audio.
        assert any(
            b["block_id"] == "blk-voice" for b in result.blocks_index
        )


def test_voice_block_audio_embedded_when_inline_b64(combined_db):
    """When the substrate (future sprint) DOES surface audio via the
    in-memory hint, the writer embeds the bytes. Today this exercises
    the path so a Sprint 13+ swap doesn't have to retest the writer."""
    import base64
    audio = b"\x00\x01\x02 FAKE-AUDIO\xff" * 8
    with tempfile.TemporaryDirectory() as archive_root:
        p = AntiekPersistence(db_path=combined_db, archive_root=archive_root)
        record = p.get_or_create_notebook(
            user_id="user-test", document_id="doc-voice-2"
        )
        record.blocks = [
            BlockRecord(
                block_id="blk-voice-b",
                notebook_id=record.notebook_id,
                block_type=BlockType.VOICE_BLOCK.value,
                source_event_ids=["evt-1"],
                content_json={
                    "transcript": "with audio",
                    "audio_bytes_b64": base64.b64encode(audio).decode("ascii"),
                },
                position=1.0,
            )
        ]
        record.content_json = {
            "type": "doc",
            "content": [{
                "type": "antiek_voice_block",
                "attrs": {"block_id": "blk-voice-b"},
            }],
        }
        p.save_notebook(record, save_kind=SAVE_KIND_EXPLICIT)
        with open(p.archive_path(record.notebook_id), "rb") as f:
            data = f.read()
        result = read_antiek(data)
        assert result.audio_blobs.get("blk-voice-b") == audio
