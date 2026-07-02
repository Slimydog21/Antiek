"""Sidecar reader: .antiek bytes → restored substrate state.

SPR-10 / M3. Inverse of ``sidecar_writer.write_sidecar``.

Two-phase API
-------------
1. ``read_sidecar(data, imported_pdf_sha256=...) -> RestoredSidecar``
   — parses + validates + verifies signature. Surfaces hash-mismatch
   as a flag, NOT as a hard exception (the caller decides whether to
   surface as a warning or block apply).
2. ``apply_sidecar(restored, db_path=..., user_id=...) -> ApplyReport``
   — writes the restored rows into the substrate inside a single
   ``connect_write`` lock. Idempotent on every row type's natural key.

Why two-phase
-------------
The hash-mismatch UX (rigor #1) needs an honest "we read it; we did
NOT apply it" intermediate state the caller can render. The
substrate write is the dangerous step — keeping it explicit lets the
UI ask the user before applying a mismatched sidecar (out-of-scope
for SPR-10, but the surface is in place).

Re-resolving chunk_ids (rigor #3)
---------------------------------
The writer's ``chunker_version`` on each anchor is informational
only. ``apply_sidecar`` calls
``substrate.voice.anchor_api.resolve_chunk_for_bbox`` against the
receiving substrate's chunker for every anchor; the writer's
chunk_id is discarded. See SPEC.md §11.3.

Signature-invalid restore (rigor #5)
------------------------------------
When ``signature_valid=False`` (tampered, or signer pubkey is
unknown), ``apply_sidecar`` still writes the rows but flags each
inserted row's metadata with ``imported_from_unsigned_sidecar=true``.
The rationale: a friend's sidecar carries a pubkey this user has
never seen. Refusing imports would break the "share with annotations"
flow that motivates sidecars. Future hardening (per-key trust
decisions) replaces the flag with a richer signal; the rows
themselves are preserved with an audit trail.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import uuid
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

try:
    from .native_reader import (
        AntiekFormatError,
        MalformedAntiek,
        _check_version_policy,
        _validate_manifest,
    )
    from .native_writer import (
        BLOCKS_PREFIX,
        ENTRY_CONTENT,
        ENTRY_EDGES,
        ENTRY_MANIFEST,
        ENTRY_SIGNATURE,
        _canonical_tiptap_node,
    )
    from .sidecar_writer import (
        ENTRY_ANCHORS,
        ENTRY_HIGHLIGHTS,
        SIDECAR_CONTENT_CLASS,
    )
    from .signature import (
        build_signing_input,
        canonical_edges_bytes,
        canonical_json_bytes,
        verify_bytes,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from services.antiek_format.native_reader import (  # type: ignore[no-redef]
        AntiekFormatError,
        MalformedAntiek,
        _check_version_policy,
        _validate_manifest,
    )
    from services.antiek_format.native_writer import (  # type: ignore[no-redef]
        BLOCKS_PREFIX,
        ENTRY_CONTENT,
        ENTRY_EDGES,
        ENTRY_MANIFEST,
        ENTRY_SIGNATURE,
        _canonical_tiptap_node,
    )
    from services.antiek_format.sidecar_writer import (  # type: ignore[no-redef]
        ENTRY_ANCHORS,
        ENTRY_HIGHLIGHTS,
        SIDECAR_CONTENT_CLASS,
    )
    from services.antiek_format.signature import (  # type: ignore[no-redef]
        build_signing_input,
        canonical_edges_bytes,
        canonical_json_bytes,
        verify_bytes,
    )


_log = logging.getLogger(__name__)


# ── Errors ──


class SidecarHashMismatch(AntiekFormatError):
    """The sidecar's parent_pdf_sha256 does not match the
    caller-provided imported PDF hash. Raised only by
    ``read_sidecar(..., strict=True)``; the default (non-strict)
    surfaces this as ``RestoredSidecar.hash_mismatch`` instead so
    the UI can render the warning."""


class NotASidecar(AntiekFormatError):
    """The ``.antiek`` bytes are valid but ``content_class`` is not
    ``pdf_sidecar``. Use ``read_antiek`` for notebook variants."""


class MissingSidecarFields(AntiekFormatError):
    """A sidecar manifest is missing one of the SPR-10 required
    keys (parent_pdf_sha256, parent_pdf_size_bytes). Per the M1
    acceptance criterion, the reader refuses with this error rather
    than silently proceeding."""


# ── Output dataclasses ──


@dataclass
class RestoredSidecar:
    """The parsed state of a sidecar before substrate apply.

    The reader returns this; the caller decides whether to call
    ``apply_sidecar``. ``hash_mismatch=True`` is the gate per M3
    acceptance: a sidecar built for a different PDF revision must
    NOT silently apply.
    """

    document_id: str
    parent_pdf_sha256: str
    parent_pdf_size_bytes: int
    parent_pdf_filename_hint: str | None
    creator_user_id: str
    creator_pubkey: str
    title: str | None
    created_at: str
    chunker_version_at_write: str | None

    highlights: list[dict] = field(default_factory=list)
    anchors: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    # voice_note_id → audio bytes (extracted, integrity-checked)
    audio_blobs: dict[str, bytes] = field(default_factory=dict)

    signature_valid: bool = False
    hash_mismatch: bool = False
    # Raw values used by the apply step + the UX warning.
    imported_pdf_sha256: str | None = None
    manifest_unknown_keys: dict = field(default_factory=dict)


@dataclass
class ApplyReport:
    """What ``apply_sidecar`` wrote to the substrate."""

    highlights_written: int = 0
    highlights_skipped_existing: int = 0
    anchors_written: int = 0
    anchors_skipped_existing: int = 0
    edges_written: int = 0
    edges_skipped_existing: int = 0
    audio_blobs_written: int = 0
    chunker_re_resolved: int = 0
    unsigned_flag_applied: bool = False
    warnings: list[str] = field(default_factory=list)


# ── Public API: read ──


def read_sidecar(
    data: bytes,
    *,
    imported_pdf_sha256: str | None = None,
    strict: bool = False,
) -> RestoredSidecar:
    """Parse + validate + verify a sidecar's bytes.

    Parameters
    ----------
    data : bytes
        The full ``.antiek`` archive.
    imported_pdf_sha256 : str | None
        SHA-256 of the PDF that the caller wants the sidecar applied
        to. When supplied and the sidecar's ``parent_pdf_sha256``
        differs, ``hash_mismatch`` is set True (or raised on strict).
        When ``None``, no hash check fires — the caller is just
        inspecting the sidecar (e.g., for a UI preview).
    strict : bool
        When True, ``hash_mismatch=True`` raises ``SidecarHashMismatch``
        instead of returning. Default False — callers render the
        warning UX.

    Raises
    ------
    NotASidecar
        ``content_class`` is not ``pdf_sidecar``.
    MissingSidecarFields
        Required sidecar fields are missing.
    MalformedAntiek, ManifestValidationError, UnsupportedVersion
        Re-raised from native_reader validation.
    SidecarHashMismatch
        Only when strict=True.
    """
    try:
        zf = zipfile.ZipFile(BytesIO(data), mode="r")
    except zipfile.BadZipFile as e:
        raise MalformedAntiek(f"not a zip file: {e}") from e

    with zf:
        names = set(zf.namelist())
        for required in (ENTRY_MANIFEST, ENTRY_CONTENT, ENTRY_SIGNATURE):
            if required not in names:
                raise MalformedAntiek(
                    f"required entry {required!r} missing from sidecar "
                    f"(found: {sorted(names)})"
                )

        manifest_bytes = zf.read(ENTRY_MANIFEST)
        content_bytes = zf.read(ENTRY_CONTENT)
        edges_bytes = zf.read(ENTRY_EDGES) if ENTRY_EDGES in names else b""
        highlights_bytes = zf.read(ENTRY_HIGHLIGHTS) if ENTRY_HIGHLIGHTS in names else b""
        anchors_bytes = zf.read(ENTRY_ANCHORS) if ENTRY_ANCHORS in names else b""
        signature_bytes = zf.read(ENTRY_SIGNATURE)

        audio_blobs: dict[str, bytes] = {}
        for n in sorted(names):
            if n.startswith(BLOCKS_PREFIX) and n.endswith(".audio"):
                voice_note_id = n[len(BLOCKS_PREFIX):-len(".audio")]
                audio_blobs[voice_note_id] = zf.read(n)

    # ── Parse + validate manifest ──

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise MalformedAntiek(f"manifest.json is not UTF-8 JSON: {e}") from e

    _validate_manifest(manifest)
    _check_version_policy(manifest["schema_version"])

    if manifest.get("content_class") != SIDECAR_CONTENT_CLASS:
        raise NotASidecar(
            f"read_sidecar: content_class is "
            f"{manifest.get('content_class')!r}, not {SIDECAR_CONTENT_CLASS!r}. "
            f"Use services.antiek_format.read_antiek for notebook variants."
        )

    # SPR-10 required sidecar fields. The JSON schema marks these as
    # optional at the manifest level (since the same schema handles
    # both content classes); the sidecar reader enforces them. This
    # is the M1 "refuses with clear error" path.
    if not manifest.get("parent_pdf_sha256"):
        raise MissingSidecarFields(
            "sidecar manifest is missing required field 'parent_pdf_sha256'. "
            "Cannot verify which PDF this sidecar belongs to."
        )
    if "parent_pdf_size_bytes" not in manifest or manifest["parent_pdf_size_bytes"] is None:
        raise MissingSidecarFields(
            "sidecar manifest is missing required field 'parent_pdf_size_bytes'."
        )

    # ── Parse sections ──

    highlights = _parse_jsonl(highlights_bytes, where="highlights.jsonl")
    anchors = _parse_jsonl(anchors_bytes, where="anchors.jsonl")
    edges: list[dict] = []
    if edges_bytes:
        for i, line in enumerate(edges_bytes.decode("utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                edges.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise MalformedAntiek(
                    f"edges.jsonl line {i + 1}: {e}"
                ) from e

    # ── Verify signature ──
    #
    # Recompute canonical bytes from parsed objects (belt + braces).

    try:
        content_tiptap = json.loads(content_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise MalformedAntiek(f"content.tiptap.json: {e}") from e

    canon_manifest = canonical_json_bytes(manifest)
    canon_content = canonical_json_bytes(_canonical_tiptap_node(content_tiptap))
    canon_edges = canonical_edges_bytes(edges)
    canon_highlights = _canonical_jsonl_bytes_from_parsed(
        highlights, key="highlight_id",
    )
    canon_anchors = _canonical_jsonl_bytes_from_parsed(
        anchors, key="anchor_id",
    )

    signing_input = build_signing_input(
        manifest_bytes=canon_manifest,
        content_bytes=canon_content,
        edges_bytes=canon_edges,
        extra_sections=[canon_highlights, canon_anchors],
    )
    signature_valid = verify_bytes(
        creator_pubkey_b64=manifest["creator_pubkey"],
        signing_input=signing_input,
        signature=signature_bytes,
    )

    # ── Per-audio integrity ──
    # Same pattern as native_reader: per-blob SHA-256 inside the
    # signed manifest. Tampered audio → that blob is treated as
    # tampered, signature_valid drops, but the rest restores.
    audio_index = manifest.get("audio_blobs_index") or []
    if isinstance(audio_index, list):
        for entry in audio_index:
            if not isinstance(entry, dict):
                continue
            expected = entry.get("audio_sha256")
            voice_note_id = entry.get("voice_note_id")
            if not (expected and voice_note_id):
                continue
            blob = audio_blobs.get(voice_note_id)
            if blob is None:
                signature_valid = False
                _log.warning(
                    "read_sidecar: manifest references audio for voice "
                    "note %r but no blob in archive; treating as tampered.",
                    voice_note_id,
                )
                continue
            actual = hashlib.sha256(blob).hexdigest()
            if actual != expected:
                signature_valid = False
                _log.warning(
                    "read_sidecar: audio for voice note %r SHA-256 "
                    "mismatch (expected %s, got %s).",
                    voice_note_id, expected, actual,
                )

    # ── Hash gate against imported PDF ──

    hash_mismatch = False
    if imported_pdf_sha256 is not None:
        # Compare lowercase hex.
        wanted = imported_pdf_sha256.lower()
        got = manifest["parent_pdf_sha256"].lower()
        hash_mismatch = wanted != got
        if hash_mismatch and strict:
            raise SidecarHashMismatch(
                f"sidecar parent_pdf_sha256 ({got!r}) does not match "
                f"imported PDF sha256 ({wanted!r}). The sidecar was made "
                f"for a different PDF; restoring would place annotations "
                f"at coordinates from the original PDF; on this PDF they "
                f"may land on the wrong text. The sidecar was NOT applied."
            )

    # ── Surface unknown manifest keys ──
    known_top = {
        "schema_version", "content_class", "document_id", "parent_document_id",
        "created_at", "creator_user_id", "creator_pubkey",
        "title", "notebook_id", "format_version", "edges_present",
        "blocks_index", "parent_pdf_sha256", "parent_pdf_size_bytes",
        "parent_pdf_filename_hint", "highlights_present", "anchors_present",
        "chunker_version_at_write", "audio_blobs_index",
    }
    unknown = {k: v for k, v in manifest.items() if k not in known_top}

    return RestoredSidecar(
        document_id=manifest["document_id"],
        parent_pdf_sha256=manifest["parent_pdf_sha256"],
        parent_pdf_size_bytes=int(manifest["parent_pdf_size_bytes"]),
        parent_pdf_filename_hint=manifest.get("parent_pdf_filename_hint"),
        creator_user_id=manifest["creator_user_id"],
        creator_pubkey=manifest["creator_pubkey"],
        title=manifest.get("title"),
        created_at=manifest["created_at"],
        chunker_version_at_write=manifest.get("chunker_version_at_write"),
        highlights=highlights,
        anchors=anchors,
        edges=edges,
        audio_blobs=audio_blobs,
        signature_valid=signature_valid,
        hash_mismatch=hash_mismatch,
        imported_pdf_sha256=imported_pdf_sha256,
        manifest_unknown_keys=unknown,
    )


# ── Public API: hash-mismatch UX copy ──


HASH_MISMATCH_WARNING: str = (
    "This .antiek sidecar was made for a different version of the PDF "
    "you imported (file hash differs). Restoring would place annotations "
    "at coordinates from the original PDF; on this PDF they may land on "
    "the wrong text. The sidecar was NOT applied."
)
"""The exact text the UI surfaces when ``RestoredSidecar.hash_mismatch``
is True. Exported as a constant so the API + UI + tests use one
string. Rigor #1: the copy must be honest about what failed and what
the user should expect. Do not soften without updating the doc / test."""


# ── Public API: apply ──


def apply_sidecar(
    restored: RestoredSidecar,
    *,
    db_path: str,
    user_id: str,
    audio_storage_root: str | None = None,
    investigation_id: str = "__operator__",
) -> ApplyReport:
    """Write restored rows into the substrate. Idempotent.

    Refuses (raises ValueError) if ``restored.hash_mismatch`` is True
    — the caller MUST acknowledge the mismatch before applying. This
    is the M3 + M4 enforcement: a mismatched sidecar surfaces in UI as
    a warning but is NOT silently applied.

    Re-resolves each anchor's chunk_id under the receiving substrate's
    chunker (rigor #3). The writer's chunk_id is discarded.

    When ``restored.signature_valid`` is False, every inserted row's
    metadata is flagged ``imported_from_unsigned_sidecar=true`` (rigor
    #5). The flag is part of the row content, not a separate column,
    so the audit trail survives row migrations.
    """
    if restored.hash_mismatch:
        raise ValueError(
            "apply_sidecar: refusing to apply a hash-mismatched sidecar. "
            f"{HASH_MISMATCH_WARNING}"
        )

    # Lazy imports: keep substrate dependencies out of the
    # read-side hot path. Tests can read sidecars without a substrate
    # DB; apply requires one.
    try:
        from substrate.voice import CHUNKER_VERSION
        from substrate.voice.anchor_api import BBox, resolve_chunk_for_bbox

        from runtime.db_lock import connect_write
    except ImportError:  # pragma: no cover
        _repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if _repo not in sys.path:
            sys.path.insert(0, _repo)
        from substrate.voice import CHUNKER_VERSION  # type: ignore
        from substrate.voice.anchor_api import BBox, resolve_chunk_for_bbox  # type: ignore

        from runtime.db_lock import connect_write  # type: ignore

    report = ApplyReport()
    unsigned = not restored.signature_valid
    report.unsigned_flag_applied = unsigned
    if unsigned:
        report.warnings.append(
            "sidecar signature did not verify; rows are flagged "
            "imported_from_unsigned_sidecar=true (SPEC.md §11.6)."
        )

    # ── Audio extraction (file-level; idempotent on path) ──
    storage = audio_storage_root or _default_audio_storage_root()
    os.makedirs(storage, exist_ok=True)
    for voice_note_id, blob in restored.audio_blobs.items():
        target = os.path.join(storage, f"{voice_note_id}.audio")
        if os.path.exists(target):
            # Re-import — keep the existing file. The per-blob hash
            # check already happened in read_sidecar; if hashes matched
            # then the existing file is the same content.
            continue
        tmp = target + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, target)
        report.audio_blobs_written += 1

    # ── Substrate writes (one connect_write context) ──
    con = connect_write(db_path, purpose="sidecar_apply")
    try:
        # Highlights → behavior_events (idempotent on highlight_id).
        for hl in restored.highlights:
            wrote = _apply_one_highlight(
                con=con, hl=hl, user_id=user_id,
                investigation_id=investigation_id,
                document_id=restored.document_id,
                unsigned=unsigned,
            )
            if wrote:
                report.highlights_written += 1
            else:
                report.highlights_skipped_existing += 1

        # Voice notes + anchors (idempotent on voice_note_id).
        for an in restored.anchors:
            wrote = _apply_one_anchor(
                con=con, an=an, user_id=user_id,
                document_id=restored.document_id,
                unsigned=unsigned,
                resolve_chunk_for_bbox=resolve_chunk_for_bbox,
                bbox_cls=BBox,
                local_chunker_version=CHUNKER_VERSION,
                report=report,
                audio_storage_root=storage,
            )
            if wrote:
                report.anchors_written += 1
            else:
                report.anchors_skipped_existing += 1

        # User-asserted edges. Substrate has no user-edges table yet;
        # we record into a sidecar-import-trail table that's safe to
        # rebuild later (idempotent on (sidecar_id, edge_id) — but we
        # don't have a sidecar_id, so we key on edge_id alone since
        # the spec's edge_id is intended as the authoritative key).
        for edge in restored.edges:
            wrote = _apply_one_edge(
                con=con, edge=edge, user_id=user_id, unsigned=unsigned,
            )
            if wrote:
                report.edges_written += 1
            else:
                report.edges_skipped_existing += 1

    finally:
        con.close()

    return report


# ── Internals: row-by-row apply ──


def _apply_one_highlight(
    *,
    con: Any,
    hl: dict,
    user_id: str,
    investigation_id: str,
    document_id: str,
    unsigned: bool,
) -> bool:
    """Write one highlight as a behavior_events row of type
    'highlight_created'. Idempotent on highlight_id (carried in the
    event's action JSON).

    Returns True if a new row was written; False if a row with this
    highlight_id already exists.
    """
    highlight_id = hl.get("highlight_id")
    if not highlight_id:
        return False

    # Idempotency check: is there already a behavior_events row
    # carrying this highlight_id in its action JSON? We use a LIKE
    # match because the action is a JSON-encoded TEXT column; a real
    # JSON-path query would need DuckDB's json functions, but LIKE on
    # the exact key:value substring works given canonical JSON keys.
    try:
        marker = f'"highlight_id":"{highlight_id}"'
        existing = con.execute(
            "SELECT event_id FROM behavior_events "
            "WHERE event_type = 'highlight_created' "
            "  AND document_id = ? "
            "  AND action LIKE ? "
            "LIMIT 1",
            [document_id, f"%{marker}%"],
        ).fetchone()
    except Exception as e:
        # If behavior_events doesn't exist (test fixtures without
        # SPR-01 schema), skip writes silently rather than crashing
        # the whole apply.
        _log.warning("apply_sidecar: behavior_events probe failed: %s", e)
        return False
    if existing is not None:
        return False

    # Build the event row. The behavior_events schema (SPR-01) requires
    # event_id + user_id + session_id + event_type + state + action +
    # consent_version. We mint a session_id per import session.
    event_id = f"evt-sidecar-{uuid.uuid4().hex[:12]}"
    session_id = "sidecar-import"  # per-import session; future: thread one through

    state = {
        "document_id": document_id,
        "reading_mode": "sidecar_restore",
        "scroll_depth_pct": None,
        "chunk_id": None,
        "session_elapsed_s": None,
    }
    action = dict(hl)  # carry the sidecar row verbatim
    # Sidecar-provenance flags ride inside the action JSON so the
    # audit trail survives normalisation passes.
    action["imported_from_sidecar"] = True
    if unsigned:
        action["imported_from_unsigned_sidecar"] = True

    try:
        con.execute(
            "INSERT INTO behavior_events "
            "(event_id, user_id, session_id, document_id, "
            " event_type, state, action, consent_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                event_id, user_id, session_id, document_id,
                "highlight_created",
                # Compact form so the idempotency LIKE-marker
                # below matches exactly (no insignificant whitespace).
                json.dumps(state, sort_keys=True, separators=(",", ":")),
                json.dumps(action, sort_keys=True, separators=(",", ":")),
                1,  # consent_version 1; the consent surface lands per-user later
            ],
        )
    except Exception as e:
        _log.warning("apply_sidecar: failed to insert highlight row: %s", e)
        return False
    return True


def _apply_one_anchor(
    *,
    con: Any,
    an: dict,
    user_id: str,
    document_id: str,
    unsigned: bool,
    resolve_chunk_for_bbox: Any,
    bbox_cls: Any,
    local_chunker_version: str,
    report: ApplyReport,
    audio_storage_root: str,
) -> bool:
    """Write voice-note document + voice_note_anchor row. Idempotent
    on voice_note_id (anchor schema's UNIQUE constraint).

    Re-resolves chunk_id under the receiving substrate's chunker
    (rigor #3). The writer's chunk_id is informational only.
    """
    voice_note_id = an.get("voice_note_id")
    anchor_id = an.get("anchor_id") or f"vna-{uuid.uuid4().hex[:16]}"
    if not voice_note_id:
        return False

    # Check anchor existence first (UNIQUE on voice_note_id).
    try:
        existing = con.execute(
            "SELECT anchor_id FROM voice_note_anchor "
            "WHERE voice_note_id = ?",
            [voice_note_id],
        ).fetchone()
    except Exception as e:
        _log.warning("apply_sidecar: voice_note_anchor probe failed: %s", e)
        return False
    if existing is not None:
        return False

    # Ensure the voice-note document exists. The SPR-02 schema FKs the
    # anchor row to documents(document_id) via voice_note_id, so we
    # write a documents row if absent.
    try:
        doc_exists = con.execute(
            "SELECT document_id FROM documents WHERE document_id = ?",
            [voice_note_id],
        ).fetchone()
    except Exception as e:
        _log.warning("apply_sidecar: documents probe failed: %s", e)
        return False

    if doc_exists is None:
        meta = {
            "imported_from_sidecar": True,
            "imported_from_unsigned_sidecar": unsigned,
            "duration_seconds": an.get("duration_seconds"),
            "transcript": an.get("transcript"),
            "audio_blob_path": os.path.join(
                audio_storage_root, f"{voice_note_id}.audio",
            ) if an.get("audio_path") else None,
        }
        try:
            con.execute(
                "INSERT INTO documents "
                "(document_id, source_tier, document_type, source_uri, "
                " title, author, published_at, investigation_id, "
                " raw_text, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    voice_note_id, 2, "voice_note", None,
                    None, None, None, "__operator__",
                    an.get("transcript") or "",
                    json.dumps(meta, sort_keys=True),
                ],
            )
        except Exception as e:
            _log.warning(
                "apply_sidecar: failed to insert voice-note document "
                "row for %r: %s", voice_note_id, e,
            )
            return False

    # ── Re-resolve chunk_id under the receiving substrate's chunker
    # (rigor #3). The writer's chunk_id is informational only.

    bbox_dict = an.get("bbox") or {}
    try:
        bbox = bbox_cls(
            x0=float(bbox_dict.get("x0", 0.0)),
            y0=float(bbox_dict.get("y0", 0.0)),
            x1=float(bbox_dict.get("x1", 0.0)),
            y1=float(bbox_dict.get("y1", 0.0)),
        )
    except ValueError as e:
        # Zero-area bbox (from a no-coordinate highlight). Skip
        # the anchor row; we have nothing to land it on.
        _log.warning("apply_sidecar: degenerate bbox in anchor: %s", e)
        return False

    re_resolved = resolve_chunk_for_bbox(
        con,
        document_id=document_id,
        page=int(an.get("page", 0)),
        bbox=bbox,
    )
    report.chunker_re_resolved += 1
    writer_chunker = an.get("chunker_version")
    if writer_chunker and writer_chunker != local_chunker_version:
        report.warnings.append(
            f"anchor {anchor_id} written under chunker {writer_chunker!r}; "
            f"receiving substrate is on {local_chunker_version!r}. "
            f"chunk_id re-resolved locally; coordinates unchanged."
        )

    try:
        con.execute(
            "INSERT INTO voice_note_anchor "
            "(anchor_id, voice_note_id, document_id, page, bbox, "
            " chunk_id, chunker_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                anchor_id, voice_note_id, document_id,
                int(an.get("page", 0)),
                json.dumps(bbox_dict, sort_keys=True),
                re_resolved,
                local_chunker_version,
            ],
        )
    except Exception as e:
        _log.warning("apply_sidecar: voice_note_anchor insert failed: %s", e)
        return False
    return True


def _apply_one_edge(
    *,
    con: Any,
    edge: dict,
    user_id: str,
    unsigned: bool,
) -> bool:
    """Write one user-asserted edge into a sidecar import trail.

    Substrate today has no user-asserted-edges table. We persist into
    a ``sidecar_user_edges`` table (created on demand) so the rows
    are recoverable when a real edges surface lands. Idempotent on
    edge_id.
    """
    edge_id = edge.get("edge_id")
    if not edge_id:
        return False

    # Create-on-demand table. Same migration discipline as the
    # keypair table in signature.py.
    try:
        con.execute(_SIDECAR_USER_EDGES_DDL)
    except Exception as e:
        _log.warning(
            "apply_sidecar: failed to create sidecar_user_edges: %s", e,
        )
        return False

    existing = con.execute(
        "SELECT edge_id FROM sidecar_user_edges WHERE edge_id = ?",
        [edge_id],
    ).fetchone()
    if existing is not None:
        return False

    payload = dict(edge)
    payload["imported_from_sidecar"] = True
    if unsigned:
        payload["imported_from_unsigned_sidecar"] = True

    try:
        con.execute(
            "INSERT INTO sidecar_user_edges "
            "(edge_id, from_block_id, to_content_hash, to_document_id, "
            " kind, asserted_at, operator_note, imported_by_user_id, "
            " imported_unsigned, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                edge_id,
                edge.get("from_block_id"),
                edge.get("to_content_hash"),
                edge.get("to_document_id"),
                edge.get("kind"),
                edge.get("asserted_at"),
                edge.get("operator_note"),
                user_id,
                bool(unsigned),
                json.dumps(payload, sort_keys=True),
            ],
        )
    except Exception as e:
        _log.warning("apply_sidecar: edge insert failed: %s", e)
        return False
    return True


_SIDECAR_USER_EDGES_DDL = """
CREATE TABLE IF NOT EXISTS sidecar_user_edges (
    edge_id              TEXT PRIMARY KEY,
    from_block_id        TEXT,
    to_content_hash      TEXT,
    to_document_id       TEXT,
    kind                 TEXT,
    asserted_at          TIMESTAMP,
    operator_note        TEXT,
    imported_by_user_id  TEXT NOT NULL,
    imported_unsigned    BOOLEAN NOT NULL DEFAULT FALSE,
    payload              TEXT NOT NULL,
    imported_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _default_audio_storage_root() -> str:
    """Where extracted voice-note audio bytes land. Operator-overridable
    via ANTIEK_VOICE_AUDIO_ROOT; defaults to ``~/.antiek/voice_audio``.
    """
    explicit = os.environ.get("ANTIEK_VOICE_AUDIO_ROOT")
    if explicit:
        return os.path.expanduser(explicit)
    return os.path.expanduser("~/.antiek/voice_audio")


# ── Helpers ──


def _parse_jsonl(data: bytes, *, where: str) -> list[dict]:
    if not data:
        return []
    out: list[dict] = []
    for i, line in enumerate(data.decode("utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise MalformedAntiek(
                f"{where} line {i + 1}: {e}"
            ) from e
        if not isinstance(obj, dict):
            raise MalformedAntiek(
                f"{where} line {i + 1}: expected JSON object, got {type(obj).__name__}"
            )
        out.append(obj)
    return out


def _canonical_jsonl_bytes_from_parsed(
    rows: list[dict], *, key: str,
) -> bytes:
    """Re-serialise parsed jsonl rows in canonical form. Used by the
    verifier so a tampered file that survives JSON parsing fails the
    canonical-bytes check."""
    if not rows:
        return b""
    sorted_rows = sorted(rows, key=lambda r: r[key])
    lines = [
        json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for r in sorted_rows
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


__all__ = [
    "ApplyReport",
    "HASH_MISMATCH_WARNING",
    "MissingSidecarFields",
    "NotASidecar",
    "RestoredSidecar",
    "SidecarHashMismatch",
    "apply_sidecar",
    "read_sidecar",
]
