"""Sidecar writer: user-derived data for an imported PDF → .antiek bytes.

SPR-10 / M2. Companion to SPR-09's ``native_writer.write_antiek``.

Why a separate writer rather than overloading native_writer
----------------------------------------------------------
A sidecar carries DIFFERENT user-data sections than a notebook:
``highlights.jsonl`` + ``anchors.jsonl`` instead of a TipTap body.
Trying to thread both into one writer would force the notebook-side
``WriterInput`` to grow optional fields it never uses, and the
signing-input would gain conditional branches. The cleaner cut is
two writers behind one zip+signature machinery — the deterministic
zip builder, canonical-bytes helpers, and Ed25519 keypair API are
reused verbatim.

Substrate-derived data MUST NOT appear
--------------------------------------
Same invariant as ``native_writer``. ``_FORBIDDEN_SUBSTRATE_FIELDS``
is byte-greppable; this writer runs the same pre-flight refusal over
every input section before zipping. Chunks, embeddings, attribution
weights, reward proxies are recomputable on the receiving substrate
— they MUST NOT live in the file. (The anchor row's ``chunk_id`` IS
included but is informational only on read; the reader re-resolves
it under its own chunker. See SPEC.md §11.3.)

Determinism
-----------
The sidecar zip is byte-identical for identical input + identical
keypair, same as notebooks. Same fixed 1980-01-01 timestamps,
ZIP_STORED, sorted entries. Tested in
``services/antiek_format/tests/test_sidecar_e2e.py::test_deterministic_sidecar``.

Signing
-------
Five-section signing input (SPEC.md §11.4): manifest + content +
edges + highlights + anchors, separated by 0x1F. ``content.tiptap.json``
for a sidecar is the empty-doc carrier — the shape exists so the
reader can re-use one zip-validation path across variants. The
sidecar-only sections (highlights, anchors) ride as ``extra_sections``
into ``build_signing_input``.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

try:
    from .native_writer import (
        _FORBIDDEN_SUBSTRATE_FIELDS,
        BLOCKS_PREFIX,
        ENTRY_CONTENT,
        ENTRY_EDGES,
        ENTRY_MANIFEST,
        ENTRY_SIGNATURE,
        SCHEMA_VERSION,
        _build_deterministic_zip,
        _canonical_tiptap_node,
    )
    from .signature import (
        Keypair,
        build_signing_input,
        canonical_edges_bytes,
        canonical_json_bytes,
        sign_bytes,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from services.antiek_format.native_writer import (  # type: ignore[no-redef]
        _FORBIDDEN_SUBSTRATE_FIELDS,
        BLOCKS_PREFIX,
        ENTRY_CONTENT,
        ENTRY_EDGES,
        ENTRY_MANIFEST,
        ENTRY_SIGNATURE,
        SCHEMA_VERSION,
        _build_deterministic_zip,
        _canonical_tiptap_node,
    )
    from services.antiek_format.signature import (  # type: ignore[no-redef]
        Keypair,
        build_signing_input,
        canonical_edges_bytes,
        canonical_json_bytes,
        sign_bytes,
    )


# ── Sidecar-specific entry names ──

ENTRY_HIGHLIGHTS: str = "highlights.jsonl"
ENTRY_ANCHORS: str = "anchors.jsonl"

# Sidecar-specific forbidden list. Same as native_writer's
# ``_FORBIDDEN_SUBSTRATE_FIELDS`` minus ``chunk_id`` — anchor rows
# carry chunk_id as INFORMATIONAL provenance (see SPEC.md §11.3). The
# receiving substrate discards the writer's chunk_id and re-resolves
# under its own chunker; the field is data, not authority. Substrate
# artifacts (chunk_text, embeddings, attribution, reward proxies) are
# still forbidden — those would freeze substrate evolution.
_FORBIDDEN_SIDECAR_FIELDS: frozenset[str] = frozenset(
    f for f in _FORBIDDEN_SUBSTRATE_FIELDS if f != "chunk_id"
)


def _assert_no_forbidden_sidecar_fields(obj: Any, *, where: str) -> None:
    """Walk an object tree; raise ValueError if any key matches a
    sidecar-forbidden substrate-derived field.

    Distinct from ``native_writer._assert_no_forbidden_fields`` only
    in that ``chunk_id`` is permitted in anchor rows (informational
    only; reader re-resolves). All other substrate artifacts
    (embeddings, attribution, reward proxies, auto-edges) remain
    forbidden — the master-spec invariant carries through.
    """
    if isinstance(obj, dict):
        for key in obj.keys():
            if key in _FORBIDDEN_SIDECAR_FIELDS:
                raise ValueError(
                    f"write_sidecar: forbidden substrate-derived field "
                    f"{key!r} found in {where}. Sidecars MUST NOT carry "
                    f"substrate-derived artifacts (chunks, embeddings, "
                    f"auto-edges, attribution, reward signals). The "
                    f"receiving substrate recomputes these. See SPEC.md "
                    f"§11.8 + §9."
                )
        for k, v in obj.items():
            _assert_no_forbidden_sidecar_fields(v, where=f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_no_forbidden_sidecar_fields(v, where=f"{where}[{i}]")

SIDECAR_CONTENT_CLASS: str = "pdf_sidecar"

# The empty TipTap doc carried as content.tiptap.json for sidecars.
# Held as a module-level constant so writer + reader + tests share
# one bit pattern (and the canonical_tiptap_bytes are stable).
_EMPTY_TIPTAP_DOC: dict[str, Any] = {"type": "doc", "content": []}


# ── Inputs ──


@dataclass
class HighlightRow:
    """One user highlight on the parent PDF.

    Substrate landing: this row maps to a ``behavior_events`` row of
    type ``highlight_created`` on the receiving substrate (the
    substrate has no ``highlights`` table — highlights live as events
    per ``substrate/behavior/schemas/highlight_created.json``).

    Idempotency key: ``highlight_id``. A sidecar applied twice MUST
    NOT produce two behavior_events rows; the reader deduplicates on
    this id.
    """

    highlight_id: str
    document_id: str            # the parent PDF's document_id
    page: int                    # 0-indexed
    bbox_x0: float
    bbox_y0: float
    bbox_x1: float
    bbox_y1: float
    passage_text: str | None = None
    color: str | None = None
    tag: str | None = None
    created_at: str | None = None  # ISO 8601 UTC; reader will default if absent
    operator_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "highlight_id": self.highlight_id,
            "document_id": self.document_id,
            "page": int(self.page),
            "bbox": {
                "x0": float(self.bbox_x0),
                "y0": float(self.bbox_y0),
                "x1": float(self.bbox_x1),
                "y1": float(self.bbox_y1),
            },
            "passage_text": self.passage_text,
            "color": self.color,
            "tag": self.tag,
            "created_at": self.created_at,
            "operator_note": self.operator_note,
        }


@dataclass
class AnchorRow:
    """One voice-note anchor on the parent PDF.

    Carries both coordinate (page + bbox) and the writer's resolved
    chunk_id + chunker_version. **The chunk_id is informational only
    on read** — the receiving substrate re-resolves it via
    ``substrate.voice.anchor_api.resolve_chunk_for_bbox`` against
    its own chunker (SPEC.md §11.3).

    ``transcript`` is included so the receiving substrate has the
    voice-note's text content even if the audio store can't accept
    the bytes (substrate gap from SPR-05). When audio bytes ARE
    available they ride in ``audio_blobs`` keyed on ``voice_note_id``.

    Idempotency key: ``voice_note_id`` (the SPR-02 schema enforces
    1:1 anchor per voice_note_id).
    """

    anchor_id: str
    voice_note_id: str           # the voice-note document_id
    document_id: str             # the parent PDF's document_id
    page: int
    bbox_x0: float
    bbox_y0: float
    bbox_x1: float
    bbox_y1: float
    chunker_version: str         # informational; reader does not trust
    chunk_id: str | None = None  # informational; reader re-resolves
    transcript: str | None = None
    created_at: str | None = None
    duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "anchor_id": self.anchor_id,
            "voice_note_id": self.voice_note_id,
            "document_id": self.document_id,
            "page": int(self.page),
            "bbox": {
                "x0": float(self.bbox_x0),
                "y0": float(self.bbox_y0),
                "x1": float(self.bbox_x1),
                "y1": float(self.bbox_y1),
            },
            "chunker_version": self.chunker_version,
            "chunk_id": self.chunk_id,
            "transcript": self.transcript,
            "created_at": self.created_at,
            "duration_seconds": self.duration_seconds,
        }
        # If audio rides along, we stamp the in-zip path so the reader
        # knows where to look. The actual audio_sha256 is per-file in
        # ``audio_blobs_index`` (in the manifest) — same pattern as
        # SPR-09 §3 rule 5.
        return d


@dataclass
class SidecarInput:
    """Input bundle for ``write_sidecar``.

    The substrate-touching ``gather_sidecar`` factory composes this
    from substrate rows (see ``build_sidecar_input_for_document``).
    Tests build it directly for fixtures.
    """

    # Parent PDF identity (REQUIRED) ----------------------------------
    document_id: str            # the parent PDF's document_id
    user_id: str
    parent_pdf_sha256: str      # lowercase hex, 64 chars
    parent_pdf_size_bytes: int

    # Optional identifying / display fields ---------------------------
    parent_pdf_filename_hint: str | None = None
    title: str | None = None
    created_at: datetime | None = None

    # User-derived sections -------------------------------------------
    highlights: list[HighlightRow] = field(default_factory=list)
    anchors: list[AnchorRow] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)  # same shape as native_writer
    audio_blobs: dict[str, bytes] = field(default_factory=dict)  # keyed on voice_note_id

    # Informational provenance ----------------------------------------
    chunker_version_at_write: str | None = None

    def __post_init__(self) -> None:
        # parent_pdf_sha256 is the durable handshake key with the
        # receiving substrate. Reject malformed values loudly at
        # write-time rather than producing a sidecar that's
        # silently un-applyable.
        if not isinstance(self.parent_pdf_sha256, str):
            raise ValueError("parent_pdf_sha256 must be a string")
        if len(self.parent_pdf_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.parent_pdf_sha256
        ):
            raise ValueError(
                f"parent_pdf_sha256 must be lowercase 64-hex; got "
                f"{self.parent_pdf_sha256!r}"
            )
        if self.parent_pdf_size_bytes < 0:
            raise ValueError(
                f"parent_pdf_size_bytes must be non-negative; got "
                f"{self.parent_pdf_size_bytes}"
            )


# ── Public API ──


def write_sidecar(inp: SidecarInput, *, keypair: Keypair) -> bytes:
    """Produce a ``pdf_sidecar`` ``.antiek`` archive as bytes.

    Determinism: same input + same keypair MUST yield byte-identical
    output. Tested in ``test_sidecar_e2e::test_deterministic_sidecar``.

    Refuses on:
      - Forbidden substrate-derived field names in any section
        (chunks, embeddings, attribution, reward_proxy_*, etc).
      - Audio_blobs keyed on a voice_note_id that is not in
        ``anchors``.

    Audio integrity: each audio blob's SHA-256 is stamped into
    ``manifest.audio_blobs_index`` so a tampered blob is detectable
    at read-time without expanding the top-level signing scope (SPEC
    §3 rule 5 carries over).
    """
    # Pre-flight: refuse forbidden substrate-derived fields anywhere.
    # Uses the sidecar-specific list (chunk_id permitted in anchors as
    # informational provenance; everything else still forbidden — see
    # ``_FORBIDDEN_SIDECAR_FIELDS`` docstring).
    for i, hl in enumerate(inp.highlights):
        _assert_no_forbidden_sidecar_fields(hl.to_dict(), where=f"highlights[{i}]")
    for i, an in enumerate(inp.anchors):
        _assert_no_forbidden_sidecar_fields(an.to_dict(), where=f"anchors[{i}]")
    for i, edge in enumerate(inp.edges):
        _assert_no_forbidden_sidecar_fields(edge, where=f"edges[{i}]")

    # ── Audio embedding pass ──
    # Sidecar audio is keyed on voice_note_id (not block_id, since
    # there are no notebook blocks here). The in-zip path lives under
    # ``blocks/<voice_note_id>.audio`` — same prefix as notebooks for
    # consistency with the read-side ``_block_id_from_audio_path``
    # helper.

    known_voice_ids = {an.voice_note_id for an in inp.anchors}
    audio_entries: list[tuple[str, bytes]] = []
    audio_blobs_index: list[dict[str, Any]] = []
    for voice_note_id, audio_bytes in inp.audio_blobs.items():
        if voice_note_id not in known_voice_ids:
            raise ValueError(
                f"write_sidecar: audio_blobs has voice_note_id "
                f"{voice_note_id!r} that is not in any anchor row. "
                f"Anchors are the authoritative inventory; add the "
                f"anchor first."
            )
        path = f"{BLOCKS_PREFIX}{voice_note_id}.audio"
        audio_entries.append((path, audio_bytes))
        audio_blobs_index.append({
            "voice_note_id": voice_note_id,
            "audio_path": path,
            "audio_sha256": hashlib.sha256(audio_bytes).hexdigest(),
        })
    audio_entries.sort(key=lambda kv: kv[0])
    audio_blobs_index.sort(key=lambda r: r["voice_note_id"])

    # ── Build manifest ──

    created_at_iso = (
        inp.created_at or datetime.now(UTC)
    ).astimezone(UTC).isoformat()

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "content_class": SIDECAR_CONTENT_CLASS,
        "document_id": inp.document_id,
        # parent_document_id mirrors document_id for sidecars — a
        # sidecar is its parent. Field carried for shape symmetry
        # with notebooks.
        "parent_document_id": inp.document_id,
        "created_at": created_at_iso,
        "creator_user_id": inp.user_id,
        "creator_pubkey": keypair.public_key_b64,
        "title": inp.title,
        # Sidecar-specific REQUIRED keys (SPEC.md §11.1).
        "parent_pdf_sha256": inp.parent_pdf_sha256,
        "parent_pdf_size_bytes": int(inp.parent_pdf_size_bytes),
        "parent_pdf_filename_hint": inp.parent_pdf_filename_hint,
        # Hint flags + provenance.
        "edges_present": bool(inp.edges),
        "highlights_present": bool(inp.highlights),
        "anchors_present": bool(inp.anchors),
        "chunker_version_at_write": inp.chunker_version_at_write,
        "audio_blobs_index": audio_blobs_index,
        # Sidecar has no blocks; carry [] for shape symmetry with the
        # JSON schema's optional blocks_index field.
        "blocks_index": [],
    }

    # ── Canonical bytes for signing ──

    manifest_bytes = canonical_json_bytes(manifest)
    content_bytes = canonical_json_bytes(_canonical_tiptap_node(_EMPTY_TIPTAP_DOC))
    edges_bytes = canonical_edges_bytes(inp.edges)
    highlights_bytes = _canonical_jsonl_bytes(
        [hl.to_dict() for hl in inp.highlights], key="highlight_id",
    )
    anchors_bytes = _canonical_jsonl_bytes(
        [an.to_dict() for an in inp.anchors], key="anchor_id",
    )

    signing_input = build_signing_input(
        manifest_bytes=manifest_bytes,
        content_bytes=content_bytes,
        edges_bytes=edges_bytes,
        extra_sections=[highlights_bytes, anchors_bytes],
    )
    signature = sign_bytes(keypair, signing_input)

    # ── Assemble the zip ──

    entries: list[tuple[str, bytes]] = [
        (ENTRY_MANIFEST, manifest_bytes),
        (ENTRY_CONTENT, content_bytes),
    ]
    if edges_bytes:
        entries.append((ENTRY_EDGES, edges_bytes))
    if highlights_bytes:
        entries.append((ENTRY_HIGHLIGHTS, highlights_bytes))
    if anchors_bytes:
        entries.append((ENTRY_ANCHORS, anchors_bytes))
    entries.extend(audio_entries)
    entries.append((ENTRY_SIGNATURE, signature))

    return _build_deterministic_zip(entries)


# ── Substrate gather helper ──


def build_sidecar_input_for_document(
    *,
    document_id: str,
    user_id: str,
    parent_pdf_bytes: bytes,
    parent_pdf_filename_hint: str | None = None,
    title: str | None = None,
    db_path: str | None = None,
) -> SidecarInput:
    """Compose a ``SidecarInput`` by reading user-derived rows from the
    substrate for ``(user_id, document_id)``.

    What gets pulled:
      - All ``behavior_events`` rows where ``event_type='highlight_created'``
        and ``document_id`` matches; the row's ``action`` JSON yields
        passage_text + bbox (if a bbox is recorded; the SPR-01 schema
        keeps it in start_offset/end_offset today + the handoff flags
        this — we surface what's recorded).
      - All ``voice_note_anchor`` rows where ``document_id`` matches,
        joined to the voice-note row in ``documents``.
      - User-asserted edges: substrate has no user-edges table today
        (SPR-09 handoff flagged this); the field is left empty and the
        UI is the source until a substrate table lands.
      - Audio blobs: SPR-05/SPR-09 substrate gap — the audio bytes
        store doesn't exist yet. We pass-through any voice-note row
        carrying ``content_json.audio_blob_path`` or
        ``content_json.audio_bytes_b64`` (same hint shape as
        ``AntiekPersistence._resolve_audio_blob``); else skip.

    This function does NOT raise on a partial substrate. Missing
    tables / empty rowsets simply produce a sparse SidecarInput.

    Parameters
    ----------
    parent_pdf_bytes : bytes
        The PDF bytes — the caller fetches these (typically from the
        ingestion fetcher cache or by re-reading the original upload).
        We hash here so the SidecarInput is self-contained.

    Returns
    -------
    SidecarInput
        Ready to pass into ``write_sidecar``.
    """
    try:
        from substrate.voice import CHUNKER_VERSION
    except ImportError:  # pragma: no cover — module always present in tree
        CHUNKER_VERSION = "v1.0.0"

    parent_sha256 = hashlib.sha256(parent_pdf_bytes).hexdigest()
    parent_size = len(parent_pdf_bytes)

    highlights = _gather_highlights(document_id=document_id, db_path=db_path)
    anchors, audio_blobs = _gather_anchors_and_audio(
        document_id=document_id, db_path=db_path,
    )
    # User-asserted edges: substrate has no user-edges table; left
    # empty. The UI surface (Sprint 22+) lands the table; until then
    # any edges in the sidecar come from the caller passing them
    # in directly via ``SidecarInput.edges`` after this gather.
    edges: list[dict] = []

    return SidecarInput(
        document_id=document_id,
        user_id=user_id,
        parent_pdf_sha256=parent_sha256,
        parent_pdf_size_bytes=parent_size,
        parent_pdf_filename_hint=parent_pdf_filename_hint,
        title=title,
        highlights=highlights,
        anchors=anchors,
        edges=edges,
        audio_blobs=audio_blobs,
        chunker_version_at_write=CHUNKER_VERSION,
    )


def _gather_highlights(
    *, document_id: str, db_path: str | None,
) -> list[HighlightRow]:
    """Pull highlight rows from ``behavior_events`` for one document.

    The substrate stores highlights as events (no `highlights` table);
    we project the event's action JSON into a HighlightRow.

    The bbox is read from action.bbox when present. The SPR-01 schema
    encodes only start_offset/end_offset (text-layer character offsets),
    not PDF coordinates — when the UI lands a bbox-aware highlight flow,
    extending the schema with a bbox field will populate this; today
    we accept either shape (bbox object) or fall back to a zero-area
    bbox that the reader can detect.
    """
    if db_path is None:
        return []
    if not os.path.exists(db_path):
        return []

    import duckdb
    try:
        con = duckdb.connect(db_path)
    except Exception:
        return []
    try:
        # Tolerate missing table (test DBs may not have applied SPR-01).
        try:
            rows = con.execute(
                "SELECT event_id, action, timestamp_utc "
                "FROM behavior_events "
                "WHERE event_type = 'highlight_created' "
                "  AND document_id = ? "
                "ORDER BY timestamp_utc ASC, event_id ASC",
                [document_id],
            ).fetchall()
        except duckdb.CatalogException:
            return []
    finally:
        con.close()

    out: list[HighlightRow] = []
    for row in rows:
        event_id, action_json, ts = row
        try:
            action = json.loads(action_json) if isinstance(action_json, str) else (action_json or {})
        except json.JSONDecodeError:
            continue
        highlight_id = action.get("highlight_id") or f"hl-from-{event_id}"
        bbox = action.get("bbox")
        # 2026-05-22: the schema now allows bbox as either a 4-tuple
        # array [x0, y0, x1, y1] (PdfViewer emits this form) OR a
        # dict {x0, y0, x1, y1} (legacy / SPR-10 internal form). Accept
        # both shapes; serialize as the dict form into the sidecar.
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            try:
                x0, y0, x1, y1 = (float(v) for v in bbox)
            except (TypeError, ValueError):
                x0 = y0 = x1 = y1 = 0.0
        elif isinstance(bbox, dict):
            x0 = float(bbox.get("x0", 0.0))
            y0 = float(bbox.get("y0", 0.0))
            x1 = float(bbox.get("x1", 0.0))
            y1 = float(bbox.get("y1", 0.0))
        else:
            # No coordinate recorded — preserve the highlight as
            # zero-bbox so the reader can still restore the passage_text
            # + tag. The reader treats a zero-area bbox as "passage-only,
            # no coordinate", which is honest about what we can re-anchor.
            x0 = y0 = x1 = y1 = 0.0
        page = int(action.get("page", 0))
        out.append(HighlightRow(
            highlight_id=highlight_id,
            document_id=document_id,
            page=page,
            bbox_x0=x0, bbox_y0=y0, bbox_x1=x1, bbox_y1=y1,
            passage_text=action.get("passage_text"),
            color=action.get("color"),
            tag=action.get("tag"),
            created_at=_iso(ts),
            operator_note=action.get("operator_note"),
        ))
    return out


def _gather_anchors_and_audio(
    *, document_id: str, db_path: str | None,
) -> tuple[list[AnchorRow], dict[str, bytes]]:
    """Pull voice_note_anchor rows + any reachable audio.

    The audio gap (SPR-05): substrate stores transcripts via Sprint 13
    ASR but no audio bytes today. We accept the same hints
    ``AntiekPersistence._resolve_audio_blob`` does (audio_blob_path /
    audio_bytes_b64 in the voice-note row's content_json metadata).
    Until a real audio store lands, ``audio_blobs`` will typically be
    empty — flagged in the SPR-10 handoff.
    """
    if db_path is None:
        return [], {}
    if not os.path.exists(db_path):
        return [], {}

    import base64

    import duckdb
    try:
        con = duckdb.connect(db_path)
    except Exception:
        return [], {}
    anchors: list[AnchorRow] = []
    audio_blobs: dict[str, bytes] = {}
    try:
        try:
            rows = con.execute(
                "SELECT anchor_id, voice_note_id, page, bbox, "
                "       chunk_id, chunker_version, created_at "
                "FROM voice_note_anchor "
                "WHERE document_id = ? "
                "ORDER BY created_at ASC, anchor_id ASC",
                [document_id],
            ).fetchall()
        except duckdb.CatalogException:
            return [], {}

        for r in rows:
            (anchor_id, voice_note_id, page, bbox_json,
             chunk_id, chunker_version, created_at) = r
            try:
                bbox = json.loads(bbox_json) if isinstance(bbox_json, str) else (bbox_json or {})
            except json.JSONDecodeError:
                continue
            transcript: str | None = None
            audio_bytes: bytes | None = None
            duration: float | None = None
            # Look up the voice-note row for transcript + audio hints.
            try:
                vn_row = con.execute(
                    "SELECT raw_text, metadata FROM documents "
                    "WHERE document_id = ?",
                    [voice_note_id],
                ).fetchone()
            except duckdb.CatalogException:
                vn_row = None
            if vn_row is not None:
                raw_text, metadata = vn_row
                if isinstance(raw_text, str):
                    transcript = raw_text
                if isinstance(metadata, str):
                    try:
                        meta = json.loads(metadata)
                    except json.JSONDecodeError:
                        meta = {}
                else:
                    meta = metadata or {}
                if isinstance(meta, dict):
                    duration = meta.get("duration_seconds") if isinstance(meta.get("duration_seconds"), (int, float)) else None
                    b64 = meta.get("audio_bytes_b64")
                    if isinstance(b64, str) and b64:
                        try:
                            audio_bytes = base64.b64decode(b64, validate=True)
                        except (ValueError, base64.binascii.Error):
                            audio_bytes = None
                    if audio_bytes is None:
                        path = meta.get("audio_blob_path")
                        if isinstance(path, str) and path and os.path.exists(path):
                            try:
                                with open(path, "rb") as f:
                                    audio_bytes = f.read()
                            except OSError:
                                audio_bytes = None

            anchors.append(AnchorRow(
                anchor_id=anchor_id,
                voice_note_id=voice_note_id,
                document_id=document_id,
                page=int(page),
                bbox_x0=float(bbox.get("x0", 0.0)),
                bbox_y0=float(bbox.get("y0", 0.0)),
                bbox_x1=float(bbox.get("x1", 0.0)),
                bbox_y1=float(bbox.get("y1", 0.0)),
                chunk_id=chunk_id,
                chunker_version=chunker_version or "v0.0.0",
                transcript=transcript,
                duration_seconds=float(duration) if duration is not None else None,
                created_at=_iso(created_at),
            ))
            if audio_bytes is not None:
                audio_blobs[voice_note_id] = audio_bytes
    finally:
        con.close()
    return anchors, audio_blobs


# ── Canonical bytes helpers ──


def _canonical_jsonl_bytes(rows: list[dict[str, Any]], *, key: str) -> bytes:
    """Canonical sidecar-jsonl: one sorted-key JSON per line, lines
    sorted by ``key``, LF newlines, trailing newline.

    Empty rows → empty bytes (``b""``). The 0x1F separator before
    the section is still emitted by ``build_signing_input`` so the
    absence-of-section state is signed.
    """
    if not rows:
        return b""
    sorted_rows = sorted(rows, key=lambda r: r[key])
    lines = [
        json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for r in sorted_rows
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _iso(ts: Any) -> str | None:
    """Render a datetime (or anything stringifiable) as ISO 8601 UTC."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts.astimezone(UTC).isoformat()
    return str(ts)


__all__ = [
    "AnchorRow",
    "ENTRY_ANCHORS",
    "ENTRY_HIGHLIGHTS",
    "HighlightRow",
    "SIDECAR_CONTENT_CLASS",
    "SidecarInput",
    "build_sidecar_input_for_document",
    "write_sidecar",
]
