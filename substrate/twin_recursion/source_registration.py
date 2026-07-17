"""Canonical graph-document declarations for recursive twin obligations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

from runtime.db_lock import LockedConnection
from substrate.books.serve_guard import serve_full_text_guarded
from substrate.twin_note_taker import MAX_CONTENT_CHARS, MIN_CONTENT_CHARS, AssetContent

from .ledger import SourceRevision, TwinRecursionLedger
from .segmentation import build_segmentation_manifest
from .segmentation_ledger import TwinSegmentationLedger

ENVELOPE_SCHEMA = "antiek.twin-source-envelope.v1"
EnvelopeStatus = Literal[
    "eligible",
    "metadata_only",
    "requires_binding",
    "requires_enrichment",
    "requires_segmentation",
]
CoverageVerdict = Literal["unknown", "partial", "universal"]


class TwinSourceEnvelopeError(RuntimeError):
    """A graph document cannot be reconciled with its twin declaration."""


@dataclass(frozen=True)
class TwinSourceEnvelope:
    schema: str
    status: EnvelopeStatus
    account_id: str
    document_id: str
    title: str
    document_type: str
    body_sha256: str | None
    source_event_id: str
    source_hash: str | None
    reason: str | None

    def to_json(self) -> str:
        return _canonical_json(asdict(self))

    @classmethod
    def from_json(cls, value: str) -> TwinSourceEnvelope:
        try:
            raw = json.loads(value)
            envelope = cls(**raw)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise TwinSourceEnvelopeError("twin source envelope is malformed") from exc
        if envelope.to_json() != value:
            raise TwinSourceEnvelopeError("twin source envelope is not canonical")
        if envelope.schema != ENVELOPE_SCHEMA or envelope.status not in {
            "eligible",
            "metadata_only",
            "requires_binding",
            "requires_enrichment",
            "requires_segmentation",
        }:
            raise TwinSourceEnvelopeError("twin source envelope has unsupported semantics")
        if (envelope.status == "eligible") != (envelope.source_hash is not None):
            raise TwinSourceEnvelopeError("twin source envelope eligibility is inconsistent")
        return envelope


@dataclass(frozen=True)
class TwinSourceCoverage:
    account_id: str
    documents: int
    eligible: int
    metadata_only: int
    requires_binding: int
    requires_enrichment: int
    requires_segmentation: int
    registered: int
    segmentation_registered: int
    verdict: CoverageVerdict


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_twin_source_envelope(
    *,
    document_id: str,
    title: str | None,
    raw_text: str | None,
    document_type: str,
    owner_user_id: str,
) -> TwinSourceEnvelope:
    """Derive the complete declaration from fields in one canonical document row."""
    exact_title = title or document_id
    body_sha = None if raw_text is None else _sha(raw_text)
    stripped_length = 0 if raw_text is None else len(raw_text.strip())
    event_material = _canonical_json(
        [ENVELOPE_SCHEMA, owner_user_id, document_id, exact_title, document_type, body_sha]
    )
    source_event_id = "evt-twin-source-" + _sha(event_material)[:40]
    if raw_text is None or stripped_length == 0:
        return TwinSourceEnvelope(
            ENVELOPE_SCHEMA,
            "metadata_only",
            owner_user_id,
            document_id,
            exact_title,
            document_type,
            body_sha,
            source_event_id,
            None,
            "no_substantive_body",
        )
    if document_type == "multimedia_twin":
        return TwinSourceEnvelope(
            ENVELOPE_SCHEMA,
            "requires_binding",
            owner_user_id,
            document_id,
            exact_title,
            document_type,
            body_sha,
            source_event_id,
            None,
            "legacy_twin_requires_canonical_binding",
        )
    if stripped_length < MIN_CONTENT_CHARS:
        return TwinSourceEnvelope(
            ENVELOPE_SCHEMA,
            "requires_enrichment",
            owner_user_id,
            document_id,
            exact_title,
            document_type,
            body_sha,
            source_event_id,
            None,
            "body_below_materializer_floor",
        )
    if len(raw_text) > MAX_CONTENT_CHARS:
        return TwinSourceEnvelope(
            ENVELOPE_SCHEMA,
            "requires_segmentation",
            owner_user_id,
            document_id,
            exact_title,
            document_type,
            body_sha,
            source_event_id,
            None,
            "body_exceeds_materializer_limit",
        )
    asset = _asset(document_id, exact_title, raw_text, document_type, source_event_id)
    revision = SourceRevision(owner_user_id, asset)
    return TwinSourceEnvelope(
        ENVELOPE_SCHEMA,
        "eligible",
        owner_user_id,
        document_id,
        exact_title,
        document_type,
        body_sha,
        source_event_id,
        revision.source_hash,
        None,
    )


def _asset(
    document_id: str, title: str, raw_text: str, document_type: str, source_event_id: str
) -> AssetContent:
    return AssetContent(
        asset_id=document_id,
        title=title,
        content_text=raw_text,
        content_class=document_type,
        source_event_ids=(source_event_id,),
    )


def _row_envelope(
    con: LockedConnection, row: tuple[Any, ...]
) -> tuple[TwinSourceEnvelope, str | None]:
    served = serve_full_text_guarded(con, str(row[0]), owner=True)
    envelope = build_twin_source_envelope(
        document_id=str(row[0]),
        title=None if row[1] is None else str(row[1]),
        raw_text=served.full_text,
        document_type=str(row[2]),
        owner_user_id=str(row[3]),
    )
    return envelope, served.full_text


def stamp_existing_document(
    con: LockedConnection, document_id: str, *, refresh: bool = False
) -> None:
    """Fill one legacy NULL declaration; reject drift unless refresh is explicit."""
    _require_locked(con)
    row = con.execute(
        "SELECT document_id,title,document_type,owner_user_id,twin_source_envelope "
        "FROM documents WHERE document_id=?",
        [document_id],
    ).fetchone()
    if row is None:
        raise KeyError(document_id)
    expected = _row_envelope(con, tuple(row[:4]))[0].to_json()
    if row[4] is not None and row[4] != expected and not refresh:
        raise TwinSourceEnvelopeError(
            f"document {document_id!r} twin declaration conflicts with stored bytes"
        )
    if row[4] != expected:
        con.execute(
            "UPDATE documents SET twin_source_envelope=? "
            "WHERE document_id=?",
            [expected, document_id],
        )


def backfill_twin_source_envelopes(con: LockedConnection) -> int:
    """Backfill all legacy rows under one caller-held graph write lock."""
    _require_locked(con)
    rows = con.execute(
        "SELECT document_id,title,document_type,owner_user_id "
        "FROM documents WHERE twin_source_envelope IS NULL ORDER BY document_id"
    ).fetchall()
    con.execute("BEGIN")
    try:
        for row in rows:
            con.execute(
                "UPDATE documents SET twin_source_envelope=? "
                "WHERE document_id=? AND twin_source_envelope IS NULL",
                [_row_envelope(con, tuple(row))[0].to_json(), str(row[0])],
            )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return len(rows)


def verify_twin_source_envelopes(
    con: LockedConnection, *, account_id: str | None = None
) -> tuple[TwinSourceEnvelope, ...]:
    """Prove every document has one exact declaration derived from current row bytes."""
    return tuple(envelope for envelope, _asset_value in _verified_rows(con, account_id))


def _verified_rows(
    con: LockedConnection, account_id: str | None
) -> list[tuple[TwinSourceEnvelope, AssetContent | None]]:
    _require_locked(con)
    query = (
        "SELECT document_id,title,document_type,owner_user_id,twin_source_envelope "
        "FROM documents"
    )
    params: list[str] = []
    if account_id is not None:
        query += " WHERE owner_user_id=?"
        params.append(account_id)
    rows = con.execute(query + " ORDER BY owner_user_id,document_id", params).fetchall()
    envelopes: list[tuple[TwinSourceEnvelope, AssetContent | None]] = []
    for row in rows:
        if row[4] is None:
            raise TwinSourceEnvelopeError(f"document {row[0]!r} lacks a twin declaration")
        persisted = TwinSourceEnvelope.from_json(str(row[4]))
        expected, guarded_body = _row_envelope(con, tuple(row[:4]))
        if persisted != expected:
            raise TwinSourceEnvelopeError(
                f"document {row[0]!r} conflicts with its twin declaration"
            )
        asset = None
        if persisted.status in {"eligible", "requires_segmentation"}:
            if guarded_body is None:
                raise TwinSourceEnvelopeError(
                    f"document {row[0]!r} lost owner-readable body authority"
                )
            asset = _asset(
                persisted.document_id, persisted.title, guarded_body,
                persisted.document_type, persisted.source_event_id,
            )
        envelopes.append((persisted, asset))
    return envelopes


def project_twin_sources(
    con: LockedConnection,
    ledger: TwinRecursionLedger,
    segmentation_ledger: TwinSegmentationLedger,
    *,
    account_id: str,
) -> TwinSourceCoverage:
    """Idempotently project one account's verified eligible documents."""
    selected_rows = _verified_rows(con, account_id)
    selected = [envelope for envelope, _asset_value in selected_rows]
    snapshots = []
    segmentation_snapshots = []
    for envelope, asset in selected_rows:
        if envelope.status == "eligible":
            assert asset is not None
            snapshots.append(ledger.register_source(SourceRevision(account_id, asset)))
        elif envelope.status == "requires_segmentation":
            assert asset is not None
            manifest = build_segmentation_manifest(account_id=account_id, asset=asset)
            segmentation_snapshots.append(
                segmentation_ledger.register(manifest, account_id=account_id, asset=asset)
            )
    eligible = sum(envelope.status == "eligible" for envelope in selected)
    metadata_only = sum(envelope.status == "metadata_only" for envelope in selected)
    binding = sum(envelope.status == "requires_binding" for envelope in selected)
    enrichment = sum(envelope.status == "requires_enrichment" for envelope in selected)
    segmentation = sum(envelope.status == "requires_segmentation" for envelope in selected)
    if eligible == 0 and not (binding or enrichment or segmentation):
        verdict: CoverageVerdict = "unknown"
    elif binding or enrichment or segmentation:
        verdict = "partial"
    else:
        verdict = (
            "universal" if all(snapshot.state == "ready" for snapshot in snapshots) else "partial"
        )
    return TwinSourceCoverage(
        account_id,
        len(selected),
        eligible,
        metadata_only,
        binding,
        enrichment,
        segmentation,
        len(snapshots),
        len(segmentation_snapshots),
        verdict,
    )


def _require_locked(con: LockedConnection) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError("twin source registration requires a LockedConnection")


__all__ = [
    "ENVELOPE_SCHEMA",
    "TwinSourceCoverage",
    "TwinSourceEnvelope",
    "TwinSourceEnvelopeError",
    "backfill_twin_source_envelopes",
    "build_twin_source_envelope",
    "project_twin_sources",
    "stamp_existing_document",
    "verify_twin_source_envelopes",
]
