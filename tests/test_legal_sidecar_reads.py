from __future__ import annotations

import json

import duckdb
import pytest

from services.antiek_format.sidecar_reader import RestoredSidecar, apply_sidecar
from services.antiek_format.sidecar_writer import _gather_anchors_and_audio


@pytest.mark.parametrize("setting", [None, "0", "malformed", "1"])
def test_sidecar_apply_is_inert_before_write_admission(
    tmp_path, monkeypatch, setting
):
    if setting is None:
        monkeypatch.delenv("ANTIEK_LEGAL_READ_ENFORCEMENT", raising=False)
    else:
        monkeypatch.setenv("ANTIEK_LEGAL_READ_ENFORCEMENT", setting)
    database = tmp_path / "must-not-be-created.duckdb"
    audio = tmp_path / "must-not-write-audio"
    restored = RestoredSidecar(
        document_id="doc-parent",
        parent_pdf_sha256="a" * 64,
        parent_pdf_size_bytes=1,
        parent_pdf_filename_hint="book.pdf",
        creator_user_id="alice",
        creator_pubkey="public-key",
        title="Book",
        created_at="2026-07-15T00:00:00Z",
        chunker_version_at_write="v1",
        anchors=[
            {
                "anchor_id": "anchor-1",
                "voice_note_id": "voice-foreign",
                "transcript": "must not enter custody",
                "audio_path": "audio/voice-foreign.bin",
            }
        ],
        audio_blobs={"voice-foreign": b"must not be written"},
        signature_valid=True,
    )

    report = apply_sidecar(
        restored,
        db_path=str(database),
        user_id="alice",
        audio_storage_root=str(audio),
        investigation_id="inv-a",
    )

    assert report.anchors_written == 0
    assert report.audio_blobs_written == 0
    assert report.warnings == [
        "sidecar apply is unavailable until imported voice-note documents "
        "receive investigation-bound legal admission receipts"
    ]
    assert not database.exists()
    assert not audio.exists()


def test_sidecar_export_never_reads_unadmitted_voice_audio_path(tmp_path):
    database = tmp_path / "sidecar.duckdb"
    secret = tmp_path / "foreign.audio"
    secret.write_bytes(b"foreign account audio")
    con = duckdb.connect(str(database))
    try:
        con.execute(
            "CREATE TABLE voice_note_anchor (anchor_id TEXT, voice_note_id TEXT, "
            "document_id TEXT, page INTEGER, bbox TEXT, chunk_id TEXT, "
            "chunker_version TEXT, created_at TEXT)"
        )
        con.execute(
            "CREATE TABLE documents (document_id TEXT, raw_text TEXT, metadata TEXT)"
        )
        con.execute(
            "INSERT INTO voice_note_anchor VALUES "
            "('a1', 'voice-foreign', 'parent', 1, '{}', NULL, 'v1', '2026-07-15')"
        )
        con.execute(
            "INSERT INTO documents VALUES (?, ?, ?)",
            [
                "voice-foreign",
                "foreign transcript",
                json.dumps({"audio_blob_path": str(secret)}),
            ],
        )
    finally:
        con.close()

    anchors, audio = _gather_anchors_and_audio(
        document_id="parent", db_path=str(database), authority=None
    )

    assert len(anchors) == 1
    assert anchors[0].transcript is None
    assert audio == {}
