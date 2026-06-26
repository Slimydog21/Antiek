"""End-to-end + invariants tests for the .antiek sidecar (SPR-10 / M6).

Verification gates (mirrors the sprint HTML table):

- End-to-end share: 5 highlights + 2 voice notes + 1 user-asserted edge
  → write → re-import → all rows restored.
- Hash mismatch: sidecar built for different PDF → reader refuses with
  the documented warning; highlights NOT applied.
- Idempotency: same sidecar applied twice → no duplicate rows.
- Invalid signature → restore proceeds; rows flagged
  ``imported_from_unsigned_sidecar=true``.
- Determinism: same input + same keypair → byte-identical sidecar.
- No substrate-derived data: the produced bytes do NOT contain any of
  the ``_FORBIDDEN_SUBSTRATE_FIELDS``.

Re-resolving anchors under a chunker delta (rigor #3): we cannot
simulate a real chunker version delta because the receiving substrate's
``resolve_chunk_for_bbox`` is the geometry-gap stub (returns None
regardless of bbox). We test the call-shape — that the writer's
chunk_id is discarded and a fresh call to the local resolver happens
per anchor — and document the gap honestly.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from typing import Iterator

import duckdb
import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


from services.antiek_format import (
    AnchorRow,
    HASH_MISMATCH_WARNING,
    HighlightRow,
    SidecarInput,
    apply_sidecar,
    ensure_keypair,
    read_sidecar,
    write_sidecar,
)
from services.antiek_format.native_writer import _FORBIDDEN_SUBSTRATE_FIELDS
from services.antiek_format.sidecar_reader import (
    MissingSidecarFields,
    NotASidecar,
    SidecarHashMismatch,
)
from services.antiek_format.sidecar_writer import (
    ENTRY_ANCHORS,
    ENTRY_HIGHLIGHTS,
    SIDECAR_CONTENT_CLASS,
)
# The ingestion-boundary glue (``services/ingestion/sidecar_detector``) is
# SPR-03 / SPR-10 work and is NOT part of the self-contained ``.antiek``
# container format landed in SPR-01 — it lives on the diverged branch and
# reaches into the substrate ingest pipeline. The format package itself
# (``services.antiek_format``) imports nothing from ``services.ingestion``;
# the dependency runs the other way (ingestion depends on the format).
# Only the six tests below that exercise that boundary call these names.
# On a fresh branch off main (no ``services.ingestion`` yet) we import them
# guardedly so the module still collects and the format's own sidecar
# reader/writer tests (determinism, round-trip, forbidden-fields, signature
# tamper, hash-mismatch reader behavior, idempotency) run. The six
# boundary tests skip with an explicit reason until the ingestion surface
# lands in a later sprint. This mirrors the guarded-optional-import pattern
# the format's own production modules already use.
try:
    from services.ingestion.sidecar_detector import (
        apply_sidecar_for_pdf_after_ingest,
        is_antiek_sidecar_bytes,
        parse_zip_upload,
    )
except ModuleNotFoundError:  # services.ingestion not present on this branch
    apply_sidecar_for_pdf_after_ingest = None  # type: ignore[assignment]
    is_antiek_sidecar_bytes = None  # type: ignore[assignment]
    parse_zip_upload = None  # type: ignore[assignment]

_INGESTION_BOUNDARY_AVAILABLE = apply_sidecar_for_pdf_after_ingest is not None
_skip_no_ingestion = pytest.mark.skipif(
    not _INGESTION_BOUNDARY_AVAILABLE,
    reason=(
        "services.ingestion.sidecar_detector is SPR-03/SPR-10 ingestion-boundary "
        "work, not part of the SPR-01 self-contained .antiek container format. "
        "Skipped until the ingestion surface lands on this branch."
    ),
)


# The sidecar APPLY path (``apply_sidecar`` → write restored rows back into a
# receiving substrate) is substrate-coupled by construction: it inserts into
# ``behavior_events`` and ``voice_note_anchor`` via ``runtime.db_lock`` and
# re-resolves anchor chunk_ids under ``substrate.voice``. The container-format
# core (write/read/sign/verify/project/forbidden-fields/determinism) is
# self-contained and those tests run unconditionally; only the four
# apply-path tests below need the substrate modules. ``substrate.behavior``
# and ``substrate.voice`` are Wave-2 work that exists on the diverged branch
# but not on a fresh branch off main, so apply-side tests are skipped here
# until those modules land. The apply path itself (``apply_sidecar``) is
# transported verbatim — it will run once the substrate surface is present.
def _substrate_apply_available() -> bool:
    try:
        import substrate.behavior.taxonomy  # noqa: F401
        import substrate.voice  # noqa: F401
        import runtime.db_lock  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


_skip_no_substrate_apply = pytest.mark.skipif(
    not _substrate_apply_available(),
    reason=(
        "apply_sidecar restores sidecar rows into the receiving substrate via "
        "substrate.behavior + substrate.voice + runtime.db_lock, which are "
        "Wave-2 modules not present on a fresh branch off main. The "
        "self-contained container-format tests (read/write/sign/verify/project/"
        "forbidden-fields/determinism) run regardless. Skipped until the "
        "substrate surface lands on this branch."
    ),
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def antiek_db(tmp_path) -> Iterator[str]:
    """Per-test DuckDB with the schemas we need.

    We bootstrap:
      - The keypair table (created by ``ensure_keypair`` on demand).
      - documents + voice_note_anchor (for apply tests).
      - behavior_events (for highlight apply tests).

    The schemas are installed manually rather than calling the project
    migrate commands so the test stays focused on sidecar behavior, not
    migration plumbing.
    """
    path = str(tmp_path / "antiek-spr10-test.duckdb")
    con = duckdb.connect(path)
    try:
        # documents (minimal columns the sidecar apply touches).
        con.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                document_id      TEXT PRIMARY KEY,
                source_tier      INTEGER NOT NULL DEFAULT 2,
                document_type    TEXT NOT NULL,
                source_uri       TEXT,
                title            TEXT,
                author           TEXT,
                published_at     TIMESTAMP,
                investigation_id TEXT,
                raw_text         TEXT,
                metadata         TEXT
            );
        """)
        # chunks (referenced by voice_note_anchor.chunk_id FK).
        con.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id      TEXT PRIMARY KEY,
                document_id   TEXT NOT NULL,
                chunk_index   INTEGER NOT NULL,
                text          TEXT NOT NULL,
                section_path  TEXT,
                embedding     FLOAT[],
                token_count   INTEGER
            );
        """)
        # voice_note_anchor.
        con.execute("""
            CREATE TABLE IF NOT EXISTS voice_note_anchor (
                anchor_id        TEXT PRIMARY KEY,
                voice_note_id    TEXT NOT NULL UNIQUE,
                document_id      TEXT NOT NULL,
                page             INTEGER NOT NULL,
                bbox             TEXT NOT NULL,
                chunk_id         TEXT,
                chunker_version  TEXT NOT NULL,
                created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # behavior_events.
        con.execute("""
            CREATE TABLE IF NOT EXISTS behavior_events (
                event_id                TEXT PRIMARY KEY,
                user_id                 TEXT NOT NULL,
                session_id              TEXT NOT NULL,
                document_id             TEXT,
                timestamp_utc           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                event_type              TEXT NOT NULL,
                state                   TEXT NOT NULL,
                action                  TEXT NOT NULL,
                outcome                 TEXT,
                reward_proxy_immediate  DOUBLE,
                reward_proxy_medium     DOUBLE,
                reward_proxy_deep       DOUBLE,
                consent_version         INTEGER NOT NULL,
                dp_shuffler_batch_id    TEXT
            );
        """)
        # Insert a parent-PDF documents row so the FK on
        # voice_note_anchor.document_id is satisfiable.
        con.execute(
            "INSERT INTO documents (document_id, document_type, raw_text) "
            "VALUES (?, ?, ?)",
            ["doc-pdf-fixture", "pdf", "fake pdf text"],
        )
    finally:
        con.close()
    yield path


@pytest.fixture
def keypair_a(antiek_db: str):
    return ensure_keypair("user-A", db_path=antiek_db)


@pytest.fixture
def keypair_b(antiek_db: str):
    return ensure_keypair("user-B", db_path=antiek_db)


@pytest.fixture
def fixed_created_at() -> datetime:
    return datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def fake_pdf_bytes() -> bytes:
    # Minimal "PDF-shaped" bytes; the parent_pdf_sha256 check only cares
    # about the SHA-256, not PDF validity.
    return b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\nfake-pdf-fixture-bytes\n%%EOF\n"


@pytest.fixture
def sidecar_input_full(fixed_created_at, fake_pdf_bytes) -> SidecarInput:
    """Five highlights + two voice anchors + one user-asserted edge —
    the exact spec from the sprint HTML M6 acceptance criterion.
    """
    pdf_sha = hashlib.sha256(fake_pdf_bytes).hexdigest()
    highlights = [
        HighlightRow(
            highlight_id=f"hl-share-{i}",
            document_id="doc-pdf-fixture",
            page=i,
            bbox_x0=50.0, bbox_y0=100.0 + i * 30,
            bbox_x1=400.0, bbox_y1=130.0 + i * 30,
            passage_text=f"highlight passage {i}",
            color="yellow",
            created_at=fixed_created_at.isoformat(),
        )
        for i in range(5)
    ]
    anchors = [
        AnchorRow(
            anchor_id=f"vna-share-{i}",
            voice_note_id=f"doc-vn-share-{i}",
            document_id="doc-pdf-fixture",
            page=i + 1,
            bbox_x0=60.0, bbox_y0=200.0,
            bbox_x1=400.0, bbox_y1=240.0,
            chunker_version="v0.9.0",  # writer is on an OLDER version
            chunk_id=f"chk-stale-{i}",  # informational; reader re-resolves
            transcript=f"voice transcript {i}",
            duration_seconds=12.5 + i,
            created_at=fixed_created_at.isoformat(),
        )
        for i in range(2)
    ]
    edges = [{
        "edge_id": "edg-share-1",
        "from_block_id": "blk-share-h0",
        "to_content_hash": "c" * 64,
        "to_document_id": "doc-share-related",
        "kind": "supports",
        "asserted_at": fixed_created_at.isoformat(),
        "operator_note": "share fixture",
    }]
    return SidecarInput(
        document_id="doc-pdf-fixture",
        user_id="user-A",
        parent_pdf_sha256=pdf_sha,
        parent_pdf_size_bytes=len(fake_pdf_bytes),
        parent_pdf_filename_hint="paper.pdf",
        title="Share fixture",
        highlights=highlights,
        anchors=anchors,
        edges=edges,
        audio_blobs={"doc-vn-share-0": b"fake-audio-bytes-for-voice-0"},
        created_at=fixed_created_at,
        chunker_version_at_write="v0.9.0",
    )


# ─────────────────────────────────────────────────────────────────────
# Writer + reader basic round-trip
# ─────────────────────────────────────────────────────────────────────


def test_write_sidecar_uses_pdf_sidecar_content_class(
    sidecar_input_full, keypair_a,
):
    """M1 acceptance: content_class is 'pdf_sidecar'."""
    data = write_sidecar(sidecar_input_full, keypair=keypair_a)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert manifest["content_class"] == "pdf_sidecar"
    assert manifest["parent_pdf_sha256"] == sidecar_input_full.parent_pdf_sha256
    assert manifest["parent_pdf_size_bytes"] == sidecar_input_full.parent_pdf_size_bytes
    assert manifest["parent_pdf_filename_hint"] == "paper.pdf"
    assert manifest["highlights_present"] is True
    assert manifest["anchors_present"] is True


def test_write_sidecar_includes_section_files(
    sidecar_input_full, keypair_a,
):
    """M2 acceptance: highlights.jsonl + anchors.jsonl land in the zip."""
    data = write_sidecar(sidecar_input_full, keypair=keypair_a)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
    assert ENTRY_HIGHLIGHTS in names
    assert ENTRY_ANCHORS in names
    assert "edges.jsonl" in names
    # Voice-block audio rides as blocks/<voice_note_id>.audio.
    assert "blocks/doc-vn-share-0.audio" in names


def test_read_sidecar_round_trips_all_sections(
    sidecar_input_full, keypair_a, fake_pdf_bytes,
):
    data = write_sidecar(sidecar_input_full, keypair=keypair_a)
    restored = read_sidecar(
        data,
        imported_pdf_sha256=hashlib.sha256(fake_pdf_bytes).hexdigest(),
    )
    assert restored.signature_valid
    assert not restored.hash_mismatch
    assert len(restored.highlights) == 5
    assert len(restored.anchors) == 2
    assert len(restored.edges) == 1
    assert "doc-vn-share-0" in restored.audio_blobs


def test_deterministic_sidecar(sidecar_input_full, keypair_a):
    """M2 acceptance: same input + same keypair → byte-identical bytes."""
    a = write_sidecar(sidecar_input_full, keypair=keypair_a)
    b = write_sidecar(sidecar_input_full, keypair=keypair_a)
    assert a == b
    # And the inner manifest is identical too.
    with zipfile.ZipFile(io.BytesIO(a)) as zf_a, zipfile.ZipFile(io.BytesIO(b)) as zf_b:
        assert zf_a.read("manifest.json") == zf_b.read("manifest.json")


# ─────────────────────────────────────────────────────────────────────
# Required-fields enforcement (M1 last criterion)
# ─────────────────────────────────────────────────────────────────────


def test_sidecar_without_parent_pdf_sha256_refuses(
    sidecar_input_full, keypair_a,
):
    """M1 acceptance: sidecar without parent_pdf_sha256 → reader refuses
    with clear error.

    We forge the manifest by surgically stripping the field after the
    deterministic write (you can't construct a SidecarInput without it —
    __post_init__ blocks that — so we tamper at the bytes level)."""
    data = write_sidecar(sidecar_input_full, keypair=keypair_a)
    tampered = _tamper_manifest(data, lambda m: m.pop("parent_pdf_sha256"))
    with pytest.raises(MissingSidecarFields) as exc_info:
        read_sidecar(tampered)
    assert "parent_pdf_sha256" in str(exc_info.value)


def test_sidecar_input_rejects_malformed_sha256():
    """The writer-side SidecarInput rejects malformed hashes up front."""
    with pytest.raises(ValueError, match="parent_pdf_sha256"):
        SidecarInput(
            document_id="doc-x",
            user_id="user-A",
            parent_pdf_sha256="not-a-hash",
            parent_pdf_size_bytes=100,
        )


# ─────────────────────────────────────────────────────────────────────
# End-to-end share (M6 acceptance: 5+2+1 → 5+2+1)
# ─────────────────────────────────────────────────────────────────────


@_skip_no_substrate_apply
def test_share_end_to_end_restores_all_rows(
    sidecar_input_full, keypair_a, antiek_db, fake_pdf_bytes,
):
    """User A writes the sidecar; user B applies it. After apply:
      - 5 behavior_events rows of type highlight_created.
      - 2 voice_note_anchor rows.
      - 2 voice-note documents rows.
      - 1 sidecar_user_edges row.
      - 1 audio blob on disk.
    """
    data = write_sidecar(sidecar_input_full, keypair=keypair_a)
    restored = read_sidecar(
        data,
        imported_pdf_sha256=hashlib.sha256(fake_pdf_bytes).hexdigest(),
    )
    assert not restored.hash_mismatch

    audio_root = os.path.join(os.path.dirname(antiek_db), "audio")
    report = apply_sidecar(
        restored,
        db_path=antiek_db,
        user_id="user-B",
        audio_storage_root=audio_root,
    )

    assert report.highlights_written == 5
    assert report.anchors_written == 2
    assert report.edges_written == 1
    assert report.audio_blobs_written == 1
    assert report.chunker_re_resolved == 2  # one per anchor

    # Substrate state matches.
    con = duckdb.connect(antiek_db)
    try:
        hl_count = con.execute(
            "SELECT COUNT(*) FROM behavior_events "
            "WHERE event_type = 'highlight_created' AND document_id = ?",
            ["doc-pdf-fixture"],
        ).fetchone()[0]
        an_count = con.execute(
            "SELECT COUNT(*) FROM voice_note_anchor WHERE document_id = ?",
            ["doc-pdf-fixture"],
        ).fetchone()[0]
        vn_doc_count = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_type = 'voice_note'",
        ).fetchone()[0]
        edge_count = con.execute(
            "SELECT COUNT(*) FROM sidecar_user_edges",
        ).fetchone()[0]
    finally:
        con.close()
    assert hl_count == 5
    assert an_count == 2
    assert vn_doc_count == 2
    assert edge_count == 1


# ─────────────────────────────────────────────────────────────────────
# Hash mismatch (M6 acceptance + rigor #1)
# ─────────────────────────────────────────────────────────────────────


def test_hash_mismatch_reader_returns_flag_not_raise(
    sidecar_input_full, keypair_a,
):
    data = write_sidecar(sidecar_input_full, keypair=keypair_a)
    wrong_pdf = b"completely different pdf bytes"
    restored = read_sidecar(
        data,
        imported_pdf_sha256=hashlib.sha256(wrong_pdf).hexdigest(),
    )
    assert restored.hash_mismatch is True
    assert restored.signature_valid is True  # signature is fine; PDF is wrong


def test_hash_mismatch_strict_raises(sidecar_input_full, keypair_a):
    data = write_sidecar(sidecar_input_full, keypair=keypair_a)
    wrong_pdf = b"completely different pdf bytes"
    with pytest.raises(SidecarHashMismatch):
        read_sidecar(
            data,
            imported_pdf_sha256=hashlib.sha256(wrong_pdf).hexdigest(),
            strict=True,
        )


def test_hash_mismatch_apply_refuses(
    sidecar_input_full, keypair_a, antiek_db,
):
    """Highlights are NOT applied when hashes don't match."""
    data = write_sidecar(sidecar_input_full, keypair=keypair_a)
    wrong_pdf = b"completely different pdf bytes"
    restored = read_sidecar(
        data,
        imported_pdf_sha256=hashlib.sha256(wrong_pdf).hexdigest(),
    )
    assert restored.hash_mismatch
    with pytest.raises(ValueError, match="hash-mismatched"):
        apply_sidecar(restored, db_path=antiek_db, user_id="user-B")

    # Substrate stayed empty.
    con = duckdb.connect(antiek_db)
    try:
        hl_count = con.execute(
            "SELECT COUNT(*) FROM behavior_events "
            "WHERE event_type = 'highlight_created'",
        ).fetchone()[0]
    finally:
        con.close()
    assert hl_count == 0


def test_hash_mismatch_warning_text_is_honest():
    """Rigor #1: the warning surfaces the failure mode honestly."""
    assert "different version of the PDF" in HASH_MISMATCH_WARNING
    assert "wrong text" in HASH_MISMATCH_WARNING
    assert "NOT applied" in HASH_MISMATCH_WARNING


@_skip_no_ingestion
def test_pipeline_hash_mismatch_outcome_uses_documented_text(
    sidecar_input_full, keypair_a, antiek_db,
):
    """The ingest-side outcome surfaces the documented warning text."""
    data = write_sidecar(sidecar_input_full, keypair=keypair_a)
    wrong_pdf = b"completely different pdf bytes"
    outcome = apply_sidecar_for_pdf_after_ingest(
        sidecar_bytes=data,
        pdf_bytes=wrong_pdf,
        document_id="doc-pdf-other",
        user_id="user-B",
        db_path=antiek_db,
        sidecar_source="zip",
    )
    assert outcome.hash_mismatch
    assert not outcome.applied
    assert outcome.ui_message == HASH_MISMATCH_WARNING


# ─────────────────────────────────────────────────────────────────────
# Idempotency (M6 acceptance)
# ─────────────────────────────────────────────────────────────────────


@_skip_no_substrate_apply
def test_idempotent_apply(
    sidecar_input_full, keypair_a, antiek_db, fake_pdf_bytes,
):
    """Importing the same sidecar twice → no duplicate rows."""
    data = write_sidecar(sidecar_input_full, keypair=keypair_a)

    # First apply.
    restored = read_sidecar(
        data,
        imported_pdf_sha256=hashlib.sha256(fake_pdf_bytes).hexdigest(),
    )
    r1 = apply_sidecar(restored, db_path=antiek_db, user_id="user-B")
    assert r1.highlights_written == 5
    assert r1.anchors_written == 2
    assert r1.edges_written == 1

    # Re-read + re-apply (simulates a real re-import — the file is the
    # same on disk).
    restored2 = read_sidecar(
        data,
        imported_pdf_sha256=hashlib.sha256(fake_pdf_bytes).hexdigest(),
    )
    r2 = apply_sidecar(restored2, db_path=antiek_db, user_id="user-B")
    assert r2.highlights_written == 0
    assert r2.anchors_written == 0
    assert r2.edges_written == 0
    assert r2.highlights_skipped_existing == 5
    assert r2.anchors_skipped_existing == 2
    assert r2.edges_skipped_existing == 1

    # Row counts unchanged from after the first apply.
    con = duckdb.connect(antiek_db)
    try:
        hl_count = con.execute(
            "SELECT COUNT(*) FROM behavior_events "
            "WHERE event_type = 'highlight_created'",
        ).fetchone()[0]
        an_count = con.execute("SELECT COUNT(*) FROM voice_note_anchor").fetchone()[0]
        ed_count = con.execute("SELECT COUNT(*) FROM sidecar_user_edges").fetchone()[0]
    finally:
        con.close()
    assert hl_count == 5
    assert an_count == 2
    assert ed_count == 1


# ─────────────────────────────────────────────────────────────────────
# Invalid signature (M6 acceptance + rigor #5)
# ─────────────────────────────────────────────────────────────────────


@_skip_no_substrate_apply
def test_unsigned_sidecar_restores_with_flag(
    sidecar_input_full, keypair_a, antiek_db, fake_pdf_bytes,
):
    """Invalid signature → restore proceeds; rows flagged."""
    data = write_sidecar(sidecar_input_full, keypair=keypair_a)
    # Tamper the highlight passage_text after signing. The signature
    # was computed over the canonical bytes; this edit breaks them.
    tampered = _tamper_highlights_jsonl(
        data, lambda h: {**h, "passage_text": "TAMPERED!"},
    )
    restored = read_sidecar(
        tampered,
        imported_pdf_sha256=hashlib.sha256(fake_pdf_bytes).hexdigest(),
    )
    assert restored.signature_valid is False  # tamper detected
    assert restored.hash_mismatch is False

    report = apply_sidecar(restored, db_path=antiek_db, user_id="user-B")
    assert report.unsigned_flag_applied is True
    assert report.highlights_written == 5  # restore still proceeds

    # Verify the flag landed on the inserted rows.
    con = duckdb.connect(antiek_db)
    try:
        row = con.execute(
            "SELECT action FROM behavior_events "
            "WHERE event_type = 'highlight_created' LIMIT 1",
        ).fetchone()
    finally:
        con.close()
    action = json.loads(row[0])
    assert action.get("imported_from_unsigned_sidecar") is True


# ─────────────────────────────────────────────────────────────────────
# Re-resolving anchors under the receiving chunker (rigor #3)
# ─────────────────────────────────────────────────────────────────────


@_skip_no_substrate_apply
def test_anchor_chunk_id_re_resolved_under_local_chunker(
    sidecar_input_full, keypair_a, antiek_db, fake_pdf_bytes,
):
    """The writer recorded ``chunk_id='chk-stale-N'`` and
    ``chunker_version='v0.9.0'``. The reader MUST discard those and
    re-resolve under the local chunker — which today returns None
    (geometry gap surfaced honestly).

    We assert the inserted anchor row has the LOCAL chunker_version
    stamped + chunk_id reflecting the local resolver's answer (None),
    NOT the writer's stale id.
    """
    from substrate.voice import CHUNKER_VERSION

    data = write_sidecar(sidecar_input_full, keypair=keypair_a)
    restored = read_sidecar(
        data,
        imported_pdf_sha256=hashlib.sha256(fake_pdf_bytes).hexdigest(),
    )
    report = apply_sidecar(restored, db_path=antiek_db, user_id="user-B")
    # The chunker-delta warning fired because writer's v0.9.0 !=
    # the substrate's live CHUNKER_VERSION.
    if CHUNKER_VERSION != "v0.9.0":
        assert any("chunker" in w for w in report.warnings)

    con = duckdb.connect(antiek_db)
    try:
        rows = con.execute(
            "SELECT chunk_id, chunker_version FROM voice_note_anchor "
            "WHERE document_id = ?",
            ["doc-pdf-fixture"],
        ).fetchall()
    finally:
        con.close()
    for chunk_id, version in rows:
        # Geometry gap: local resolver returns None today. The point is
        # that the WRITER's stale ids ('chk-stale-N') did NOT land.
        assert chunk_id != "chk-stale-0"
        assert chunk_id != "chk-stale-1"
        # And the chunker_version is the LOCAL one, not v0.9.0.
        assert version == CHUNKER_VERSION


# ─────────────────────────────────────────────────────────────────────
# No substrate-derived data leaks into a sidecar
# ─────────────────────────────────────────────────────────────────────


def test_no_substrate_data_in_sidecar_bytes(
    sidecar_input_full, keypair_a,
):
    """Master-spec invariant: byte-grep the produced sidecar against the
    forbidden field names. Some names (e.g. 'chunk_id') intentionally
    DO appear inside ``anchors.jsonl`` for informational provenance.
    The list below is the substrate-leakage subset we actually forbid
    end-to-end."""
    data = write_sidecar(sidecar_input_full, keypair=keypair_a)
    # We forbid substrate ARTIFACTS, not the field name 'chunk_id'
    # alone (that one IS in our anchor rows by design — reader
    # re-resolves it). Subset of _FORBIDDEN_SUBSTRATE_FIELDS that
    # we MUST NOT see in sidecar bytes:
    substrate_only_forbidden = (
        "chunk_text",
        "chunk_embedding",
        "embedding_vector",
        "vector_embedding",
        "graph_edges_auto",
        "auto_edges",
        "discovered_edges",
        "attribution_weights",
        "attribution_scores",
        "attribution_vector",
        "reward_proxy_immediate",
        "reward_proxy_medium",
        "reward_proxy_long",
        "reward_signal",
    )
    for forbidden in substrate_only_forbidden:
        assert forbidden.encode("utf-8") not in data, (
            f"forbidden substrate field {forbidden!r} found in sidecar bytes"
        )


def test_writer_refuses_forbidden_field_in_highlight(keypair_a):
    """Defensive: if a caller smuggles 'chunk_embedding' into a
    highlight row via the to_dict path, the byte-grep pre-flight in
    ``_assert_no_forbidden_fields`` should refuse."""
    hl = HighlightRow(
        highlight_id="hl-leak",
        document_id="doc-x",
        page=0,
        bbox_x0=0.0, bbox_y0=0.0, bbox_x1=10.0, bbox_y1=10.0,
    )
    # Forging a leak: a malicious caller could subclass HighlightRow
    # and add the field. We simulate by patching to_dict.
    original = hl.to_dict
    def leaky():
        d = original()
        d["chunk_embedding"] = [0.1, 0.2]
        return d
    hl.to_dict = leaky  # type: ignore[method-assign]

    inp = SidecarInput(
        document_id="doc-pdf-fixture",
        user_id="user-A",
        parent_pdf_sha256="a" * 64,
        parent_pdf_size_bytes=1024,
        highlights=[hl],
    )
    with pytest.raises(ValueError, match="forbidden substrate-derived field"):
        write_sidecar(inp, keypair=keypair_a)


# ─────────────────────────────────────────────────────────────────────
# Zip-upload detection (M4 acceptance)
# ─────────────────────────────────────────────────────────────────────


@_skip_no_ingestion
def test_parse_zip_upload_finds_pdf_plus_sidecar(
    sidecar_input_full, keypair_a, fake_pdf_bytes,
):
    sidecar_bytes = write_sidecar(sidecar_input_full, keypair=keypair_a)
    # Build a zip containing both.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("paper.pdf", fake_pdf_bytes)
        zf.writestr("paper.antiek", sidecar_bytes)
    parse = parse_zip_upload(buf.getvalue())
    assert parse.pdf_bytes == fake_pdf_bytes
    assert parse.sidecar_bytes == sidecar_bytes
    assert parse.pdf_filename == "paper.pdf"
    assert parse.sidecar_filename == "paper.antiek"


@_skip_no_ingestion
def test_parse_zip_upload_with_no_sidecar(fake_pdf_bytes):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("paper.pdf", fake_pdf_bytes)
    parse = parse_zip_upload(buf.getvalue())
    assert parse.pdf_bytes == fake_pdf_bytes
    assert parse.sidecar_bytes is None


@_skip_no_ingestion
def test_is_antiek_sidecar_bytes_discriminates_notebook(
    sidecar_input_full, keypair_a,
):
    sidecar_bytes = write_sidecar(sidecar_input_full, keypair=keypair_a)
    assert is_antiek_sidecar_bytes(sidecar_bytes) is True
    assert is_antiek_sidecar_bytes(b"random bytes") is False


@_skip_no_ingestion
def test_zip_upload_detection_to_apply_outcome(
    sidecar_input_full, keypair_a, antiek_db, fake_pdf_bytes,
):
    sidecar_bytes = write_sidecar(sidecar_input_full, keypair=keypair_a)
    outcome = apply_sidecar_for_pdf_after_ingest(
        sidecar_bytes=sidecar_bytes,
        pdf_bytes=fake_pdf_bytes,
        document_id="doc-pdf-fixture",
        user_id="user-B",
        db_path=antiek_db,
        sidecar_source="zip",
    )
    assert outcome.detected
    assert outcome.applied
    assert not outcome.hash_mismatch
    assert outcome.highlights_written == 5
    assert outcome.anchors_written == 2
    assert outcome.edges_written == 1
    # The UI string matches the sprint HTML's example shape.
    assert "Restored" in outcome.ui_message
    assert "highlight" in outcome.ui_message
    assert "voice note" in outcome.ui_message


@_skip_no_ingestion
def test_not_a_sidecar_returns_clean_error(
    sidecar_input_full, keypair_a, antiek_db, fake_pdf_bytes,
):
    """A notebook .antiek dropped into the sidecar path → NotASidecar."""
    from services.antiek_format import WriterInput, write_antiek
    notebook_input = WriterInput(
        notebook_id="nbk-x",
        user_id="user-A",
        document_id="doc-fixture",
        parent_document_id="doc-fixture",
        content_class="notebook",
        title="test notebook",
        content_tiptap={"type": "doc", "content": []},
    )
    notebook_bytes = write_antiek(notebook_input, keypair=keypair_a)
    outcome = apply_sidecar_for_pdf_after_ingest(
        sidecar_bytes=notebook_bytes,
        pdf_bytes=fake_pdf_bytes,
        document_id="doc-pdf-fixture",
        user_id="user-B",
        db_path=antiek_db,
    )
    assert outcome.detected
    assert not outcome.applied
    assert outcome.error and "not_a_sidecar" in outcome.error


# ─────────────────────────────────────────────────────────────────────
# Helpers — manifest / jsonl tampering for tests
# ─────────────────────────────────────────────────────────────────────


def _tamper_manifest(data: bytes, mutate):
    """Read the sidecar bytes, mutate the manifest in-memory, re-emit
    a tampered zip with the same other entries. Signature will no
    longer verify (the test should not depend on it doing so)."""
    with zipfile.ZipFile(io.BytesIO(data), mode="r") as zf:
        entries = []
        for n in zf.namelist():
            entries.append((n, zf.read(n)))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as zf:
        for n, payload in entries:
            if n == "manifest.json":
                manifest = json.loads(payload.decode("utf-8"))
                mutate(manifest)
                payload = (json.dumps(manifest, sort_keys=True,
                                       ensure_ascii=False, separators=(",", ":"))
                           + "\n").encode("utf-8")
            zf.writestr(n, payload)
    return out.getvalue()


def _tamper_highlights_jsonl(data: bytes, mutate_row):
    """Rewrite highlights.jsonl with mutated rows. Used to simulate
    a tampered sidecar (signature no longer matches)."""
    with zipfile.ZipFile(io.BytesIO(data), mode="r") as zf:
        entries = []
        for n in zf.namelist():
            entries.append((n, zf.read(n)))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as zf:
        for n, payload in entries:
            if n == ENTRY_HIGHLIGHTS:
                lines = []
                for line in payload.decode("utf-8").splitlines():
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    row = mutate_row(row)
                    lines.append(json.dumps(row, sort_keys=True,
                                            ensure_ascii=False, separators=(",", ":")))
                payload = ("\n".join(lines) + "\n").encode("utf-8")
            zf.writestr(n, payload)
    return out.getvalue()
